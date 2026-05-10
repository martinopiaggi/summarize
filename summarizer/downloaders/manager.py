"""Downloader manager that picks the right backend."""

import os
import tempfile
from typing import Optional
from ..exceptions import AudioProcessingError, UnsupportedSourceError
from .cobalt import CobaltDownloader
from .youtube import YouTubeDownloader
from .ytdlp import YtdlpDownloader


class DownloadManager:
    """Select and run the appropriate downloader for a URL."""

    def __init__(self, cobalt_base_url: Optional[str] = None):
        self.cobalt_base_url = (
            os.getenv("COBALT_BASE_URL") or cobalt_base_url or "http://localhost:9000"
        )
        self.downloaders = [
            YouTubeDownloader(),
            YtdlpDownloader(),
            CobaltDownloader(self.cobalt_base_url),
        ]

    def download_audio(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        audio_speed: float = 1.0,
        use_proxy: bool = False,
    ) -> str:
        from ..progress import print_status

        temp_root = temp_dir or tempfile.gettempdir()
        last_error = None

        if verbose:
            proxy_state = "enabled" if use_proxy else "disabled"
            print_status(f"Proxy {proxy_state} for download", "INFO", verbose)

        tried_downloader = False
        for i, downloader in enumerate(self.downloaders):
            if downloader.supports(url):
                downloader_name = downloader.__class__.__name__.replace("Downloader", "")
                if tried_downloader:
                    print_status(f"Falling back to {downloader_name}", "WARNING", verbose)
                else:
                    print_status(f"Trying {downloader_name}", "INFO", verbose)
                tried_downloader = True
                try:
                    result_path = downloader.download_audio(
                        url,
                        temp_dir=temp_root,
                        verbose=verbose,
                        audio_speed=audio_speed,
                        use_proxy=use_proxy,
                    )
                    if verbose and os.path.exists(result_path):
                        size_kb = os.path.getsize(result_path) / 1024
                        print_status(
                            f"Audio file ready: {size_kb:.0f} KB", "INFO", verbose
                        )
                    return result_path
                except AudioProcessingError as exc:
                    last_error = exc
                    print_status(
                        f"{downloader_name} failed: {str(exc)[:120]}", "WARNING", verbose
                    )
                    # pytubefix is fragile on YouTube bot checks; try the next backend.
                    continue

        if last_error is not None:
            raise last_error
        raise UnsupportedSourceError("No downloader available for the provided URL")
