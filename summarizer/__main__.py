"""CLI interface for the summarizer package."""
import argparse
import os
from datetime import datetime
from typing import List
from .core import main, CONFIG

def parse_args():
    parser = argparse.ArgumentParser(description="Summarize video content from various sources")
    
    # Source configuration
    parser.add_argument("--urls", required=True, nargs='+',
                       help="One or more video URLs or paths")
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
    
    # Processing settings
    parser.add_argument("--prompt-type", 
                       choices=["Summarization", 
                               "Only grammar correction with highlights",
                               "Distill Wisdom", 
                               "Questions and answers",
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

def process_url(url: str, base_config: dict, output_dir: str) -> None:
    """Process a single URL."""
    print(f"\nProcessing: {url}")
    
    config = base_config.copy()
    config["source_url_or_path"] = url
    
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
        print(f"\nSummary saved to: {filepath}")
            
    except Exception as e:
        print(f"Error processing {url}: {str(e)}")

def cli():
    """Entry point for the CLI."""
    args = parse_args()
    
    # Base config
    base_config = {
        "type_of_source": args.type,
        "use_youtube_captions": not args.force_download,
        "transcription_method": args.transcription,
        "language": args.language,
        "prompt_type": args.prompt_type,
        "chunk_size": args.chunk_size,
        "parallel_api_calls": args.parallel_calls,
        "max_output_tokens": args.max_tokens,
        "base_url": args.base_url,
        "model": args.model
    }
    
    # If API key provided via CLI, use it
    if args.api_key:
        base_config["api_key"] = args.api_key
    
    # Process each URL
    for url in args.urls:
        process_url(url, base_config, args.output_dir)
    
if __name__ == "__main__":
    cli()