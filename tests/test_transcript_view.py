from unittest.mock import patch

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


SCRIPT = '''
import streamlit as st
from webapp.state import init_session_state
from webapp.ui import _render_file_tab, _render_summary_panel, _render_url_tab
init_session_state({})
st.session_state.theme = "system"
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
_render_file_tab(sidebar, {})
_render_summary_panel()
'''


def _result_app():
    app = AppTest.from_string(SCRIPT)
    app.session_state["seed_summary"] = True
    return app


def test_only_run_buttons_remain_for_url_and_file():
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    assert [button.label for button in app.button].count("RUN") == 2
    assert "JUST TRANSCRIPT" not in [button.label for button in app.button]


def test_tabs_show_output_and_complete_cached_transcript():
    app = _result_app().run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["OUTPUT", "TRANSCRIPT"]
    assert any(area.value == "00:00:00 cached transcript" for area in app.text_area)


def test_each_tab_actions_use_its_own_content():
    app = _result_app()
    with patch("webapp.ui.st.download_button") as download, patch(
        "webapp.ui.copy_to_clipboard"
    ) as copy, patch(
        "webapp.ui.publish_to_tinypaste", side_effect=["https://example.test/summary", "https://example.test/transcript"]
    ) as publish:
        app.run()
        assert not app.exception
        downloads = {call.kwargs["key"]: call.kwargs for call in download.call_args_list}
        assert downloads["download_summary"]["data"] == "Summary text"
        assert downloads["download_summary"]["file_name"].endswith(".md")
        assert downloads["download_summary"]["mime"] == "text/markdown"
        assert downloads["download_transcript"]["data"] == "00:00:00 cached transcript"
        assert downloads["download_transcript"]["file_name"].endswith(".txt")
        assert downloads["download_transcript"]["mime"] == "text/plain"
        copy.assert_any_call("Summary text", "system")
        copy.assert_any_call("00:00:00 cached transcript", "system")

        app.tabs[0].button[0].click().run()
        publish.assert_called_once_with("Summary text")
        assert app.session_state.tinypaste_results["OUTPUT"]["url"] == "https://example.test/summary"
        assert app.session_state.tinypaste_results["TRANSCRIPT"]["url"] is None

        app.tabs[1].button[0].click().run()
        assert publish.call_args.args == ("00:00:00 cached transcript",)
        assert app.session_state.tinypaste_results["TRANSCRIPT"]["url"] == "https://example.test/transcript"
        assert app.session_state.tinypaste_results["OUTPUT"]["url"] == "https://example.test/summary"


def test_summary_run_attaches_complete_transcript_to_its_history_item():
    script = '''
import streamlit as st
from webapp.state import init_session_state
from webapp.ui import _run_and_store
init_session_state({})
class Status:
    def update(self, **kwargs):
        pass
sidebar = {
    "provider_config": {}, "provider": "test", "prompt_type": "Questions and answers",
    "chunk_size": 10000, "language": "auto", "output_language": "auto",
    "speed": 1.0, "transcription_method": "Cloud Whisper", "whisper_model": "tiny",
    "verbose": False,
}
_run_and_store("https://example.test/video", "Video", "Video URL", False, sidebar, {}, Status())
'''
    with patch("webapp.ui.run_summarization", return_value="new summary"), patch(
        "webapp.ui._lookup_cached_transcript", return_value="complete cached transcript"
    ):
        app = AppTest.from_string(script).run()
    assert not app.exception
    assert app.session_state.current_summary == "new summary"
    assert app.session_state.current_transcript == "complete cached transcript"
    assert app.session_state.history[0]["transcript"] == "complete cached transcript"


def test_history_does_not_show_unrelated_current_transcript():
    app = _result_app()
    app.session_state.history = [{"source": "old source", "summary": "old summary"}]
    app.session_state.show_history_item = 0
    with patch("webapp.ui.st.download_button") as download, patch(
        "webapp.ui.copy_to_clipboard"
    ) as copy:
        app.run()
    assert not app.exception
    assert [call.kwargs["data"] for call in download.call_args_list] == ["old summary"]
    copy.assert_called_once_with("old summary", "system")
    assert any("No cached transcript" in info.value for info in app.info)
    assert not app.tabs[1].button


def test_history_uses_its_own_transcript():
    app = _result_app()
    app.session_state.history = [{
        "source": "old source", "summary": "old summary", "transcript": "old transcript",
    }]
    app.session_state.show_history_item = 0
    with patch("webapp.ui.st.download_button") as download, patch(
        "webapp.ui.copy_to_clipboard"
    ) as copy:
        app.run()
    assert not app.exception
    assert download.call_args.kwargs["data"] == "old transcript"
    copy.assert_any_call("old transcript", "system")
