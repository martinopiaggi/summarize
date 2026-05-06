"""Core functionality for video transcription and summarization."""

import asyncio
import logging
import os
from urllib.parse import urlparse

# Re-export for backward compatibility
from .config import DEFAULT_CONFIG as CONFIG, get_api_key, validate_config
from .progress import ProgressSpinner, ProgressBar, print_status
from .handlers import (
    VideoSourceHandler,
    LocalFileHandler,
    GoogleDriveHandler,
    DropboxHandler,
    get_handler,
    convert_to_wav,
    process_audio_file,
)
from .transcription import (
    get_transcript,
    get_youtube_transcript,
    transcribe_audio,
    extract_youtube_id,
    format_timestamp,
)
from .downloaders import download_youtube_audio
from .downloaders.ytdlp import YtdlpDownloader, YTDLP_PRIMARY_HOSTS
from .api import (
    chunk_text,
    extract_and_clean_chunks,
    process_chunk,
    process_chunks,
    format_summary_with_timestamps,
    parse_response_content,
)
from .multimodal import extract_video_frames, MAX_FRAMES_HARD_CAP
from .engines.gemini_video import (
    analyze_video_with_gemini,
    GeminiVideoEngineError,
)
from .prompts import load_prompt_template, get_available_prompts
from .exceptions import (
    SummarizerError,
    TranscriptError,
    APIError,
    APIKeyError,
    ConfigurationError,
    AudioProcessingError,
    SourceNotFoundError,
)


def _is_ytdlp_visual_eligible(url: str) -> bool:
    """Return True if the URL host is one yt-dlp can give us a video file for."""
    host = (urlparse(url or "").hostname or "").lower()
    return any(
        host == h or host.endswith("." + h) for h in YTDLP_PRIMARY_HOSTS
    )


