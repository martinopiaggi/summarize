"""Change summarizer.yaml from Telegram: /set, uploaded files, redacted downloads.

Editing the YAML is an admin-only action: a provider ``base_url`` decides which
API key from .env is sent where, so whoever edits it controls your keys.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from ..api_utils import TRANSCRIPTION_METHODS, WHISPER_MODELS
from ..config_file import merge_configs, update_config_file
from ..exceptions import ConfigurationError, SummarizerError
from ..prompts import get_available_prompts
from ..sidecars import SIDECAR_CHOICES, SIDECAR_ORDERS

REDACTED = "***REDACTED***"
MAX_CONFIG_BYTES = 256 * 1024
_API_KEY_NAME = re.compile(r"api[-_]?key$", re.IGNORECASE)
# "api_key: value" wherever it is written: on its own line, in a {flow: mapping},
# under a "quoted" key, in a list item or in a commented-out line.
_API_KEY_PAIR = re.compile(
    r"""(api[-_]?key["']?[ \t]*:[ \t]*)(?![ \t]*(?:\#|$))"""
    r"""("(?:[^"\\\n]|\\.)*"|'[^'\n]*'|[^\s,}\]\#]+)""",
    re.IGNORECASE | re.MULTILINE,
)
# Shorter values are left to the pattern above: replacing them everywhere would garble the file.
_MIN_SECRET_CHARS = 8


@dataclass(frozen=True)
class Setting:
    key: str  # YAML key under defaults:, or the top-level "default_provider"
    kind: str  # str, text, int, float, bool, choice, provider, style, url
    help: str
    choices: Tuple[str, ...] = ()
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    @property
    def top_level(self) -> bool:
        return self.key == "default_provider"


SETTINGS: Dict[str, Setting] = {
    setting.key: setting
    for setting in (
        Setting("default_provider", "provider", "provider used unless a chat picks another"),
        Setting("prompt-type", "style", "default summary style"),
        Setting("output-language", "str", "auto, or a language name such as Italian"),
        Setting("language", "str", "caption/transcription language code, or auto"),
        Setting("chunk-size", "int", "characters per chunk", minimum=500, maximum=1_000_000),
        Setting("parallel-calls", "int", "concurrent LLM requests", minimum=1, maximum=100),
        Setting("max-tokens", "int", "max output tokens per chunk", minimum=1, maximum=1_000_000),
        Setting("speed", "float", "playback speed before transcription", minimum=0.01, maximum=10),
        Setting("transcription-method", "choice", "Cloud Whisper or Local Whisper", tuple(TRANSCRIPTION_METHODS)),
        Setting("whisper-model", "choice", "local Whisper model size", tuple(WHISPER_MODELS)),
        Setting("visual", "bool", "send video to a video-capable model"),
        Setting("use-proxy", "bool", "route requests through PROXY_URL"),
        Setting("keep-history", "bool", "also save summaries to output-dir"),
        Setting("output-dir", "str", "folder for saved summaries"),
        Setting("cache-transcript", "bool", "reuse transcripts in memory"),
        Setting("cache-transcript-persist", "bool", "also keep transcripts on disk"),
        Setting("cobalt-base-url", "url", "Cobalt download fallback URL"),
        Setting("sidecar", "choice", "external transcript service", tuple(SIDECAR_CHOICES)),
        Setting("sidecar-order", "choice", "fallback or first", tuple(SIDECAR_ORDERS)),
        Setting("use-jev-prefiltering", "bool", "select passages before summarizing"),
        Setting("jev-provider", "provider", "provider used for JEV scoring"),
        Setting("jev-include", "text", "keep only passages about this"),
        Setting("jev-exclude", "text", "drop passages about this"),
    )
}

_ALIASES = {
    "provider": "default_provider",
    "default-provider": "default_provider",
    "style": "prompt-type",
    "prompt": "prompt-type",
    "parallel-api-calls": "parallel-calls",
    "max-output-tokens": "max-tokens",
    "cobalt-url": "cobalt-base-url",
    "transcription": "transcription-method",
}

_TRUE = {"true", "yes", "on", "1", "enable", "enabled"}
_FALSE = {"false", "no", "off", "0", "disable", "disabled"}


def resolve_setting(name: str) -> Setting:
    key = name.strip().lower().replace("_", "-")
    key = _ALIASES.get(key, key)
    if key not in SETTINGS:
        raise ConfigurationError(f"Unknown setting {name!r}. Send /set to see the list.")
    return SETTINGS[key]


def match_choice(raw: str, choices, what: str) -> str:
    """Case-insensitive exact, then unique prefix/substring match."""
    value = raw.strip().strip("\"'")
    lowered = value.lower()
    for choice in choices:
        if choice.lower() == lowered:
            return choice
    ambiguous = []
    for test in (str.startswith, str.__contains__):
        matches = [choice for choice in choices if test(choice.lower(), lowered)]
        if len(matches) == 1:
            return matches[0]
        ambiguous = ambiguous or matches
    if value and ambiguous:
        raise ConfigurationError(f"{value!r} matches several: {', '.join(ambiguous)}")
    raise ConfigurationError(f"Unknown {what} {value!r}. Options: {', '.join(choices)}")


def parse_value(setting: Setting, raw: str, file_config: Dict[str, Any]) -> Any:
    """Validate the text after /set <key> and convert it to the YAML value."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if not value and setting.kind not in ("text",):
        raise ConfigurationError(f"Missing value for {setting.key}")

    if setting.kind in ("int", "float"):
        try:
            number = int(value) if setting.kind == "int" else float(value)
        except ValueError:
            raise ConfigurationError(f"{setting.key} must be a number") from None
        if setting.minimum is not None and number < setting.minimum:
            raise ConfigurationError(f"{setting.key} must be at least {setting.minimum:g}")
        if setting.maximum is not None and number > setting.maximum:
            raise ConfigurationError(f"{setting.key} must be at most {setting.maximum:g}")
        return number
    if setting.kind == "bool":
        if value.lower() in _TRUE:
            return True
        if value.lower() in _FALSE:
            return False
        raise ConfigurationError(f"{setting.key} must be true or false")
    if setting.kind == "choice":
        return match_choice(value, setting.choices, setting.key)
    if setting.kind == "style":
        return match_choice(value, get_available_prompts(), "style")
    if setting.kind == "provider":
        providers = list((file_config.get("providers") or {}).keys())
        if not providers:
            raise ConfigurationError("summarizer.yaml has no providers yet")
        return match_choice(value, providers, "provider")
    if setting.kind == "url":
        if not re.match(r"^https?://\S+$", value):
            raise ConfigurationError(f"{setting.key} must be an http(s) URL")
        return value
    if setting.kind == "text" and len(value) > 2000:
        raise ConfigurationError(f"{setting.key} must be at most 2000 characters")
    return value


def apply_setting(path: Path, setting: Setting, value: Any) -> None:
    if not Path(path).exists():
        raise ConfigurationError(
            f"No summarizer.yaml at {path}. Send one to the bot, or run summarizer --init-config."
        )
    update_config_file(path, {setting.key: value}, section=None if setting.top_level else "defaults")


def redact_config_text(text: str) -> str:
    """Hide api_key values before a config file leaves the machine.

    Two passes, so an unusual layout cannot leak a key: the values YAML itself
    reads under ``api_key`` are blanked wherever they appear, then every
    ``api_key: value`` pair in the text is (which also covers comments and a
    file that no longer parses).
    """
    try:
        secrets = sorted(_api_key_values(yaml.safe_load(text)), key=len, reverse=True)
    except yaml.YAMLError:
        secrets = []
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    return _API_KEY_PAIR.sub(lambda m: f'{m.group(1)}"{REDACTED}"', text)


def _api_key_values(node: Any) -> set:
    """Every value stored under an ``api_key`` key, at any depth."""
    found = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and _API_KEY_NAME.search(key) and not isinstance(value, (dict, list, bool)):
                secret = "" if value is None else str(value).strip()
                if len(secret) >= _MIN_SECRET_CHARS:
                    found.add(secret)
            else:
                found |= _api_key_values(value)
    elif isinstance(node, list):
        for item in node:
            found |= _api_key_values(item)
    return found


def validate_config_text(text: str) -> Dict[str, Any]:
    """Parse an uploaded summarizer.yaml and check it can actually run."""
    if len(text.encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ConfigurationError("The file is too large for a summarizer.yaml")
    if REDACTED in text:
        raise ConfigurationError(
            f"The file still contains {REDACTED} API keys. Keep keys in .env "
            "(recommended) or paste the real values."
        )
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML: {exc}") from None
    data = {} if data is None else data
    if not isinstance(data, dict):
        raise ConfigurationError("summarizer.yaml must be a mapping (key: value pairs)")

    providers = data.get("providers")
    if not isinstance(providers, dict) or not providers:
        raise ConfigurationError("summarizer.yaml needs a providers: section with at least one provider")
    for name, provider in providers.items():
        if not isinstance(provider, dict) or not provider.get("base_url") or not provider.get("model"):
            raise ConfigurationError(f"Provider {name!r} needs base_url and model")
    default_provider = data.get("default_provider")
    if default_provider and default_provider not in providers:
        raise ConfigurationError(f"default_provider {default_provider!r} is not in providers")
    if data.get("defaults") is not None and not isinstance(data.get("defaults"), dict):
        raise ConfigurationError("defaults: must be a mapping")
    try:
        merge_configs(data, {})
    except SummarizerError as exc:
        raise ConfigurationError(str(exc)) from None
    return data


def replace_config_file(path: Path, text: str) -> Optional[Path]:
    """Write a validated config, keeping the previous one as summarizer.yaml.bak.

    Rewritten in place (not renamed over) so Docker single-file bind mounts work.
    """
    path = Path(path)
    backup = None
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        # The file may hold API keys: the copy is never more readable than the original.
        backup.touch(mode=0o600, exist_ok=True)
        os.chmod(backup, 0o600)  # also tightens a backup left by an earlier run
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        shutil.copymode(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return backup
