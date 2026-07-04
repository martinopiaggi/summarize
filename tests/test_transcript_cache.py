"""Tests for transcript cache memory + disk persistence."""

import os
from pathlib import Path

import pytest

from summarizer import transcript_cache
from summarizer.runtime_env import fill_env_defaults, normalize_explicit_keys


@pytest.fixture(autouse=True)
def reset_cache():
    transcript_cache.clear_cache()
    yield
    transcript_cache.clear_cache()


def _sample_config(**overrides):
    config = {
        "source_url_or_path": "https://youtube.com/watch?v=test123",
        "language": "auto",
        "transcription_method": "Cloud Whisper",
        "whisper_model": "tiny",
        "speed": 1.0,
        "use_youtube_captions": True,
        "output_dir": "summaries",
    }
    config.update(overrides)
    return config


def test_memory_cache_roundtrip():
    config = _sample_config()
    transcript = "Hello transcript"

    cached, key, source = transcript_cache.get_cached_transcript(config)
    assert cached is None
    assert source == "miss"

    stored_key, wrote_to_disk = transcript_cache.put_cached_transcript(config, transcript)
    assert stored_key == key
    assert wrote_to_disk is False

    cached, _, source = transcript_cache.get_cached_transcript(config)
    assert cached == transcript
    assert source == "memory"


def test_disk_cache_roundtrip(tmp_path):
    config = _sample_config(
        output_dir=str(tmp_path / "summaries"),
        cache_transcript_persist=True,
    )
    transcript = "Persisted transcript"

    transcript_cache.put_cached_transcript(config, transcript)
    transcript_cache.clear_cache()

    cached, _, source = transcript_cache.get_cached_transcript(config)
    assert cached == transcript
    assert source == "disk"

    cache_file = (
        tmp_path / "summaries" / ".cache" / "transcripts" / f"{transcript_cache._build_cache_key(config)}.txt"
    )
    assert cache_file.exists()


def test_explicit_cache_dir(tmp_path):
    cache_dir = tmp_path / "custom-cache"
    config = _sample_config(cache_transcript_dir=str(cache_dir))

    transcript_cache.put_cached_transcript(config, "custom dir transcript")
    transcript_cache.clear_cache()

    cached, _, source = transcript_cache.get_cached_transcript(config)
    assert cached == "custom dir transcript"
    assert source == "disk"
    assert list(cache_dir.glob("*.txt"))


def test_env_defaults_apply_when_not_in_yaml(monkeypatch):
    monkeypatch.setenv("SUMMARIZER_KEEP_HISTORY", "true")
    monkeypatch.setenv("SUMMARIZER_CACHE_PERSIST", "1")
    monkeypatch.setenv("SUMMARIZER_CACHE_DIR", "/tmp/summarizer-cache")

    defaults = fill_env_defaults({}, set())
    assert defaults["keep_history"] is True
    assert defaults["cache_transcript_persist"] is True
    assert defaults["cache_transcript_dir"] == "/tmp/summarizer-cache"


def test_env_defaults_respect_explicit_yaml(monkeypatch):
    monkeypatch.setenv("SUMMARIZER_KEEP_HISTORY", "true")
    monkeypatch.setenv("SUMMARIZER_CACHE_PERSIST", "true")

    raw = {"keep-history": False, "cache-transcript-persist": False}
    explicit = normalize_explicit_keys(raw.keys())
    defaults = fill_env_defaults(
        {"keep_history": False, "cache_transcript_persist": False},
        explicit,
    )
    assert defaults["keep_history"] is False
    assert defaults["cache_transcript_persist"] is False