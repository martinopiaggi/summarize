"""FILE-tab "paste from clipboard" transport tests.

Browsers only expose the clipboard to page scripts, so the button is
raw HTML/JS: it writes the pasted text into a Streamlit text area whose
change event makes the server store it as a plain .txt source. The same
area is visible so Ctrl+V still works when the browser blocks clipboard
reads. These tests cover the server half of that contract.
"""

from unittest.mock import patch

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from webapp.clipboard import paste_from_clipboard_button
from webapp.state import UPLOADED_FILE_STATE_KEY

NOTICE_KEY = "clipboard_paste_notice"

FILE_TAB_SCRIPT = '''
import streamlit as st
from webapp.state import init_session_state
from webapp.ui import _render_file_tab
init_session_state({})
st.session_state.theme = "dark"
sidebar = {
    "provider_config": {}, "provider": "test", "prompt_type": "Questions and answers",
    "chunk_size": 10000, "language": "auto", "output_language": "auto",
    "speed": 1.0, "transcription_method": "Cloud Whisper", "whisper_model": "tiny",
    "verbose": False,
}
_render_file_tab(sidebar, {})
'''


def test_paste_button_scripts_the_clipboard_into_the_target_input():
    with patch("webapp.clipboard.st.html") as html:
        paste_from_clipboard_button("clipboard_paste", "dark")

    markup = html.call_args.args[0]
    assert html.call_args.kwargs["unsafe_allow_javascript"] is True
    assert "PASTE FROM CLIPBOARD" in markup
    assert 'const target = "clipboard_paste"' in markup
    assert "navigator.clipboard" in markup
    # Not every deployment is a secure context: the failure path must tell
    # the user to fall back to the keyboard.
    assert "FAILED - USE CTRL+V" in markup


def test_file_tab_registers_the_paste_target():
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()

    assert not app.exception
    assert [widget.key for widget in app.text_area] == ["clipboard_paste"]


def test_paste_button_is_rendered_before_the_uploader():
    """Full width, above the dropzone: side-by-side placement lined up
    badly against the taller uploader box."""
    import inspect

    from webapp import ui

    source = inspect.getsource(ui._render_file_tab)
    assert source.index("paste_from_clipboard_button(") < source.index("st.file_uploader(")


def test_pasted_text_becomes_a_plain_txt_source():
    """A pasted URL must stay text: the FILE tab never parses it as a video."""
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()
    pasted = "https://example.test/watch?v=1"

    app.text_area(key="clipboard_paste").set_value(pasted).run()

    assert not app.exception
    state = app.session_state[UPLOADED_FILE_STATE_KEY]
    assert state["name"] == "clipboard.txt"
    assert state["bytes"] == pasted.encode("utf-8")
    # The input is cleared so the same text can be pasted again, and RUN
    # becomes available through the existing .txt upload path.
    assert app.session_state["clipboard_paste"] == ""
    assert app.button(key="run_file").disabled is False


def test_empty_paste_does_not_replace_the_current_upload():
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()
    app.text_area(key="clipboard_paste").set_value("real content").run()

    app.text_area(key="clipboard_paste").set_value("   ").run()

    assert not app.exception
    assert app.session_state[UPLOADED_FILE_STATE_KEY]["bytes"] == b"real content"


def test_first_paste_confirms_what_was_pasted():
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()

    app.text_area(key="clipboard_paste").set_value("first paste").run()

    assert not app.exception
    notice = app.session_state[NOTICE_KEY]
    assert "Pasted text from clipboard" in notice
    assert "11 characters" in notice


def test_pasting_again_reports_the_replacement():
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()
    app.text_area(key="clipboard_paste").set_value("first paste").run()

    app.text_area(key="clipboard_paste").set_value("second paste").run()

    assert not app.exception
    assert "replaced clipboard.txt" in app.session_state[NOTICE_KEY]
    assert app.session_state[UPLOADED_FILE_STATE_KEY]["bytes"] == b"second paste"


def test_pasting_the_same_text_again_says_nothing_changed():
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()
    app.text_area(key="clipboard_paste").set_value("same text").run()

    app.text_area(key="clipboard_paste").set_value("same text").run()

    assert not app.exception
    assert "same clipboard text again" in app.session_state[NOTICE_KEY]


def test_paste_notice_survives_reruns():
    """The confirmation must outlive the rerun the paste itself triggers,
    otherwise the user never gets to read it."""
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()
    app.text_area(key="clipboard_paste").set_value("once").run()
    notice = app.session_state[NOTICE_KEY]

    app.run()

    assert app.session_state[NOTICE_KEY] == notice
    assert app.session_state[UPLOADED_FILE_STATE_KEY]["origin"] == "clipboard"


def test_paste_notice_is_dropped_when_a_file_takes_over():
    app = AppTest.from_string(FILE_TAB_SCRIPT)
    app.session_state[UPLOADED_FILE_STATE_KEY] = {
        "name": "video.mp4", "type": "video/mp4", "bytes": b"x", "origin": "upload",
    }
    app.session_state[NOTICE_KEY] = "Pasted text from clipboard (3 characters)."

    app.run()

    assert not app.exception
    assert app.session_state.get(NOTICE_KEY) is None


def test_clearing_the_pasted_source_drops_the_notice():
    app = AppTest.from_string(FILE_TAB_SCRIPT).run()
    app.text_area(key="clipboard_paste").set_value("hello").run()
    assert app.session_state[NOTICE_KEY]

    app.button(key="clear_uploaded_file").click().run()

    assert not app.exception
    assert app.session_state.get(UPLOADED_FILE_STATE_KEY) is None
    assert app.session_state.get(NOTICE_KEY) is None


def test_paste_button_renders_the_notice_and_failure_states_visually():
    with patch("webapp.clipboard.st.html") as html:
        paste_from_clipboard_button(
            "clipboard_paste", "dark", notice="Pasted text replaced clipboard.txt (12 characters)."
        )

    markup = html.call_args.args[0]
    assert 'id="pasteStatus"' in markup
    assert 'role="status"' in markup
    assert "#pasteStatus.ok {" in markup
    assert (
        'const initialNotice = "Pasted text replaced clipboard.txt (12 characters).";'
        in markup
    )
    assert "Could not read the clipboard. Press Ctrl+V instead." in markup
    assert "The clipboard is empty - copy something first." in markup