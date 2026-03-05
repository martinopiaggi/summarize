"""Shared Webshare proxy configuration."""

import os
from typing import Dict, Optional

from .exceptions import ConfigurationError

WEBSHARE_PROXY_HOST = "p.webshare.io"
WEBSHARE_PROXY_PORT = "80"


def get_webshare_proxies(use_proxy: bool = False) -> Optional[Dict[str, str]]:
    """
    Return Webshare proxies when ``use_proxy`` is enabled.

    Args:
        use_proxy: Whether proxy usage was requested.

    Returns:
        Requests/pytubefix-compatible proxy mapping or None.

    Raises:
        ConfigurationError: When proxy is enabled but credentials are missing.
    """
    if not use_proxy:
        return None

    username = os.getenv("WEBSHARE_PROXY_USERNAME")
    password = os.getenv("WEBSHARE_PROXY_PASSWORD")
    if not username or not password:
        raise ConfigurationError(
            "use_proxy is true, but WEBSHARE_PROXY_USERNAME and "
            "WEBSHARE_PROXY_PASSWORD are missing."
        )

    proxy_url = (
        f"http://{username}:{password}@{WEBSHARE_PROXY_HOST}:{WEBSHARE_PROXY_PORT}"
    )
    return {"http": proxy_url, "https": proxy_url}
