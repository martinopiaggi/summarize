"""TranscriptFetch sidecar (https://transcriptfetch.com/docs). Reads TRANSCRIPTFETCH_API_KEY."""

import os
import time
from urllib.parse import urljoin

import requests

from ..exceptions import APIKeyError, TranscriptError
from ..progress import print_status

LABEL = "TranscriptFetch"
API_URL = "https://transcriptfetch.com"
REQUEST_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 3
JOB_TIMEOUT_SECONDS = 15 * 60


def fetch(url, config):
    api_key = os.getenv("TRANSCRIPTFETCH_API_KEY")
    if not api_key:
        raise APIKeyError("TRANSCRIPTFETCH_API_KEY is not set in .env")
    headers = {"Authorization": f"Bearer {api_key}"}

    body = _request("POST", "/api/v2/transcripts/video", headers, json={"video": url})
    if body.get("status") == "processing":
        body = _wait_for_job(body, headers, config.get("verbose", False))

    try:
        return [
            (float(segment["start"]), str(segment["text"]))
            for segment in body["data"]["segments"]
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise TranscriptError(f"{LABEL} returned no transcript segments") from exc


def _wait_for_job(body, headers, verbose):
    # Videos without captions are transcribed by an asynchronous job.
    print_status(f"{LABEL} is transcribing the audio", "INFO", verbose)
    job_path = body.get("poll_url") or f"/api/v2/transcripts/jobs/{body.get('job_id')}"
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    while body.get("status") == "processing":
        if time.monotonic() > deadline:
            raise TranscriptError(
                f"{LABEL} is still transcribing after {JOB_TIMEOUT_SECONDS // 60} minutes; "
                "run again later to collect the result"
            )
        time.sleep(POLL_INTERVAL_SECONDS)
        body = _request("GET", job_path, headers)
    return body


def _request(method, path, headers, **kwargs):
    try:
        response = requests.request(
            method,
            urljoin(API_URL, path),
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as exc:
        raise TranscriptError(f"{LABEL} is unreachable: {exc}") from exc

    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise TranscriptError(f"{LABEL} returned HTTP {response.status_code} {response.reason}")
    if body.get("ok"):
        return body

    error = body.get("error") if isinstance(body.get("error"), dict) else {}
    code = error.get("code", f"HTTP {response.status_code}")
    raise TranscriptError(f"{LABEL} {code}: {error.get('message', response.reason)}")
