"""Video-to-model API call for visual mode."""

import asyncio
import logging
from typing import Any, Dict, List, Tuple

import aiohttp

from .api import parse_response_content
from .exceptions import APIError, ConfigurationError, VideoValidationError
from .progress import print_status
from .prompts import load_prompt_template
from .proxy import get_webshare_proxy_url, should_proxy_url

logger = logging.getLogger(__name__)


def build_visual_messages(
    config: Dict,
    data_url: str,
) -> List[Dict[str, Any]]:
    """Build OpenAI-compatible messages for a visual-mode request."""
    prompt_type = config.get("prompt_type", "Questions and answers")
    output_language = config.get("output_language")

    template = load_prompt_template(prompt_type)
    visual_placeholder = (
        "the attached video, including its audio, visible text, scenes, and actions"
    )
    try:
        user_text = template.format(text=visual_placeholder)
    except KeyError:
        user_text = template

    segment_start = config.get("visual_segment_start")
    segment_end = config.get("visual_segment_end")
    segment_index = config.get("visual_segment_index")
    segment_total = config.get("visual_segment_total")
    if segment_start and segment_end:
        segment_context = (
            f"This is video segment {segment_index}/{segment_total}, "
            f"covering {segment_start} to {segment_end}. "
            "Summarize only this segment, but preserve any visible text, actions, "
            "scene changes, and spoken audio that matter for the overall video.\n\n"
        )
        user_text = segment_context + user_text

    system_content = (
        "You are a helpful assistant specializing in video content analysis. "
        "Always provide direct responses based on the attached video without asking for more content."
    )
    if output_language and str(output_language).strip().lower() not in ("auto", "none", ""):
        system_content += (
            f" Always write your response in {output_language}, "
            f"regardless of the language of the video."
        )

    return [
        {"role": "system", "content": system_content},
        {
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": data_url}},
                {"type": "text", "text": user_text},
            ],
        },
    ]


def _check_base64_payload_size(video_path: str, profile: Dict, config: Dict) -> None:
    """Guard against oversized base64 payloads before encoding."""
    import os

    max_size_mb = config.get("visual_max_size_mb") or profile.get("max_file_mb")
    if max_size_mb is None:
        return

    file_size_bytes = os.path.getsize(video_path)
    estimated_payload_mb = (file_size_bytes * 1.34) / (1024 * 1024)

    if estimated_payload_mb > max_size_mb:
        raise VideoValidationError(
            f"Video segment payload is estimated at {estimated_payload_mb:.1f} MB "
            f"(base64 of {file_size_bytes / (1024 * 1024):.1f} MB file), "
            f"but {profile['name']} visual mode has a {max_size_mb} MB limit. "
            "Try a lower visual-chunk-seconds value, enable visual-compression: auto, "
            "or use a lower-resolution source."
        )


def _is_url_or_data_url(value: str) -> bool:
    """Return True if value looks like a http(s) or data URL."""
    return value.startswith(("http://", "https://", "data:"))


def build_visual_payload(
    config: Dict,
    video_path_or_url: str,
    profile: Dict,
) -> Dict[str, Any]:
    """Build the OpenAI-compatible JSON payload for visual mode."""
    from .visual import encode_video_base64

    model = config.get("model", "")
    max_output_tokens = config.get("max_output_tokens", 4096)

    if _is_url_or_data_url(video_path_or_url):
        data_url = video_path_or_url
    else:
        _check_base64_payload_size(video_path_or_url, profile, config)
        data_url = encode_video_base64(video_path_or_url)

    messages = build_visual_messages(config, data_url)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_output_tokens,
    }

    return payload


async def process_video(
    config: Dict,
    video_path: str,
    profile: Dict,
    max_retries: int = 3,
) -> str:
    """
    Send a video to a video-capable model and return the summary.

    Args:
        config: Runtime configuration dictionary.
        video_path: Path to the local video file.
        profile: Provider profile dict from ``visual.py``.
        max_retries: Number of retry attempts for transient failures.

    Returns:
        Summary text from the model.
    """
    return await _process_video_openai_url(config, video_path, profile, max_retries)


