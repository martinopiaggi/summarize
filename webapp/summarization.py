"""Adapter between the Streamlit UI and ``summarizer.core.main``.

Assembles the runtime config dict from provider/sidebar inputs and
wires the progress callback to a Streamlit status container.
"""

from webapp.config import (
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    coerce_int,
    get_cobalt_url,
    load_config,
)

_STATUS_ICONS = {
    "INFO": "\u2139",      # ℹ
    "SUCCESS": "\u2713",   # ✓
    "ERROR": "\u2717",     # ✗
    "WARNING": "\u26a0",   # ⚠
    "PROCESSING": "\u27f3",  # ⟳
}


def run_summarization(
    source: str,
    provider_config: dict,
    prompt_type: str,
    chunk_size: int,
    force_download: bool,
    language: str,
    audio_speed: float,
    source_type: str = "YouTube Video",
    transcription_method: str = "Cloud Whisper",
    whisper_model: str = "tiny",
    verbose: bool = False,
    status_container=None,
    video_engine: str = "auto",
    gemini_model: str = "gemini-2.5-flash",
) -> str:
    """Run the summarizer pipeline and return the generated markdown."""
    from summarizer.core import main
    from summarizer.progress import set_progress_callback, clear_progress_callback

    _, _, defaults = load_config()

    parallel_api_calls = coerce_int(
        provider_config.get(
            "parallel_api_calls",
            defaults.get("parallel_api_calls", 30),
        ),
        30,
        minimum=1,
        maximum=100,
    )
    max_output_tokens = coerce_int(
        provider_config.get(
            "max_output_tokens",
            defaults.get("max_output_tokens", 4096),
        ),
        4096,
        minimum=1,
    )
    effective_chunk_size = coerce_int(
        chunk_size,
        defaults.get("chunk_size", 10000),
        minimum=MIN_CHUNK_SIZE,
        maximum=MAX_CHUNK_SIZE,
    )

    config = {
        "source_url_or_path": source,
        "type_of_source": source_type,
        "use_youtube_captions": not force_download and source_type == "YouTube Video",
        "transcription_method": transcription_method,
        "whisper_model": whisper_model,
        "audio_speed": audio_speed,
        "language": language,
        "prompt_type": prompt_type,
        "chunk_size": effective_chunk_size,
        "parallel_api_calls": parallel_api_calls,
        "max_output_tokens": max_output_tokens,
        "cobalt_base_url": get_cobalt_url(),
        "use_proxy": bool(defaults.get("use_proxy", False)),
        "base_url": provider_config.get("base_url"),
        "model": provider_config.get("model"),
        "verbose": verbose,
        "cache_transcript": bool(defaults.get("cache_transcript", True)),
        # Multimodal / Gemini Files plumbing. Defaults come from the
        # YAML defaults: section so the user controls the flow centrally.
        "enable_visual": bool(defaults.get("enable_visual", False)),
        "visual_max_duration": int(defaults.get("visual_max_duration", 180)),
        "visual_max_dimension": int(defaults.get("visual_max_dimension", 768)),
        "video_engine": str(video_engine or defaults.get("video_engine") or "auto").lower(),
        "gemini_model": gemini_model or defaults.get("gemini_model", "gemini-2.5-flash"),
        "output_language": defaults.get("output_language"),
    }

    if status_container is not None:
        def _callback(message: str, status: str) -> None:
            icon = _STATUS_ICONS.get(status, "\u2022")
            status_container.write(f"`{icon}` {message}")
        set_progress_callback(_callback)

    try:
        return main(config)
    finally:
        if status_container is not None:
            clear_progress_callback()
