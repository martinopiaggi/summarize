import os
from typing import Optional

import requests

DEFAULT_TINYPASTE_URL = "https://tnypst.xyz"
REQUEST_TIMEOUT_SECONDS = 15


class TinypastePublishError(Exception):
    pass


def _publish_endpoint(base_url: Optional[str]) -> str:
    resolved_base_url = (
        base_url or os.environ.get("TINYPASTE_URL") or DEFAULT_TINYPASTE_URL
    ).strip()

    if not resolved_base_url:
        resolved_base_url = DEFAULT_TINYPASTE_URL

    return f"{resolved_base_url.rstrip('/')}/api/pastes"


def publish_to_tinypaste(markdown: str, base_url: Optional[str] = None) -> str:
    if not isinstance(markdown, str) or not markdown.strip():
        raise TinypastePublishError("Cannot publish an empty summary.")

    try:
        response = requests.post(
            _publish_endpoint(base_url),
            json={"markdown": markdown},
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.Timeout as error:
        raise TinypastePublishError("Tinypaste request timed out.") from error
    except requests.RequestException as error:
        raise TinypastePublishError(f"Tinypaste request failed: {error}") from error

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        message = "Tinypaste rate limit exceeded."
        if retry_after:
            message = f"{message} Retry after {retry_after} seconds."
        raise TinypastePublishError(message)

    if not 200 <= response.status_code < 300:
        detail = response.text.strip()
        message = f"Tinypaste returned HTTP {response.status_code}."
        if detail:
            message = f"{message} {detail}"
        raise TinypastePublishError(message)

    try:
        payload = response.json()
    except ValueError:
        url = response.text.strip()
        if url:
            return url
        raise TinypastePublishError("Tinypaste returned an empty response.")

    if not isinstance(payload, dict):
        raise TinypastePublishError("Tinypaste returned invalid JSON.")

    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        raise TinypastePublishError("Tinypaste returned JSON without a valid url.")

    return url.strip()
