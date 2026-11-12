"""Transcript sidecars: registry, TranscriptFetch client, pipeline order, and persistence."""

from unittest.mock import MagicMock, patch

import pytest

from summarizer.exceptions import ConfigurationError, TranscriptError
from summarizer.sidecars import resolve_sidecar, transcriptfetch
from summarizer.transcription import _fetch_transcript


def _response(status, body):
    response = MagicMock(status_code=status, reason="reason")
    response.json.return_value = body
    return response


def _video_config(**overrides):
    config = {
        "type_of_source": "Video URL",
        "source_url_or_path": "https://www.tiktok.com/@user/video/1",
        "sidecar": "transcriptfetch",
        "sidecar_order": "fallback",
    }
    config.update(overrides)
    return config


def test_resolve_sidecar_defaults_to_none_and_validates():
    assert resolve_sidecar({}) == ("none", "fallback")
    assert resolve_sidecar({"sidecar": False}) == ("none", "fallback")
    assert resolve_sidecar({"sidecar": "TranscriptFetch", "sidecar_order": "first"}) == (
        "transcriptfetch",
        "first",
    )
    with pytest.raises(ConfigurationError, match="none, transcriptfetch"):
        resolve_sidecar({"sidecar": "nope"})
    with pytest.raises(ConfigurationError, match="fallback, first"):
        resolve_sidecar({"sidecar_order": "later"})


