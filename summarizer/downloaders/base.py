"""Downloader base types."""

from typing import Optional


class BaseDownloader:
    """Base class for URL downloaders."""

    def supports(self, url: str) -> bool:
        raise NotImplementedError

    def download_audio(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        audio_speed: float = 1.0,
        use_proxy: bool = False,
    ) -> str:
        raise NotImplementedError

    def download_video(
        self,
        url: str,
        temp_dir: Optional[str] = None,
        verbose: bool = False,
        use_proxy: bool = False,
    ) -> str:
        """Download full video (audio + video muxed). Returns path to video file."""
        raise NotImplementedError
