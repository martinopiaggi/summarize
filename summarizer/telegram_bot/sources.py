"""Turn incoming Telegram messages into summarizer sources."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..downloaders import is_youtube_url
from ..handlers import is_dropbox_url, is_google_drive_url

# Same text types as the Streamlit FILE tab and the /summarize/upload endpoint.
TEXT_EXTENSIONS = frozenset(
    {".txt", ".md", ".vtt", ".srt", ".csv", ".log", ".rst", ".html", ".xml", ".json"}
)
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".3gp", ".mpeg", ".mpg", ".ts", ".flv", ".wmv"}
)
AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus", ".flac", ".aac", ".wma", ".amr", ".mka"}
)
CONFIG_EXTENSIONS = frozenset({".yaml", ".yml"})

MAX_URLS_PER_MESSAGE = 5
# Text without a link is summarized automatically only when it is this long;
# shorter text needs an explicit /summarize.
AUTO_TEXT_MIN_CHARS = 800

_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}>»\"'"


class UnsupportedMessage(Exception):
    """The message cannot be summarized; ``str(exc)`` is shown to the user."""


@dataclass(frozen=True)
class Source:
    """Something to summarize: a link, a Telegram file, or pasted text."""

    kind: str  # "url", "file" or "text"
    label: str  # shown in status messages and saved summaries
    url: str = ""
    file_id: str = ""
    file_unique_id: str = ""
    file_size: int = 0
    extension: str = ""
    media: str = ""  # video, video_note, audio, voice, animation, document
    text: str = ""

    @property
    def is_text(self) -> bool:
        return self.kind == "text" or (self.kind == "file" and self.extension in TEXT_EXTENSIONS)

    @property
    def has_video(self) -> bool:
        """Whether visual mode can use this source."""
        if self.kind == "url":
            return True
        if self.kind != "file":
            return False
        return self.media in ("video", "video_note", "animation") or self.extension in VIDEO_EXTENSIONS

    @property
    def type_of_source(self) -> str:
        if self.kind == "url":
            return url_source_type(self.url)
        return "TXT" if self.is_text else "Local File"

    def local_name(self) -> str:
        """Stable file name: re-sending the same file reuses its cached transcript."""
        if self.kind == "text":
            digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:20]
            return f"text_{digest}.txt"
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", self.file_unique_id)
        if not safe_id:
            safe_id = hashlib.sha256(self.file_id.encode("utf-8")).hexdigest()[:20]
        return f"tg_{safe_id}{self.extension or '.bin'}"


def url_source_type(url: str) -> str:
    """Pick the pipeline source type for a URL (mirrors the Streamlit URL tab)."""
    if is_youtube_url(url):
        return "YouTube Video"
    if is_google_drive_url(url):
        return "Google Drive Video Link"
    if is_dropbox_url(url):
        return "Dropbox Video Link"
    return "Video URL"


def short_url(url: str, limit: int = 60) -> str:
    parsed = urlparse(url)
    text = (parsed.netloc.removeprefix("www.") + parsed.path).rstrip("/")
    if parsed.query:
        text += "?" + parsed.query
    return text if len(text) <= limit else text[: limit - 1] + "…"


def utf16_slice(text: str, offset: int, length: int) -> str:
    """Slice ``text`` with Telegram entity offsets (UTF-16 code units)."""
    encoded = text.encode("utf-16-le")
    return encoded[offset * 2 : (offset + length) * 2].decode("utf-16-le", errors="ignore")


def extract_urls(text: str, entities: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """Links in a message: URL entities, hidden text links, then a regex fallback."""
    found: List[str] = []
    for entity in entities or []:
        if entity.get("type") == "text_link":
            found.append(entity.get("url") or "")
        elif entity.get("type") == "url":
            found.append(utf16_slice(text, entity.get("offset", 0), entity.get("length", 0)))
    if not found:
        found.extend(match.group(0).rstrip(_TRAILING_PUNCTUATION) for match in _URL_RE.finditer(text or ""))

    urls: List[str] = []
    for url in found:
        url = url.strip()
        if not url:
            continue
        if "://" not in url:
            url = "https://" + url  # Telegram detects "youtu.be/x" without a scheme
        if urlparse(url).scheme in ("http", "https") and url not in urls:
            urls.append(url)
    return urls


def url_source(url: str) -> Source:
    return Source(kind="url", label=url, url=url)


def text_source(text: str) -> Source:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "text")
    label = first_line if len(first_line) <= 40 else first_line[:39] + "…"
    return Source(kind="text", label=f"“{label}”", text=text)


def _duration(seconds: Any) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _extension(file_name: str, mime_type: str, default: str) -> str:
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext:
        return ext
    guessed = mimetypes.guess_extension((mime_type or "").split(";")[0].strip()) if mime_type else None
    return (guessed or default).lower()


def is_config_document(message: Dict[str, Any]) -> bool:
    document = message.get("document") or {}
    return os.path.splitext(document.get("file_name") or "")[1].lower() in CONFIG_EXTENSIONS


def media_source(message: Dict[str, Any]) -> Optional[Source]:
    """Source for a video, audio, voice note or document attached to a message."""
    for media, default_ext in (
        ("video", ".mp4"),
        ("video_note", ".mp4"),
        ("voice", ".ogg"),
        ("audio", ".mp3"),
        ("animation", ".mp4"),
        ("document", ""),
    ):
        item = message.get(media)
        if not item:
            continue
        name = item.get("file_name") or ""
        mime = item.get("mime_type") or ""
        ext = _extension(name, mime, default_ext)
        if media == "document":
            kind_hint = mime.split("/")[0]
            if not (
                ext in TEXT_EXTENSIONS
                or ext in VIDEO_EXTENSIONS
                or ext in AUDIO_EXTENSIONS
                or kind_hint in ("video", "audio")
            ):
                raise UnsupportedMessage(
                    f"I can't summarize {name or 'this file'}. Send a video, an audio file, "
                    "a voice message, a text file (.txt, .srt, .vtt, .md…) or a link."
                )
        return Source(
            kind="file",
            label=name or _media_label(media, item),
            file_id=item.get("file_id", ""),
            file_unique_id=item.get("file_unique_id", ""),
            file_size=int(item.get("file_size") or 0),
            extension=ext,
            media=media,
        )
    return None


def _media_label(media: str, item: Dict[str, Any]) -> str:
    duration = _duration(item.get("duration"))
    suffix = f" ({duration})" if duration else ""
    if media == "audio":
        title = " – ".join(part for part in (item.get("performer"), item.get("title")) if part)
        if title:
            return title
    names = {"video_note": "video message", "voice": "voice message", "animation": "animation"}
    return names.get(media, media) + suffix


def sources_from_message(message: Dict[str, Any], explicit: bool = False) -> List[Source]:
    """Everything worth summarizing in a message.

    Attached media wins over links in its caption; links win over text.
    ``explicit`` (an explicit /summarize) also accepts short text.
    """
    media = media_source(message)
    if media:
        return [media]

    text = message.get("text") or message.get("caption") or ""
    entities = message.get("entities") or message.get("caption_entities")
    urls = extract_urls(text, entities)
    if urls:
        return [url_source(url) for url in urls[:MAX_URLS_PER_MESSAGE]]

    stripped = text.strip()
    if stripped and (explicit or len(stripped) >= AUTO_TEXT_MIN_CHARS):
        return [text_source(stripped)]
    if message.get("photo") or message.get("sticker"):
        raise UnsupportedMessage("I can't summarize photos or stickers. Send a video, audio or link.")
    return []
