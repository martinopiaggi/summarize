"""Telegram bot interface: send a link, video, audio or voice note, get a summary.

Run with ``summarizer telegram``. Settings come from TELEGRAM_* variables in
the environment or ``.env`` (CLI flags win); summaries are sent as Telegram
rich messages, which render the pipeline's Markdown natively.
"""

from __future__ import annotations

import logging
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, List

from dotenv import find_dotenv, load_dotenv

from ..config_file import load_config_file, merge_configs
from ..exceptions import ConfigurationError, SummarizerError
from .api import TelegramError
from .bot import SummarizeBot
from .options import BotOptions

__all__ = ["BotOptions", "SummarizeBot", "run_from_args"]

logger = logging.getLogger(__name__)


# Exit codes for service managers: 2 = fix the configuration (restarting cannot
# help, e.g. systemd RestartPreventExitStatus=2); 1 = try again later.
EXIT_CONFIG_ERROR = 2
EXIT_RETRY = 1


def run_from_args(args: Any = None) -> int:
    """Entry point of ``summarizer telegram``; returns the exit code."""
    # summarizer.config loads the .env next to the package; a pip/pipx install
    # also needs the one in the working directory, next to summarizer.yaml.
    env_path = find_dotenv(usecwd=True)
    load_dotenv(env_path)
    for key in duplicate_env_keys(env_path):
        logger.warning(
            "%s is set on more than one line of %s: only the last line counts. "
            "Put all the IDs on one line, separated by commas.",
            key, env_path,
        )
    try:
        options = BotOptions.from_args(args, output_dir=_output_dir(args))
    except SummarizerError as exc:
        print(f"[-] {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    bot = SummarizeBot(options)
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        print("Telegram bot stopped.")
        return 0
    except ConfigurationError as exc:  # e.g. Telegram rejected the token
        print(f"[-] {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except (SummarizerError, TelegramError) as exc:  # e.g. no network yet at boot
        print(f"[-] {exc}", file=sys.stderr)
        return EXIT_RETRY
    return 0


def duplicate_env_keys(path: str) -> List[str]:
    """TELEGRAM_* keys that appear on more than one line of a .env file."""
    try:
        text = Path(path).read_text(encoding="utf-8") if path else ""
    except OSError:
        return []
    keys = re.findall(r"^\s*(?:export\s+)?(TELEGRAM_[A-Z_]+)\s*=", text, flags=re.MULTILINE)
    return sorted(key for key, count in Counter(keys).items() if count > 1)


def _output_dir(args: Any) -> str:
    """Where chat settings live by default: output-dir from summarizer.yaml."""
    try:
        path = getattr(args, "bot_config", None)
        merged = merge_configs(load_config_file(Path(path) if path else None), {})
        return str(merged.get("output_dir") or "summaries")
    except SummarizerError:
        return "summaries"
