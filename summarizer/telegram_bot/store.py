"""Per-chat preferences, persisted as a small JSON file.

Only values a chat changed are stored; everything else falls back to
summarizer.yaml, so editing the YAML still changes every chat's defaults.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

CHAT_SETTING_KEYS = (
    "provider",
    "prompt_type",
    "output_language",
    "language",
    "visual",
    "force_download",
    "attach_markdown",
)


class ChatSettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._chats: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            logger.warning("Ignoring unreadable chat settings %s: %s", self.path, exc)
            return {}
        chats = raw.get("chats") if isinstance(raw, dict) else None
        if not isinstance(chats, dict):
            return {}
        return {
            str(chat_id): {k: v for k, v in values.items() if k in CHAT_SETTING_KEYS}
            for chat_id, values in chats.items()
            if isinstance(values, dict)
        }

    def get(self, chat_id: int) -> Dict[str, Any]:
        with self._lock:
            return dict(self._chats.get(str(chat_id), {}))

    def update(self, chat_id: int, **changes: Any) -> Dict[str, Any]:
        """Set values for a chat; ``None`` restores the summarizer.yaml default."""
        unknown = set(changes) - set(CHAT_SETTING_KEYS)
        if unknown:
            raise KeyError(f"Unknown chat setting: {', '.join(sorted(unknown))}")
        with self._lock:
            settings = dict(self._chats.get(str(chat_id), {}))
            for key, value in changes.items():
                if value is None:
                    settings.pop(key, None)
                else:
                    settings[key] = value
            if settings:
                self._chats[str(chat_id)] = settings
            else:
                self._chats.pop(str(chat_id), None)
            self._save()
            return dict(settings)

    def reset(self, chat_id: int) -> None:
        with self._lock:
            if self._chats.pop(str(chat_id), None) is not None:
                self._save()

    def _save(self) -> None:
        """Write atomically; on failure keep the settings in memory and log."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(
                json.dumps({"version": 1, "chats": self._chats}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning("Could not save chat settings to %s: %s", self.path, exc)
