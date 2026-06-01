"""Config file support for the summarizer package."""

import os
from pathlib import Path
from typing import Dict, Optional, Any
from .exceptions import ConfigurationError


def find_config_file() -> Optional[Path]:
    """
    Find the default config file.

    Returns:
        Path to config file or None if not found
    """
    path = Path.cwd() / "summarizer.yaml"
    if path.exists():
        return path
    return None


def load_config_file(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        path: Optional explicit path to config file

    Returns:
        Configuration dictionary
    """
    if path is None:
        path = find_config_file()

    if path is None:
        return {}

    try:
        import yaml
    except ImportError:
        # YAML is optional - fail silently if not installed
        return {}

    # If an explicit path is provided but doesn't exist, return empty dict
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            config = loaded if loaded is not None else {}
        return config
    except Exception as e:
        raise ConfigurationError(f"Failed to load config file {path}: {str(e)}")


def get_provider_config(config: Dict, provider_name: str) -> Dict[str, Any]:
    """
    Get configuration for a specific provider.

    Args:
        config: Full config dictionary
        provider_name: Name of the provider (e.g., 'groq', 'gemini')

    Returns:
        Provider-specific config dictionary
    """
    providers = config.get("providers", {})

    if provider_name not in providers:
        available = list(providers.keys())
        if available:
            raise ConfigurationError(
                f"Unknown provider: '{provider_name}'. "
                f"Available: {', '.join(available)}"
            )
        else:
            raise ConfigurationError(
                f"No providers configured. Add providers to your config file."
            )

    return providers[provider_name]


def merge_configs(file_config: Dict, cli_args: Dict) -> Dict:
    """
    Merge file config with CLI arguments.
    CLI arguments take precedence.

    Args:
        file_config: Configuration from file
        cli_args: Configuration from CLI arguments

    Returns:
        Merged configuration dictionary
    """
    # Start with defaults
    merged = {
        "chunk_size": 10000,
        "parallel_api_calls": 30,
        "max_output_tokens": 4096,
        "prompt_type": "Questions and answers",
        "language": "auto",
        "output_language": "auto",
        "transcription_method": "Cloud Whisper",
        "audio_speed": 1.0,
        "output_dir": "summaries",
        "cobalt_base_url": os.getenv("COBALT_BASE_URL", "http://localhost:9000"),
        "cache_transcript": True,
        "visual": False,
        "visual_compression": "off",
        "visual_max_size_mb": None,
        "visual_max_duration_seconds": None,
        "visual_chunk_seconds": "auto",
        "visual_chunk_overlap_seconds": 0,
        "visual_synthesis": False,
    }

    # Apply file config defaults
    defaults = file_config.get("defaults", {})
    for key, value in defaults.items():
        # Convert kebab-case to snake_case
        snake_key = key.replace("-", "_")
        if snake_key == "cobalt_url":
            snake_key = "cobalt_base_url"
        merged[snake_key] = value

    # Apply provider config if specified
    provider_name = cli_args.get("provider") or file_config.get("default_provider")
    if provider_name:
        try:
            provider_config = get_provider_config(file_config, provider_name)
            merged["base_url"] = provider_config.get("base_url")
            merged["model"] = provider_config.get("model")
            # Provider-specific defaults
            for key, value in provider_config.items():
                if key not in ("base_url", "model"):
                    merged[key.replace("-", "_")] = value
        except ConfigurationError:
            pass  # Will be caught later if required

    # CLI args override everything (skip None values)
    for key, value in cli_args.items():
        if value is not None:
            merged[key] = value

    return merged


def create_example_config() -> str:
    """
    Generate example config file content.

    Returns:
        YAML string with example configuration
    """
    return """# Summarizer Configuration
# Save as ./summarizer.yaml

# Default provider to use when --provider is not specified
default_provider: groq

# Provider configurations
providers:
  groq:
    base_url: https://api.groq.com/openai/v1
    model: llama-3.3-70b-versatile
  
  gemini:
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    model: gemini-2.5-flash-lite
  
  deepseek:
    base_url: https://api.deepseek.com/v1
    model: deepseek-chat
  
  openai:
    base_url: https://api.openai.com/v1
    model: gpt-5.5

  nvidia:
    base_url: https://integrate.api.nvidia.com/v1
    model: nvidia/nemotron-3-nano-omni-30b-a3b-reasoning

  openrouter:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-2.5-flash

  # URL mode example: sends YouTube URLs directly without downloading
  openrouter-youtube:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-2.5-flash
    visual-input-mode: url

  perplexity:
    base_url: https://openrouter.ai/api/v1
    model: perplexity/sonar
    chunk-size: 128000

  # LiteLLM: access 100+ providers via a single interface
  # pip install 'summarizer[litellm]'
  # See https://docs.litellm.ai/docs/providers for the full list
  litellm-anthropic:
    base_url: litellm
    model: anthropic/claude-sonnet-4-6
  litellm-groq:
    base_url: litellm
    model: groq/llama-3.3-70b-versatile

# Default settings (can be overridden by CLI)
defaults:
  prompt-type: Questions and answers
  chunk-size: 10000
  parallel-calls: 30
  max-tokens: 4096
  output-language: auto
  audio-speed: 1.0
  use-proxy: false
  output-dir: summaries
  keep-history: false
  cobalt-base-url: http://localhost:9000
  cache-transcript: true
  visual: false
  visual-compression: off
  visual-chunk-seconds: auto
  visual-chunk-overlap-seconds: 0
  visual-synthesis: false
  # visual-max-size-mb: 100
  # visual-max-duration-seconds: 120
"""
