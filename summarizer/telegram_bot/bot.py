"""The Telegram bot: long polling, access control, commands and buttons."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from ..config_file import merge_configs
from ..exceptions import ConfigurationError, SummarizerError
from ..prompts import get_available_prompts
from ..runtime_env import normalize_config_key
from ..transcript_cache import get_cached_transcript
from . import config_admin, ui
from .api import TelegramAPI, TelegramError
from .config_admin import MAX_CONFIG_BYTES
from .formatting import escape_html as esc
from .jobs import MAX_QUEUED_PER_USER, Job, JobQueue, JobRunner, ResultStore, summary_file, too_big_message
from .options import BotOptions, ensure_private_dir
from .runtime import effective_config, load_file_config, providers_of
from .sender import MessageSender
from .sources import (
    Source,
    UnsupportedMessage,
    extract_urls,
    is_config_document,
    media_source,
    sources_from_message,
    url_source,
)
from .store import ChatSettingsStore

logger = logging.getLogger(__name__)

GROUP_TYPES = ("group", "supergroup")
UPLOAD_TTL_SECONDS = 600
UNAUTHORIZED_REPLY_INTERVAL = 600

USER_COMMANDS = [
    ("summarize", "Summarize a link, or reply to a message with it"),
    ("settings", "Provider, style and languages for this chat"),
    ("style", "Pick the summary style"),
    ("status", "What is running and queued"),
    ("cancel", "Drop your queued jobs"),
    ("help", "How to use this bot"),
    ("id", "Show your Telegram IDs"),
]
ADMIN_COMMANDS = [
    ("config", "View, download or replace summarizer.yaml"),
    ("set", "Change one value in summarizer.yaml"),
]


class SummarizeBot:
    def __init__(
        self,
        options: BotOptions,
        api: Optional[TelegramAPI] = None,
        core_main: Optional[Callable[[Dict[str, Any]], str]] = None,
    ):
        self.options = options
        self.api = api or TelegramAPI(options.token, options.api_url)
        self.sender = MessageSender(self.api)
        self.store = ChatSettingsStore(options.state_file)
        self.results = ResultStore()
        self.runner = JobRunner(options, self.api, self.sender, self.store, self.results, core_main)
        self.queue = JobQueue(self.runner.run, on_advance=self._refresh_positions)
        self.bot_id: Optional[int] = None
        self.username = ""
        self.reads_all_messages = False  # privacy mode off: plain @mentions arrive too
        self._uploads: Dict[str, Dict[str, Any]] = {}
        self._uploads_lock = threading.Lock()
        self._unauthorized_seen: Dict[int, float] = {}
        self._stop = threading.Event()
        self._greeted: Dict[int, float] = {}

    # ── lifecycle ──

    def setup(self) -> None:
        try:
            me = self.api.call("getMe")
        except TelegramError as exc:
            if exc.error_code in (401, 404):  # 404: malformed token
                raise ConfigurationError(
                    "Telegram rejected the bot token. Copy it again from @BotFather "
                    "(/mybots → your bot → API Token) into TELEGRAM_BOT_TOKEN."
                ) from None
            raise
        self.bot_id, self.username = me.get("id"), me.get("username") or ""
        self.reads_all_messages = bool(me.get("can_read_all_group_messages"))
        # Long polling does not work while a webhook is set.
        self.api.call("deleteWebhook", {"drop_pending_updates": False})
        self._register_commands()
        ensure_private_dir(self.options.work_dir)

    def _register_commands(self) -> None:
        def payload(commands):
            return [{"command": name, "description": text} for name, text in commands]

        try:
            self.api.call("setMyCommands", {"commands": payload(USER_COMMANDS)})
            for admin in self.options.admins:
                self.api.call(
                    "setMyCommands",
                    {"commands": payload(USER_COMMANDS + ADMIN_COMMANDS), "scope": {"type": "chat", "chat_id": admin}},
                )
        except TelegramError as exc:
            logger.warning("Could not register the command menu: %s", exc.description)

    def run_forever(self) -> None:
        self.setup()
        logger.info("Telegram bot @%s is running (config: %s)", self.username, self.options.config_path)
        if self.options.setup_mode:
            logger.warning(
                "No TELEGRAM_ALLOWED_USERS set: the bot only replies with each user's ID. "
                "Message @%s to get yours.",
                self.username,
            )
        self.queue.start()
        offset: Optional[int] = None
        failures = 0
        try:
            while not self._stop.is_set():
                try:
                    updates = self.api.call(
                        "getUpdates",
                        {
                            "offset": offset,
                            "timeout": 50,
                            "allowed_updates": ["message", "callback_query", "my_chat_member"],
                        },
                        timeout=65,
                        retries=0,
                    )
                    failures = 0
                except TelegramError as exc:
                    if exc.error_code == 401:
                        raise ConfigurationError("Telegram rejected the bot token (401 Unauthorized)") from None
                    if exc.error_code == 409:
                        logger.error(
                            "409 Conflict: another program is running this same bot token (another "
                            "`summarizer telegram` in a terminal, server or container). Only one can run "
                            "at a time; stop the other one. Retrying in 10s"
                        )
                    else:
                        logger.warning("getUpdates failed: %s", exc.description)
                    failures += 1
                    self._stop.wait(min(5 * failures, 30) if exc.error_code != 409 else 10)
                    continue
                for update in updates or []:
                    offset = update["update_id"] + 1
                    self.handle_update(update)
        finally:
            self.queue.stop()

    def stop(self) -> None:
        self._stop.set()

    # ── dispatch ──

    def handle_update(self, update: Dict[str, Any]) -> None:
        if self.options.debug:
            logger.info("Update %s: %s", update.get("update_id"), _describe_update(update))
        try:
            if "message" in update:
                self.handle_message(update["message"])
            elif "callback_query" in update:
                self.handle_callback(update["callback_query"])
            elif "my_chat_member" in update:
                self.handle_membership(update["my_chat_member"])
        except Exception:
            logger.exception("Failed to handle update %s", update.get("update_id"))

    def handle_message(self, message: Dict[str, Any]) -> None:
        user = message.get("from") or {}
        chat = message.get("chat") or {}
        sender_chat = message.get("sender_chat")
        if not chat or (user.get("is_bot") and not sender_chat):
            return
        # Anonymous group admins and "send as channel" hide who is writing.
        user_id = None if sender_chat else user.get("id")
        chat_id = chat.get("id")
        in_group = chat.get("type") in GROUP_TYPES

        if in_group and self._is_join(message):
            self._greet_group(message, user_id)
            return
        if message.get("migrate_to_chat_id"):
            logger.info(
                "Group %s became supergroup %s: update TELEGRAM_ALLOWED_CHATS if it lists the old ID",
                chat_id, message["migrate_to_chat_id"],
            )
            return

        command = _command_text(message)
        if command:
            logger.info(
                "%s from user %s in %s %s", command.split()[0], user_id, chat.get("type"), chat_id
            )
        if not self.options.is_allowed(user_id, chat_id):
            self._reply_unauthorized(message, user_id, explicit=bool(command) and self._is_for_me(command))
            return
        if command:
            self.handle_command(message, command)
            return
        if in_group and not self._addressed_to_me(message):
            return  # in groups, act on commands, mentions and replies to the bot only
        if is_config_document(message) and self.options.is_admin(user_id):
            self.handle_config_upload(message)
            return
        reply_to = None
        try:
            sources = sources_from_message(message)
            target = message.get("reply_to_message")
            if not sources and target and self._mentions_me(message) and not self._is_mine(target):
                # "@bot" as a reply means "summarize that message", like /summarize
                sources = sources_from_message(target, explicit=True)
                reply_to = target.get("message_id")
        except UnsupportedMessage as exc:
            self._reply(message, esc(exc))
            return
        if not sources:
            self._reply(
                message,
                "Send me a video link, a video, an audio file or a voice message to summarize. /help",
            )
            return
        for source in sources:
            self.enqueue(message, source, reply_to=reply_to)

    def _is_mine(self, message: Dict[str, Any]) -> bool:
        return bool(self.bot_id) and (message.get("from") or {}).get("id") == self.bot_id

    def _mentions_me(self, message: Dict[str, Any]) -> bool:
        text = (message.get("text") or message.get("caption") or "").lower()
        return bool(self.username) and f"@{self.username.lower()}" in text

    def _addressed_to_me(self, message: Dict[str, Any]) -> bool:
        return self._is_mine(message.get("reply_to_message") or {}) or self._mentions_me(message)

    def _is_for_me(self, command: str) -> bool:
        target = command.split()[0].partition("@")[2]
        return not target or target.lower() == self.username.lower()

    def _is_join(self, message: Dict[str, Any]) -> bool:
        if message.get("group_chat_created") or message.get("supergroup_chat_created"):
            return True
        return any(member.get("id") == self.bot_id for member in message.get("new_chat_members") or [])

    def handle_membership(self, update: Dict[str, Any]) -> None:
        """The bot was added to, removed from, or changed in a chat."""
        chat = update.get("chat") or {}
        old = (update.get("old_chat_member") or {}).get("status")
        new = (update.get("new_chat_member") or {}).get("status")
        user_id = (update.get("from") or {}).get("id")
        logger.info(
            "Bot status in %s %s (%s): %s -> %s, changed by user %s",
            chat.get("type"), chat.get("id"), chat.get("title", ""), old, new, user_id,
        )
        if new == "restricted":
            logger.warning("The bot is restricted in chat %s and may not be able to post", chat.get("id"))
        if new not in ("member", "administrator") or old not in ("left", "kicked", None):
            return
        if chat.get("type") == "channel":
            logger.warning("Added to channel %s: channels are not supported, add the bot to a group", chat.get("id"))
        elif chat.get("type") in GROUP_TYPES:
            self._greet_group({"chat": chat}, user_id)

    def _greet_group(self, message: Dict[str, Any], user_id: Optional[int]) -> None:
        """Say how to use the bot when it joins a group.

        Besides explaining, posting makes this the last bot that spoke in the
        group, and Telegram then delivers plain /summarize and /s (without
        @botname) to it even in privacy mode.
        """
        chat = message["chat"]
        now = time.monotonic()
        if now - self._greeted.get(chat["id"], -60.0) < 60:
            return  # Telegram reports a join twice (service message and status change)
        self._greeted[chat["id"]] = now
        logger.info("Added to %s %s (%s) by user %s", chat.get("type"), chat["id"], chat.get("title", ""), user_id)
        try:
            self.sender.send_html(
                chat["id"],
                ui.group_greeting(self.username, chat["id"], user_id, self.options, self.reads_all_messages),
                thread_id=_thread_id(message),
            )
        except TelegramError as exc:
            logger.warning("Could not post in %s %s: %s", chat.get("type"), chat["id"], exc.description)

    def _reply_unauthorized(self, message: Dict[str, Any], user_id: Optional[int], explicit: bool) -> None:
        chat = message.get("chat") or {}
        logger.info(
            "Ignored message from unauthorized user %s (@%s) in %s %s",
            user_id, (message.get("from") or {}).get("username", ""), chat.get("type"), chat.get("id"),
        )
        private = chat.get("type") == "private"
        if not (private or explicit):
            return  # in groups, only answer people who address the bot
        key = (chat.get("id"), user_id)
        now = time.monotonic()
        if now - self._unauthorized_seen.get(key, -UNAUTHORIZED_REPLY_INTERVAL) < UNAUTHORIZED_REPLY_INTERVAL:
            return
        self._unauthorized_seen[key] = now
        if private:
            if user_id is not None:
                self._reply(message, ui.setup_text(user_id, self.options.setup_mode))
        else:
            self._reply(message, ui.group_denied_text(user_id, chat.get("id")))

    def _reply(self, message: Dict[str, Any], html_text: str, reply_markup=None) -> Optional[Dict[str, Any]]:
        try:
            return self.sender.send_html(
                message["chat"]["id"],
                html_text,
                reply_to=message.get("message_id"),
                thread_id=_thread_id(message),
                reply_markup=reply_markup,
            )
        except TelegramError as exc:
            logger.warning("Could not reply in chat %s: %s", message["chat"]["id"], exc.description)
            return None

    # ── jobs ──

    def enqueue(
        self,
        message: Dict[str, Any],
        source: Source,
        overrides: Optional[Dict[str, Any]] = None,
        reply_to: Optional[int] = None,
    ) -> Optional[Job]:
        chat_id, user_id = message["chat"]["id"], (message.get("from") or {}).get("id")
        if source.kind == "file" and source.file_size > self.options.max_file_bytes:
            self._reply(message, esc(too_big_message(source.file_size, self.options)))
            return None
        if source.media == "animation" and not self._visual_enabled(chat_id):
            self._reply(message, "This animation has no audio to transcribe. Turn on <b>Visual</b> in /settings to summarize it.")
            return None
        if self.queue.count_for_user(user_id) >= MAX_QUEUED_PER_USER:
            self._reply(message, f"You already have {MAX_QUEUED_PER_USER} jobs waiting. Try again later, or /cancel.")
            return None

        job = Job(
            chat_id=chat_id,
            user_id=user_id,
            source=source,
            reply_to=reply_to or message.get("message_id"),
            thread_id=_thread_id(message),
            overrides=dict(overrides or {}),
        )
        ahead = self.queue.ahead()
        status = "⏳ Starting…" if not ahead else f"🕒 Queued (#{ahead + 1})"
        try:
            sent = self.sender.send_plain(
                chat_id, f"{status}\n{job.describe()}", reply_to=job.reply_to, thread_id=job.thread_id
            )
            job.status_message_id = sent[0].get("message_id") if sent else None
        except TelegramError as exc:
            logger.warning("Could not send status message: %s", exc.description)
        self.queue.submit(job)
        return job

    def _visual_enabled(self, chat_id: int) -> bool:
        try:
            file_config = load_file_config(self.options.config_path)
            return bool(effective_config(file_config, self.store.get(chat_id)).get("visual"))
        except SummarizerError:
            return False

    def _refresh_positions(self, waiting: List[Job]) -> None:
        for position, job in enumerate(waiting[:5], start=2):
            if job.status_message_id:
                self.sender.edit_plain(job.chat_id, job.status_message_id, f"🕒 Queued (#{position})\n{job.describe()}")

    # ── commands ──

    def handle_command(self, message: Dict[str, Any], text: str) -> None:
        head, _, args = text.partition(" ")
        if "\n" in head:
            head, _, rest = head.partition("\n")
            args = f"{rest} {args}".strip()
        name, _, target = head[1:].partition("@")
        if target and self.username and target.lower() != self.username.lower():
            return  # addressed to another bot in the same group
        name = name.lower()
        user_id = (message.get("from") or {}).get("id")
        handlers = {
            "start": self.cmd_start,
            "help": self.cmd_help,
            "id": self.cmd_id,
            "settings": self.cmd_settings,
            "style": self.cmd_style,
            "provider": self.cmd_provider,
            "language": self.cmd_language,
            "lang": self.cmd_language,
            "summarize": self.cmd_summarize,
            "s": self.cmd_summarize,
            "status": self.cmd_status,
            "cancel": self.cmd_cancel,
        }
        admin_handlers = {"config": self.cmd_config, "set": self.cmd_set}
        if name in handlers:
            handlers[name](message, args.strip())
        elif name in admin_handlers:
            if self.options.is_admin(user_id):
                admin_handlers[name](message, args.strip())
            else:
                self._reply(message, "Only the bot admin can change summarizer.yaml.")
        else:
            self._reply(message, "Unknown command. /help")

    def cmd_start(self, message, args) -> None:
        # The "Add me to a group" link adds the bot, then sends /start in the group.
        if message["chat"].get("type") in GROUP_TYPES:
            user_id = None if message.get("sender_chat") else (message.get("from") or {}).get("id")
            self._greet_group(message, user_id)
        else:
            self.cmd_help(message, args)

    def cmd_help(self, message, args) -> None:
        in_group = message["chat"].get("type") in GROUP_TYPES
        is_admin = self.options.is_admin((message.get("from") or {}).get("id"))
        markup = None if in_group else ui.add_to_group_keyboard(self.username)
        self._reply(message, ui.help_text(is_admin, in_group, self.username, self.reads_all_messages), markup)

    def cmd_id(self, message, args) -> None:
        user_id = (message.get("from") or {}).get("id")
        self._reply(message, f"User ID: <code>{user_id}</code>\nChat ID: <code>{message['chat']['id']}</code>")

    def cmd_settings(self, message, args) -> None:
        text, markup = self._settings_view(message["chat"]["id"])
        self._reply(message, text, markup)

    def cmd_style(self, message, args) -> None:
        self._set_or_pick(message, args, "style", get_available_prompts(), "style")

    def cmd_provider(self, message, args) -> None:
        providers = list(providers_of(self._file_config_or_empty()))
        self._set_or_pick(message, args, "prov", providers, "provider")

    def cmd_language(self, message, args) -> None:
        chat_id = message["chat"]["id"]
        if not args:
            self._send_picker(message, "olang")
            return
        value = None if args.lower() == "default" else args[:60]
        self.store.update(chat_id, output_language=value)
        self._reply(message, f"🌐 Summary language for this chat: <b>{esc(value or 'default')}</b>")

    def _set_or_pick(self, message, args, field, choices, what) -> None:
        if not args:
            self._send_picker(message, field)
            return
        chat_id = message["chat"]["id"]
        key = ui.CHAT_FIELDS[field]
        if args.lower() == "default":
            self.store.update(chat_id, **{key: None})
            self._reply(message, f"Using the default {what} from summarizer.yaml.")
            return
        try:
            value = config_admin.match_choice(args, choices, what)
        except ConfigurationError as exc:
            self._reply(message, esc(exc))
            return
        self.store.update(chat_id, **{key: value})
        self._reply(message, f"{ui.FIELD_TITLES[field]} for this chat: <b>{esc(value)}</b>")

    def _send_picker(self, message, field) -> None:
        chat_id = message["chat"]["id"]
        choices = ui.chat_choices(field, self._file_config_or_empty())
        current = self.store.get(chat_id).get(ui.CHAT_FIELDS[field])
        self._reply(
            message,
            f"<b>{ui.FIELD_TITLES[field]}</b> for this chat:",
            ui.picker_keyboard(f"set:val:{field}", choices, current, "set:home"),
        )

    def cmd_summarize(self, message, args) -> None:
        """Summarize the links in ``args``, the attached media, or the replied-to message."""
        sources: List[Source] = []
        reply_to = None
        try:
            own_media = media_source(message)  # a video sent with /summarize as caption
            urls = extract_urls(args) if args else []
            if urls:
                sources = [url_source(url) for url in urls]
            elif own_media:
                sources = [own_media]
            elif args:
                sources = sources_from_message({"text": args}, explicit=True)
            elif message.get("reply_to_message"):
                target = message["reply_to_message"]
                sources = sources_from_message(target, explicit=True)
                reply_to = target.get("message_id")
        except UnsupportedMessage as exc:
            self._reply(message, esc(exc))
            return
        if not sources:
            # Plain commands: this reply makes the bot the last one that spoke in a group.
            self._reply(
                message,
                "Reply to a video, voice message or link with /summarize (or just /s), "
                "or send <code>/s https://…</code>",
            )
            return
        for source in sources:
            self.enqueue(message, source, reply_to=reply_to)

    def cmd_status(self, message, args) -> None:
        running, pending = self.queue.snapshot()
        user_id = (message.get("from") or {}).get("id")
        if not running and not pending:
            self._reply(message, "Nothing running. Send me something to summarize.")
            return
        lines = []
        if running:
            lines.append(f"▶️ Running: {esc(running.describe())}")
        lines.append(f"🕒 Queued: {len(pending)}")
        mine = [f"#{i} {esc(job.describe())}" for i, job in enumerate(pending, start=1) if job.user_id == user_id]
        if mine:
            lines += ["", "Yours:"] + mine
        self._reply(message, "\n".join(lines))

    def cmd_cancel(self, message, args) -> None:
        user_id = (message.get("from") or {}).get("id")
        cancelled = self.queue.cancel(message["chat"]["id"], user_id)
        for job in cancelled:
            if job.status_message_id:
                self.sender.edit_plain(job.chat_id, job.status_message_id, f"✖ Cancelled\n{job.describe()}")
        note = " The running job cannot be stopped." if self.queue.snapshot()[0] else ""
        self._reply(message, f"Cancelled {len(cancelled)} queued job(s).{note}")

    # ── admin: summarizer.yaml ──

    def cmd_config(self, message, args) -> None:
        text, markup = self._config_view()
        self._reply(message, text, markup)

    def cmd_set(self, message, args) -> None:
        try:
            file_config = load_file_config(self.options.config_path)
        except ConfigurationError as exc:
            self._reply(message, esc(exc))
            return
        if not args:
            self._reply(message, self._set_usage(file_config))
            return
        name, _, raw = args.partition(" ")
        try:
            setting = config_admin.resolve_setting(name)
            value = config_admin.parse_value(setting, raw, file_config)
            config_admin.apply_setting(self.options.config_path, setting, value)
        except ConfigurationError as exc:
            self._reply(message, f"⚠️ {esc(exc)}")
            return
        shown = str(value).lower() if isinstance(value, bool) else value
        self._reply(message, f"✅ <code>{esc(setting.key)}</code> = <code>{esc(shown)}</code> in summarizer.yaml")

    def _set_usage(self, file_config: Dict[str, Any]) -> str:
        try:
            effective = dict(merge_configs(file_config, {}))
        except SummarizerError:
            effective = {}
        effective["default_provider"] = file_config.get("default_provider")
        return ui.set_usage_text(config_admin.SETTINGS, effective, normalize_config_key)

    def handle_config_upload(self, message: Dict[str, Any]) -> None:
        document = message["document"]
        if (document.get("file_size") or 0) > MAX_CONFIG_BYTES:
            self._reply(message, "That file is too large for a summarizer.yaml.")
            return
        path = self.options.work_dir / f"upload_{secrets.token_hex(6)}.yaml"
        try:
            ensure_private_dir(self.options.work_dir)
            self.api.download_file(document["file_id"], str(path), max_bytes=MAX_CONFIG_BYTES)
            text = path.read_text(encoding="utf-8")
            data = config_admin.validate_config_text(text)
        except (TelegramError, ConfigurationError, UnicodeDecodeError) as exc:
            reason = exc.description if isinstance(exc, TelegramError) else str(exc)
            self._reply(message, f"⚠️ Not applied: {esc(reason)}")
            return
        finally:
            if path.exists():
                path.unlink()
        token = secrets.token_hex(6)
        with self._uploads_lock:
            now = time.monotonic()
            for key in [k for k, v in self._uploads.items() if now - v["at"] > UPLOAD_TTL_SECONDS]:
                del self._uploads[key]
            self._uploads[token] = {"user": message["from"]["id"], "text": text, "at": now}
        providers = providers_of(data)
        self._reply(
            message,
            "Replace summarizer.yaml with this file?\n\n"
            f"Default provider: <b>{esc(data.get('default_provider') or 'none')}</b>\n"
            f"Providers: {esc(', '.join(providers))}\n"
            f"Defaults: {len(data.get('defaults') or {})} keys\n\n"
            f"The current file is kept as <code>{esc(self.options.config_path.name)}.bak</code>.",
            ui.upload_keyboard(token),
        )

    def _file_config_or_empty(self) -> Dict[str, Any]:
        try:
            return load_file_config(self.options.config_path)
        except ConfigurationError:
            return {}

    def _config_view(self, error: str = ""):
        try:
            file_config = load_file_config(self.options.config_path)
        except ConfigurationError as exc:
            return ui.config_text(self.options.config_path, {}, None, error=str(exc)), ui.config_keyboard()
        try:
            effective = merge_configs(file_config, {}) if file_config else None
        except SummarizerError as exc:
            effective, error = None, error or str(exc)
        return ui.config_text(self.options.config_path, file_config, effective, error), ui.config_keyboard()

    def _settings_view(self, chat_id: int):
        file_config = self._file_config_or_empty()
        chat = self.store.get(chat_id)
        try:
            effective = effective_config(file_config, chat)
        except SummarizerError:
            effective = {}
        return ui.settings_text(chat, file_config, effective), ui.settings_keyboard(chat, effective)

    # ── buttons ──

    def handle_callback(self, query: Dict[str, Any]) -> None:
        user_id = (query.get("from") or {}).get("id")
        message = query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        if not chat_id or not self.options.is_allowed(user_id, chat_id):
            self.sender.answer_callback(query["id"], "Not allowed", alert=True)
            return
        prefix, _, rest = (query.get("data") or "").partition(":")
        handler = {
            "set": self._on_settings,
            "cfg": self._on_config,
            "res": self._on_result,
            "up": self._on_upload,
        }.get(prefix)
        notice = handler(query, message, rest) if handler else "This button has expired"
        self.sender.answer_callback(query["id"], notice)

    def _on_settings(self, query, message, rest) -> Optional[str]:
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        action, _, arg = rest.partition(":")
        notice = None
        if action == "close":
            self.sender.edit_markup(chat_id, message_id, None)
            return "Saved"
        if action == "open" and arg in ui.CHAT_FIELDS:
            choices = ui.chat_choices(arg, self._file_config_or_empty())
            current = self.store.get(chat_id).get(ui.CHAT_FIELDS[arg])
            self.sender.edit_html(
                chat_id,
                message_id,
                f"<b>{ui.FIELD_TITLES[arg]}</b> for this chat:",
                ui.picker_keyboard(f"set:val:{arg}", choices, current, "set:home"),
            )
            return None
        if action == "val":
            field, _, index = arg.partition(":")
            choices = ui.chat_choices(field, self._file_config_or_empty()) if field in ui.CHAT_FIELDS else []
            if not index.isdigit() or int(index) >= len(choices):
                notice = "Options changed, pick again"
            else:
                value, label = choices[int(index)]
                self.store.update(chat_id, **{ui.CHAT_FIELDS[field]: value})
                notice = f"{ui.FIELD_TITLES[field]}: {label}"
        elif action == "tog" and arg in ui.CHAT_TOGGLES:
            key = ui.CHAT_TOGGLES[arg]
            if arg == "visual":
                self.store.update(chat_id, visual=not self._visual_enabled(chat_id))
            else:
                self.store.update(chat_id, **{key: (not self.store.get(chat_id).get(key)) or None})
        elif action == "reset":
            self.store.reset(chat_id)
            notice = "Back to the summarizer.yaml defaults"
        text, markup = self._settings_view(chat_id)
        self.sender.edit_html(chat_id, message_id, text, markup)
        return notice

    def _on_config(self, query, message, rest) -> Optional[str]:
        user_id = query["from"]["id"]
        if not self.options.is_admin(user_id):
            return "Only the bot admin can change summarizer.yaml"
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        action, _, arg = rest.partition(":")
        fields = {"prov": "default_provider", "style": "prompt-type", "side": "sidecar"}
        if action == "close":
            self.sender.edit_markup(chat_id, message_id, None)
            return None
        if action == "dl":
            return self._send_config_file(chat_id, message)
        file_config = self._file_config_or_empty()
        if action == "open" and arg in fields:
            if not file_config:
                return "No summarizer.yaml yet"
            try:
                current = (
                    file_config.get("default_provider") if arg == "prov"
                    else merge_configs(file_config, {}).get(normalize_config_key(fields[arg]))
                )
            except SummarizerError:
                current = None
            self.sender.edit_html(
                chat_id,
                message_id,
                f"<b>{ui.FIELD_TITLES.get(arg, 'Default style')}</b> in summarizer.yaml (all chats):",
                ui.picker_keyboard(f"cfg:val:{arg}", ui.config_choices(arg, file_config), current, "cfg:home"),
            )
            return None
        notice, error = None, ""
        if action == "val":
            field, _, index = arg.partition(":")
            choices = ui.config_choices(field, file_config) if field in fields else []
            if not index.isdigit() or int(index) >= len(choices):
                notice = "Options changed, pick again"
            else:
                value = choices[int(index)][0]
                try:
                    config_admin.apply_setting(self.options.config_path, config_admin.SETTINGS[fields[field]], value)
                    notice = f"Saved: {value}"
                except ConfigurationError as exc:
                    error = str(exc)
        text, markup = self._config_view(error)
        self.sender.edit_html(chat_id, message_id, text, markup)
        return notice

    def _send_config_file(self, chat_id, message) -> Optional[str]:
        path = self.options.config_path
        if not path.exists():
            return "No summarizer.yaml yet"
        data = config_admin.redact_config_text(path.read_text(encoding="utf-8")).encode("utf-8")
        try:
            self.sender.send_document(
                chat_id,
                path.name,
                data,
                caption="Edit it and send it back to replace the current file. API keys are hidden.",
                thread_id=_thread_id(message),
            )
        except TelegramError as exc:
            return f"Could not send the file: {exc.description}"[:190]
        return None

    def _on_result(self, query, message, rest) -> Optional[str]:
        result_id, _, action = rest.partition(":")
        result = self.results.get(result_id)
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        if result is None or result.job.chat_id != chat_id:  # a result only answers in its own chat
            self.sender.edit_markup(chat_id, message_id, None)
            return "This result has expired. Send the source again."
        thread_id = _thread_id(message)
        if action == "md":
            name, data = summary_file(result)
            self.sender.send_document(chat_id, name, data, reply_to=message_id, thread_id=thread_id)
            return None
        if action == "tx":
            transcript = get_cached_transcript(result.config)[0]
            if not transcript:
                reason = "visual mode has no transcript" if result.config.get("visual") else "it is no longer cached"
                return f"No transcript available ({reason})"
            name = summary_file(result)[0].replace(".md", "_transcript.txt")
            self.sender.send_document(chat_id, name, transcript.encode("utf-8"), reply_to=message_id, thread_id=thread_id)
            return None
        if action == "rs":
            self.sender.edit_markup(chat_id, message_id, ui.restyle_keyboard(result_id, result.prompt_type))
            return "Pick a style"
        if action == "back":
            self.sender.edit_markup(chat_id, message_id, ui.result_keyboard(result_id))
            return None
        if action.startswith("rs:"):
            index = action[3:]
            styles = get_available_prompts()
            self.sender.edit_markup(chat_id, message_id, ui.result_keyboard(result_id))
            if not index.isdigit() or int(index) >= len(styles):
                return "Unknown style"
            fake_message = {
                "chat": message["chat"],
                "from": query["from"],
                "message_id": result.job.reply_to,
                "message_thread_id": result.job.thread_id,
                "is_topic_message": bool(result.job.thread_id),
            }
            job = self.enqueue(fake_message, result.job.source, overrides={"prompt_type": styles[int(index)]})
            return f"Restyling as {styles[int(index)]}" if job else None
        return None

    def _on_upload(self, query, message, rest) -> Optional[str]:
        token, _, action = rest.partition(":")
        chat_id, message_id = message["chat"]["id"], message["message_id"]
        with self._uploads_lock:
            upload = self._uploads.get(token)
            if upload and upload["user"] != query["from"]["id"]:
                return "Only the admin who sent the file can apply it"
            self._uploads.pop(token, None)
        if upload is None:
            self.sender.edit_html(chat_id, message_id, "This upload has expired. Send the file again.")
            return None
        if action != "ok":
            self.sender.edit_html(chat_id, message_id, "✖ Kept the current summarizer.yaml.")
            return None
        if not self.options.is_admin(query["from"]["id"]):
            return "Only the bot admin can change summarizer.yaml"
        try:
            backup = config_admin.replace_config_file(self.options.config_path, upload["text"])
        except OSError as exc:
            self.sender.edit_html(chat_id, message_id, f"⚠️ Not applied: {esc(exc)}")
            return None
        note = f" Previous version: <code>{esc(backup.name)}</code>." if backup else ""
        self.sender.edit_html(chat_id, message_id, f"✅ summarizer.yaml replaced.{note}")
        logger.info("summarizer.yaml replaced from Telegram by user %s", query["from"]["id"])
        return "Saved"


def _thread_id(message: Dict[str, Any]) -> Optional[int]:
    return message.get("message_thread_id") if message.get("is_topic_message") else None


def _describe_update(update: Dict[str, Any]) -> str:
    """One log line saying what Telegram delivered (for --debug)."""
    if "callback_query" in update:
        query = update["callback_query"]
        chat = (query.get("message") or {}).get("chat") or {}
        return (
            f"button {query.get('data')!r} from user {(query.get('from') or {}).get('id')} "
            f"in {chat.get('type')} {chat.get('id')}"
        )
    if "my_chat_member" in update:
        change = update["my_chat_member"]
        chat = change.get("chat") or {}
        return (
            f"bot status in {chat.get('type')} {chat.get('id')}: "
            f"{(change.get('old_chat_member') or {}).get('status')} -> "
            f"{(change.get('new_chat_member') or {}).get('status')}"
        )
    kind = next((key for key in update if key != "update_id"), "?")
    body = update.get(kind) or {}
    if not isinstance(body, dict):
        return kind
    chat = body.get("chat") or {}
    parts = [f"{kind} in {chat.get('type')} {chat.get('id')} from user {(body.get('from') or {}).get('id')}"]
    if body.get("sender_chat"):
        parts.append(f"(as chat {body['sender_chat'].get('id')})")
    text = body.get("text") or body.get("caption")
    if text:
        parts.append(repr(text[:80]))
    media = [key for key in ("video", "video_note", "voice", "audio", "document", "animation", "photo") if key in body]
    if media:
        parts.append("+" + "/".join(media))
    if body.get("reply_to_message"):
        parts.append(f"replying to message {body['reply_to_message'].get('message_id')}")
    if body.get("new_chat_members"):
        parts.append("new members " + ", ".join(str(m.get("id")) for m in body["new_chat_members"]))
    return " ".join(parts)


def _command_text(message: Dict[str, Any]) -> str:
    """The command of a message: its text, or the caption of a video sent with one."""
    for key in ("text", "caption"):
        value = (message.get(key) or "").strip()
        if value.startswith("/"):
            return value
    return ""
