"""Downloaders for extracting audio from video URLs."""

from .base import BaseDownloader
from .youtube import YouTubeDownloader, download_youtube_audio, is_youtube_url
from .cobalt import CobaltDownloader
from .manager import DownloadManager

__all__ = [
    "BaseDownloader",
    "YouTubeDownloader",
    "CobaltDownloader",
    "DownloadManager",
    "download_youtube_audio",
    "is_youtube_url",
]
