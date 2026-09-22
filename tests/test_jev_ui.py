from unittest.mock import patch

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


SCRIPT = '''
import streamlit as st
from webapp.ui import _render_sidebar
st.session_state.setdefault("theme", "system")
st.session_state.setdefault("history", [])
providers = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "google/gemini-2.5-flash"},
}
st.session_state["result"] = _render_sidebar(providers, "openrouter", DEFAULTS, ["Questions and answers"])
'''


def test_jev_controls_only_appear_after_enabling():
    app = AppTest.from_string(SCRIPT.replace("DEFAULTS", "{}"))
    with patch("webapp.ui.load_config_raw", return_value=""):
        app.run()
        assert not app.exception
        assert "JEV PROVIDER" not in [box.label for box in app.selectbox]
        assert "I want to include only…" not in [box.label for box in app.text_area]
        assert "I want to exclude…" not in [box.label for box in app.text_area]
        assert next(box for box in app.selectbox if box.label == "PROVIDER").options == ["groq", "openrouter"]
        next(box for box in app.checkbox if box.label == "Use JEV prefiltering").check().run()
        assert not app.exception
        assert next(box for box in app.selectbox if box.label == "JEV PROVIDER").options == ["openrouter"]
        next(box for box in app.text_area if box.label == "I want to include only…").input("X").run()
        next(box for box in app.text_area if box.label == "I want to exclude…").input("Sponsorship").run()
        assert app.session_state["result"]["jev_include"] == "X"
        assert app.session_state["result"]["jev_exclude"] == "Sponsorship"
        next(box for box in app.checkbox if box.label == "Visual mode").check().run()
        assert any("rules will not be applied" in warning.value for warning in app.warning)
    assert app.session_state["result"]["jev_provider"] == "openrouter"


def test_yaml_enabled_prefilter_shows_openrouter():
    defaults = {"use_jev_prefiltering": True, "jev_provider": "openrouter", "jev_include": "X", "jev_exclude": "Sponsorship"}
    with patch("webapp.ui.load_config_raw", return_value=""):
        app = AppTest.from_string(SCRIPT.replace("DEFAULTS", repr(defaults))).run()
    assert not app.exception
    assert next(box for box in app.selectbox if box.label == "JEV PROVIDER").value == "openrouter"
    assert next(box for box in app.text_area if box.label == "I want to include only…").value == "X"
    assert next(box for box in app.text_area if box.label == "I want to exclude…").value == "Sponsorship"
