"""Environment-driven defaults for Docker and headless deployments."""

import os
from typing import Any, Dict, Iterable, Set

_TRUTHY = frozenset({"1", "true", "yes", "on"})

_CONFIG_KEY_ALIASES = {
    "parallel_calls": "parallel_api_calls",
    "max_tokens": "max_output_tokens",
    "cobalt_url": "cobalt_base_url",
}


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def normalize_explicit_keys(keys: Iterable[str]) -> Set[str]:
    """Normalize YAML default keys to snake_case names used in code."""
    explicit: Set[str] = set()
    for key in keys:
        normalized = str(key).replace("-", "_")
        explicit.add(_CONFIG_KEY_ALIASES.get(normalized, normalized))
    return explicit


def fill_env_defaults(defaults: Dict[str, Any], explicit_keys: Set[str]) -> Dict[str, Any]:
    """Apply env overrides only for settings not explicitly set in YAML."""
    result = dict(defaults)

    if "keep_history" not in explicit_keys and _env_truthy("SUMMARIZER_KEEP_HISTORY"):
        result["keep_history"] = True

    if "cache_transcript_persist" not in explicit_keys and _env_truthy(
        "SUMMARIZER_CACHE_PERSIST"
    ):
        result["cache_transcript_persist"] = True

    if "cache_transcript_dir" not in explicit_keys:
        cache_dir = os.environ.get("SUMMARIZER_CACHE_DIR", "").strip()
        if cache_dir:
            result["cache_transcript_dir"] = cache_dir

    return result