"""Transcription functionality for audio and video sources."""

import os
import re
from typing import Optional

from .exceptions import TranscriptError, APIKeyError
from .progress import ProgressSpinner, print_status
from .handlers import get_handler
from .downloaders import DownloadManager, is_youtube_url
from .proxy import get_youtube_transcript_proxy_config


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def extract_youtube_id(url: str) -> str:
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
    if not match:
        raise TranscriptError("Could not extract YouTube video ID from URL")
    return match.group(1)


def get_youtube_transcript(
    video_id: str,
    language: str = "auto",
    verbose: bool = False,
    use_proxy: bool = False,
) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            NoTranscriptFound,
            YouTubeTranscriptApiException,
        )
    except ImportError:
        raise TranscriptError("youtube-transcript-api package not installed")

    spinner = ProgressSpinner("Fetching YouTube transcript", verbose)
    try:
        spinner.start()

        proxy_config = get_youtube_transcript_proxy_config(use_proxy)
        if proxy_config is not None:
            ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)
            print_status("Using Webshare proxy for YouTube transcript", "INFO", verbose)
        else:
            ytt_api = YouTubeTranscriptApi()

        if language == "auto":
            transcript_list = ytt_api.list(video_id)
            transcript = next(iter(transcript_list), None)
            if transcript is None:
                raise TranscriptError(
                    "No YouTube captions are available for this video. Try using --force-download instead."
                )
            transcript_data = transcript.fetch().to_raw_data()
        else:
            transcript_data = ytt_api.fetch(video_id, languages=[language]).to_raw_data()

        spinner.stop()
        print_status("YouTube transcript fetched successfully", "SUCCESS", verbose)

        return "\n".join(
            f"{format_timestamp(entry['start'])} {entry['text'].strip()}"
            for entry in transcript_data
        )
    except NoTranscriptFound as e:
        spinner.stop()
        raise TranscriptError(
            f"Requested YouTube caption language '{language}' is not available for this video. Try --language auto or --force-download instead."
        ) from e
    except TranscriptError:
        spinner.stop()
        raise
    except YouTubeTranscriptApiException as e:
        spinner.stop()
        raise TranscriptError(
            f"Failed to get YouTube transcript. Try using --force-download instead. Error: {str(e)}"
        ) from e
    except Exception as e:
        spinner.stop()
        raise TranscriptError(
            f"Failed to get YouTube transcript. Try using --force-download instead. Error: {str(e)}"
        ) from e


def transcribe_audio(
    audio_path: str,
    method: str = "Cloud Whisper",
    verbose: bool = False,
    whisper_model: str = "tiny",
    language: str = "auto",
) -> str:
    if method == "Cloud Whisper":
        return _transcribe_cloud_whisper(audio_path, verbose, language)
    elif method == "Local Whisper":
        return _transcribe_local_whisper(audio_path, verbose, whisper_model, language)
    else:
        raise TranscriptError(f"Unknown transcription method: {method}")


def _transcribe_cloud_whisper(
    audio_path: str, verbose: bool, language: str = "auto"
) -> str:
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
            request = {
                "file": audio_file,
                "model": "whisper-large-v3",
                "response_format": "text",
                "temperature": 0.0,
            }
            if language and language != "auto":
                request["language"] = language

            response = groq_client.audio.transcriptions.create(**request)

            timestamp = format_timestamp(0)
            transcript = f"{timestamp} {response.strip()}\n"

            spinner.stop()
            print_status("Audio transcription completed", "SUCCESS", verbose)
            return transcript

    except Exception as e:
        spinner.stop()
        raise TranscriptError(f"Cloud Whisper transcription failed: {str(e)}")


