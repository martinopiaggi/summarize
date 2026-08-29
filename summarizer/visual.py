"""Visual-mode orchestration helpers for direct video-to-model pipeline."""

import base64
import html
import json
import os
import re
import subprocess
import tempfile
import uuid
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

from .downloaders import DownloadManager
from .exceptions import (
    AudioProcessingError,
    SourceNotFoundError,
    VideoValidationError,
    VisualModeError,
)
from .handlers import (
    build_google_drive_download_url,
    extract_google_drive_confirm_url,
    extract_google_drive_file_id,
    is_dropbox_url,
    is_google_drive_url,
    normalize_dropbox_url,
)
from .progress import ProgressSpinner, print_status
from .proxy import get_proxies, should_proxy_url

# Hardcoded YouTube hosts for URL passthrough mode.
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def get_visual_profile(config: Dict) -> Dict:
    """Return the generic visual profile with hardcoded defaults."""
    max_duration = config.get("visual_max_duration_seconds")
    max_size = config.get("visual_max_size_mb")

    return {
        "name": "openai-video",
        "max_duration_seconds": 120 if max_duration is None else max_duration,
        "max_file_mb": 100 if max_size is None else max_size,
        "formats": {"mp4", "mpeg", "mov", "webm"},
        "supported_mime_types": {"video/mp4", "video/mpeg", "video/quicktime", "video/webm"},
        "supports_chunking": True,
        "visual_input_mode": config.get("visual_input_mode") or "base64",
    }


def resolve_visual_url(config: Dict, profile: Optional[Dict] = None) -> Optional[str]:
    """
    Return a direct video URL for URL mode, or None to fall back to base64.

    URL mode is only supported for YouTube URLs. Local files fall back to
    base64 mode; non-YouTube remote URLs raise a clear configuration error.
    """
    input_mode = config.get("visual_input_mode") or (profile or {}).get("visual_input_mode") or "base64"
    if input_mode != "url":
        return None

    source_type = config.get("type_of_source", "YouTube Video")
    source = config.get("source_url_or_path", "")

    if source_type == "TXT":
        raise VisualModeError(
            "Visual mode does not support TXT sources because there is no video to send."
        )

    # Local files always use base64 mode
    if source_type == "Local File":
        return None

    # Validate host against hardcoded YouTube hosts
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()

    matched = any(
        host == yt_host or host.endswith("." + yt_host)
        for yt_host in _YOUTUBE_HOSTS
    )
    if not matched:
        raise VisualModeError(
            "visual-input-mode: url only supports YouTube URLs. "
            "Use base64 mode for other sources."
        )

    # URL passthrough cannot apply speed preprocessing; fall back to download path.
    if _build_speed_filters(_get_speed(config)):
        print_status(
            "Non-default speed requires base64 mode; downloading video for preprocessing",
            "INFO",
            config.get("verbose", False),
        )
        return None

    return source


def resolve_video_source(config: Dict) -> Tuple[str, bool]:
    """
    Resolve the source into a local video path and a cleanup flag.

    Returns:
        Tuple of (local_video_path, should_delete)
    """
    source_type = config.get("type_of_source", "YouTube Video")
    source = config.get("source_url_or_path", "")
    verbose = config.get("verbose", False)
    use_proxy = config.get("use_proxy", False)

    if source_type == "Local File":
        if not os.path.exists(source):
            raise SourceNotFoundError(f"Local file not found: {source}")
        return source, False

    if source_type == "TXT":
        raise VisualModeError(
            "Visual mode does not support TXT sources because there is no video to send."
        )

    if source_type in ("YouTube Video", "Video URL"):
        dm = DownloadManager(config.get("cobalt_base_url"))
        path = dm.download_video(
            source, temp_dir=None, verbose=verbose, use_proxy=use_proxy
        )
        return path, True

    if source_type == "Google Drive Video Link":
        return _download_google_drive_video(source, verbose, use_proxy)

    if source_type == "Dropbox Video Link":
        return _download_dropbox_video(source, verbose, use_proxy)

    raise VisualModeError(
        f"Visual mode does not support source type: {source_type}"
    )


