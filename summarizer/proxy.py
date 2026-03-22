"""Shared Webshare proxy configuration."""

import os
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

from .exceptions import ConfigurationError

WEBSHARE_PROXY_HOST = "p.webshare.io"
WEBSHARE_PROXY_PORT = "80"


def _get_webshare_credentials(use_proxy: bool = False) -> Optional[Tuple[str, str]]:
    if not use_proxy:
        return None

    username = os.getenv("WEBSHARE_PROXY_USERNAME")
    password = os.getenv("WEBSHARE_PROXY_PASSWORD")
    if not username or not password:
        raise ConfigurationError(
            "use_proxy is true, but WEBSHARE_PROXY_USERNAME and "
            "WEBSHARE_PROXY_PASSWORD are missing."
        )

    return username, password


def get_webshare_proxy_url(use_proxy: bool = False) -> Optional[str]:
    """
    Return a Webshare proxy URL when ``use_proxy`` is enabled.

    Raises:
        ConfigurationError: When proxy is enabled but credentials are missing.
    """
    credentials = _get_webshare_credentials(use_proxy)
    if credentials is None:
        return None

    username, password = credentials
    return f"http://{username}:{password}@{WEBSHARE_PROXY_HOST}:{WEBSHARE_PROXY_PORT}"


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
    proxy_url = get_webshare_proxy_url(use_proxy)
    if proxy_url is None:
        return None
    return {"http": proxy_url, "https": proxy_url}


def get_youtube_transcript_proxy_config(use_proxy: bool = False):
    """
    Return a youtube-transcript-api proxy config when ``use_proxy`` is enabled.

    Raises:
        ConfigurationError: When proxy is enabled but credentials are missing or
            the installed youtube-transcript-api version lacks proxy support.
    """
    credentials = _get_webshare_credentials(use_proxy)
    if credentials is None:
        return None

    try:
        from youtube_transcript_api.proxies import WebshareProxyConfig
    except ImportError as exc:
        raise ConfigurationError(
            "youtube-transcript-api proxy support is unavailable. "
            "Install a version that includes WebshareProxyConfig."
        ) from exc

    username, password = credentials
    return WebshareProxyConfig(
        proxy_username=username,
        proxy_password=password,
    )


def should_proxy_url(url: str, use_proxy: bool = False) -> bool:
    """
    Decide whether a request should use the Webshare proxy.

    Groq and local/Cobalt endpoints stay direct. Everything else follows the
    ``use_proxy`` flag.
    """
    hostname = (urlparse(url or "").hostname or "").lower()
    if hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    if hostname == "api.groq.com" or hostname.endswith(".groq.com"):
        return False
    if get_webshare_proxy_url(use_proxy) is None:
        return False
    return True
