"""Config file support for the summarizer package."""

import json
import os
import re
from pathlib import Path
from typing import Dict, Optional, Any
from .exceptions import ConfigurationError
from .runtime_env import fill_env_defaults, normalize_config_key, normalize_explicit_keys


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
        # kebab-case and aliases (parallel-calls, max-tokens, cobalt-url) → code names
        snake_key = normalize_config_key(key)
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
                    snake_key = normalize_config_key(key)
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

    from .jev import JEV_DEFAULTS, resolve_provider

    for key, value in JEV_DEFAULTS.items():
        merged.setdefault(key, value)
    merged["jev_provider_config"] = resolve_provider(merged, file_config.get("providers", {}))
    return merged


def format_yaml_scalar(value: Any) -> str:
    """Render a scalar for a ``key: value`` line so it reads back unchanged."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    import yaml

    text = str(value)
    try:
        if text and yaml.safe_load(f"key: {text}") == {"key": text}:
            return text
    except yaml.YAMLError:
        pass
    # A JSON string is a valid double-quoted YAML scalar.
    return json.dumps(text, ensure_ascii=False)


def update_config_file(
    path: Path, updates: Dict[str, Any], section: Optional[str] = "defaults"
) -> None:
    """Set flat scalar keys in summarizer.yaml without losing its comments.

    ``section`` names a top-level block (``defaults``); ``None`` edits top-level
    keys such as ``default_provider``. Deliberate line surgery instead of a YAML
    round-trip so user comments survive. The result is re-parsed and verified
    before anything is written, so a bad match raises instead of corrupting the
    file. The file is rewritten in place, which keeps Docker bind mounts working.
    """
    import yaml

    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    if section is None:
        start, end, indent = -1, len(lines), ""
    else:
        start = next(
            (i for i, line in enumerate(lines) if line.split("#")[0].rstrip() == f"{section}:"),
            None,
        )
        if start is None:
            lines.append(f"{section}:")
            start = len(lines) - 1
        end = start + 1  # just after the last indented line of the block
        for i in range(start + 1, len(lines)):
            if lines[i][:1].isspace() and lines[i].strip():
                end = i + 1
            elif lines[i].strip() and not lines[i].startswith("#"):
                break
        indent = "  "

    for key, value in updates.items():
        key_pattern = re.escape(key).replace("_", "[-_]").replace("\\-", "[-_]")
        leading = r"\s+" if section is not None else ""
        pattern = re.compile(rf"^({leading}{key_pattern}\s*:\s*)[^#]*?(\s+#.*)?$")
        rendered = format_yaml_scalar(value)
        row = next((i for i in range(start + 1, end) if pattern.match(lines[i])), None)
        if row is not None:
            match = pattern.match(lines[row])
            prefix = match.group(1)
            if not prefix[-1:].isspace():  # "key:" with no value yet
                prefix += " "
            lines[row] = f"{prefix}{rendered}{match.group(2) or ''}"
            continue
        new_line = f"{indent}{key.replace('_', '-') if section is not None else key}: {rendered}"
        if section is not None:
            lines.insert(end, new_line)
            end += 1
        else:
            # New top-level keys go above the first mapping key (after header comments).
            first = next(
                (i for i, line in enumerate(lines) if line.strip() and not line.startswith("#")),
                len(lines),
            )
            lines.insert(first, new_line)
            end += 1

    content = "\n".join(lines) + "\n"
    try:
        loaded = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Could not update {path}: {exc}") from exc
    block = loaded if section is None else (loaded.get(section) or {})
    saved = {normalize_config_key(k): v for k, v in block.items()} if isinstance(block, dict) else {}
    if any(saved.get(normalize_config_key(k)) != v for k, v in updates.items()):
        raise ConfigurationError(f"Could not update the {section or 'top-level'} keys in {path}")
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(f"Cannot save config {path}: {exc}") from exc


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
    model: gemini-3.5-flash-lite

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