def _download_google_drive_video(
    url: str, verbose: bool, use_proxy: bool
) -> Tuple[str, bool]:
    """Download a Google Drive shared video to a temp file."""
    file_id = extract_google_drive_file_id(url)
    if not file_id:
        raise SourceNotFoundError(
            "Could not extract a Google Drive file ID from the shared link"
        )

    download_url = build_google_drive_download_url(file_id)
    proxies = get_proxies(use_proxy) if should_proxy_url(download_url, use_proxy) else None

    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"gdrive_visual_{uuid.uuid4().hex}.mp4")

    spinner = ProgressSpinner("Downloading Google Drive video", verbose)
    session = requests.Session()
    response = None
    try:
        spinner.start()
        response = session.get(download_url, stream=True, timeout=120, proxies=proxies)
        response.raise_for_status()

        confirm_url = extract_google_drive_confirm_url(response, file_id)
        if confirm_url:
            response.close()
            response = session.get(
                confirm_url, stream=True, timeout=120, proxies=proxies
            )
            response.raise_for_status()

        with response, open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
        spinner.stop()
        print_status("Google Drive video downloaded", "SUCCESS", verbose)
        return temp_path, True
    except Exception as exc:
        spinner.stop()
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise AudioProcessingError(f"Failed to download Google Drive video: {exc}")
    finally:
        if response is not None:
            response.close()
        session.close()


def _download_dropbox_video(
    url: str, verbose: bool, use_proxy: bool
) -> Tuple[str, bool]:
    """Download a Dropbox shared video to a temp file."""
    if not is_dropbox_url(url):
        raise SourceNotFoundError(f"Not a valid Dropbox URL: {url}")

    download_url = normalize_dropbox_url(url)
    proxies = get_proxies(use_proxy) if should_proxy_url(download_url, use_proxy) else None

    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"dropbox_visual_{uuid.uuid4().hex}.mp4")

    spinner = ProgressSpinner("Downloading Dropbox video", verbose)
    try:
        spinner.start()
        with requests.get(
            download_url, stream=True, timeout=120, proxies=proxies
        ) as response:
            response.raise_for_status()
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        spinner.stop()
        print_status("Dropbox video downloaded", "SUCCESS", verbose)
        return temp_path, True
    except Exception as exc:
        spinner.stop()
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise AudioProcessingError(f"Failed to download Dropbox video: {exc}")


def probe_video(video_path: str) -> Dict:
    """
    Probe a video file with ffprobe.

    Returns:
        Dict with duration, size_mb, container, and codec hints.
    """
    result = {
        "duration": None,
        "size_mb": None,
        "container": None,
        "video_codec": None,
        "audio_codec": None,
    }

    if not os.path.exists(video_path):
        return result

    result["size_mb"] = os.path.getsize(video_path) / (1024 * 1024)
    result["container"] = os.path.splitext(video_path)[1].lstrip(".").lower()

    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-show_entries", "stream=codec_name,codec_type",
            "-of", "json",
            video_path,
        ]
        output = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=30
        ).stdout
        data = json.loads(output or "{}")
    except (
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ):
        return result

    try:
        result["duration"] = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        pass

    for stream in data.get("streams", []):
        codec_type = (stream.get("codec_type") or "").lower()
        codec_name = (stream.get("codec_name") or "").lower()
        if codec_type == "video" and codec_name:
            result["video_codec"] = codec_name
        elif codec_type == "audio" and codec_name:
            result["audio_codec"] = codec_name

    return result


def _container_to_mime_type(container: str) -> str:
    """Map a file extension to a video MIME type."""
    mapping = {
        "mp4": "video/mp4",
        "mpeg": "video/mpeg",
        "mpg": "video/mpeg",
        "mov": "video/quicktime",
        "qt": "video/quicktime",
        "webm": "video/webm",
        "avi": "video/x-msvideo",
        "mkv": "video/x-matroska",
    }
    return mapping.get(container.lower(), f"video/{container.lower()}")


def _format_set_contains(container: str, supported_formats) -> bool:
    """Check whether a container extension or its MIME type is in supported_formats."""
    if not supported_formats:
        return True
    container_mime = _container_to_mime_type(container)
    return container in supported_formats or container_mime in supported_formats


def _format_set_contains_mp4(supported_formats) -> bool:
    """Check whether supported_formats includes MP4 (by extension or MIME type)."""
    return "mp4" in supported_formats or "video/mp4" in supported_formats


