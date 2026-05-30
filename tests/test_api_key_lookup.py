"""Tests for provider API key discovery."""

import pytest

from summarizer.config import get_api_key
from summarizer.exceptions import APIKeyError


def test_nvidia_lookup_accepts_documented_env_name(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    monkeypatch.delenv("nvidia", raising=False)

    result = get_api_key({"base_url": "https://integrate.api.nvidia.com/v1"})

    assert result == "nvapi-test"


def test_nvidia_lookup_accepts_lowercase_alias(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("nvidia", "nvapi-lowercase")

    result = get_api_key({"base_url": "https://integrate.api.nvidia.com/v1"})

    assert result == "nvapi-lowercase"


def test_nvidia_lookup_accepts_legacy_provider_pattern_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("nvidia", raising=False)
    monkeypatch.setenv("integrate.api.nvidia.com", "nvapi-pattern")

    result = get_api_key({"base_url": "https://integrate.api.nvidia.com/v1"})

    assert result == "nvapi-pattern"


def test_missing_nvidia_key_lists_env_keys_not_provider_patterns(monkeypatch):
    for env_var in (
        "NVIDIA_API_KEY",
        "nvidia",
        "integrate.api.nvidia.com",
        "integrate",
        "api_key",
    ):
        monkeypatch.delenv(env_var, raising=False)

    with pytest.raises(APIKeyError) as exc_info:
        get_api_key({"base_url": "https://integrate.api.nvidia.com/v1"})

    message = str(exc_info.value)
    assert "Matched provider: integrate.api.nvidia.com" in message
    assert (
        "Set one of these .env keys: NVIDIA_API_KEY, nvidia, "
        "integrate.api.nvidia.com"
    ) in message
    assert "generativelanguage.googleapis.com" not in message
