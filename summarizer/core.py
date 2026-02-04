"""Core functionality for video transcription and summarization."""

import asyncio
import logging

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

        # Get API key
        with ProgressSpinner("Validating API configuration", verbose) as spinner:
            config["api_key"] = get_api_key(config)
        print_status("API configuration validated", "SUCCESS", verbose)

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

        if verbose:
            print_status(
                f"Created {len(chunks)} content chunks (chunk size: {config.get('chunk_size', 10000)})",
                "SUCCESS",
                verbose,
            )
        else:
            print_status(f"Created {len(chunks)} chunks", "SUCCESS", verbose)

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