def _fetch_visual_and_transcript(config: dict, verbose: bool):
    """Download video + audio + metadata once, extract frames, transcribe audio.

    Returns (transcript, visual_context, caption) where visual_context is None
    if duration exceeds the configured cap (a warning is printed and the
    caller falls back transparently to audio-only reasoning).
    """
    source_url = config.get("source_url_or_path", "")
    max_duration = float(config.get("visual_max_duration", 180))
    max_dimension = int(config.get("visual_max_dimension", 768))

    downloader = YtdlpDownloader()
    media = downloader.download_with_metadata(
        source_url,
        verbose=verbose,
        audio_speed=float(config.get("audio_speed", 1.0)),
    )

    audio_path = media.get("audio_path")
    video_path = media.get("video_path")
    caption = media.get("caption")
    duration = media.get("duration")

    visual_context = None
    try:
        if duration and duration > max_duration:
            print_status(
                f"Visual analysis is not available for videos longer than "
                f"{int(max_duration)}s (this video is {duration:.0f}s). "
                f"Falling back to audio-only summary.",
                "WARNING",
                verbose,
            )
        elif video_path and os.path.isfile(video_path):
            print_status(
                f"Extracting up to {MAX_FRAMES_HARD_CAP} frames for visual context",
                "PROCESSING",
                verbose,
            )
            visual_context = extract_video_frames(
                video_path,
                n_frames=MAX_FRAMES_HARD_CAP,
                max_dimension=max_dimension,
            )
            print_status(
                f"Visual context ready: {len(visual_context)} frames",
                "SUCCESS",
                verbose,
            )

        # Transcribe the audio track yt-dlp gave us. We bypass get_transcript()
        # here because we already have the audio file on disk and don't want
        # to re-download.
        transcript = transcribe_audio(
            audio_path,
            config.get("transcription_method", "Cloud Whisper"),
            verbose,
            config.get("whisper_model", "tiny"),
            config.get("language", "auto"),
        )
        return transcript, visual_context, caption
    finally:
        for path in (audio_path, video_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


def _run_gemini_video_engine(config: dict, verbose: bool) -> str:
    """End-to-end summary using Gemini Files API for the full video.

    Downloads the source via YtdlpDownloader (we need a real video file
    on disk), uploads to Gemini, asks for the summary using the same
    prompt template the standard pipeline uses, returns the formatted
    string. Raises on any error so a caller in 'auto' mode can fall back.
    """
    source_url = config.get("source_url_or_path", "")
    downloader = YtdlpDownloader()
    media = downloader.download_with_metadata(
        source_url,
        verbose=verbose,
        audio_speed=float(config.get("audio_speed", 1.0)),
    )
    audio_path = media.get("audio_path")
    video_path = media.get("video_path")
    caption = media.get("caption")
    duration = media.get("duration")

    try:
        if not video_path or not os.path.isfile(video_path):
            raise GeminiVideoEngineError(
                "yt-dlp did not produce a video file (audio-only stream?)"
            )

        max_duration = float(config.get("visual_max_duration", 180))
        if duration and duration > max_duration:
            print_status(
                f"Visual analysis is not available for videos longer than "
                f"{int(max_duration)}s (this video is {duration:.0f}s). "
                f"Skipping Gemini Files engine.",
                "WARNING",
                verbose,
            )
            raise GeminiVideoEngineError(
                f"Video exceeds visual_max_duration ({duration:.0f}s > {max_duration:.0f}s)"
            )

        prompt_template = load_prompt_template(
            config.get("prompt_type", "Questions and answers")
        )

        print_status(
            "Uploading video to Gemini Files API",
            "PROCESSING",
            verbose,
        )
        summary = analyze_video_with_gemini(
            video_path,
            prompt_text=prompt_template,
            caption=caption,
            output_language=config.get("output_language"),
            model=config.get("gemini_model", "gemini-2.5-flash"),
            api_key=config.get("gemini_api_key"),
            max_output_tokens=int(config.get("max_output_tokens", 4096)),
            verbose=verbose,
        )
        print_status("Gemini Files engine completed", "SUCCESS", verbose)

        # Match the formatting of the standard pipeline so downstream
        # code (file naming, history) is unchanged. format_summary_with_timestamps
        # expects (timestamp, summary) 2-tuples — synthesise one for the
        # whole video at t=0.
        formatted = format_summary_with_timestamps(
            [("00:00:00", summary)], config
        )
        return formatted
    finally:
        for path in (audio_path, video_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main(config: dict) -> str:
    """
    Main processing function.

    Args:
        config: Configuration dictionary with all settings

    Returns:
        Final formatted summary string
    """
    verbose = config.get("verbose", False)

    try:
        print_status("Starting summarization", "PROCESSING", verbose)
        if verbose:
            print_status(
                f"Source: {config.get('source_url_or_path', 'unknown')}",
                "INFO",
                verbose,
            )
            print_status(
                f"Prompt type: {config.get('prompt_type', 'unknown')}", "INFO", verbose
            )
            print_status(
                f"Provider: {config.get('base_url', 'unknown')} / {config.get('model', 'unknown')}",
                "INFO",
                verbose,
            )
            proxy_state = "enabled" if config.get("use_proxy") else "disabled"
            print_status(f"Proxy: {proxy_state}", "INFO", verbose)


        # Get API key
        with ProgressSpinner("Validating API configuration", verbose) as spinner:
            config["api_key"] = get_api_key(config)
        print_status("API configuration validated", "SUCCESS", verbose)

        # Pick the video-analysis engine. For yt-dlp-eligible URLs (IG,
        # TikTok, X, Reddit, FB):
        #   - 'gemini-files'    : upload full video to Gemini Files API
        #   - 'groq-multimodal' : 5 evenly-spaced frames + Whisper transcript
        #   - 'auto' (default)  : try Gemini first, fall back to multimodal
        # For everything else (YouTube via captions, local files, etc.) the
        # video_engine value is ignored and we go through get_transcript().
        visual_context = None
        caption = None
        source_url = config.get("source_url_or_path", "") or ""
        ytdlp_eligible = _is_ytdlp_visual_eligible(source_url)
        engine = (config.get("video_engine") or "auto").lower()

        if ytdlp_eligible and engine in ("auto", "gemini-files"):
            try:
                return _run_gemini_video_engine(config, verbose)
            except GeminiVideoEngineError as exc:
                if engine == "gemini-files":
                    # User explicitly asked for Gemini and we cannot serve
                    # it — surface the error instead of silently degrading.
                    raise SummarizerError(
                        f"Gemini Files engine failed: {exc}"
                    ) from exc
                # auto mode: warn and fall through to multimodal/audio.
                print_status(
                    f"Gemini Files engine failed ({exc}). "
                    f"Falling back to Groq + 5 frames.",
                    "WARNING",
                    verbose,
                )

        if (
            ytdlp_eligible
            and config.get("enable_visual")
            and engine in ("auto", "groq-multimodal")
        ):
            transcript, visual_context, caption = _fetch_visual_and_transcript(
                config, verbose
            )
        else:
            transcript = get_transcript(config)

        if not transcript or not transcript.strip():
            raise TranscriptError("No transcript content to process")

        # If the platform gave us the author's caption, prepend it so the
        # model has the same textual context a viewer would have when they
        # opened the post.
        if caption:
            transcript = (
                f"Caption from the author of the post:\n"
                f"\"\"\"\n{caption}\n\"\"\"\n\n"
                f"Audio transcript:\n{transcript}"
            )

        # Extract chunks with timestamps
        with ProgressSpinner("Preparing content chunks", verbose) as spinner:
            chunks = extract_and_clean_chunks(
                transcript, config.get("chunk_size", 10000)
            )
        if not chunks:
            raise TranscriptError("Failed to create content chunks")

        print_status(
            f"Number of chunks: {len(chunks)} (chunk size: {config.get('chunk_size', 10000)})",
            "SUCCESS",
            verbose,
        )

        # Load template
        with ProgressSpinner("Loading prompt template", verbose) as spinner:
            template = load_prompt_template(
                config.get("prompt_type", "Questions and answers")
            )
        print_status("Template loaded", "SUCCESS", verbose)

        # Use nest_asyncio if in notebook environment
        try:
            import nest_asyncio

            nest_asyncio.apply()
        except ImportError:
            pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            summaries = loop.run_until_complete(
                process_chunks(chunks, template, config, visual_context=visual_context)
            )
            if not summaries:
                raise APIError("No valid summaries generated")

            if verbose:
                print_status("Finalizing summary output", "PROCESSING", verbose)
            final_summary = format_summary_with_timestamps(summaries, config)
            print_status("Summarization completed", "SUCCESS", verbose)
            return final_summary
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()

    except SummarizerError as e:
        print_status(f"Processing failed: {str(e)}", "ERROR", verbose)
        raise
    except Exception as e:
        print_status(f"Processing failed: {str(e)}", "ERROR", verbose)
        raise SummarizerError(f"Processing failed: {str(e)}")
