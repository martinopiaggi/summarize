"""CLI interface for the summarizer package."""
import argparse
import os
import sys
from datetime import datetime
from typing import List
from .core import main, CONFIG

def parse_args():
    parser = argparse.ArgumentParser(description="Summarize video content from various sources")
    
    # Source configuration
    parser.add_argument("--source", required=True, nargs='+',
                       help="One or more video sources")
    parser.add_argument("--type", 
                       choices=["YouTube Video", "Google Drive Video Link", 
                               "Dropbox Video Link", "Local File"],
                       default="YouTube Video", 
                       help="Source type")
    parser.add_argument("--force-download", action="store_true", 
                       help="Force audio download instead of using YouTube captions")
    
    # API configuration
    parser.add_argument("--base-url", required=True,
                       help="Base URL for API (e.g., https://api.deepseek.com/v1)")
    parser.add_argument("--model", required=True,
                       help="Model to use (e.g., deepseek-chat)")
    parser.add_argument("--api-key",
                       help="API key. If not provided, will look in .env file")
    
    # Output configuration
    parser.add_argument("--output-dir", default="summaries",
                       help="Directory to save summaries (default: summaries)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Enable verbose output with detailed progress")
    
    # Processing settings
    parser.add_argument("--prompt-type", 
                       choices=["Summarization", 
                               "Only grammar correction with highlights",
                               "Distill Wisdom", 
                               "Questions and answers",
                               "DNA Extractor",
                               "Research",
                               "Tutorial",
                               "Reflections",
                               "Fact Checker",
                               "Essay Writing in Paul Graham Style"],
                       default="Questions and answers", 
                       help="Summary style")
    parser.add_argument("--chunk-size", type=int, default=10000,
                       help="Size of text chunks for processing")
    parser.add_argument("--parallel-calls", type=int, default=30,
                       help="Number of parallel API calls")
    parser.add_argument("--max-tokens", type=int, default=4096,
                       help="Maximum tokens in model output")
    parser.add_argument("--language", default="auto", 
                       help="Language code (e.g., 'en')")
    parser.add_argument("--transcription", 
                       choices=["Cloud Whisper", "Local Whisper"],
                       default="Cloud Whisper", 
                       help="Transcription method when forcing download")
    
    return parser.parse_args()

def process_url(url: str, base_config: dict, output_dir: str, verbose: bool) -> None:
    """Process a single URL."""
    from .core import print_status

    if verbose:
        print_status(f"Starting processing for: {url}", "PROCESSING", verbose)
    # In non-verbose mode, don't show processing start

    config = base_config.copy()
    config["source_url_or_path"] = url
    config["verbose"] = verbose

    try:
        summary = main(config)

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Clean URL for filename
        clean_url = url.split("?")[0].split("/")[-1]
        filename = f"{clean_url}_{timestamp}.md"
        filepath = os.path.join(output_dir, filename)

        # Save summary
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Summary for: {url}\n\n")
            f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(summary)

        if verbose:
            print_status(f"Summary saved to: {filepath}", "SUCCESS", verbose)
        else:
            print_status(f"Saved {filename}", "SUCCESS", verbose)

    except Exception as e:
        print_status(f"Error: {str(e)}", "ERROR", verbose)

def cli():
    """Entry point for the CLI."""
    from .core import print_status

    args = parse_args()
    verbose = args.verbose

    if verbose:
        print_status("Video Summarizer CLI Started", "PROCESSING", verbose)
        print_status(f"Output directory: {args.output_dir}", "INFO", verbose)
        print_status(f"Model: {args.model}", "INFO", verbose)
        print_status(f"Prompt type: {args.prompt_type}", "INFO", verbose)
        print_status(f"Processing {len(args.source)} source(s)", "INFO", verbose)
    # In non-verbose mode, show nothing at startup

    # Smart caption logic: If user explicitly specifies ANY transcription method,
    # they want to use that method, so disable captions for YouTube videos
    # Only consider it explicit if the user provided the --transcription flag
    transcription_was_provided = any('--transcription' in arg for arg in sys.argv)
    explicit_transcription = transcription_was_provided and args.transcription in ["Cloud Whisper", "Local Whisper"]
    smart_force_download = args.force_download or explicit_transcription

    if verbose and explicit_transcription and not args.force_download:
        print_status(f"Auto-enabling audio download for {args.transcription} testing", "INFO", verbose)

    # Base config
    base_config = {
        "type_of_source": args.type,
        "use_youtube_captions": not smart_force_download,
        "transcription_method": args.transcription,
        "language": args.language,
        "prompt_type": args.prompt_type,
        "chunk_size": args.chunk_size,
        "parallel_api_calls": args.parallel_calls,
        "max_output_tokens": args.max_tokens,
        "base_url": args.base_url,
        "model": args.model,
        "verbose": verbose
    }

    # If API key provided via CLI, use it
    if args.api_key:
        base_config["api_key"] = args.api_key

    # Process each URL
    success_count = 0
    for i, source in enumerate(args.source, 1):
        if verbose:
            print_status(f"[{i}/{len(args.source)}] Processing source", "PROCESSING", verbose)
        try:
            process_url(source, base_config, args.output_dir, verbose)
            success_count += 1
        except Exception as e:
            print_status(f"Failed to process source {i}: {str(e)}", "ERROR", verbose)

    # Final summary
    if success_count == len(args.source):
        if verbose:
            print_status(f"All {len(args.source)} sources processed successfully!", "SUCCESS", verbose)
        else:
            print_status(f"Completed all {len(args.source)} sources", "SUCCESS", verbose)
    else:
        print_status(f"Completed {success_count}/{len(args.source)} sources", "WARNING", verbose)
    
if __name__ == "__main__":
    cli()