def _transcribe_local_whisper(
    audio_path: str,
    verbose: bool,
    model_size: str = "tiny",
    language: str = "auto",
) -> str:
    try:
        import whisper
        import torch
    except ImportError:
        raise TranscriptError(
            "Local Whisper requires 'openai-whisper' package: pip install openai-whisper"
        )

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if verbose:
        if device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            print_status(f"Using GPU: {gpu_name}", "INFO", verbose)
        else:
            print_status("No GPU detected, using CPU", "INFO", verbose)

    valid_models = ["tiny", "base", "small", "medium", "large"]
    if model_size not in valid_models:
        print_status(f"Invalid model '{model_size}', using 'tiny'", "WARNING", verbose)
        model_size = "tiny"

    spinner = ProgressSpinner(f"Loading Whisper {model_size} model", verbose)
    try:
        spinner.start()
        model = whisper.load_model(model_size, device=device)
        spinner.stop()
        print_status(f"Whisper {model_size} model loaded on {device.upper()}", "SUCCESS", verbose)
    except Exception as e:
        spinner.stop()
        raise TranscriptError(f"Whisper model loading failed: {str(e)}")

    spinner = ProgressSpinner("Transcribing with local Whisper", verbose)
    try:
        spinner.start()
        transcribe_options = {}
        if language and language != "auto":
            transcribe_options["language"] = language
        result = model.transcribe(audio_path, **transcribe_options)

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
    source_type = config.get("type_of_source")
    source_path = config.get("source_url_or_path")
    transcription_method = config.get("transcription_method", "Cloud Whisper")
    whisper_model = config.get("whisper_model", "tiny")
    verbose = config.get("verbose", False)
    use_proxy = bool(config.get("use_proxy", False))
    language = config.get("language", "auto")

    if not source_type or not source_path:
        raise TranscriptError("Source type and path/URL are required")

    if source_type == "TXT":
        if not os.path.exists(source_path):
            raise TranscriptError(f"Text file not found: {source_path}")
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(source_path, "r", encoding="latin-1") as f:
                text = f.read()
        if not text or not text.strip():
            raise TranscriptError("Text file is empty")
        return text

    raw_audio_speed = config.get("audio_speed", 1.0)
    try:
        audio_speed = float(raw_audio_speed)
    except (TypeError, ValueError):
        raise TranscriptError("audio_speed must be a positive number")
    if audio_speed <= 0:
        raise TranscriptError("audio_speed must be greater than 0")

    if source_type == "YouTube Video":
        if is_youtube_url(source_path) and config.get("use_youtube_captions", True):
            video_id = extract_youtube_id(source_path)
            print_status("Attempting YouTube captions", "INFO", verbose)
            if use_proxy:
                print_status("Proxy enabled for caption fetch", "INFO", verbose)
            try:
                return get_youtube_transcript(
                    video_id,
                    language,
                    verbose,
                    use_proxy=use_proxy,
                )
            except TranscriptError as e:
                print_status(f"Captions failed: {e}", "WARNING", verbose)
                print_status(
                    "Falling back to audio download + transcription", "PROCESSING", verbose
                )

        if use_proxy:
            print_status("Proxy enabled for audio download", "INFO", verbose)
        audio_path = DownloadManager(config.get("cobalt_base_url")).download_audio(
            source_path,
            verbose=verbose,
            audio_speed=audio_speed,
            use_proxy=use_proxy,
        )
        try:
            return transcribe_audio(
                audio_path,
                transcription_method,
                verbose,
                whisper_model,
                language,
            )
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

    if source_type in ("Local File", "Google Drive Video Link", "Dropbox Video Link"):
        handler = get_handler(
            source_type,
            source_path,
            audio_speed=audio_speed,
            use_proxy=use_proxy,
        )
        audio_path, should_delete = handler.get_processed_audio()
        try:
            return transcribe_audio(
                audio_path,
                transcription_method,
                verbose,
                whisper_model,
                language,
            )
        finally:
            if should_delete and os.path.exists(audio_path):
                os.remove(audio_path)

    if source_type == "Video URL":
        if use_proxy:
            print_status("Proxy enabled for video URL download", "INFO", verbose)
        audio_path = DownloadManager(config.get("cobalt_base_url")).download_audio(
            source_path,
            verbose=verbose,
            audio_speed=audio_speed,
            use_proxy=use_proxy,
        )
        try:
            return transcribe_audio(
                audio_path,
                transcription_method,
                verbose,
                whisper_model,
                language,
            )
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

    raise TranscriptError(f"Unknown source type: {source_type}")
