"""YouTube audio downloader."""

import os
import re
import tempfile
import uuid
from typing import Optional
from ..exceptions import AudioProcessingError
from ..handlers import process_audio_file
from ..progress import ProgressSpinner, print_status
from .base import BaseDownloader


YOUTUBE_URL_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/|youtu\.be\/)",
    re.IGNORECASE,
)


def is_youtube_url(url: str) -> bool:
    return bool(YOUTUBE_URL_REGEX.search(url or ""))


def download_youtube_audio(
    url: str, verbose: bool = False, temp_dir: Optional[str] = None
) -> str:
    """
    Download YouTube video audio.

    Args:
        url: YouTube video URL
        verbose: Enable verbose output
        temp_dir: Optional temp directory to use

    Returns:
        Path to the processed audio file
    """
    try:
        import pytubefix as pytube
    except ImportError:
        raise AudioProcessingError("pytubefix package not installed")

    spinner = ProgressSpinner("Downloading YouTube audio", verbose)
    temp_root = temp_dir or tempfile.gettempdir()
    temp_name = f"yt_audio_{uuid.uuid4().hex}"
    temp_path = os.path.join(temp_root, f"{temp_name}.mp4")
    processed_path = os.path.join(temp_root, f"{temp_name}.mp3")

    try:
        spinner.start()

        yt = pytube.YouTube(url)
        stream = yt.streams.get_audio_only()
        stream.download(output_path=temp_root, filename=f"{temp_name}.mp4")

        spinner.stop()
        print_status("Audio download completed", "SUCCESS", verbose)

        spinner = ProgressSpinner("Processing audio file", verbose)
        spinner.start()

        process_audio_file(temp_path, processed_path)
        os.remove(temp_path)

        spinner.stop()
        print_status("Audio processing completed", "SUCCESS", verbose)

        return processed_path
    except Exception as e:
        spinner.stop()
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(processed_path):
            os.remove(processed_path)
        raise AudioProcessingError(f"Failed to download YouTube audio: {str(e)}")


class YouTubeDownloader(BaseDownloader):
    """Downloader for YouTube URLs."""

    def supports(self, url: str) -> bool:
        return is_youtube_url(url)

    def download_audio(
        self, url: str, temp_dir: Optional[str] = None, verbose: bool = False
    ) -> str:
        return download_youtube_audio(url, verbose=verbose, temp_dir=temp_dir)
