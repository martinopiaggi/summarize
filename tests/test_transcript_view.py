from unittest.mock import patch

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from summarizer.transcript_cache import clear_cache, put_cached_transcript
from webapp.summarization import build_runtime_config, fetch_cached_transcript


SCRIPT = '''
import streamlit as st
from webapp.state import init_session_state
from webapp.ui import _render_summary_panel, _render_url_tab
init_session_state({})
st.session_state.theme = "system"
st.session_state.history = []
sidebar = {
    "provider_config": {"base_url": "https://summary", "model": "summary"},
    "prompt_type": "Questions and answers", "chunk_size": 10000,
    "force_download": False, "language": "auto", "output_language": "auto",
    "speed": 1.0, "transcription_method": "Cloud Whisper", "whisper_model": "tiny",
    "verbose": False, "visual": False,
}
if st.session_state.get("seed_summary"):
    st.session_state.current_summary = "Summary text"
    st.session_state.current_transcript = "00:00:00 cached transcript"
_render_url_tab(sidebar, {})
_render_summary_panel()
'''


def test_url_actions_keep_run_and_add_transcript_button():
    app = AppTest.from_string(SCRIPT).run()
    labels = [button.label for button in app.button]
    assert "RUN" in labels
    assert "JUST TRANSCRIPT" in labels


def test_output_and_cached_transcript_tabs_switch_content():
    app = AppTest.from_string(SCRIPT)
    app.session_state["seed_summary"] = True
    app.run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["OUTPUT", "CACHED TRANSCRIPT"]
    assert app.session_state.current_summary == "Summary text"
    assert any(area.value == "00:00:00 cached transcript" for area in app.text_area)


def test_transcript_only_uses_cache_and_skips_summary_and_jev():
    clear_cache()
    config = build_runtime_config(
        "https://example.test/video", {"base_url": "https://summary", "model": "summary"},
        "Questions and answers", 10000, False, "auto", "auto", 1.0,
    )
    put_cached_transcript(config, "00:00:01 complete cached transcript")
    with patch("summarizer.core.main") as summary, patch("summarizer.jev.prefilter_chunks") as jev:
        result = fetch_cached_transcript(
            "https://example.test/video", {"base_url": "https://summary", "model": "summary"},
            "Questions and answers", 10000, False, "auto", "auto", 1.0,
        )
    assert result == "00:00:01 complete cached transcript"
    summary.assert_not_called()
    jev.assert_not_called()
    clear_cache()
