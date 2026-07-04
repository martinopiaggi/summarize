"""Config file support for the summarizer package."""

import os
from pathlib import Path
from typing import Dict, Optional, Any
from .exceptions import ConfigurationError
from .runtime_env import fill_env_defaults, normalize_explicit_keys


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


def _reject_legacy_audio_speed_key(snake_key: str) -> None:
    if snake_key == "audio_speed":
        raise ConfigurationError(
            "audio-speed / audio_speed is no longer supported; use speed instead."
        )


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
        "speed": 1.0,
        "output_dir": "summaries",
        "cobalt_base_url": os.getenv("COBALT_BASE_URL", "http://localhost:9000"),
        "cache_transcript": True,
        "cache_transcript_persist": False,
        "visual": False,
        "visual_compression": "off",
        "visual_max_size_mb": None,
        "visual_max_duration_seconds": None,
        "visual_chunk_seconds": "auto",
        "visual_chunk_overlap_seconds": 0,
    }

    # Apply file config defaults
    raw_defaults = file_config.get("defaults", {}) or {}
    explicit_keys = normalize_explicit_keys(raw_defaults.keys())
    defaults = raw_defaults
    for key, value in defaults.items():
        # Convert kebab-case to snake_case
        snake_key = key.replace("-", "_")
        if snake_key == "cobalt_url":
            snake_key = "cobalt_base_url"
        _reject_legacy_audio_speed_key(snake_key)
        merged[snake_key] = value

    # Apply provider config if specified
    provider_name = cli_args.get("provider") or file_config.get("default_provider")
    explicit_provider = bool(cli_args.get("provider"))
    if provider_name:
        try:
            provider_config = get_provider_config(file_config, provider_name)
        except ConfigurationError:
            if explicit_provider:
                # Explicit --provider or provider= in API must succeed
                raise
            # Implicit default_provider only: swallow so legacy flows don't hard-fail
            pass
        else:
            merged["base_url"] = provider_config.get("base_url")
            merged["model"] = provider_config.get("model")
            # Provider-specific defaults
            for key, value in provider_config.items():
                if key not in ("base_url", "model"):
                    snake_key = key.replace("-", "_")
                    _reject_legacy_audio_speed_key(snake_key)
                    merged[snake_key] = value

    # CLI args override everything (skip None values)
    for key, value in cli_args.items():
        if value is not None:
            _reject_legacy_audio_speed_key(key)
            merged[key] = value

    for key, value in fill_env_defaults({}, explicit_keys).items():
        if key not in explicit_keys:
            merged[key] = value

    return merged


def create_example_config() -> str:
    """
    Generate example config file content.

    Returns:
        YAML string with example configuration
    """
    example_path = Path(__file__).resolve().parent.parent / "summarizer.example.yaml"
    if example_path.exists():
        return example_path.read_text(encoding="utf-8")
    return """# Summarizer Configuration
# Copy to ./summarizer.yaml or run: python -m summarizer --init-config

default_provider: groq

providers:
  groq:
    base_url: https://api.groq.com/openai/v1
    model: openai/gpt-oss-120b

  gemini:
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    model: gemini-3.1-flash-lite

  deepseek:
    base_url: https://api.deepseek.com/v1
    model: deepseek-v4-flash

  openai:
    base_url: https://api.openai.com/v1
    model: gpt-5.5

  nvidia:
    base_url: https://integrate.api.nvidia.com/v1
    model: nvidia/nemotron-3-nano-omni-30b-a3b-reasoning

defaults:
  prompt-type: Questions and answers
  chunk-size: 120000
  parallel-calls: 10
  max-tokens: 4096
  output-language: auto
  speed: 1.0
  use-proxy: false
  output-dir: summaries
  keep-history: false
  cobalt-base-url: http://localhost:9000
  cache-transcript: true
"""
