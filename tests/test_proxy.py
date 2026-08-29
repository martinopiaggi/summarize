"""Tests for HTTP proxy configuration."""

import pytest

from summarizer.exceptions import ConfigurationError
from summarizer.proxy import (
    get_proxies,
    get_proxy_url,
    get_webshare_proxies,
    get_webshare_proxy_url,
    get_youtube_transcript_proxy_config,
    should_proxy_url,
)


PROXY_ENV_KEYS = (
    "PROXY_URL",
    "PROXY_HTTP_URL",
    "PROXY_HTTPS_URL",
    "PROXY_USERNAME",
    "PROXY_PASSWORD",
    "PROXY_HOST",
    "PROXY_PORT",
    "PROXY_SCHEME",
    "WEBSHARE_PROXY_USERNAME",
    "WEBSHARE_PROXY_PASSWORD",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    for key in PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _set_component_proxy_env(monkeypatch):
    monkeypatch.setenv("PROXY_USERNAME", "user")
    monkeypatch.setenv("PROXY_PASSWORD", "pass")
    monkeypatch.setenv("PROXY_HOST", "proxy.example.com")
    monkeypatch.setenv("PROXY_PORT", "8080")


def test_disabled_returns_none():
    assert get_proxy_url(False) is None
    assert get_proxies(False) is None
    assert get_youtube_transcript_proxy_config(False) is None


def test_missing_settings_raise():
    with pytest.raises(ConfigurationError, match="no proxy is configured"):
        get_proxy_url(True)


def test_builds_authenticated_component_proxy_url(monkeypatch):
    _set_component_proxy_env(monkeypatch)

    url = get_proxy_url(True)
    assert url == "http://user:pass@proxy.example.com:8080"
    assert get_proxies(True) == {"http": url, "https": url}


def test_component_proxy_allows_no_auth_and_custom_scheme(monkeypatch):
    monkeypatch.setenv("PROXY_HOST", "proxy.example.com")
    monkeypatch.setenv("PROXY_PORT", "8443")
    monkeypatch.setenv("PROXY_SCHEME", "https")

    expected = "https://proxy.example.com:8443"
    assert get_proxy_url(True) == expected
    assert get_proxies(True) == {"http": expected, "https": expected}


def test_component_proxy_requires_complete_credentials(monkeypatch):
    monkeypatch.setenv("PROXY_HOST", "proxy.example.com")
    monkeypatch.setenv("PROXY_PORT", "8080")
    monkeypatch.setenv("PROXY_USERNAME", "user")

    with pytest.raises(ConfigurationError, match="must either both be set"):
        get_proxy_url(True)


def test_component_proxy_rejects_host_with_embedded_port(monkeypatch):
    monkeypatch.setenv("PROXY_HOST", "proxy.example.com:8080")
    monkeypatch.setenv("PROXY_PORT", "8080")

    with pytest.raises(ConfigurationError, match="must not include a port"):
        get_proxy_url(True)


def test_quotes_special_characters_in_component_credentials(monkeypatch):
    monkeypatch.setenv("PROXY_USERNAME", "user")
    monkeypatch.setenv("PROXY_PASSWORD", "p@ss:word")
    monkeypatch.setenv("PROXY_HOST", "proxy.example.com")
    monkeypatch.setenv("PROXY_PORT", "8443")

    assert get_proxy_url(True) == "http://user:p%40ss%3Aword@proxy.example.com:8443"


def test_accepts_complete_proxy_url(monkeypatch):
    monkeypatch.setenv("PROXY_URL", "https://proxy.example.com:8443")

    expected = "https://proxy.example.com:8443"
    assert get_proxy_url(True) == expected
    assert get_proxies(True) == {"http": expected, "https": expected}


def test_split_proxy_urls_follow_target_scheme(monkeypatch):
    monkeypatch.setenv("PROXY_HTTP_URL", "http://plain-proxy.example.com:8080")
    monkeypatch.setenv("PROXY_HTTPS_URL", "https://secure-proxy.example.com:8443")

    assert get_proxy_url(True, "http://example.com") == (
        "http://plain-proxy.example.com:8080"
    )
    assert get_proxy_url(True, "https://example.com") == (
        "https://secure-proxy.example.com:8443"
    )
    assert get_proxies(True) == {
        "http": "http://plain-proxy.example.com:8080",
        "https": "https://secure-proxy.example.com:8443",
    }


def test_standard_proxy_environment_is_supported(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://plain-proxy.example.com:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://secure-proxy.example.com:8080")

    assert get_proxy_url(True, "http://example.com") == (
        "http://plain-proxy.example.com:8080"
    )
    assert get_proxy_url(True, "https://example.com") == (
        "http://secure-proxy.example.com:8080"
    )


def test_invalid_complete_proxy_url_is_rejected(monkeypatch):
    monkeypatch.setenv("PROXY_URL", "proxy.example.com:8080")

    with pytest.raises(ConfigurationError, match="absolute proxy URL"):
        get_proxy_url(True)


def test_should_proxy_url_skips_local_private_groq_and_no_proxy(monkeypatch):
    _set_component_proxy_env(monkeypatch)
    monkeypatch.setenv("NO_PROXY", ".direct.example.com")

    assert should_proxy_url("https://www.instagram.com/reel/123", True)
    assert should_proxy_url("https://www.youtube.com/watch?v=abc", True)
    assert not should_proxy_url("https://api.groq.com/openai/v1", True)
    assert not should_proxy_url("http://localhost:9000/api", True)
    assert not should_proxy_url("http://ollama:11434/api", True)
    assert not should_proxy_url("http://host.docker.internal:11434/api", True)
    assert not should_proxy_url("http://192.168.1.10:11434/api", True)
    assert not should_proxy_url("http://service.local:8080/api", True)
    assert not should_proxy_url("https://api.direct.example.com/v1", True)
    assert not should_proxy_url("https://www.instagram.com/reel/123", False)


def test_youtube_transcript_uses_generic_proxy_config(monkeypatch):
    monkeypatch.setenv("PROXY_HTTP_URL", "http://plain-proxy.example.com:8080")
    monkeypatch.setenv("PROXY_HTTPS_URL", "https://secure-proxy.example.com:8443")

    config = get_youtube_transcript_proxy_config(True)
    from youtube_transcript_api.proxies import GenericProxyConfig

    assert isinstance(config, GenericProxyConfig)
    assert config.to_requests_dict() == {
        "http": "http://plain-proxy.example.com:8080",
        "https": "https://secure-proxy.example.com:8443",
    }


def test_legacy_webshare_settings_and_helpers_remain_supported(monkeypatch):
    monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "legacy-user")
    monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "legacy-pass")

    expected = "http://legacy-user:legacy-pass@p.webshare.io:80"
    assert get_proxy_url(True) == expected
    assert get_proxy_url(True, "http://example.com") == expected
    assert get_proxies(True) == {"http": expected, "https": expected}
    assert get_webshare_proxy_url(True) == expected
    assert get_webshare_proxies(True) == {"http": expected, "https": expected}


def test_legacy_webshare_transcript_keeps_specialized_behavior(monkeypatch):
    monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "legacy-user")
    monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "legacy-pass")

    config = get_youtube_transcript_proxy_config(True)
    from youtube_transcript_api.proxies import WebshareProxyConfig

    assert isinstance(config, WebshareProxyConfig)
    assert config.retries_when_blocked == 10
    assert config.prevent_keeping_connections_alive is True
