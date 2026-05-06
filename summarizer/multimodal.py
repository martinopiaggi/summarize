"""Visual frame extraction for multimodal video summarization.

Extracts a small fixed number of evenly-spaced JPEG frames from a video file
using ffmpeg, resizes them, and returns base64-encoded data URLs ready for the
OpenAI-compatible chat completions image_url payload.

The 5-frames cap exists because Llama-4-Scout on Groq currently rejects
requests with more than 5 images (`error: "This model supports up to 5
images"`). Other vision-capable models may have different limits — adjust
`MAX_FRAMES_HARD_CAP` if you change provider/model.
"""

import base64
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional

from .exceptions import AudioProcessingError


# Groq Llama-4-Scout hard cap, May 2026. Trying to send more returns
# "Too many images provided. This model supports up to 5 images".
MAX_FRAMES_HARD_CAP = 5


def ffprobe_duration(video_path: str) -> Optional[float]:
    """Return duration of the video in seconds, or None if probing fails."""
    if not os.path.isfile(video_path):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return None
        return float(result.stdout.strip())
    except (ValueError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def extract_video_frames(
    video_path: str,
    n_frames: int = MAX_FRAMES_HARD_CAP,
    max_dimension: int = 768,
    output_dir: Optional[str] = None,
) -> List[str]:
    """Extract `n_frames` evenly-distributed JPEG frames from `video_path`.

    Frames are sampled at timestamps `duration * (i + 0.5) / n_frames` for
    i in 0..n_frames-1 — i.e. centered within their share of the timeline,
    which gives a more representative slice than starting at exactly t=0
    (often a black frame or splash) and ending at the end (often a fadeout).

    Args:
        video_path: Path to a video file readable by ffmpeg.
        n_frames: How many frames to extract. Capped at MAX_FRAMES_HARD_CAP
            because Llama-4-Scout on Groq rejects more than that.
        max_dimension: Maximum length of the longer side after resize. Keeps
            tokens reasonable while preserving enough detail for the model.
        output_dir: Where to write the frame files. If None, a tmpdir is used
            and cleaned up at the end (frames are returned as base64 anyway).

    Returns:
        List of base64-encoded JPEG strings (no `data:` prefix). Caller adds
        the data URL prefix when building the chat payload.

    Raises:
        AudioProcessingError: if duration probing or ffmpeg fails.
    """
    n_frames = min(max(n_frames, 1), MAX_FRAMES_HARD_CAP)

    duration = ffprobe_duration(video_path)
    if duration is None or duration <= 0:
        raise AudioProcessingError(
            f"Could not probe duration of video: {video_path}"
        )

    cleanup = output_dir is None
    out = output_dir or tempfile.mkdtemp(prefix="summarize_frames_")

    try:
        timestamps = [duration * (i + 0.5) / n_frames for i in range(n_frames)]
        frame_paths: List[str] = []

        for idx, ts in enumerate(timestamps):
            frame_path = os.path.join(out, f"frame_{idx:02d}.jpg")
            # Seek then output a single frame, scaled so that the longer side
            # is at most max_dimension while keeping aspect ratio.
            cmd = [
                "ffmpeg", "-y",
                "-ss", f"{ts:.3f}",
                "-i", video_path,
                "-frames:v", "1",
                "-vf",
                f"scale='if(gt(iw,ih),min({max_dimension},iw),-2)':"
                f"'if(gt(iw,ih),-2,min({max_dimension},ih))'",
                "-q:v", "5",  # JPEG quality 5/31 (1=best, 31=worst). 5 is a
                              # good compromise for vision input.
                frame_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0 or not os.path.isfile(frame_path):
                raise AudioProcessingError(
                    f"ffmpeg failed extracting frame at {ts:.2f}s: "
                    f"{result.stderr.strip()[:300]}"
                )
            frame_paths.append(frame_path)

        encoded = []
        for p in frame_paths:
            with open(p, "rb") as fh:
                encoded.append(base64.b64encode(fh.read()).decode("ascii"))
        return encoded
    finally:
        if cleanup and os.path.isdir(out):
            shutil.rmtree(out, ignore_errors=True)


def frames_to_image_url_parts(frames_b64: List[str]) -> List[dict]:
    """Build the chat-completions `image_url` content parts from b64 frames.

    Returns a list of dicts ready to drop into the user message `content`
    array alongside the text part.
    """
    return [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        }
        for b64 in frames_b64
    ]
