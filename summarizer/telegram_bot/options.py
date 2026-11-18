"""Bot options from CLI flags and TELEGRAM_* environment variables, and access control."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

from ..exceptions import ConfigurationError
from .api import DEFAULT_API_URL

# The cloud Bot API lets bots download files up to 20 MB; a local
# telegram-bot-api server removes the limit.
CLOUD_MAX_FILE_MB = 20.0
LOCAL_MAX_FILE_MB = 2000.0


def default_work_dir() -> Path:
    """Scratch folder for downloads, one per OS user (a stable path keeps cache hits)."""
    suffix = f"-{os.getuid()}" if hasattr(os, "getuid") else ""  # Windows temp is per-user
    return Path(tempfile.gettempdir()) / f"summarize-telegram{suffix}"


def ensure_private_dir(path: Path) -> Path:
    """Create the work folder for this user only, and refuse one prepared by someone else.

    It holds the voice messages and videos people send, in a temp folder that
    other local users can usually write to: a folder or symlink they created
    there first would let them read those files or redirect what the bot writes.
    """
    path = Path(path)
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
        info = os.lstat(path)
        if not stat.S_ISDIR(info.st_mode):  # lstat: a symlink to a folder is refused too
            raise ConfigurationError(f"The work folder {path} is a link, not a folder. Remove it.")
        if hasattr(os, "getuid"):
            if info.st_uid != os.getuid():
                raise ConfigurationError(
                    f"The work folder {path} belongs to another user. Remove it, or set TMPDIR "
                    "to a folder of your own."
                )
            if stat.S_IMODE(info.st_mode) & 0o077:
                os.chmod(path, 0o700)
    except OSError as exc:
        raise ConfigurationError(f"Cannot prepare the work folder {path}: {exc}") from None
    return path


def parse_id_list(value: Optional[str], name: str) -> Tuple[int, ...]:
    """Parse "123, 456 -100789" into IDs, keeping order and dropping duplicates."""
    ids = []
    for item in re.split(r"[\s,;]+", value or ""):
        if not item:
            continue
        try:
            number = int(item)
        except ValueError:
            raise ConfigurationError(
                f"{name}: {item!r} is not a numeric Telegram ID. Send /id to the bot to see yours."
            ) from None
        if number not in ids:
            ids.append(number)
    return tuple(ids)


@dataclass(frozen=True)
class BotOptions:
    token: str
    config_path: Path
    state_file: Path
    allowed_users: Tuple[int, ...] = ()
    allowed_chats: Tuple[int, ...] = ()
    admin_users: Tuple[int, ...] = ()
    api_url: str = DEFAULT_API_URL
    max_file_mb: float = CLOUD_MAX_FILE_MB
    debug: bool = False  # log every update Telegram delivers
    work_dir: Path = field(default_factory=default_work_dir)

    @property
    def setup_mode(self) -> bool:
        """No one is allowed yet: the bot only tells people their user ID."""
        return not (self.allowed_users or self.allowed_chats or self.admin_users)

    @property
    def admins(self) -> Tuple[int, ...]:
        # Without an explicit admin list, the first allowed user owns the bot.
        if self.admin_users:
            return self.admin_users
        return self.allowed_users[:1]

    @property
    def max_file_bytes(self) -> int:
        return int(self.max_file_mb * 1024 * 1024)

    def is_admin(self, user_id: Optional[int]) -> bool:
        return user_id is not None and user_id in self.admins

    def is_allowed(self, user_id: Optional[int], chat_id: Optional[int]) -> bool:
        return (
            (user_id is not None and (user_id in self.allowed_users or user_id in self.admins))
            or (chat_id is not None and chat_id in self.allowed_chats)
        )

    @classmethod
    def from_args(
        cls,
        args: Any = None,
        env: Optional[Mapping[str, str]] = None,
        output_dir: str = "summaries",
    ) -> "BotOptions":
        """Build options; CLI flags win over environment variables."""
        env = os.environ if env is None else env

        def pick(attr: str, var: str) -> Optional[str]:
            value = getattr(args, attr, None) if args is not None else None
            if value is None or value == "":
                value = env.get(var)
            return value.strip() if isinstance(value, str) else value

        token = pick("token", "TELEGRAM_BOT_TOKEN")
        if not token:
            raise ConfigurationError(
                "Missing bot token. Create a bot with @BotFather and add "
                "TELEGRAM_BOT_TOKEN=... to .env (or pass --token)."
            )
        api_url = pick("api_url", "TELEGRAM_API_URL") or DEFAULT_API_URL
        max_file_mb = pick("max_file_mb", "TELEGRAM_MAX_FILE_MB")
        if max_file_mb in (None, ""):
            max_file_mb = CLOUD_MAX_FILE_MB if api_url.rstrip("/") == DEFAULT_API_URL else LOCAL_MAX_FILE_MB
        try:
            max_file_mb = float(max_file_mb)
        except (TypeError, ValueError):
            raise ConfigurationError("TELEGRAM_MAX_FILE_MB must be a number") from None

        # Same default as the CLI and the HTTP API: ./summarizer.yaml
        config_path = Path(getattr(args, "bot_config", None) or Path.cwd() / "summarizer.yaml")
        state_file = pick("state_file", "TELEGRAM_STATE_FILE")
        state_path = Path(state_file) if state_file else Path(output_dir) / ".telegram" / "chat_settings.json"

        return cls(
            token=token,
            config_path=config_path.expanduser().resolve(),
            state_file=state_path.expanduser().resolve(),
            allowed_users=parse_id_list(pick("allowed_users", "TELEGRAM_ALLOWED_USERS"), "TELEGRAM_ALLOWED_USERS"),
            allowed_chats=parse_id_list(pick("allowed_chats", "TELEGRAM_ALLOWED_CHATS"), "TELEGRAM_ALLOWED_CHATS"),
            admin_users=parse_id_list(pick("admin_users", "TELEGRAM_ADMIN_USERS"), "TELEGRAM_ADMIN_USERS"),
            api_url=api_url,
            max_file_mb=max_file_mb,
            debug=bool(getattr(args, "debug", False))
            or str(env.get("TELEGRAM_DEBUG", "")).strip().lower() in ("1", "true", "yes", "on"),
        )
