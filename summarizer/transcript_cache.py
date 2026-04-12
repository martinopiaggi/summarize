"""In-memory transcript cache.

Transcripts are keyed by a SHA-256 hash of the config parameters that
affect transcription output.  The cache lives in process memory and is
cleared when the process exits.
"""

import hashlib
from typing import Optional, Dict, Tuple

_cache: Dict[str, str] = {}


def _build_cache_key(config: dict) -> str:
    """Build a deterministic cache key from transcript-relevant config."""
    parts = [
        config.get("source_url_or_path", ""),
        config.get("language", "auto"),
        config.get("transcription_method", "Cloud Whisper"),
        config.get("whisper_model", "tiny"),
        str(config.get("audio_speed", 1.0)),
        str(config.get("use_youtube_captions", True)),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_cached_transcript(config: dict) -> Tuple[Optional[str], str]:
    """Look up a cached transcript.

    Returns:
        (transcript_or_None, cache_key_hex)
    """
    key = _build_cache_key(config)
    return _cache.get(key), key


def put_cached_transcript(config: dict, transcript: str) -> str:
    """Store a transcript in the cache.

    Returns:
        The cache key that was used.
    """
    key = _build_cache_key(config)
    _cache[key] = transcript
    return key


def clear_cache() -> None:
    """Drop all cached transcripts."""
    _cache.clear()


def cache_info() -> Dict[str, int]:
    """Return basic cache statistics."""
    return {
        "entries": len(_cache),
        "total_chars": sum(len(v) for v in _cache.values()),
    }
