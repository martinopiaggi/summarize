"""CLI interface for the summarizer package."""
import argparse
import os
import sys
from datetime import datetime
from typing import List, Optional
from .core import main, CONFIG
from .progress import print_status
from .config_file import load_config_file, merge_configs, find_config_file, create_example_config


def parse_args():
    parser = argparse.ArgumentParser(
        description="Summarize video content from various sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using config file with provider shortcut
  python -m summarizer --source "URL" --provider groq

  # Generate example config file
  python -m summarizer --init-config

  # Traditional usage
  python -m summarizer --source "URL" --base-url "https://api.groq.com/openai/v1" --model "llama-3.3-70b-versatile"
"""
    )
    
    # Config file options
    parser.add_argument("--provider", "-p",
                       help="Provider name from config file (e.g., 'groq', 'gemini')")
    parser.add_argument("--config",
                       help="Path to config file (default: auto-detect)")
    parser.add_argument("--init-config", action="store_true",
                       help="Generate example config file and exit")
    parser.add_argument("--no-config", action="store_true",
                       help="Ignore config file, use CLI args only")
    
    # Source configuration
    parser.add_argument("--source", nargs='+',
                       help="One or more video sources (URLs or filenames)")
    parser.add_argument("--type", 
                       choices=["YouTube Video", "Google Drive Video Link", 
                               "Dropbox Video Link", "Local File"],
                       default="YouTube Video", 
                       help="Source type")
    parser.add_argument("--force-download", action="store_true", 
                       help="Force audio download instead of using YouTube captions")
    
    # API configuration (optional if using config file)
    parser.add_argument("--base-url",
                       help="Base URL for API (e.g., https://api.deepseek.com/v1)")
    parser.add_argument("--model",
                       help="Model to use (e.g., deepseek-chat)")
    parser.add_argument("--api-key",
                       help="API key. If not provided, will look in .env file")
    
    # Output configuration
    parser.add_argument("--output-dir", default="summaries",
                       help="Directory to save summaries (default: summaries)")
    parser.add_argument("--output-format", "-f",
                       choices=["markdown", "json", "html"],
                       default="markdown",
                       help="Output format (default: markdown)")
    parser.add_argument("--no-save", action="store_true",
                       help="Print to stdout instead of saving to file")
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


def format_output(summary: str, url: str, format_type: str, metadata: dict) -> str:
    """
    Format summary in the requested output format.
    
    Args:
        summary: The summary text
        url: Source URL
        format_type: 'markdown', 'json', or 'html'
        metadata: Additional metadata dict
        
    Returns:
        Formatted output string
    """
    import json
    
    if format_type == "json":
        output = {
            "source": url,
            "generated_at": datetime.now().isoformat(),
            "prompt_type": metadata.get("prompt_type", ""),
            "model": metadata.get("model", ""),
            "summary": summary
        }
        return json.dumps(output, indent=2, ensure_ascii=False)
    
    elif format_type == "html":
        escaped_summary = summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Convert markdown-style headers and bold to HTML
        lines = escaped_summary.split("\n")
        html_lines = []
        for line in lines:
            if line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("### "):
                html_lines.append(f"<h3>{line[4:]}</h3>")
            elif line.startswith("- "):
                html_lines.append(f"<li>{line[2:]}</li>")
            elif line.strip():
                html_lines.append(f"<p>{line}</p>")
            else:
                html_lines.append("")
        
        body = "\n".join(html_lines)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Summary: {url}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               max-width: 800px; margin: 0 auto; padding: 2rem; line-height: 1.6; }}
        h1, h2, h3 {{ color: #333; }}
        li {{ margin: 0.5rem 0; }}
        .meta {{ color: #666; font-size: 0.9rem; border-bottom: 1px solid #eee; padding-bottom: 1rem; margin-bottom: 2rem; }}
    </style>
</head>
<body>
    <div class="meta">
        <strong>Source:</strong> <a href="{url}">{url}</a><br>
        <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
    {body}
</body>
</html>"""
    
    else:  # markdown (default)
        return f"""# Summary for: {url}

Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{summary}"""


def get_file_extension(format_type: str) -> str:
    """Get file extension for output format."""
    extensions = {
        "markdown": ".md",
        "json": ".json",
        "html": ".html"
    }
    return extensions.get(format_type, ".md")


def process_url(url: str, base_config: dict, output_dir: str, verbose: bool,
                output_format: str = "markdown", no_save: bool = False) -> bool:
    """Process a single URL."""
    if verbose:
        print_status(f"Starting processing for: {url}", "PROCESSING", verbose)

    config = base_config.copy()
    config["source_url_or_path"] = url
    config["verbose"] = verbose

    try:
        summary = main(config)

        # Format output
        metadata = {
            "prompt_type": config.get("prompt_type", ""),
            "model": config.get("model", "")
        }
        formatted = format_output(summary, url, output_format, metadata)

        if no_save:
            print(formatted)
            return True

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_url = url.split("?")[0].split("/")[-1]
        ext = get_file_extension(output_format)
        filename = f"{clean_url}_{timestamp}{ext}"
        filepath = os.path.join(output_dir, filename)

        # Save
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(formatted)

        if verbose:
            print_status(f"Summary saved to: {filepath}", "SUCCESS", verbose)
        else:
            print_status(f"Saved {filename}", "SUCCESS", verbose)

        return True

    except Exception as e:
        print_status(f"Error: {str(e)}", "ERROR", verbose)
        return False


def cli():
    """Entry point for the CLI."""
    args = parse_args()
    verbose = args.verbose

    # Handle --init-config
    if args.init_config:
        config_path = os.path.join(os.getcwd(), "summarizer.yaml")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(create_example_config())
        print(f"Created example config: {config_path}")
        return

    # Load config file
    file_config = {}
    if not args.no_config:
        config_path = args.config if args.config else None
        file_config = load_config_file(config_path if config_path else None)
        
        if file_config and verbose:
            found_path = find_config_file()
            print_status(f"Loaded config from: {found_path}", "INFO", verbose)

    # Build CLI args dict
    cli_args = {
        "provider": args.provider,
        "base_url": args.base_url,
        "model": args.model,
        "api_key": args.api_key,
        "prompt_type": args.prompt_type,
        "chunk_size": args.chunk_size,
        "parallel_api_calls": args.parallel_calls,
        "max_output_tokens": args.max_tokens,
        "language": args.language,
        "transcription_method": args.transcription,
        "output_dir": args.output_dir,
    }

    # Merge configs
    merged = merge_configs(file_config, cli_args)

    # Validate required fields
    if not merged.get("base_url") or not merged.get("model"):
        if args.provider:
            print_status(f"Provider '{args.provider}' not found in config file", "ERROR", True)
        else:
            print_status("--base-url and --model are required (or use --provider with config file)", "ERROR", True)
        sys.exit(1)

    if not args.source:
        print_status("--source is required", "ERROR", True)
        sys.exit(1)

    if verbose:
        print_status("Video Summarizer CLI Started", "PROCESSING", verbose)
        print_status(f"Output directory: {merged.get('output_dir')}", "INFO", verbose)
        print_status(f"Model: {merged.get('model')}", "INFO", verbose)
        print_status(f"Prompt type: {merged.get('prompt_type')}", "INFO", verbose)
        print_status(f"Output format: {args.output_format}", "INFO", verbose)

    # Smart caption logic
    transcription_was_provided = any('--transcription' in arg for arg in sys.argv)
    explicit_transcription = transcription_was_provided and args.transcription in ["Cloud Whisper", "Local Whisper"]
    smart_force_download = args.force_download or explicit_transcription

    if verbose and explicit_transcription and not args.force_download:
        print_status(f"Auto-enabling audio download for {args.transcription} testing", "INFO", verbose)

    # Build final config
    base_config = {
        "type_of_source": args.type,
        "use_youtube_captions": not smart_force_download,
        "transcription_method": merged.get("transcription_method"),
        "language": merged.get("language"),
        "prompt_type": merged.get("prompt_type"),
        "chunk_size": merged.get("chunk_size"),
        "parallel_api_calls": merged.get("parallel_api_calls"),
        "max_output_tokens": merged.get("max_output_tokens"),
        "base_url": merged.get("base_url"),
        "model": merged.get("model"),
        "verbose": verbose
    }

    if merged.get("api_key"):
        base_config["api_key"] = merged["api_key"]

    # Process each URL
    success_count = 0
    for i, source in enumerate(args.source, 1):
        if verbose:
            print_status(f"[{i}/{len(args.source)}] Processing source", "PROCESSING", verbose)
        if process_url(source, base_config, merged.get("output_dir", "summaries"), 
                      verbose, args.output_format, args.no_save):
            success_count += 1

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