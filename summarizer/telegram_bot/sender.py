"""Send summaries as Telegram rich messages, with graceful fallbacks.

Summaries go through ``sendRichMessage`` (Bot API 10.1+) with the Markdown
the pipeline produced. When Telegram finds a part too big it is halved and
retried; when it rejects the Markdown, or the Bot API server predates rich
messages, the part is sent as plain text instead so the summary always lands.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List, Optional

from .api import TelegramAPI, TelegramError
from .formatting import RICH_PART_BYTES, Footer, halve_markdown, split_markdown, split_plain

logger = logging.getLogger(__name__)

_SIZE_ERRORS = ("too long", "too_long", "too many", "too_many", "too big", "too_big", "limit")


def reply_parameters(message_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if not message_id:
        return None
    return {"message_id": message_id, "allow_sending_without_reply": True}


def _is_unsupported(exc: TelegramError) -> bool:
    text = exc.description.lower()
    return exc.error_code == 404 or "method not found" in text or "unknown method" in text


def _is_too_big(exc: TelegramError) -> bool:
    text = exc.description.lower()
    return exc.error_code == 400 and any(marker in text for marker in _SIZE_ERRORS)


class MessageSender:
    def __init__(self, api: TelegramAPI):
        self.api = api
        self.rich_supported = True

    # ── summaries ──

    def send_summary(
        self,
        chat_id: int,
        markdown: str,
        footer: Optional[Footer] = None,
        *,
        reply_to: Optional[int] = None,
        thread_id: Optional[int] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Send a Markdown document; the keyboard and footer go on the last part."""
        reserve = len(footer.rich.encode("utf-8")) + 2 if footer and footer.rich else 0
        parts = split_markdown(markdown, max_bytes=RICH_PART_BYTES - reserve) or [""]
        sent: List[Dict[str, Any]] = []
        for index, part in enumerate(parts):
            last = index == len(parts) - 1
            sent += self._send_part(
                chat_id,
                part,
                footer if last else None,
                reply_to=reply_to if index == 0 else None,
                thread_id=thread_id,
                reply_markup=reply_markup if last else None,
            )
        return sent

    def _send_part(self, chat_id, part, footer, *, reply_to, thread_id, reply_markup, depth=0):
        if self.rich_supported:
            body = "\n\n".join(text for text in (part, footer.rich if footer else "") if text)
            try:
                return [
                    self.api.call(
                        "sendRichMessage",
                        {
                            "chat_id": chat_id,
                            "message_thread_id": thread_id,
                            "rich_message": {"markdown": body},
                            "reply_parameters": reply_parameters(reply_to),
                            "reply_markup": reply_markup,
                        },
                    )
                ]
            except TelegramError as exc:
                if _is_unsupported(exc):
                    self.rich_supported = False
                    logger.warning("Bot API server has no rich messages (%s); using plain text", exc.description)
                elif _is_too_big(exc) and depth < 3 and len(halves := halve_markdown(part)) > 1:
                    sent = []
                    for index, half in enumerate(halves):
                        last = index == len(halves) - 1
                        sent += self._send_part(
                            chat_id,
                            half,
                            footer if last else None,
                            reply_to=reply_to if index == 0 else None,
                            thread_id=thread_id,
                            reply_markup=reply_markup if last else None,
                            depth=depth + 1,
                        )
                    return sent
                elif exc.error_code != 400:
                    raise
                else:
                    logger.warning("Telegram rejected a rich message (%s); sending plain text", exc.description)
        plain = "\n\n".join(text for text in (part, footer.plain if footer else "") if text)
        return self.send_plain(chat_id, plain, reply_to=reply_to, thread_id=thread_id, reply_markup=reply_markup)

    # ── plain and HTML messages (status, settings, help) ──

    def send_plain(self, chat_id, text, *, reply_to=None, thread_id=None, reply_markup=None):
        chunks = split_plain(text)
        sent = []
        for index, chunk in enumerate(chunks):
            sent.append(
                self.api.call(
                    "sendMessage",
                    {
                        "chat_id": chat_id,
                        "message_thread_id": thread_id,
                        "text": chunk,
                        "reply_parameters": reply_parameters(reply_to) if index == 0 else None,
                        "reply_markup": reply_markup if index == len(chunks) - 1 else None,
                        "link_preview_options": {"is_disabled": True},
                    },
                )
            )
        return sent

    def send_html(self, chat_id, text, *, reply_to=None, thread_id=None, reply_markup=None):
        params = {
            "chat_id": chat_id,
            "message_thread_id": thread_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_parameters": reply_parameters(reply_to),
            "reply_markup": reply_markup,
            "link_preview_options": {"is_disabled": True},
        }
        try:
            return self.api.call("sendMessage", params)
        except TelegramError as exc:
            if exc.error_code != 400 or "parse" not in exc.description.lower():
                raise
            params.update(text=_strip_tags(text), parse_mode=None)
            return self.api.call("sendMessage", params)

    def edit_html(self, chat_id, message_id, text, reply_markup=None) -> None:
        self._edit(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "link_preview_options": {"is_disabled": True},
            }
        )

    def edit_plain(self, chat_id, message_id, text, reply_markup=None) -> None:
        self._edit(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": split_plain(text)[0],
                "reply_markup": reply_markup,
                "link_preview_options": {"is_disabled": True},
            }
        )

    def _edit(self, params) -> None:
        try:
            self.api.call("editMessageText", params, retries=0)
        except TelegramError as exc:
            if not exc.not_modified:
                logger.debug("editMessageText failed: %s", exc.description)

    def edit_markup(self, chat_id, message_id, reply_markup) -> None:
        try:
            self.api.call(
                "editMessageReplyMarkup",
                {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup},
                retries=0,
            )
        except TelegramError as exc:
            if not exc.not_modified:
                logger.debug("editMessageReplyMarkup failed: %s", exc.description)

    def send_document(self, chat_id, filename, data: bytes, *, caption=None, reply_to=None, thread_id=None):
        params = {
            "chat_id": chat_id,
            "message_thread_id": thread_id,
            "caption": caption,
            "reply_parameters": reply_parameters(reply_to),
        }
        return self.api.call("sendDocument", params, files={"document": (filename, data)})

    # ── best-effort helpers ──

    def delete(self, chat_id, message_id) -> None:
        if not message_id:
            return
        try:
            self.api.call("deleteMessage", {"chat_id": chat_id, "message_id": message_id}, retries=0)
        except TelegramError as exc:
            logger.debug("deleteMessage failed: %s", exc.description)

    def answer_callback(self, query_id, text=None, alert=False) -> None:
        try:
            self.api.call(
                "answerCallbackQuery",
                {"callback_query_id": query_id, "text": text, "show_alert": alert or None},
                retries=0,
            )
        except TelegramError as exc:
            logger.debug("answerCallbackQuery failed: %s", exc.description)

    def typing(self, chat_id, thread_id=None) -> None:
        try:
            self.api.call(
                "sendChatAction",
                {"chat_id": chat_id, "message_thread_id": thread_id, "action": "typing"},
                retries=0,
            )
        except TelegramError:
            pass


def _strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))