def validate_video_limits(video_path: str, profile: Dict, config: Dict) -> None:
    """Enforce provider video limits; raise VideoValidationError on violation."""
    probe = probe_video(video_path)
    duration = probe.get("duration")
    size_mb = probe.get("size_mb")

    # Allow config overrides even though CLI only exposes --visual for MVP
    max_duration = config.get("visual_max_duration_seconds") or profile.get("max_duration_seconds")
    max_size = config.get("visual_max_size_mb") or profile.get("max_file_mb")

    if max_duration is not None:
        if duration is None:
            raise VideoValidationError(
                f"Could not determine video duration, but {profile['name']} visual mode "
                f"requires a {max_duration}s limit. "
                "Ensure ffprobe is available, or run audio-only mode."
            )
        if duration > max_duration:
            raise VideoValidationError(
                f"Video duration is {duration:.0f}s, but {profile['name']} visual mode "
                f"is configured for a {max_duration}s limit. "
                "Use a shorter clip, choose Gemini Files, or run audio-only mode."
            )

    if max_size is not None and size_mb is not None and size_mb > max_size:
        raise VideoValidationError(
            f"Video file size is {size_mb:.1f} MB, but {profile['name']} visual mode "
            f"is configured for a {max_size} MB limit. "
            "Use a shorter clip, choose Gemini Files, or run audio-only mode."
        )

    # Format check (supported_mime_types takes precedence over legacy formats)
    container = probe.get("container", "")
    supported_formats = profile.get("supported_mime_types") or profile.get("formats", set())
    if supported_formats and container:
        if not _format_set_contains(container, supported_formats):
            # Build human-readable list from MIME types if present
            display_formats = sorted(
                f if not f.startswith("video/") else f.replace("video/", "")
                for f in supported_formats
            )
            raise VideoValidationError(
                f"Video container '{container}' is not supported by {profile['name']}. "
                f"Supported formats: {', '.join(display_formats)}."
            )


