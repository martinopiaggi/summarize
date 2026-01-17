"""Video source handlers for different platforms."""
import os
import tempfile
import subprocess
from typing import Tuple, Optional, List
from .exceptions import SourceNotFoundError, UnsupportedSourceError, AudioProcessingError


class VideoSourceHandler:
    """Base class for handling different video sources."""
    
    def __init__(self, source_path: str, temp_dir: Optional[str] = None):
        self.source_path = source_path
        self.temp_dir = temp_dir or tempfile.gettempdir()
        
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


def process_audio_file(input_path: str, output_path: str) -> None:
    """Convert audio to MP3 with reduced quality for API limits."""
    command = [
        'ffmpeg', '-y', '-i', input_path,
        '-ar', '8000',
        '-ac', '1',
        '-b:a', '16k',
        output_path
    ]
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
        process_audio_file(temp_wav, processed_path)
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
        process_audio_file(temp_wav, processed_path)
        self.cleanup(temp_wav)
        
        return processed_path, True


class DropboxHandler(VideoSourceHandler):
    """Handler for Dropbox video files."""
    
    def get_processed_audio(self) -> Tuple[str, bool]:
        import wget
        
        temp_video = os.path.join(self.temp_dir, "dropbox_video.mp4")
        wget.download(self.source_path, temp_video)
        
        temp_wav = os.path.join(self.temp_dir, "dropbox_audio.wav")
        convert_to_wav(temp_video, temp_wav)
        processed_path = os.path.join(self.temp_dir, "dropbox_processed.mp3")
        process_audio_file(temp_wav, processed_path)
        self.cleanup(temp_video)
        self.cleanup(temp_wav)
        
        return processed_path, True


# Handler registry
HANDLERS = {
    "Local File": LocalFileHandler,
    "Google Drive Video Link": GoogleDriveHandler,
    "Dropbox Video Link": DropboxHandler
}


def get_handler(source_type: str, source_path: str) -> VideoSourceHandler:
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
        
    return handler_class(source_path)
