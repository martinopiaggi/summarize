"""yt-dlp downloader for YouTube and supported social platforms."""

import os
import tempfile
import time
import uuid
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from ..exceptions import AudioProcessingError, TranscriptError
from ..handlers import process_audio_file
from ..progress import ProgressSpinner, print_status
from ..proxy import get_proxy_url, should_proxy_url
from .base import BaseDownloader
from .youtube import is_youtube_url


YTDLP_PRIMARY_HOSTS = (
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "twitter.com", "x.com", "www.x.com",
    "reddit.com", "www.reddit.com", "old.reddit.com", "v.redd.it",
    "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch",
)

_HOST_CREDENTIAL_ENV = {
    "instagram.com": ("INSTAGRAM_USER", "INSTAGRAM_PASS"),
}

_HOST_COOKIE_ENV = {
    "instagram.com": "INSTAGRAM_COOKIES_FILE",
    "tiktok.com": "TIKTOK_COOKIES_FILE",
    "twitter.com": "TWITTER_COOKIES_FILE",
    "x.com": "TWITTER_COOKIES_FILE",
    "reddit.com": "REDDIT_COOKIES_FILE",
    "facebook.com": "FACEBOOK_COOKIES_FILE",
    "fb.watch": "FACEBOOK_COOKIES_FILE",
    "youtube.com": "YOUTUBE_COOKIES_FILE",
    "youtu.be": "YOUTUBE_COOKIES_FILE",
}


def _host_matches(host: str, needle: str) -> bool:
    return host == needle or host.endswith("." + needle)


