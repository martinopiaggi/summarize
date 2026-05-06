"""yt-dlp downloader for non-YouTube platforms (IG, TikTok, X, Reddit, etc.)."""

import os
import tempfile
import uuid
from typing import Dict, Optional
from urllib.parse import urlparse

import yt_dlp

from ..exceptions import AudioProcessingError, TranscriptError
from ..handlers import process_audio_file
from ..progress import ProgressSpinner, print_status
from .base import BaseDownloader
from .youtube import is_youtube_url


# Hosts where yt-dlp's local extractors handle content that Cobalt cannot
# reach without cookies (IG, TikTok, X, Reddit, FB). YouTube is excluded so
# the lighter pytubefix path keeps owning it.
YTDLP_PRIMARY_HOSTS = (
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com",
    "twitter.com", "x.com", "www.x.com",
    "reddit.com", "www.reddit.com", "old.reddit.com",
    "facebook.com", "www.facebook.com", "fb.watch",
)

# Per-host credential lookup. Each tuple maps a hostname substring to the
# pair of env vars that hold its login. The matching is "host contains
# substring" so 'instagram.com' covers 'www.instagram.com' too. Set by the
# user via .env or an injected provider config; missing creds simply fall
# through to anonymous fetching (which is what we did before this change).
_HOST_CREDENTIAL_ENV = {
    "instagram.com": ("INSTAGRAM_USER", "INSTAGRAM_PASS"),
    # Add more hosts here as needed; tested only for Instagram so far.
    # "tiktok.com": ("TIKTOK_USER", "TIKTOK_PASS"),
}


def _credentials_for_url(url: str) -> Dict[str, str]:
    """Return yt-dlp ydl_opts with username/password for the URL host, if any.

    Looks up _HOST_CREDENTIAL_ENV by host substring and reads the named
    env vars. Returns an empty dict when either var is missing so the
    caller can `dict.update()` unconditionally.
    """
    host = (urlparse(url or "").hostname or "").lower()
    for needle, (user_var, pass_var) in _HOST_CREDENTIAL_ENV.items():
        if needle in host:
            user = os.getenv(user_var)
            pwd = os.getenv(pass_var)
            if user and pwd:
                return {"username": user, "password": pwd}
            break
    return {}


class YtdlpDownloader(BaseDownloader):
    """Downloader that uses yt-dlp locally for platforms Cobalt cannot reach."""

    def supports(self, url: str) -> bool:
        if not url or is_youtube_url(url):
            return False
        host = (urlparse(url).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in YTDLP_PRIMARY_HOSTS)

    def download_audio(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        audio_speed: float = 1.0,
        use_proxy: bool = False,
    ) -> str:
        temp_root = temp_dir or tempfile.gettempdir()
        temp_name = f"ytdlp_audio_{uuid.uuid4().hex}"
        temp_template = os.path.join(temp_root, f"{temp_name}.%(ext)s")
        processed_path = os.path.join(temp_root, f"{temp_name}_processed.mp3")

        # Download raw audio; do not run FFmpegExtractAudio here — process_audio_file()
        # converts to the target format and writing both into temp_name.mp3 would
        # collide (ffmpeg cannot read and write the same file).
        spinner = ProgressSpinner("Downloading audio with yt-dlp", verbose)
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_template,
            "quiet": not verbose,
            "no_warnings": not verbose,
            "noplaylist": True,
        }
        ydl_opts.update(_credentials_for_url(url))
        produced_files = []
        try:
            spinner.start()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            spinner.stop()

            produced_files = [
                os.path.join(temp_root, f) for f in os.listdir(temp_root)
                if f.startswith(temp_name)
            ]
            if not produced_files:
                raise TranscriptError("yt-dlp finished but produced no output file")

            raw_path = next(
                (p for p in produced_files if p.endswith(".mp3")),
                produced_files[0],
            )

            spinner = ProgressSpinner("Processing audio file", verbose)
            spinner.start()
            process_audio_file(raw_path, processed_path, playback_speed=audio_speed)
            spinner.stop()
            print_status("yt-dlp audio ready", "SUCCESS", verbose)

            for p in produced_files:
                if p != processed_path and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            return processed_path
        except Exception as e:
            spinner.stop()
            for p in produced_files + [processed_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            raise AudioProcessingError(f"yt-dlp download failed: {str(e)}")

    def download_with_metadata(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        audio_speed: float = 1.0,
    ) -> Dict[str, Optional[str]]:
        """Download both audio and the original video file plus metadata.

        Returns a dict with:
          - audio_path: processed mp3 ready for Whisper (always present)
          - video_path: original video file kept on disk for frame extraction
            (None if yt-dlp returned audio-only formats)
          - caption: post description / caption text from the platform
            (None if not provided by the extractor)
          - title: media title (None if absent)
          - duration: float seconds (None if absent)

        Caller is responsible for deleting `video_path` once done with it.
        """
        temp_root = temp_dir or tempfile.gettempdir()
        temp_name = f"ytdlp_full_{uuid.uuid4().hex}"
        temp_template = os.path.join(temp_root, f"{temp_name}.%(ext)s")
        processed_audio = os.path.join(temp_root, f"{temp_name}_processed.mp3")

        # Ask for best video+audio so we get a real video file to extract
        # frames from. yt-dlp will mux into a single container when possible.
        ydl_opts = {
            "format": "bestvideo*+bestaudio/best",
            "outtmpl": temp_template,
            "quiet": not verbose,
            "no_warnings": not verbose,
            "noplaylist": True,
        }
        ydl_opts.update(_credentials_for_url(url))
        produced_files = []
        spinner = ProgressSpinner("Downloading video with yt-dlp", verbose)
        try:
            spinner.start()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}
            spinner.stop()

            produced_files = [
                os.path.join(temp_root, f) for f in os.listdir(temp_root)
                if f.startswith(temp_name)
            ]
            if not produced_files:
                raise TranscriptError("yt-dlp finished but produced no file")

            # Pick the largest file as the main video (mp4/mkv/webm). It also
            # contains the audio track that we'll feed to ffmpeg for the mp3.
            video_path = max(produced_files, key=lambda p: os.path.getsize(p))

            spinner = ProgressSpinner("Extracting audio track", verbose)
            spinner.start()
            process_audio_file(
                video_path, processed_audio, playback_speed=audio_speed,
            )
            spinner.stop()
            print_status("yt-dlp audio + video ready", "SUCCESS", verbose)

            # Clean up the smaller artefacts, keep video_path and processed_audio.
            for p in produced_files:
                if p != video_path and os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

            return {
                "audio_path": processed_audio,
                "video_path": video_path,
                "caption": (info.get("description") or "").strip() or None,
                "title": (info.get("title") or "").strip() or None,
                "duration": info.get("duration"),
            }
        except Exception as e:
            spinner.stop()
            for p in produced_files + [processed_audio]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            raise AudioProcessingError(
                f"yt-dlp download_with_metadata failed: {str(e)}"
            )
