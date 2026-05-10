"""yt-dlp downloader for non-YouTube platforms."""

import os
import tempfile
import uuid
from typing import Optional
from urllib.parse import urlparse

from ..exceptions import AudioProcessingError, TranscriptError
from ..handlers import process_audio_file
from ..progress import ProgressSpinner, print_status
from ..proxy import get_webshare_proxy_url
from .base import BaseDownloader
from .youtube import is_youtube_url


YTDLP_PRIMARY_HOSTS = (
    "instagram.com", "www.instagram.com",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "twitter.com", "x.com", "www.x.com",
    "reddit.com", "www.reddit.com", "old.reddit.com", "v.redd.it",
    "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch",
)


class YtdlpDownloader(BaseDownloader):
    """Downloader that uses yt-dlp locally before Cobalt fallback."""

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
        try:
            import yt_dlp
        except ImportError:
            raise AudioProcessingError("yt-dlp package not installed")

        temp_root = temp_dir or tempfile.gettempdir()
        temp_name = f"ytdlp_audio_{uuid.uuid4().hex}"
        temp_template = os.path.join(temp_root, f"{temp_name}.%(ext)s")
        processed_path = os.path.join(temp_root, f"{temp_name}_processed.mp3")

        def find_produced_files():
            try:
                return [
                    os.path.join(temp_root, name)
                    for name in os.listdir(temp_root)
                    if name.startswith(temp_name)
                ]
            except OSError:
                return []

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_template,
            "quiet": not verbose,
            "no_warnings": not verbose,
            "noplaylist": True,
        }

        proxy_url = get_webshare_proxy_url(use_proxy)
        if proxy_url:
            ydl_opts["proxy"] = proxy_url
            print_status("Using Webshare proxy for yt-dlp", "INFO", verbose)

        spinner = ProgressSpinner("Downloading audio with yt-dlp", verbose)
        produced_files = []
        try:
            spinner.start()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
            spinner.stop()

            produced_files = find_produced_files()
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

            for path in produced_files:
                if path != processed_path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            return processed_path
        except Exception as e:
            spinner.stop()
            cleanup_paths = list(dict.fromkeys(
                produced_files + find_produced_files() + [processed_path]
            ))
            for path in cleanup_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            raise AudioProcessingError(f"yt-dlp download failed: {str(e)}")
