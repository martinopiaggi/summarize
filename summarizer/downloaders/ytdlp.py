"""yt-dlp downloader for non-YouTube platforms (IG, TikTok, X, Reddit, etc.)."""

import os
import tempfile
import uuid
from typing import Optional
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
