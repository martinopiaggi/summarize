"""Video source handlers for different platforms."""
import html
import os
import re
import tempfile
import subprocess
from typing import Tuple, Optional, List
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
import requests

from .exceptions import SourceNotFoundError, UnsupportedSourceError, AudioProcessingError
from .proxy import get_webshare_proxies, should_proxy_url


DROPBOX_HOST_SUFFIXES = ("dropbox.com", "dropboxusercontent.com")
GOOGLE_DRIVE_HOST_SUFFIXES = ("drive.google.com", "docs.google.com", "drive.usercontent.google.com")


def is_dropbox_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in DROPBOX_HOST_SUFFIXES)


def normalize_dropbox_url(url: str) -> str:
    if not is_dropbox_url(url):
        return url

    parsed = urlparse(url)
    if parsed.netloc.lower().endswith("dropboxusercontent.com"):
        return url

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.pop("raw", None)
    query["dl"] = "1"
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def is_google_drive_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in GOOGLE_DRIVE_HOST_SUFFIXES)


def extract_google_drive_file_id(url: str) -> Optional[str]:
    if not is_google_drive_url(url):
        return None

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    file_id = query.get("id")
    if file_id:
        return file_id

    match = re.search(r"/file/d/([^/]+)", parsed.path)
    if match:
        return match.group(1)

    return None


def build_google_drive_download_url(file_id: str, extra_query: Optional[dict] = None) -> str:
    query = {"export": "download", "id": file_id}
    if extra_query:
        query.update(extra_query)
    return f"https://drive.google.com/uc?{urlencode(query, doseq=True)}"


def extract_google_drive_confirm_url(response: requests.Response, file_id: str) -> Optional[str]:
    cookie_token = None
    for name, value in response.cookies.items():
        if name.startswith("download_warning"):
            cookie_token = value
            break
    if cookie_token:
        return build_google_drive_download_url(file_id, {"confirm": cookie_token})

    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type.lower():
        return None

    body = response.text
    action_match = re.search(r'action="([^"]+)"', body)
    if action_match:
        action_url = html.unescape(action_match.group(1))
        hidden_fields = {
            name: value
            for name, value in re.findall(r'type="hidden"\s+name="([^"]+)"\s+value="([^"]*)"', body)
        }
        if hidden_fields:
            parsed_action = urlparse(urljoin("https://drive.google.com", action_url))
            action_query = dict(parse_qsl(parsed_action.query, keep_blank_values=True))
            action_query.update(hidden_fields)
            return urlunparse(parsed_action._replace(query=urlencode(action_query, doseq=True)))
        return urljoin("https://drive.google.com", action_url)

    href_match = re.search(r'href="([^"]*confirm=[^"]+)"', body)
    if href_match:
        return urljoin("https://drive.google.com", html.unescape(href_match.group(1)))

    return None


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

    def download_raw_video(self, output_path: str) -> str:
        """Download the raw video file without audio processing."""
        file_id = extract_google_drive_file_id(self.source_path)
        if not file_id:
            raise SourceNotFoundError("Could not extract a Google Drive file ID from the shared link")

        download_url = build_google_drive_download_url(file_id)
        proxies = None
        if should_proxy_url(download_url, self.use_proxy):
            proxies = get_webshare_proxies(True)

        session = requests.Session()
        response = None
        try:
            response = session.get(
                download_url,
                stream=True,
                timeout=120,
                proxies=proxies,
            )
            response.raise_for_status()

            confirm_url = extract_google_drive_confirm_url(response, file_id)
            if confirm_url:
                response.close()
                response = session.get(
                    confirm_url,
                    stream=True,
                    timeout=120,
                    proxies=proxies,
                )
                response.raise_for_status()

            with response, open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        except Exception as exc:
            raise AudioProcessingError(f"Failed to download Google Drive file: {exc}")
        finally:
            if response is not None:
                response.close()
            session.close()

        return output_path

    def _download_shared_file(self, temp_video: str) -> Tuple[str, bool]:
        file_id = extract_google_drive_file_id(self.source_path)
        if not file_id:
            raise SourceNotFoundError("Could not extract a Google Drive file ID from the shared link")

        download_url = build_google_drive_download_url(file_id)
        proxies = None
        if should_proxy_url(download_url, self.use_proxy):
            proxies = get_webshare_proxies(True)

        session = requests.Session()
        response = None
        try:
            response = session.get(
                download_url,
                stream=True,
                timeout=120,
                proxies=proxies,
            )
            response.raise_for_status()

            confirm_url = extract_google_drive_confirm_url(response, file_id)
            if confirm_url:
                response.close()
                response = session.get(
                    confirm_url,
                    stream=True,
                    timeout=120,
                    proxies=proxies,
                )
                response.raise_for_status()

            with response, open(temp_video, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        except Exception as exc:
            raise AudioProcessingError(f"Failed to download Google Drive file: {exc}")
        finally:
            if response is not None:
                response.close()
            session.close()

        temp_wav = os.path.join(self.temp_dir, "gdrive_audio.wav")
        convert_to_wav(temp_video, temp_wav)
        processed_path = os.path.join(self.temp_dir, "gdrive_processed.mp3")
        process_audio_file(temp_wav, processed_path, playback_speed=self.audio_speed)
        self.cleanup(temp_video)
        self.cleanup(temp_wav)

        return processed_path, True
    
    def get_processed_audio(self) -> Tuple[str, bool]:
        if is_google_drive_url(self.source_path):
            temp_video = os.path.join(self.temp_dir, "gdrive_video.mp4")
            return self._download_shared_file(temp_video)

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

    def download_raw_video(self, output_path: str) -> str:
        """Download the raw video file without audio processing."""
        download_url = normalize_dropbox_url(self.source_path)
        proxies = None
        if should_proxy_url(download_url, self.use_proxy):
            proxies = get_webshare_proxies(True)

        try:
            with requests.get(
                download_url,
                stream=True,
                timeout=120,
                proxies=proxies,
            ) as response:
                response.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
        except Exception as exc:
            raise AudioProcessingError(f"Failed to download Dropbox file: {exc}")

        return output_path

    def get_processed_audio(self) -> Tuple[str, bool]:
        temp_video = os.path.join(self.temp_dir, "dropbox_video.mp4")
        download_url = normalize_dropbox_url(self.source_path)
        proxies = None
        if should_proxy_url(download_url, self.use_proxy):
            proxies = get_webshare_proxies(True)

        try:
            with requests.get(
                download_url,
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
