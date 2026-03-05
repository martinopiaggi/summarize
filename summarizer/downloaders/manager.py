"""Downloader manager that picks the right backend."""

import os
import tempfile
from typing import Optional
from ..exceptions import AudioProcessingError, UnsupportedSourceError
from .cobalt import CobaltDownloader
from .youtube import YouTubeDownloader


class DownloadManager:
    """Select and run the appropriate downloader for a URL."""

    def __init__(self, cobalt_base_url: Optional[str] = None):
        self.cobalt_base_url = (
            os.getenv("COBALT_BASE_URL") or cobalt_base_url or "http://localhost:9000"
        )
        self.downloaders = [
            YouTubeDownloader(),
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
        temp_root = temp_dir or tempfile.gettempdir()
        last_error = None

        for downloader in self.downloaders:
            if downloader.supports(url):
                try:
                    return downloader.download_audio(
                        url,
                        temp_dir=temp_root,
                        verbose=verbose,
                        audio_speed=audio_speed,
                        use_proxy=use_proxy,
                    )
                except AudioProcessingError as exc:
                    last_error = exc
                    # pytubefix is fragile on YouTube bot checks; try the next backend.
                    continue

        if last_error is not None:
            raise last_error
        raise UnsupportedSourceError("No downloader available for the provided URL")