def format_visual_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS for visual segment labels."""
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _get_visual_chunk_seconds(profile: Dict, config: Dict) -> float:
    raw_value = config.get("visual_chunk_seconds", "auto")
    if raw_value in (None, "", "auto"):
        raw_value = profile.get("max_duration_seconds")

    try:
        chunk_seconds = float(raw_value)
    except (TypeError, ValueError):
        raise VideoValidationError(
            "visual_chunk_seconds must be a positive number or 'auto'"
        )

    if chunk_seconds <= 0:
        raise VideoValidationError("visual_chunk_seconds must be greater than 0")
    return chunk_seconds


def _get_visual_overlap_seconds(config: Dict, chunk_seconds: float) -> float:
    raw_value = config.get("visual_chunk_overlap_seconds", 0)
    try:
        overlap_seconds = float(raw_value or 0)
    except (TypeError, ValueError):
        raise VideoValidationError("visual_chunk_overlap_seconds must be a number")

    if overlap_seconds < 0:
        raise VideoValidationError("visual_chunk_overlap_seconds cannot be negative")
    if overlap_seconds >= chunk_seconds:
        raise VideoValidationError(
            "visual_chunk_overlap_seconds must be smaller than visual_chunk_seconds"
        )
    return overlap_seconds


def _get_speed(config: Dict) -> float:
    """Return the configured playback speed."""
    raw = config.get("speed", 1.0)
    try:
        speed = float(raw)
    except (TypeError, ValueError):
        raise AudioProcessingError("speed must be a positive number")
    if speed <= 0:
        raise AudioProcessingError("speed must be greater than 0")
    return speed


def _build_speed_filters(speed: float) -> List[str]:
    """Build ffmpeg filter strings for speeding up video and audio."""
    if abs(speed - 1.0) < 1e-9:
        return []

    # setpts changes video frame timestamps; atempo changes audio tempo.
    # atempo accepts 0.5..2.0 per stage, so chain stages for larger ranges.
    tempo_stages = []
    remaining = speed
    while remaining > 2.0:
        tempo_stages.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        tempo_stages.append(0.5)
        remaining /= 0.5
    if abs(remaining - 1.0) > 1e-9:
        tempo_stages.append(remaining)

    filters = [f"setpts=PTS/{speed:g}"]
    if tempo_stages:
        filters.append(",".join(f"atempo={stage:g}" for stage in tempo_stages))
    return filters


def _append_audio_encode_options(
    cmd: List[str], has_audio: bool, *, bitrate: Optional[str] = None
) -> None:
    """Append ffmpeg audio output options, using -an when the input has no audio."""
    if has_audio:
        cmd.extend(["-c:a", "aac"])
        if bitrate:
            cmd.extend(["-b:a", bitrate])
    else:
        cmd.append("-an")


def build_visual_segments(video_path: str, profile: Dict, config: Dict) -> List[Dict]:
    """
    Build timestamped visual segments for a provider duration window.

    Returns a list of dicts with start, end, duration, index, total, and timestamp.
    """
    probe = probe_video(video_path)
    duration = probe.get("duration")
    if duration is None:
        raise VideoValidationError(
            "Could not determine video duration. Ensure ffprobe is available, "
            "or run audio-only mode."
        )

    chunk_seconds = _get_visual_chunk_seconds(profile, config)
    provider_limit = profile.get("max_duration_seconds")
    if provider_limit is not None and chunk_seconds > provider_limit:
        chunk_seconds = float(provider_limit)

    overlap_seconds = _get_visual_overlap_seconds(config, chunk_seconds)
    step_seconds = chunk_seconds - overlap_seconds

    segments = []
    start = 0.0
    while start < duration:
        end = min(start + chunk_seconds, duration)
        if end <= start:
            break
        segments.append(
            {
                "index": len(segments) + 1,
                "start": start,
                "end": end,
                "duration": end - start,
                "timestamp": format_visual_timestamp(start),
                "end_timestamp": format_visual_timestamp(end),
            }
        )
        if end >= duration:
            break
        start += step_seconds

    total = len(segments)
    for segment in segments:
        segment["total"] = total
    return segments


def split_video_segments(
    video_path: str,
    segments: List[Dict],
    config: Dict,
) -> List[Dict]:
    """
    Split a video into physical segment files.

    A single segment reuses the original path. Multiple segments are re-encoded
    for accurate provider-limit boundaries.
    """
    if not segments:
        raise VideoValidationError("No valid visual segments were created")

    if len(segments) <= 1:
        return [
            {
                **segments[0],
                "path": video_path,
                "should_delete": False,
            }
        ]

    verbose = config.get("verbose", False)
    temp_dir = tempfile.gettempdir()
    segment_results = []

    for segment in segments:
        segment_path = os.path.join(
            temp_dir,
            f"visual_segment_{uuid.uuid4().hex}_{segment['index']:03d}.mp4",
        )
        time_range = f"{segment.get('timestamp', '')}-{segment.get('end_timestamp', '')}"
        spinner = ProgressSpinner(
            f"Creating visual segment {segment['index']}/{segment['total']} ({time_range})",
            verbose,
        )
        try:
            spinner.start()
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{segment['start']:.3f}",
                "-i", video_path,
                "-t", f"{segment['duration']:.3f}",
                "-map", "0:v:0",
                "-map", "0:a?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "28",
                "-c:a", "aac",
                "-b:a", "96k",
                "-movflags", "+faststart",
                segment_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            spinner.stop()
            print_status(
                f"Visual segment {segment['index']}/{segment['total']} ({time_range}) ready",
                "SUCCESS",
                verbose,
            )
            segment_results.append(
                {
                    **segment,
                    "path": segment_path,
                    "should_delete": True,
                }
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            spinner.stop()
            if os.path.exists(segment_path):
                os.remove(segment_path)
            for created_segment in segment_results:
                created_path = created_segment.get("path")
                if created_segment.get("should_delete") and created_path and os.path.exists(created_path):
                    os.remove(created_path)
            raise AudioProcessingError(f"Failed to split video segment: {exc}")

    return segment_results


def normalize_video(video_path: str, profile: Dict, config: Dict) -> str:
    """
    Remux non-MP4 files to MP4 when possible; optionally compress if enabled.

    Returns:
        Path to the normalized video (may be the same as input).
    """
    verbose = config.get("verbose", False)
    speed = _get_speed(config)
    speed_filters = _build_speed_filters(speed)
    probe = probe_video(video_path)
    container = probe.get("container", "")
    supported_formats = profile.get("supported_mime_types") or profile.get("formats", set())
    has_audio = bool(probe.get("audio_codec"))

    needs_remux = (
        supported_formats
        and _format_set_contains_mp4(supported_formats)
        and not _format_set_contains(container, supported_formats)
    )
    needs_compress = _should_compress(video_path, profile, config, probe)
    needs_speed = bool(speed_filters)

    if not needs_remux and not needs_compress and not needs_speed:
        return video_path

    temp_dir = tempfile.gettempdir()
    normalized_path = os.path.join(
        temp_dir, f"visual_normalized_{uuid.uuid4().hex}.mp4"
    )

    if needs_remux and not needs_compress and not needs_speed:
        spinner = ProgressSpinner("Remuxing video to MP4", verbose)
        try:
            spinner.start()
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-c", "copy",
                normalized_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            spinner.stop()
            print_status("Video remuxed to MP4", "SUCCESS", verbose)
            return normalized_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            spinner.stop()
            if os.path.exists(normalized_path):
                os.remove(normalized_path)
            raise AudioProcessingError(f"Failed to remux video: {exc}")

    if needs_remux and not needs_compress and needs_speed:
        spinner = ProgressSpinner("Remuxing and speeding up video", verbose)
        try:
            spinner.start()
            cmd = ["ffmpeg", "-y", "-i", video_path]
            cmd.extend(["-filter:v", speed_filters[0]])
            if len(speed_filters) > 1 and has_audio:
                cmd.extend(["-filter:a", speed_filters[1]])
            cmd.extend(["-c:v", "libx264"])
            _append_audio_encode_options(cmd, has_audio)
            cmd.append(normalized_path)
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            spinner.stop()
            print_status("Video remuxed to MP4", "SUCCESS", verbose)
            return normalized_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            spinner.stop()
            if os.path.exists(normalized_path):
                os.remove(normalized_path)
            raise AudioProcessingError(f"Failed to remux video: {exc}")

    if not needs_remux and not needs_compress and needs_speed:
        # Speed-only change: re-encode as little as possible (no scaling/CRF/fps).
        spinner = ProgressSpinner("Applying playback speed", verbose)
        try:
            spinner.start()
            cmd = ["ffmpeg", "-y", "-i", video_path]
            cmd.extend(["-filter:v", speed_filters[0]])
            if len(speed_filters) > 1 and has_audio:
                cmd.extend(["-filter:a", speed_filters[1]])
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-movflags", "+faststart",
            ])
            _append_audio_encode_options(cmd, has_audio, bitrate="96k")
            cmd.append(normalized_path)
            subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            spinner.stop()
            print_status("Playback speed applied", "SUCCESS", verbose)
            return normalized_path
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            spinner.stop()
            if os.path.exists(normalized_path):
                os.remove(normalized_path)
            raise AudioProcessingError(f"Failed to apply playback speed: {exc}")

    # Compression path
    spinner = ProgressSpinner("Compressing video to fit limits", verbose)
    try:
        spinner.start()
        video_filter = "scale='min(854,iw)':-2"
        if speed_filters:
            video_filter = f"{speed_filters[0]},{video_filter}"
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", video_filter,
            "-r", "24",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "30",
        ]
        if speed_filters and len(speed_filters) > 1 and has_audio:
            cmd.extend(["-filter:a", speed_filters[1]])
        _append_audio_encode_options(cmd, has_audio, bitrate="64k")
        cmd.append(normalized_path)
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
        spinner.stop()
        print_status("Video compressed", "SUCCESS", verbose)
        return normalized_path
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        spinner.stop()
        if os.path.exists(normalized_path):
            os.remove(normalized_path)
        raise AudioProcessingError(f"Failed to compress video: {exc}")


def _should_compress(
    video_path: str, profile: Dict, config: Dict, probe: Optional[Dict] = None
) -> bool:
    """Check whether auto-compression is enabled and the video exceeds limits."""
    compression = (config.get("visual_compression") or "off").lower()
    if compression != "auto":
        return False

    if probe is None:
        probe = probe_video(video_path)

    max_duration = config.get("visual_max_duration_seconds") or profile.get("max_duration_seconds")
    max_size = config.get("visual_max_size_mb") or profile.get("max_file_mb")
    duration = probe.get("duration")
    size_mb = probe.get("size_mb")

    if (
        profile.get("supports_chunking")
        and max_duration is not None
        and duration is not None
        and duration > max_duration
    ):
        return False

    if (
        max_duration is not None
        and duration is not None
        and duration > max_duration
        and not profile.get("supports_chunking")
    ):
        return True
    if max_size is not None and size_mb is not None and size_mb > max_size:
        return True
    return False


def encode_video_base64(video_path: str) -> str:
    """Return a data:video/<type>;base64,... URL for OpenAI-compatible providers."""
    ext = os.path.splitext(video_path)[1].lstrip(".").lower()
    mime_type = "mp4" if ext == "mp4" else "webm" if ext == "webm" else "quicktime" if ext in ("mov", "qt") else ext
    with open(video_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:video/{mime_type};base64,{encoded}"