def test_transcriptfetch_returns_segments(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTFETCH_API_KEY", "tf-key")
    body = {"ok": True, "data": {"segments": [{"start": 1.5, "text": "hi"}]}}
    with patch("requests.request", return_value=_response(200, body)) as request:
        assert transcriptfetch.fetch("https://youtu.be/x", {}) == [(1.5, "hi")]
    method, url = request.call_args.args
    assert (method, url) == ("POST", "https://transcriptfetch.com/api/v2/transcripts/video")
    assert request.call_args.kwargs["json"] == {"video": "https://youtu.be/x"}
    assert request.call_args.kwargs["headers"] == {"Authorization": "Bearer tf-key"}


def test_transcriptfetch_polls_async_jobs(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTFETCH_API_KEY", "tf-key")
    monkeypatch.setattr(transcriptfetch, "POLL_INTERVAL_SECONDS", 0)
    queued = {"ok": True, "status": "processing", "poll_url": "/api/v2/transcripts/jobs/asr_1"}
    done = {"ok": True, "status": "completed", "data": {"segments": [{"start": 0, "text": "done"}]}}
    responses = [_response(202, queued), _response(200, queued), _response(200, done)]
    with patch("requests.request", side_effect=responses) as request:
        assert transcriptfetch.fetch("https://youtu.be/x", {}) == [(0.0, "done")]
    assert request.call_args.args == ("GET", "https://transcriptfetch.com/api/v2/transcripts/jobs/asr_1")


def test_transcriptfetch_reports_api_errors(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTFETCH_API_KEY", "tf-key")
    body = {"ok": False, "error": {"code": "private", "message": "The video is private."}}
    with patch("requests.request", return_value=_response(422, body)):
        with pytest.raises(TranscriptError, match="private: The video is private"):
            transcriptfetch.fetch("https://youtu.be/x", {})


def test_transcriptfetch_needs_api_key(monkeypatch):
    monkeypatch.delenv("TRANSCRIPTFETCH_API_KEY", raising=False)
    with pytest.raises(Exception, match="TRANSCRIPTFETCH_API_KEY"):
        transcriptfetch.fetch("https://youtu.be/x", {})


@patch("summarizer.sidecars.transcriptfetch.fetch", return_value=[(65, "from\nsidecar")])
@patch("summarizer.transcription._fetch_local_transcript", side_effect=TranscriptError("blocked"))
def test_fallback_order_uses_sidecar_after_local_failure(local, sidecar):
    assert _fetch_transcript(_video_config()) == "00:01:05 from sidecar"
    local.assert_called_once()


@patch("summarizer.sidecars.transcriptfetch.fetch", return_value=[(0, "remote")])
@patch("summarizer.transcription._fetch_local_transcript")
def test_first_order_skips_local_work(local, sidecar):
    assert _fetch_transcript(_video_config(sidecar_order="first")) == "00:00:00 remote"
    local.assert_not_called()


@patch("summarizer.sidecars.transcriptfetch.fetch", side_effect=TranscriptError("no credits"))
@patch("summarizer.transcription._fetch_local_transcript", return_value="00:00:00 local")
def test_first_order_falls_back_to_local(local, sidecar):
    assert _fetch_transcript(_video_config(sidecar_order="first")) == "00:00:00 local"


@patch("summarizer.sidecars.transcriptfetch.fetch", side_effect=TranscriptError("private"))
@patch("summarizer.transcription._fetch_local_transcript", side_effect=TranscriptError("blocked"))
def test_reports_both_failures(local, sidecar):
    with pytest.raises(TranscriptError, match="Local transcription: blocked .* TranscriptFetch: private"):
        _fetch_transcript(_video_config())


@pytest.mark.parametrize(
    "source_type, source",
    [
        ("Local File", "/tmp/lecture.mp4"),
        ("Video URL", "https://www.dropbox.com/s/abc/video.mp4"),
        ("Video URL", "https://drive.google.com/file/d/abc/view"),
    ],
)
@patch("summarizer.sidecars.transcriptfetch.fetch")
@patch("summarizer.transcription._fetch_local_transcript", return_value="local")
def test_files_and_private_links_never_reach_the_sidecar(local, sidecar, source_type, source):
    config = _video_config(type_of_source=source_type, source_url_or_path=source, sidecar_order="first")
    assert _fetch_transcript(config) == "local"
    sidecar.assert_not_called()


def test_save_defaults_updates_yaml_in_place(tmp_path, monkeypatch):
    import webapp.config as webapp_config

    path = tmp_path / "summarizer.yaml"
    path.write_text("providers: {}\n\ndefaults:\n  speed: 1.0  # playback\n  sidecar: none\n\nextra: 1\n")
    monkeypatch.setattr(webapp_config, "CONFIG_PATH", path)
    assert webapp_config.save_defaults({"sidecar": "transcriptfetch", "sidecar_order": "first"})
    assert path.read_text() == (
        "providers: {}\n\ndefaults:\n  speed: 1.0  # playback\n  sidecar: transcriptfetch\n"
        "  sidecar-order: first\n\nextra: 1\n"
    )
    monkeypatch.setattr(webapp_config, "CONFIG_PATH", tmp_path / "missing.yaml")
    assert webapp_config.save_defaults({"sidecar": "none"}) is False


def test_streamlit_sidecar_choice_survives_a_new_session(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    import webapp.config as webapp_config

    path = tmp_path / "summarizer.yaml"
    path.write_text("providers:\n  g:\n    base_url: https://g/v1\n    model: m\ndefaults:\n  sidecar: transcriptfetch\n")
    monkeypatch.setattr(webapp_config, "CONFIG_PATH", path)
    script = """
from webapp.config import load_config
from webapp.ui import _render_sidebar
import streamlit as st
st.session_state.setdefault("theme", "system")
st.session_state.setdefault("history", [])
providers, default, defaults = load_config()
_render_sidebar(providers, default, defaults, ["Questions and answers"])
"""
    order = lambda app: next(box for box in app.selectbox if box.label == "Sidecar order")

    first_visit = AppTest.from_string(script).run()
    assert order(first_visit).value == "fallback"
    order(first_visit).select("first").run()
    assert "sidecar-order: first" in path.read_text()

    reconnect = AppTest.from_string(script).run()
    assert not reconnect.exception
    assert order(reconnect).value == "first"


def test_cli_and_api_accept_sidecar_settings(monkeypatch):
    import sys
    from summarizer.__main__ import parse_args
    from summarizer.server import SummarizeRequest

    monkeypatch.setattr(
        sys, "argv", ["summarizer", "--sidecar", "transcriptfetch", "--sidecar-order", "first"]
    )
    args = parse_args()
    assert (args.sidecar, args.sidecar_order) == ("transcriptfetch", "first")

    request = SummarizeRequest(source="https://youtu.be/x", sidecar="transcriptfetch", sidecar_order="first")
    assert (request.sidecar, request.sidecar_order) == ("transcriptfetch", "first")
    with pytest.raises(ValueError):
        SummarizeRequest(source="https://youtu.be/x", sidecar="nope")
