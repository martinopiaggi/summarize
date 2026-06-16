"""Core functionality for video transcription and summarization."""

import asyncio
import logging
import os

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
from .api import (
    chunk_text,
    extract_and_clean_chunks,
    process_chunk,
    process_chunks,
    format_summary_with_timestamps,
    parse_response_content,
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
        # Centralized validation for both CLI and API paths
        validate_config(config)

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

        # Use nest_asyncio if in notebook environment
        try:
            import nest_asyncio

            nest_asyncio.apply()
        except ImportError:
            pass

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Visual mode branch
            if config.get("visual"):
                from .visual import (
                    get_visual_profile,
                    resolve_visual_url,
                    resolve_video_source,
                    normalize_video,
                    validate_video_limits,
                    build_visual_segments,
                    split_video_segments,
                )
                from .visual_api import process_video, process_video_segments

                profile = get_visual_profile(config)

                # URL mode: send original URL directly without downloading/splitting
                visual_url = resolve_visual_url(config, profile)
                if visual_url:
                    summary = loop.run_until_complete(
                        process_video(config, visual_url, profile)
                    )
                    if not summary:
                        raise APIError("No valid summary generated")
                    formatted = format_summary_with_timestamps([("", summary)], config)
                    print_status("Summarization completed", "SUCCESS", verbose)
                    return formatted

                # Base64 mode: download, normalize, split, encode
                original_path, should_delete = resolve_video_source(config)
                normalized_path = normalize_video(original_path, profile, config)
                segment_paths = []
                try:
                    segments = build_visual_segments(normalized_path, profile, config)
                    if len(segments) > 1 and not profile.get("supports_chunking"):
                        validate_video_limits(normalized_path, profile, config)

                    segment_paths = split_video_segments(
                        normalized_path,
                        segments,
                        config,
                    )
                    for segment in segment_paths:
                        validate_video_limits(segment["path"], profile, config)

                    summaries = loop.run_until_complete(
                        process_video_segments(config, segment_paths, profile)
                    )
                    if not summaries:
                        raise APIError("No valid summaries generated")
                    summary = format_summary_with_timestamps(summaries, config)
                    print_status("Summarization completed", "SUCCESS", verbose)
                    return summary
                finally:
                    for segment in segment_paths:
                        segment_path = segment.get("path")
                        if (
                            segment.get("should_delete")
                            and segment_path
                            and os.path.exists(segment_path)
                        ):
                            try:
                                os.remove(segment_path)
                            except OSError:
                                pass
                    # Clean up the original downloaded file
                    if should_delete and os.path.exists(original_path):
                        try:
                            os.remove(original_path)
                        except OSError:
                            pass
                    # Clean up any normalized temp file we created
                    if normalized_path != original_path and os.path.exists(normalized_path):
                        try:
                            os.remove(normalized_path)
                        except OSError:
                            pass

            # Get transcript
            transcript = get_transcript(config)
            if not transcript or not transcript.strip():
                raise TranscriptError("No transcript content to process")

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

            summaries = loop.run_until_complete(
                process_chunks(chunks, template, config)
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
