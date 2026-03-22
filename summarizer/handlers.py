"""Video source handlers for different platforms."""
import os
import tempfile
import subprocess
from typing import Tuple, Optional, List
import requests

from .exceptions import SourceNotFoundError, UnsupportedSourceError, AudioProcessingError
from .proxy import get_webshare_proxies, should_proxy_url


class VideoSourceHandler:
    """Base class for handling different video sources."""
    
    def __init__(
        self,
        source_path: str,
        temp_dir: Optional[str] = None,
        audio_speed: float = 1.0,
        use_proxy: bool = False,
    ):
        self.source_path = source_path
        self.temp_dir = temp_dir or tempfile.gettempdir()
        self.audio_speed = audio_speed
        self.use_proxy = use_proxy
        
    def get_processed_audio(self) -> Tuple[str, bool]:
        """
        Get processed audio file from the source.
        
        Returns:
            Tuple of (processed_audio_path, should_delete)
        """
        raise NotImplementedError
        
    def cleanup(self, file_path: str) -> None:
        """Remove a temporary file if it exists."""
        if os.path.exists(file_path):
            os.remove(file_path)


def convert_to_wav(input_path: str, output_wav: str, ffmpeg_args: Optional[List[str]] = None) -> None:
    """Convert audio/video file to WAV format."""
    args = ['ffmpeg', '-y', '-i', input_path, '-vn']
    if ffmpeg_args:
        args.extend(ffmpeg_args)
    else:
        args.extend(['-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1'])
    args.append(output_wav)
    
    try:
        subprocess.run(args, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise AudioProcessingError(f"Failed to convert audio: {e.stderr.decode() if e.stderr else str(e)}")


def process_audio_file(
    input_path: str, output_path: str, playback_speed: float = 1.0
) -> None:
    """Convert audio to MP3 with reduced quality for API limits."""
    try:
        speed = float(playback_speed)
    except (TypeError, ValueError):
        raise AudioProcessingError("Audio speed must be a number")
    if speed <= 0:
        raise AudioProcessingError("Audio speed must be greater than 0")

    # ffmpeg atempo accepts 0.5..2.0 per stage; chain stages for any positive speed.
    tempo_stages = []
    remaining = speed
    while remaining > 2.0:
        tempo_stages.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        tempo_stages.append(0.5)
        remaining /= 0.5
    if abs(remaining - 1.0) > 1e-9:
        tempo_stages.append(remaining)

    command = [
        'ffmpeg', '-y', '-i', input_path,
    ]
    if tempo_stages:
        atempo_filter = ",".join(f"atempo={stage:g}" for stage in tempo_stages)
        command.extend(['-filter:a', atempo_filter])
    command.extend([
        '-ar', '8000',
        '-ac', '1',
        '-b:a', '16k',
        output_path
    ])
    try:
        subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise AudioProcessingError(f"Failed to process audio: {e.stderr.decode() if e.stderr else str(e)}")


class LocalFileHandler(VideoSourceHandler):
    """Handler for local video/audio files."""
    
    def get_processed_audio(self) -> Tuple[str, bool]:
        if not os.path.exists(self.source_path):
            raise SourceNotFoundError(f"Local file not found: {self.source_path}")
            
        temp_wav = os.path.join(self.temp_dir, "local_audio.wav")
        convert_to_wav(self.source_path, temp_wav)
        processed_path = os.path.join(self.temp_dir, "local_processed.mp3")
        process_audio_file(temp_wav, processed_path, playback_speed=self.audio_speed)
        self.cleanup(temp_wav)
        
        return processed_path, True


class GoogleDriveHandler(VideoSourceHandler):
    """Handler for Google Drive video files."""
    
    def get_processed_audio(self) -> Tuple[str, bool]:
        try:
            from google.colab import drive
            drive.mount('/content/drive')
        except ImportError:
            raise ImportError("Google Drive operations require Google Colab environment")
            
        if not self.source_path.startswith('/content/drive'):
            self.source_path = f"/content/drive/MyDrive/{self.source_path}"
            
        if not os.path.exists(self.source_path):
            raise SourceNotFoundError(f"File not found in Google Drive: {self.source_path}")
            
        temp_wav = os.path.join(self.temp_dir, "gdrive_audio.wav")
        convert_to_wav(self.source_path, temp_wav)
        processed_path = os.path.join(self.temp_dir, "gdrive_processed.mp3")
        process_audio_file(temp_wav, processed_path, playback_speed=self.audio_speed)
        self.cleanup(temp_wav)
        
        return processed_path, True


class DropboxHandler(VideoSourceHandler):
    """Handler for Dropbox video files."""
    
    def get_processed_audio(self) -> Tuple[str, bool]:
        temp_video = os.path.join(self.temp_dir, "dropbox_video.mp4")
        proxies = None
        if should_proxy_url(self.source_path, self.use_proxy):
            proxies = get_webshare_proxies(True)

        try:
            with requests.get(
                self.source_path,
                stream=True,
                timeout=120,
                proxies=proxies,
            ) as response:
                response.raise_for_status()
                with open(temp_video, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
        except Exception as exc:
            raise AudioProcessingError(f"Failed to download Dropbox file: {exc}")
        
        temp_wav = os.path.join(self.temp_dir, "dropbox_audio.wav")
        convert_to_wav(temp_video, temp_wav)
        processed_path = os.path.join(self.temp_dir, "dropbox_processed.mp3")
        process_audio_file(temp_wav, processed_path, playback_speed=self.audio_speed)
        self.cleanup(temp_video)
        self.cleanup(temp_wav)
        
        return processed_path, True


# Handler registry
HANDLERS = {
    "Local File": LocalFileHandler,
    "Google Drive Video Link": GoogleDriveHandler,
    "Dropbox Video Link": DropboxHandler
}


def get_handler(
    source_type: str,
    source_path: str,
    audio_speed: float = 1.0,
    use_proxy: bool = False,
) -> VideoSourceHandler:
    """
    Get the appropriate handler for a source type.
    
    Args:
        source_type: Type of the video source
        source_path: Path or URL to the source
        
    Returns:
        VideoSourceHandler instance
        
    Raises:
        UnsupportedSourceError: If the source type is not supported
    """
    handler_class = HANDLERS.get(source_type)
    if not handler_class:
        available = ", ".join(HANDLERS.keys())
        raise UnsupportedSourceError(
            f"Unsupported source type: {source_type}. "
            f"Available types: {available}"
        )
        
    return handler_class(source_path, audio_speed=audio_speed, use_proxy=use_proxy)
