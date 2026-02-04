"""Downloader manager that picks the right backend."""

import os
import tempfile
from typing import Optional
from ..exceptions import UnsupportedSourceError
from .cobalt import CobaltDownloader
from .youtube import YouTubeDownloader


class DownloadManager:
    """Select and run the appropriate downloader for a URL."""

    def __init__(self, cobalt_base_url: Optional[str] = None):
        self.cobalt_base_url = (
            cobalt_base_url or os.getenv("COBALT_BASE_URL") or "http://localhost:9000"
        )
        self.downloaders = [
            YouTubeDownloader(),
            CobaltDownloader(self.cobalt_base_url),
        ]

    def download_audio(
        self, url: str, temp_dir: Optional[str] = None, verbose: bool = False
    ) -> str:
        temp_root = temp_dir or tempfile.gettempdir()
        for downloader in self.downloaders:
            if downloader.supports(url):
                return downloader.download_audio(
                    url, temp_dir=temp_root, verbose=verbose
                )
        raise UnsupportedSourceError("No downloader available for the provided URL")
