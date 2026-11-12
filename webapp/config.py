"""YAML config loading, saving, and normalization helpers.

Public surface:
    CONFIG_PATH, MIN_CHUNK_SIZE, MAX_CHUNK_SIZE
    normalize_config_section, coerce_int
    load_config, get_cobalt_url
    load_config_raw, save_config_raw
"""

import os
import re
from pathlib import Path

import yaml

from summarizer.runtime_env import fill_env_defaults, normalize_explicit_keys

CONFIG_PATH = Path.cwd() / "summarizer.yaml"
MIN_CHUNK_SIZE = 20
MAX_CHUNK_SIZE = 1000000


def normalize_config_section(section):
    """Normalize YAML keys so kebab-case and snake_case behave the same."""
    if not isinstance(section, dict):
        return {}

    aliases = {
        "parallel_calls": "parallel_api_calls",
        "max_tokens": "max_output_tokens",
        "cobalt_url": "cobalt_base_url",
    }

    normalized = {}
    for key, value in section.items():
        normalized_key = str(key).replace("-", "_")
        normalized[aliases.get(normalized_key, normalized_key)] = value
    return normalized


def coerce_int(value, fallback, minimum=None, maximum=None):
    """Convert a value to int with optional bounds."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(fallback)

    if minimum is not None and result < minimum:
        result = minimum
    if maximum is not None and result > maximum:
        result = maximum
    return result


def _get_config_path():
    """Return the active config path."""
    return CONFIG_PATH


def load_config():
    """Load config from YAML.

    Returns ``(providers, default_provider, defaults)`` where ``defaults``
    is a normalized dict with snake_case keys.
    """
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            raw_defaults = config.get("defaults", {}) or {}
            defaults = fill_env_defaults(
                normalize_config_section(raw_defaults),
                normalize_explicit_keys(raw_defaults.keys()),
            )
            providers = {
                name: normalize_config_section(provider_cfg)
                for name, provider_cfg in (config.get("providers", {}) or {}).items()
            }
            return (
                providers,
                config.get("default_provider", ""),
                defaults,
            )
    return (
        {
            "gemini": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "gemini-3.5-flash-lite",
            }
        },
        "gemini",
        fill_env_defaults({}, set()),
    )


def get_cobalt_url():
    """Resolve Cobalt URL. Environment variable wins, then YAML, then default."""
    env_url = os.environ.get("COBALT_BASE_URL")
    if env_url:
        return env_url
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            defaults = normalize_config_section(config.get("defaults", {}))
            url = defaults.get("cobalt_base_url")
            if url:
                return url
    return "http://localhost:9000"


def load_config_raw():
    path = _get_config_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def save_config_raw(content: str):
    """Save config to the config path."""
    try:
        CONFIG_PATH.write_text(content, encoding="utf-8")
    except OSError as e:
        raise OSError(f"Cannot save config {CONFIG_PATH}: {e}")


def save_defaults(updates):
    """Set simple keys in the ``defaults:`` block of summarizer.yaml, keeping its comments.

    Deliberate line surgery instead of a YAML round-trip so user comments
    survive. It only handles flat scalar values inside ``defaults:`` (all it
    is used for); the result is re-parsed and verified before anything is
    written, so a bad match raises instead of corrupting the file.

    Returns False when there is no config file to update.
    """
    # Without a config file the app runs on built-in providers; writing one would hide them.
    if not CONFIG_PATH.exists():
        return False

    lines = load_config_raw().splitlines()
    start = next((i for i, line in enumerate(lines) if line.split("#")[0].rstrip() == "defaults:"), None)
    if start is None:
        lines.append("defaults:")
        start = len(lines) - 1
    end = start + 1  # just after the last indented line of the block
    for i in range(start + 1, len(lines)):
        if lines[i][:1].isspace() and lines[i].strip():
            end = i + 1
        elif lines[i].strip() and not lines[i].startswith("#"):
            break

    for key, value in updates.items():
        pattern = re.compile(rf"^(\s+{key.replace('_', '[-_]')}\s*:\s*)[^#]*?(\s+#.*)?$")
        row = next((i for i in range(start + 1, end) if pattern.match(lines[i])), None)
        if row is None:
            lines.insert(end, f"  {key.replace('_', '-')}: {value}")
            end += 1
        else:
            match = pattern.match(lines[row])
            lines[row] = f"{match.group(1)}{value}{match.group(2) or ''}"

    content = "\n".join(lines) + "\n"
    saved = normalize_config_section((yaml.safe_load(content) or {}).get("defaults"))
    if any(saved.get(key) != value for key, value in updates.items()):
        raise ValueError(f"Could not update the defaults block in {CONFIG_PATH}")
    save_config_raw(content)
    return True
