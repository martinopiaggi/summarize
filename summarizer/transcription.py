"""Transcription functionality for audio and video sources."""

import os
import re
from typing import Optional
from .exceptions import TranscriptError, APIKeyError
from .progress import ProgressSpinner, print_status
from .handlers import get_handler
from .downloaders import DownloadManager, is_youtube_url


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def extract_youtube_id(url: str) -> str:
    """
    Extract YouTube video ID from URL.

    Supports various YouTube URL formats including:
    - youtube.com/watch?v=ID
    - youtu.be/ID
    - youtube.com/embed/ID
    """
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
    if not match:
        raise TranscriptError("Could not extract YouTube video ID from URL")
    return match.group(1)


def get_youtube_transcript(
    video_id: str, language: str = "en", verbose: bool = False
) -> str:
    """
    Get transcript from YouTube captions.

    Args:
        video_id: YouTube video ID
        language: Language code for captions
        verbose: Enable verbose output

    Returns:
        Formatted transcript with timestamps
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        raise TranscriptError("youtube-transcript-api package not installed")

    spinner = ProgressSpinner("Fetching YouTube transcript", verbose)
    try:
        spinner.start()

        if language == "auto":
            language = "en"

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=[language]).to_raw_data()

        spinner.stop()
        print_status("YouTube transcript fetched successfully", "SUCCESS", verbose)

        return "\n".join(
            f"{format_timestamp(entry['start'])} {entry['text'].strip()}"
            for entry in transcript
        )
    except Exception as e:
        spinner.stop()
        raise TranscriptError(
            f"Failed to get YouTube transcript. Try using --force-download instead. Error: {str(e)}"
        )


def transcribe_audio(
    audio_path: str, method: str = "Cloud Whisper", verbose: bool = False
) -> str:
    """
    Transcribe audio file using specified method.

    Args:
        audio_path: Path to the audio file
        method: Transcription method ("Cloud Whisper" or "Local Whisper")
        verbose: Enable verbose output

    Returns:
        Transcription text with timestamps
    """
    if method == "Cloud Whisper":
        return _transcribe_cloud_whisper(audio_path, verbose)
    elif method == "Local Whisper":
        return _transcribe_local_whisper(audio_path, verbose)
    else:
        raise TranscriptError(f"Unknown transcription method: {method}")


def _transcribe_cloud_whisper(audio_path: str, verbose: bool) -> str:
    """Transcribe using Groq's Cloud Whisper API."""
    api_key = os.getenv("groq")
    if not api_key:
        raise APIKeyError("Groq API key not found in environment (set 'groq' in .env)")

    spinner = ProgressSpinner("Transcribing audio with Groq API", verbose)
    try:
        spinner.start()

        try:
            from groq import Groq
        except ImportError:
            spinner.stop()
            raise TranscriptError(
                "Cloud Whisper requires 'groq' package: pip install groq"
            )

        groq_client = Groq(api_key=api_key)

        with open(audio_path, "rb") as audio_file:
            response = groq_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                response_format="text",
                language="en",
                temperature=0.0,
            )

            timestamp = format_timestamp(0)
            transcript = f"{timestamp} {response.strip()}\n"

            spinner.stop()
            print_status("Audio transcription completed", "SUCCESS", verbose)
            return transcript

    except Exception as e:
        spinner.stop()
        raise TranscriptError(f"Cloud Whisper transcription failed: {str(e)}")


def _transcribe_local_whisper(audio_path: str, verbose: bool) -> str:
    """Transcribe using local Whisper model."""
    try:
        import whisper
    except ImportError:
        raise TranscriptError(
            "Local Whisper requires 'openai-whisper' package: pip install openai-whisper"
        )

    spinner = ProgressSpinner("Loading Whisper model", verbose)
    try:
        spinner.start()
        model = whisper.load_model("base")
        spinner.stop()
        print_status("Whisper model loaded", "SUCCESS", verbose)
    except Exception as e:
        spinner.stop()
        raise TranscriptError(f"Whisper model loading failed: {str(e)}")

    spinner = ProgressSpinner("Transcribing with local Whisper", verbose)
    try:
        spinner.start()
        result = model.transcribe(audio_path)

        transcript = ""
        for segment in result["segments"]:
            time = format_timestamp(segment["start"])
            transcript += f"{time} {segment['text'].strip()}\n"

        spinner.stop()
        print_status("Local transcription completed", "SUCCESS", verbose)
        return transcript

    except Exception as e:
        spinner.stop()
        raise TranscriptError(f"Whisper transcription failed: {str(e)}")


def get_transcript(config: dict) -> str:
    """
    Get transcript based on source type and configuration.

    Args:
        config: Configuration dictionary with source details

    Returns:
        Transcript text with timestamps
    """
    source_type = config.get("type_of_source")
    source_path = config.get("source_url_or_path")
    transcription_method = config.get("transcription_method", "Cloud Whisper")
    verbose = config.get("verbose", False)

    if not source_type or not source_path:
        raise TranscriptError("Source type and path/URL are required")

    if source_type == "YouTube Video":
        if is_youtube_url(source_path) and config.get("use_youtube_captions", True):
            video_id = extract_youtube_id(source_path)
            return get_youtube_transcript(
                video_id, config.get("language", "en"), verbose
            )

        audio_path = DownloadManager(config.get("cobalt_base_url")).download_audio(
            source_path,
            verbose=verbose,
        )
        try:
            transcript = transcribe_audio(audio_path, transcription_method, verbose)
            return transcript
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

    if source_type in ("Local File", "Google Drive Video Link", "Dropbox Video Link"):
        handler = get_handler(source_type, source_path)
        audio_path, should_delete = handler.get_processed_audio()
        try:
            transcript = transcribe_audio(audio_path, transcription_method, verbose)
            return transcript
        finally:
            if should_delete and os.path.exists(audio_path):
                os.remove(audio_path)

    if source_type == "Video URL":
        audio_path = DownloadManager(config.get("cobalt_base_url")).download_audio(
            source_path,
            verbose=verbose,
        )
        try:
            transcript = transcribe_audio(audio_path, transcription_method, verbose)
            return transcript
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

    raise TranscriptError(f"Unknown source type: {source_type}")
