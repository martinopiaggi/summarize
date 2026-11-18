"""Build pipeline configs for the bot through the shared merge path.

Layers, later wins: built-in defaults < summarizer.yaml < chat settings <
per-job overrides (e.g. "Restyle"). Same functions as the CLI and HTTP API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..api_utils import build_runtime_config
from ..config_file import load_config_file, merge_configs
from ..exceptions import ConfigurationError
from ..prompts import get_available_prompts


def load_file_config(path: Path) -> Dict[str, Any]:
    return load_config_file(Path(path)) or {}


def providers_of(file_config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    providers = file_config.get("providers") or {}
    return providers if isinstance(providers, dict) else {}


def chat_overrides(
    file_config: Dict[str, Any], chat: Dict[str, Any], extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Chat settings as merge_configs overrides, skipping stale values.

    A provider or style removed from summarizer.yaml after a chat picked it
    silently falls back to the default instead of breaking every job.
    """
    overrides: Dict[str, Any] = {}
    if chat.get("provider") in providers_of(file_config):
        overrides["provider"] = chat["provider"]
    if chat.get("prompt_type") in get_available_prompts():
        overrides["prompt_type"] = chat["prompt_type"]
    for key in ("output_language", "language"):
        if chat.get(key):
            overrides[key] = chat[key]
    if chat.get("visual") is not None:
        overrides["visual"] = bool(chat["visual"])
    overrides.update(extra or {})
    return overrides


def effective_config(
    file_config: Dict[str, Any], chat: Dict[str, Any], extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """The merged settings the next job in this chat would use."""
    return merge_configs(file_config, chat_overrides(file_config, chat, extra))


def build_job_config(
    file_config: Dict[str, Any],
    chat: Dict[str, Any],
    source: str,
    source_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return ``(runtime_config, merged)`` for one job."""
    merged = effective_config(file_config, chat, extra)
    if not merged.get("base_url") or not merged.get("model"):
        raise ConfigurationError(
            "No LLM provider is configured. Add providers and default_provider to "
            "summarizer.yaml (an admin can send the file to the bot)."
        )
    config = build_runtime_config(
        merged=merged,
        source=source,
        type_of_source=source_type,
        verbose=False,
        force_download=bool(chat.get("force_download")),
    )
    return config, merged