async def process_video_segments(
    config: Dict,
    segments: List[Dict],
    profile: Dict,
    max_retries: int = 3,
) -> List[Tuple[str, str]]:
    """Process timestamped visual segments sequentially."""
    verbose = config.get("verbose", False)
    results: List[Tuple[str, str]] = []

    for segment in segments:
        segment_config = dict(config)
        segment_config.update(
            {
                "visual_segment_start": segment.get("timestamp"),
                "visual_segment_end": segment.get("end_timestamp"),
                "visual_segment_index": segment.get("index"),
                "visual_segment_total": segment.get("total"),
            }
        )
        time_range = f"{segment.get('timestamp', '')}-{segment.get('end_timestamp', '')}"
        print_status(
            f"Processing visual segment {segment.get('index')}/{segment.get('total')} ({time_range})",
            "PROCESSING",
            verbose,
        )
        summary = await process_video(
            segment_config,
            segment["path"],
            profile,
            max_retries=max_retries,
        )
        if summary and summary.strip():
            results.append((segment.get("timestamp", ""), summary.strip()))

    return results


def _segment_context(config: Dict) -> str:
    """Build a short segment context string for error messages."""
    index = config.get("visual_segment_index")
    total = config.get("visual_segment_total")
    start = config.get("visual_segment_start")
    end = config.get("visual_segment_end")
    if index is not None and total is not None:
        return f" [segment {index}/{total} {start}-{end}]"
    return ""


async def _process_video_openai_url(
    config: Dict,
    video_path: str,
    profile: Dict,
    max_retries: int = 3,
) -> str:
    """OpenAI-compatible ``video_url`` path (NVIDIA, OpenRouter, etc.)."""
    verbose = config.get("verbose", False)
    base_url = config.get("base_url", "")
    model = config.get("model", "")
    api_key = config.get("api_key", "")
    seg_ctx = _segment_context(config)

    if not base_url or not model:
        raise ConfigurationError("base_url and model are required for visual mode")
    if not api_key:
        raise ConfigurationError("API key is required for visual mode")
    if "generativelanguage.googleapis.com" in base_url.lower():
        raise ConfigurationError(
            "Direct Google Gemini's OpenAI-compatible endpoint does not support "
            "video_url content parts. Use an OpenAI-compatible video provider "
            "such as OpenRouter for YouTube URL passthrough, or disable visual mode."
        )

    payload = build_visual_payload(config, video_path, profile)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = f"{base_url}/chat/completions"
    proxy = None
    if should_proxy_url(url, bool(config.get("use_proxy", False))):
        proxy = get_webshare_proxy_url(True)

    data_url = payload["messages"][1]["content"][0]["video_url"]["url"]
    print_status(
        f"Sending video to {model} ({len(data_url) / 1024 / 1024:.1f} MB payload){seg_ctx}",
        "PROCESSING",
        verbose,
    )

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    proxy=proxy,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Visual API request failed{seg_ctx} (attempt {attempt + 1}/{max_retries}): {error_text}"
                            )
                            await asyncio.sleep(2 ** attempt)
                            continue
                        raise APIError(
                            f"Visual API request failed after {max_retries} attempts{seg_ctx}: {error_text}"
                        )

                    result = await response.json()
                    content = parse_response_content(result, base_url)

                    if "please provide" in content.lower() or "please share" in content.lower():
                        return ""

                    print_status(f"Visual summarization completed{seg_ctx}", "SUCCESS", verbose)
                    return content

        except asyncio.CancelledError:
            return ""
        except APIError:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"Visual request error{seg_ctx} (attempt {attempt + 1}/{max_retries}): {e}"
                )
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error(f"Visual request failed after {max_retries} attempts{seg_ctx}: {e}")
                raise APIError(f"Visual API request failed{seg_ctx}: {e}")

    return ""
