"""Gemini Files API video analysis engine.

Uploads a full video to Google's Generative Language Files API and lets
gemini-2.5-flash analyse audio + visual together. This is qualitatively
different from the Llama-4-Scout multimodal flow which sends 5 sampled
frames + a Whisper transcript: Gemini ingests the actual video stream and
its own audio understanding, so it can pick up things like ambient sounds,
fast cuts, on-screen text and visual humour that a 5-frame snapshot misses.

Free tier limits (May 2026, gemini-2.5-flash):
- 10 RPM
- 250 RPD
- 250 000 TPM
- 1 000 000 TPD
- Files API: 2 GB per file, 50 files per project, files auto-delete after 48h
- Max video duration: 7 hours (model context: 1M tokens)

The function raises GeminiVideoEngineError for any provider-side problem;
callers (e.g. core.py auto-mode) catch it and fall back to the standard
multimodal/text flow.
"""

import logging
import os
import time
from typing import Optional

from .. import config as _config_module
from ..exceptions import APIKeyError, SummarizerError


logger = logging.getLogger(__name__)


class GeminiVideoEngineError(SummarizerError):
    """Raised when the Gemini Files video flow cannot complete."""


# How long to wait for the uploaded file to leave PROCESSING. Gemini
# typically processes IG-reel-sized videos in 5-15 seconds; 120s leaves
# ample margin without dragging out an obvious failure.
_UPLOAD_PROCESSING_TIMEOUT = 120
_UPLOAD_POLL_INTERVAL = 3


def _get_gemini_api_key(config: dict) -> str:
    """Resolve the Gemini API key from explicit config or env (`generativelanguage`)."""
    if config.get("api_key") and "generativelanguage" in (config.get("base_url") or "").lower():
        return config["api_key"]
    key = os.getenv("generativelanguage") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise APIKeyError(
            "Gemini API key not found. Set 'generativelanguage' in .env or "
            "GEMINI_API_KEY in the environment."
        )
    return key


def analyze_video_with_gemini(
    video_path: str,
    prompt_text: str,
    caption: Optional[str] = None,
    output_language: Optional[str] = None,
    model: str = "gemini-2.5-flash",
    api_key: Optional[str] = None,
    max_output_tokens: int = 4096,
    verbose: bool = False,
) -> str:
    """Upload a video to Gemini Files API and ask the model to summarise it.

    Args:
        video_path: Local path to the video file (mp4/webm/mkv supported).
        prompt_text: The summarisation instruction (typically the
            prompts.json template after `{text}` substitution; with this
            engine `{text}` is replaced by an empty string because Gemini
            sees the full video).
        caption: Optional post caption / description from the platform.
            Prepended to the prompt as additional textual context.
        output_language: If set, the model is told to respond in this
            language. Mirrors the api.py system-prompt convention so the
            user-facing behaviour is consistent across engines.
        model: Gemini model to use. gemini-2.5-flash is the right balance
            of cost / quality for IG-style short videos.
        api_key: Explicit API key. Falls back to env lookup when None.
        max_output_tokens: Cap on the response size.
        verbose: Print progress updates.

    Returns:
        The summary text produced by the model.

    Raises:
        GeminiVideoEngineError: any failure in upload, processing or
            generation. The original exception is chained.
    """
    if not os.path.isfile(video_path):
        raise GeminiVideoEngineError(f"Video file not found: {video_path}")

    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise GeminiVideoEngineError(
            "google-genai is not installed. Add `google-genai>=1.0.0` to "
            "requirements and rebuild."
        ) from exc

    key = api_key or _get_gemini_api_key({"base_url": "generativelanguage"})

    if verbose:
        logger.info("Gemini Files API: uploading %s", os.path.basename(video_path))

    try:
        client = genai.Client(api_key=key)

        uploaded = client.files.upload(file=video_path)

        # The Files API returns immediately but the file is not yet usable
        # for inference. Poll until it leaves PROCESSING. Max 2 min for
        # IG-reel-sized inputs is generous; raise a clear error otherwise.
        deadline = time.time() + _UPLOAD_PROCESSING_TIMEOUT
        while True:
            state = (uploaded.state.name if hasattr(uploaded.state, "name")
                     else str(uploaded.state))
            if state == "ACTIVE":
                break
            if state == "FAILED":
                raise GeminiVideoEngineError(
                    f"Gemini reported FAILED state for uploaded video "
                    f"{uploaded.name}"
                )
            if time.time() > deadline:
                raise GeminiVideoEngineError(
                    f"Gemini Files processing timed out after "
                    f"{_UPLOAD_PROCESSING_TIMEOUT}s (state={state})"
                )
            time.sleep(_UPLOAD_POLL_INTERVAL)
            uploaded = client.files.get(name=uploaded.name)

        if verbose:
            logger.info("Gemini Files API: %s ACTIVE, generating summary",
                        uploaded.name)

        # Build the textual prompt. Gemini sees the video natively so we
        # do not feed it a transcript; the prompt template still defines
        # the OUTPUT format (Distill Wisdom, Q&A, etc.).
        text_parts = []
        if caption:
            text_parts.append(
                f"Caption from the author of the post:\n\"\"\"\n{caption}\n\"\"\""
            )
        text_parts.append(prompt_text.replace("{text}", "").strip())
        if output_language and str(output_language).strip().lower() not in ("auto", "none", ""):
            text_parts.append(
                f"Always write your response in {output_language}, "
                f"regardless of the language spoken in the video."
            )
        full_prompt = "\n\n".join(p for p in text_parts if p)

        response = client.models.generate_content(
            model=model,
            contents=[uploaded, full_prompt],
            config=genai_types.GenerateContentConfig(
                max_output_tokens=max_output_tokens,
            ),
        )

        # Best-effort cleanup. Files auto-delete after 48h anyway, but we
        # delete eagerly to stay well under the 50-files-per-project quota.
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass

        text = (response.text or "").strip()
        if not text:
            raise GeminiVideoEngineError(
                "Gemini returned an empty response"
            )
        return text

    except GeminiVideoEngineError:
        raise
    except Exception as exc:
        raise GeminiVideoEngineError(
            f"Gemini Files API call failed: {type(exc).__name__}: {exc}"
        ) from exc
