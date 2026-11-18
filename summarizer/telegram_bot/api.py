"""Minimal synchronous client for the Telegram Bot API.

The bot needs a dozen methods, including ``sendRichMessage`` (Bot API 10.1),
which general-purpose libraries do not all support yet. Plain JSON over
``requests`` keeps the bot dependency-free and forward compatible.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_API_URL = "https://api.telegram.org"


class TelegramError(Exception):
    """A Bot API call failed. ``description`` never contains the bot token."""

    def __init__(
        self,
        description: str,
        error_code: Optional[int] = None,
        retry_after: Optional[float] = None,
        method: str = "",
    ):
        super().__init__(description)
        self.description = description
        self.error_code = error_code
        self.retry_after = retry_after
        self.method = method

    @property
    def not_modified(self) -> bool:
        return "message is not modified" in self.description.lower()


class TelegramAPI:
    """Thread-safe Bot API client (one HTTP session per thread)."""

    def __init__(self, token: str, api_url: str = DEFAULT_API_URL, timeout: float = 30.0):
        if not token:
            raise ValueError("A bot token is required")
        self.token = token
        self.api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self.timeout = timeout
        self._local = threading.local()

    @property
    def is_official_server(self) -> bool:
        return self.api_url == DEFAULT_API_URL

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def _redact(self, value: Any) -> str:
        return str(value).replace(self.token, "<token>")

    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        retries: int = 2,
    ) -> Any:
        """Call a Bot API method and return its ``result``.

        ``None`` values are dropped. Rate limits (429) and server errors are
        retried up to ``retries`` times; everything else raises TelegramError.
        """
        url = f"{self.api_url}/bot{self.token}/{method}"
        payload = {key: value for key, value in (params or {}).items() if value is not None}
        attempt = 0
        while True:
            try:
                if files:
                    form = {key: _form_value(value) for key, value in payload.items()}
                    response = self._session().post(
                        url, data=form, files=files, timeout=timeout or self.timeout
                    )
                else:
                    response = self._session().post(url, json=payload, timeout=timeout or self.timeout)
            except requests.RequestException as exc:
                if attempt < retries:
                    attempt += 1
                    time.sleep(min(2 ** attempt, 10))
                    continue
                # "from None": the original exception text includes the URL, i.e. the token.
                raise TelegramError(
                    f"Network error during {method}: {self._redact(exc)}", method=method
                ) from None

            try:
                body = response.json()
            except ValueError:
                body = {"ok": False, "description": f"HTTP {response.status_code}"}
            if body.get("ok"):
                return body.get("result")

            code = body.get("error_code") or response.status_code
            description = self._redact(body.get("description") or "Unknown error")
            retry_after = (body.get("parameters") or {}).get("retry_after")
            if attempt < retries and code == 429 and retry_after is not None and retry_after <= 60:
                attempt += 1
                time.sleep(float(retry_after) + 0.5)
                continue
            if attempt < retries and isinstance(code, int) and code >= 500:
                attempt += 1
                time.sleep(min(2 ** attempt, 10))
                continue
            raise TelegramError(description, code, retry_after, method)

    def download_file(self, file_id: str, destination: str, max_bytes: Optional[int] = None) -> str:
        """Download a file sent to the bot to ``destination`` and return the path."""
        info = self.call("getFile", {"file_id": file_id}) or {}
        file_path = info.get("file_path")
        if not file_path:
            raise TelegramError("Telegram did not return a download path for this file", method="getFile")

        if os.path.isabs(file_path):
            # A local Bot API server (--local) returns a path on its own disk.
            if not os.path.exists(file_path):
                raise TelegramError(
                    "The Bot API server returned a local file path this process cannot read. "
                    "Mount the server's data directory at the same path.",
                    method="getFile",
                )
            try:
                os.link(file_path, destination)
            except OSError:
                shutil.copyfile(file_path, destination)
            return destination

        url = f"{self.api_url}/file/bot{self.token}/{file_path}"
        try:
            with self._session().get(url, stream=True, timeout=(10, 120)) as response:
                if response.status_code != 200:
                    raise TelegramError(
                        f"File download failed with HTTP {response.status_code}",
                        response.status_code,
                        method="getFile",
                    )
                written = 0
                with open(destination, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 20):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if max_bytes and written > max_bytes:
                            raise TelegramError("The file is larger than the download limit", method="getFile")
                        handle.write(chunk)
        except requests.RequestException as exc:
            raise TelegramError(f"File download failed: {self._redact(exc)}", method="getFile") from None
        return destination


def _form_value(value: Any) -> str:
    """Encode a parameter for multipart/form-data requests."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
