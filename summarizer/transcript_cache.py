"""Transcript cache with optional on-disk persistence.

Transcripts are keyed by a SHA-256 hash of the config parameters that
affect transcription output.  Entries live in process memory; when disk
persistence is enabled they are also stored under the configured cache
directory (by default ``{output_dir}/.cache/transcripts``).
"""

import hashlib
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

_cache: Dict[str, str] = {}


def _build_cache_key(config: dict) -> str:
    """Build a deterministic cache key from transcript-relevant config."""
    parts = [
        config.get("source_url_or_path", ""),
        config.get("language", "auto"),
        config.get("transcription_method", "Cloud Whisper"),
        config.get("whisper_model", "tiny"),
        str(config.get("speed", 1.0)),
        str(config.get("use_youtube_captions", True)),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _resolve_cache_dir(config: dict) -> Optional[Path]:
    """Return the active on-disk cache directory, if persistence is enabled."""
    explicit = config.get("cache_transcript_dir")
    if explicit:
        path = Path(explicit)
        path.mkdir(parents=True, exist_ok=True)
        return path

    env_dir = os.environ.get("SUMMARIZER_CACHE_DIR", "").strip()
    if env_dir:
        path = Path(env_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    persist = config.get("cache_transcript_persist")
    if persist is None:
        persist = os.environ.get("SUMMARIZER_CACHE_PERSIST", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if not persist:
        return None

    output_dir = config.get("output_dir", "summaries")
    path = Path(output_dir) / ".cache" / "transcripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _disk_cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.txt"


def get_cached_transcript(config: dict) -> Tuple[Optional[str], str, str]:
    """Look up a cached transcript.

    Returns:
        (transcript_or_None, cache_key_hex, cache_source)
        where cache_source is ``"memory"``, ``"disk"``, or ``"miss"``.
    """
    key = _build_cache_key(config)

    if key in _cache:
        return _cache[key], key, "memory"

    cache_dir = _resolve_cache_dir(config)
    if cache_dir is not None:
        disk_path = _disk_cache_path(cache_dir, key)
        if disk_path.exists():
            transcript = disk_path.read_text(encoding="utf-8")
            _cache[key] = transcript
            return transcript, key, "disk"

    return None, key, "miss"


def put_cached_transcript(config: dict, transcript: str) -> Tuple[str, bool]:
    """Store a transcript in the cache.

    Returns:
        (cache_key_hex, wrote_to_disk)
    """
    key = _build_cache_key(config)
    _cache[key] = transcript

    cache_dir = _resolve_cache_dir(config)
    wrote_to_disk = False
    if cache_dir is not None:
        _disk_cache_path(cache_dir, key).write_text(transcript, encoding="utf-8")
        wrote_to_disk = True

    return key, wrote_to_disk


def clear_cache() -> None:
    """Drop all in-memory cached transcripts."""
    _cache.clear()


def cache_info() -> Dict[str, int]:
    """Return basic in-memory cache statistics."""
    return {
        "entries": len(_cache),
        "total_chars": sum(len(v) for v in _cache.values()),
    }