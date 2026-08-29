"""Shared HTTP proxy configuration."""

import ipaddress
import os
import re
from typing import Dict, NamedTuple, Optional, Tuple
from urllib.parse import quote, urlparse

from requests.utils import should_bypass_proxies

from .exceptions import ConfigurationError


WEBSHARE_PROXY_HOST = "p.webshare.io"
WEBSHARE_PROXY_PORT = "80"


class _ProxySettings(NamedTuple):
    http_url: str
    https_url: str
    source: str


def _env(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value and value.strip():
        return value.strip()
    return None


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        value = _env(name)
        if value is not None:
            return value
    return None


def _validate_proxy_url(name: str, value: str) -> str:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{name} contains an invalid port.") from exc

    if not parsed.scheme or not parsed.hostname:
        raise ConfigurationError(
            f"{name} must be an absolute proxy URL, for example "
            "http://user:password@proxy.example.com:8080."
        )
    if port is not None and not 1 <= port <= 65535:
        raise ConfigurationError(f"{name} contains an invalid port.")
    return value


def _build_component_proxy_url() -> Optional[str]:
    username = _env("PROXY_USERNAME")
    password = _env("PROXY_PASSWORD")
    host = _env("PROXY_HOST")
    port = _env("PROXY_PORT")
    configured_scheme = _env("PROXY_SCHEME")
    scheme = configured_scheme or "http"

    component_configured = any((username, password, host, port, configured_scheme))
    if not component_configured:
        return None

    if not host or not port:
        raise ConfigurationError(
            "PROXY_HOST and PROXY_PORT are required when component proxy settings "
            "are used."
        )
    if bool(username) != bool(password):
        raise ConfigurationError(
            "PROXY_USERNAME and PROXY_PASSWORD must either both be set or both be "
            "omitted."
        )
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*", scheme):
        raise ConfigurationError("PROXY_SCHEME must be a valid URL scheme.")
    if any(character in host for character in "/?#@") or any(
        character.isspace() for character in host
    ):
        raise ConfigurationError(
            "PROXY_HOST must contain only a hostname. Use PROXY_URL for a complete URL."
        )
    try:
        port_number = int(port)
    except ValueError as exc:
        raise ConfigurationError("PROXY_PORT must be an integer from 1 to 65535.") from exc
    if not 1 <= port_number <= 65535:
        raise ConfigurationError("PROXY_PORT must be an integer from 1 to 65535.")

    raw_host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    if ":" in raw_host:
        try:
            if ipaddress.ip_address(raw_host).version != 6:
                raise ValueError
        except ValueError as exc:
            raise ConfigurationError(
                "PROXY_HOST must not include a port. Set PROXY_PORT separately."
            ) from exc
        url_host = f"[{raw_host}]"
    else:
        url_host = raw_host

    auth = ""
    if username is not None and password is not None:
        auth = f"{quote(username, safe='')}:{quote(password, safe='')}@"
    return _validate_proxy_url(
        "component proxy settings",
        f"{scheme}://{auth}{url_host}:{port_number}",
    )


def _get_webshare_credentials(use_proxy: bool = False) -> Optional[Tuple[str, str]]:
    """Return legacy Webshare credentials for backward compatibility."""
    if not use_proxy:
        return None

    username = _env("WEBSHARE_PROXY_USERNAME")
    password = _env("WEBSHARE_PROXY_PASSWORD")
    if not username or not password:
        raise ConfigurationError(
            "WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD must both be set."
        )
    return username, password


def _legacy_webshare_url(username: str, password: str) -> str:
    user = quote(username, safe="")
    encoded_password = quote(password, safe="")
    return (
        f"http://{user}:{encoded_password}@"
        f"{WEBSHARE_PROXY_HOST}:{WEBSHARE_PROXY_PORT}"
    )


def _resolve_proxy_settings(use_proxy: bool = False) -> Optional[_ProxySettings]:
    if not use_proxy:
        return None

    http_url = _env("PROXY_HTTP_URL")
    https_url = _env("PROXY_HTTPS_URL")
    if http_url or https_url:
        http_url = _validate_proxy_url("PROXY_HTTP_URL", http_url or https_url or "")
        https_url = _validate_proxy_url("PROXY_HTTPS_URL", https_url or http_url)
        return _ProxySettings(http_url, https_url, "generic")

    proxy_url = _env("PROXY_URL")
    if proxy_url:
        proxy_url = _validate_proxy_url("PROXY_URL", proxy_url)
        return _ProxySettings(proxy_url, proxy_url, "generic")

    component_url = _build_component_proxy_url()
    if component_url:
        return _ProxySettings(component_url, component_url, "generic")

    legacy_username = _env("WEBSHARE_PROXY_USERNAME")
    legacy_password = _env("WEBSHARE_PROXY_PASSWORD")
    if legacy_username or legacy_password:
        credentials = _get_webshare_credentials(True)
        assert credentials is not None
        legacy_url = _legacy_webshare_url(*credentials)
        return _ProxySettings(legacy_url, legacy_url, "webshare")

    all_proxy = _first_env("ALL_PROXY", "all_proxy")
    http_url = _first_env("HTTP_PROXY", "http_proxy") or all_proxy
    https_url = _first_env("HTTPS_PROXY", "https_proxy") or all_proxy
    if http_url or https_url:
        http_url = _validate_proxy_url("HTTP_PROXY", http_url or https_url or "")
        https_url = _validate_proxy_url("HTTPS_PROXY", https_url or http_url)
        return _ProxySettings(http_url, https_url, "environment")

    raise ConfigurationError(
        "use_proxy is true, but no proxy is configured. Set PROXY_URL, "
        "PROXY_HTTP_URL/PROXY_HTTPS_URL, PROXY_HOST/PROXY_PORT, or standard "
        "HTTP_PROXY/HTTPS_PROXY/ALL_PROXY variables."
    )


def get_proxy_url(
    use_proxy: bool = False, target_url: Optional[str] = None
) -> Optional[str]:
    """Return the configured proxy URL for an optional target URL."""
    settings = _resolve_proxy_settings(use_proxy)
    if settings is None:
        return None

    if (urlparse(target_url or "").scheme or "").lower() == "http":
        return settings.http_url
    return settings.https_url


def get_proxies(use_proxy: bool = False) -> Optional[Dict[str, str]]:
    """Return a requests/pytubefix-compatible proxy mapping."""
    settings = _resolve_proxy_settings(use_proxy)
    if settings is None:
        return None
    return {"http": settings.http_url, "https": settings.https_url}


def get_webshare_proxy_url(use_proxy: bool = False) -> Optional[str]:
    """Return the legacy Webshare proxy URL (deprecated compatibility helper)."""
    credentials = _get_webshare_credentials(use_proxy)
    if credentials is None:
        return None
    return _legacy_webshare_url(*credentials)


def get_webshare_proxies(use_proxy: bool = False) -> Optional[Dict[str, str]]:
    """Return legacy Webshare proxies (deprecated compatibility helper)."""
    proxy_url = get_webshare_proxy_url(use_proxy)
    if proxy_url is None:
        return None
    return {"http": proxy_url, "https": proxy_url}


def get_youtube_transcript_proxy_config(use_proxy: bool = False):
    """Return the appropriate youtube-transcript-api proxy configuration."""
    settings = _resolve_proxy_settings(use_proxy)
    if settings is None:
        return None

    if settings.source == "webshare":
        try:
            from youtube_transcript_api.proxies import WebshareProxyConfig
        except ImportError as exc:
            raise ConfigurationError(
                "youtube-transcript-api Webshare proxy support is unavailable."
            ) from exc

        credentials = _get_webshare_credentials(True)
        assert credentials is not None
        return WebshareProxyConfig(
            proxy_username=credentials[0],
            proxy_password=credentials[1],
        )

    try:
        from youtube_transcript_api.proxies import GenericProxyConfig
    except ImportError as exc:
        raise ConfigurationError(
            "youtube-transcript-api generic proxy support is unavailable."
        ) from exc

    return GenericProxyConfig(
        http_url=settings.http_url,
        https_url=settings.https_url,
    )


def _is_local_hostname(hostname: str) -> bool:
    if not hostname:
        return True
    if hostname == "host.docker.internal" or hostname.endswith((".localhost", ".local")):
        return True
    if "." not in hostname and ":" not in hostname:
        return True

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return not address.is_global


def should_proxy_url(url: str, use_proxy: bool = False) -> bool:
    """
    Decide whether a request should use the configured proxy.

    Loopback, private/link-local IPs, local service names, Groq, and targets
    covered by NO_PROXY stay direct.
    """
    if not use_proxy:
        return False

    parsed = urlparse(url or "")
    hostname = (parsed.hostname or "").lower()
    if _is_local_hostname(hostname):
        return False
    if hostname == "api.groq.com" or hostname.endswith(".groq.com"):
        return False
    if should_bypass_proxies(url, no_proxy=None):
        return False

    return _resolve_proxy_settings(True) is not None
