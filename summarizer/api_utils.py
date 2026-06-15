"""Shared utilities for CLI and HTTP API.

This module contains config building and output formatting logic used by both
the command-line interface and the FastAPI server, ensuring they stay in sync.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from summarizer.config_file import merge_configs


# ──────────────────────────────────────────────────────────────────────────────
# Validation constants
# ──────────────────────────────────────────────────────────────────────────────

SOURCE_TYPES: List[str] = [
    "YouTube Video",
    "Video URL",
    "Google Drive Video Link",
    "Dropbox Video Link",
    "Local File",
    "TXT",
]

OUTPUT_FORMATS: List[str] = ["markdown", "json", "html"]

TRANSCRIPTION_METHODS: List[str] = ["Cloud Whisper", "Local Whisper"]

WHISPER_MODELS: List[str] = ["tiny", "base", "small", "medium", "large"]

DEFAULT_MAX_UPLOAD_MB: int = 500


# ──────────────────────────────────────────────────────────────────────────────
# Output formatting
# ──────────────────────────────────────────────────────────────────────────────

def format_output(summary: str, source: str, format_type: str, metadata: dict) -> str:
    """Format summary in the requested output format.

    Args:
        summary: The summary text
        source: Source URL or filename
        format_type: 'markdown', 'json', or 'html'
        metadata: Additional metadata dict with keys like prompt_type, model

    Returns:
        Formatted output string
    """
    if format_type == "json":
        output = {
            "source": source,
            "generated_at": datetime.now().isoformat(),
            "prompt_type": metadata.get("prompt_type", ""),
            "model": metadata.get("model", ""),
            "summary": summary,
        }
        return json.dumps(output, indent=2, ensure_ascii=False)

    elif format_type == "html":
        escaped_summary = (
            summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
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
    <title>Summary: {source}</title>
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
        <strong>Source:</strong> <a href="{source}">{source}</a><br>
        <strong>Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    </div>
    {body}
</body>
</html>"""

    else:  # markdown (default)
        return f"""# Summary for: {source}

Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{summary}"""


def get_file_extension(format_type: str) -> str:
    """Get file extension for output format."""
    extensions = {"markdown": ".md", "json": ".json", "html": ".html"}
    return extensions.get(format_type, ".md")


# ──────────────────────────────────────────────────────────────────────────────
# Runtime config building
# ──────────────────────────────────────────────────────────────────────────────

def build_runtime_config(
    merged: Dict[str, Any],
    source: str,
    type_of_source: str,
    verbose: bool = False,
    force_download: bool = False,
) -> Dict[str, Any]:
    """Build the final runtime config dict passed to core.main().

    Args:
        merged: The merged config from merge_configs(file_config, overrides)
        source: URL or file path to process
        type_of_source: Source type string
        verbose: Enable verbose output
        force_download: Force audio download instead of captions

    Returns:
        Runtime configuration dictionary
    """
    config: Dict[str, Any] = {
        "source_url_or_path": source,
        "type_of_source": type_of_source,
        "use_youtube_captions": not force_download and type_of_source == "YouTube Video",
        "transcription_method": merged.get("transcription_method", "Cloud Whisper"),
        "whisper_model": merged.get("whisper_model", "tiny"),
        "audio_speed": merged.get("audio_speed", 1.0),
        "use_proxy": bool(merged.get("use_proxy", False)),
        "language": merged.get("language", "auto"),
        "output_language": merged.get("output_language", "auto"),
        "prompt_type": merged.get("prompt_type", "Questions and answers"),
        "chunk_size": merged.get("chunk_size", 10000),
        "parallel_api_calls": merged.get("parallel_api_calls", 30),
        "max_output_tokens": merged.get("max_output_tokens", 4096),
        "cobalt_base_url": merged.get("cobalt_base_url", "http://localhost:9000"),
        "base_url": merged.get("base_url"),
        "model": merged.get("model"),
        "verbose": verbose,
        "cache_transcript": bool(merged.get("cache_transcript", True)),
        "visual": bool(merged.get("visual", False)),
        "visual_input_mode": merged.get("visual_input_mode"),
        "visual_compression": merged.get("visual_compression", "off"),
        "visual_max_size_mb": merged.get("visual_max_size_mb"),
        "visual_max_duration_seconds": merged.get("visual_max_duration_seconds"),
        "visual_chunk_seconds": merged.get("visual_chunk_seconds", "auto"),
        "visual_chunk_overlap_seconds": merged.get("visual_chunk_overlap_seconds", 0),
    }

    if merged.get("api_key"):
        config["api_key"] = merged["api_key"]

    return config


# ──────────────────────────────────────────────────────────────────────────────
# Config redaction helpers
# ──────────────────────────────────────────────────────────────────────────────

def redact_provider_config(provider_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of provider config with sensitive keys redacted."""
    redacted = dict(provider_cfg)
    if "api_key" in redacted:
        redacted["api_key"] = "***REDACTED***"
    return redacted


def redact_config_response(file_config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of file config with all provider api_keys redacted."""
    result: Dict[str, Any] = {}
    for key, value in file_config.items():
        if key == "providers" and isinstance(value, dict):
            result[key] = {
                name: redact_provider_config(cfg)
                for name, cfg in value.items()
            }
        else:
            result[key] = value
    return result