def _env_value(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value and value.strip():
        return value.strip()
    return None


def _cookiefile_for_url(url: str) -> Optional[str]:
    host = (urlparse(url or "").hostname or "").lower()
    for needle, env_name in _HOST_COOKIE_ENV.items():
        if _host_matches(host, needle):
            cookiefile = _env_value(env_name)
            if cookiefile:
                return cookiefile
            break
    return _env_value("YTDLP_COOKIES_FILE")


def _credentials_for_url(url: str) -> Dict[str, str]:
    host = (urlparse(url or "").hostname or "").lower()
    for needle, (user_var, pass_var) in _HOST_CREDENTIAL_ENV.items():
        if _host_matches(host, needle):
            user = _env_value(user_var)
            password = _env_value(pass_var)
            if user and password:
                return {"username": user, "password": password}
            if user or password:
                raise AudioProcessingError(
                    f"{user_var} and {pass_var} must both be set for yt-dlp login"
                )
            break
    return {}


def _auth_options_for_url(url: str) -> Dict[str, str]:
    cookiefile = _cookiefile_for_url(url)
    if cookiefile:
        if not os.path.exists(cookiefile):
            raise AudioProcessingError(f"yt-dlp cookie file not found: {cookiefile}")
        return {"cookiefile": cookiefile}
    return _credentials_for_url(url)


def _load_ytdlp():
    try:
        import yt_dlp
    except ImportError:
        raise AudioProcessingError("yt-dlp package not installed")
    return yt_dlp


def _find_produced_files(temp_root: str, temp_name: str):
    try:
        return [
            os.path.join(temp_root, name)
            for name in os.listdir(temp_root)
            if name.startswith(temp_name)
        ]
    except OSError:
        return []


def _cleanup(paths):
    for path in list(dict.fromkeys(paths)):
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


class _YtdlpLogger:
    """Route yt-dlp errors into print_status so Streamlit sees them."""

    def __init__(self, verbose: bool):
        self.verbose = verbose

    def debug(self, msg):
        return None

    def info(self, msg):
        return None

    def warning(self, msg):
        text = str(msg)
        if "ERROR:" in text or "403" in text or "Forbidden" in text:
            print_status(f"yt-dlp: {text[-160:]}", "WARNING", self.verbose)

    def error(self, msg):
        text = str(msg)
        if text.startswith("ERROR: "):
            text = text[7:]
        print_status(f"yt-dlp: {text[:160]}", "WARNING", self.verbose)


def _progress_hook(verbose: bool):
    last_emit = [0.0]

    def hook(d: Dict[str, Any]) -> None:
        status = d.get("status")
        now = time.time()
        if status == "downloading":
            if now - last_emit[0] < 2:
                return
            last_emit[0] = now
            parts = ["yt-dlp downloading"]
            percent = (d.get("_percent_str") or "").strip()
            speed = (d.get("_speed_str") or "").strip()
            eta = (d.get("_eta_str") or "").strip()
            if percent:
                parts.append(percent)
            if speed:
                parts.append(speed)
            if eta and eta.lower() != "unknown":
                parts.append(f"ETA {eta}")
            print_status(" ".join(parts), "PROCESSING", verbose)
        elif status == "finished":
            print_status("yt-dlp download finished", "INFO", verbose)

    return hook


def _base_ydl_opts(verbose: bool) -> Dict[str, Any]:
    opts: Dict[str, Any] = {
        "quiet": not verbose,
        "no_warnings": not verbose,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 1,
        "check_formats": "selected",
        "js_runtimes": {"deno": {}, "node": {}},
        "remote_components": {"ejs:github"},
        "progress_hooks": [_progress_hook(verbose)],
    }
    if not verbose:
        opts["logger"] = _YtdlpLogger(verbose)
    return opts


def _apply_common_options(ydl_opts: Dict, url: str, use_proxy: bool, verbose: bool):
    auth_options = _auth_options_for_url(url)
    if auth_options:
        ydl_opts.update(auth_options)
        auth_type = "cookie file" if "cookiefile" in auth_options else "username/password"
        print_status(f"Using yt-dlp {auth_type} authentication", "INFO", verbose)

    if is_youtube_url(url):
        print_status("Using yt-dlp for YouTube", "INFO", verbose)

    proxy_url = get_proxy_url(use_proxy, url) if should_proxy_url(url, use_proxy) else None
    if proxy_url:
        ydl_opts["proxy"] = proxy_url
        print_status("Using HTTP proxy for yt-dlp", "INFO", verbose)


class YtdlpDownloader(BaseDownloader):
    """Downloader that uses yt-dlp locally before Cobalt fallback."""

    def supports(self, url: str) -> bool:
        if not url:
            return False
        if is_youtube_url(url):
            return True
        host = (urlparse(url).hostname or "").lower()
        return any(_host_matches(host, h) for h in YTDLP_PRIMARY_HOSTS)

    def download_audio(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        audio_speed: float = 1.0,
        use_proxy: bool = False,
    ) -> str:
        yt_dlp = _load_ytdlp()
        temp_root = temp_dir or tempfile.gettempdir()
        temp_name = f"ytdlp_audio_{uuid.uuid4().hex}"
        temp_template = os.path.join(temp_root, f"{temp_name}.%(ext)s")
        processed_path = os.path.join(temp_root, f"{temp_name}_processed.mp3")

        ydl_opts = _base_ydl_opts(verbose)
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["outtmpl"] = temp_template
        _apply_common_options(ydl_opts, url, use_proxy, verbose)

        spinner = ProgressSpinner("Downloading audio with yt-dlp", verbose)
        produced_files = []
        try:
            print_status("Downloading audio with yt-dlp", "PROCESSING", verbose)
            spinner.start()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            spinner.stop()

            produced_files = _find_produced_files(temp_root, temp_name)
            if not produced_files:
                raise TranscriptError("yt-dlp finished but produced no output file")

            raw_path = next(
                (path for path in produced_files if path.endswith(".mp3")),
                produced_files[0],
            )

            spinner = ProgressSpinner("Processing audio file", verbose)
            spinner.start()
            process_audio_file(raw_path, processed_path, playback_speed=audio_speed)
            spinner.stop()
            print_status("yt-dlp audio ready", "SUCCESS", verbose)

            _cleanup(path for path in produced_files if path != processed_path)
            return processed_path
        except Exception as e:
            spinner.stop()
            _cleanup(
                produced_files
                + _find_produced_files(temp_root, temp_name)
                + [processed_path]
            )
            raise AudioProcessingError(f"yt-dlp download failed: {str(e)}")

    def _download_raw_video(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        use_proxy: bool = False,
    ) -> Tuple[str, Dict[str, Any]]:
        """Download video+audio. Returns (video_path, info_dict)."""
        yt_dlp = _load_ytdlp()
        temp_root = temp_dir or tempfile.gettempdir()
        temp_name = f"ytdlp_video_{uuid.uuid4().hex}"
        temp_template = os.path.join(temp_root, f"{temp_name}.%(ext)s")

        ydl_opts = _base_ydl_opts(verbose)
        ydl_opts["format"] = "bestvideo*+bestaudio/best"
        ydl_opts["outtmpl"] = temp_template
        _apply_common_options(ydl_opts, url, use_proxy, verbose)

        spinner = ProgressSpinner("Downloading video with yt-dlp", verbose)
        produced_files = []
        try:
            print_status("Downloading video with yt-dlp", "PROCESSING", verbose)
            spinner.start()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}
            spinner.stop()

            produced_files = _find_produced_files(temp_root, temp_name)
            if not produced_files:
                raise TranscriptError("yt-dlp finished but produced no file")

            video_path = max(produced_files, key=lambda p: os.path.getsize(p))
            print_status("yt-dlp video ready", "SUCCESS", verbose)
            return video_path, info
        except Exception as e:
            spinner.stop()
            _cleanup(produced_files + _find_produced_files(temp_root, temp_name))
            raise AudioProcessingError(f"yt-dlp video download failed: {str(e)}")
        finally:
            # Cleanup produced files except the largest (video)
            if produced_files:
                video_path = max(produced_files, key=lambda p: os.path.getsize(p))
                _cleanup(path for path in produced_files if path != video_path)

    def download_video(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        use_proxy: bool = False,
    ) -> str:
        video_path, _ = self._download_raw_video(url, temp_dir, verbose, use_proxy)
        return video_path

    def download_with_metadata(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        audio_speed: float = 1.0,
        use_proxy: bool = False,
    ) -> Dict[str, Optional[str]]:
        video_path, info = self._download_raw_video(url, temp_dir, verbose, use_proxy)
        temp_root = temp_dir or tempfile.gettempdir()
        temp_name = os.path.splitext(os.path.basename(video_path))[0]
        processed_audio = os.path.join(temp_root, f"{temp_name}_processed.mp3")

        spinner = ProgressSpinner("Extracting audio track", verbose)
        try:
            spinner.start()
            process_audio_file(video_path, processed_audio, playback_speed=audio_speed)
            spinner.stop()
            print_status("yt-dlp audio + video ready", "SUCCESS", verbose)

            return {
                "audio_path": processed_audio,
                "video_path": video_path,
                "caption": (info.get("description") or "").strip() or None,
                "title": (info.get("title") or "").strip() or None,
                "duration": info.get("duration"),
            }
        except Exception as e:
            spinner.stop()
            if os.path.exists(processed_audio):
                os.remove(processed_audio)
            raise AudioProcessingError(
                f"yt-dlp audio extraction failed: {str(e)}"
            )
