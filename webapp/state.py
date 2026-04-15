"""Streamlit session-state bootstrap and upload persistence.

Streamlit reruns the whole script on every interaction. We stash the
current upload (bytes + metadata) in ``st.session_state`` so RUN can
use it even after widget state churn.
"""

import streamlit as st

UPLOADED_FILE_STATE_KEY = "uploaded_file_state"


def remember_uploaded_file(uploaded_file) -> None:
    """Persist uploaded files across Streamlit reruns."""
    if uploaded_file is None:
        return

    st.session_state[UPLOADED_FILE_STATE_KEY] = {
        "name": uploaded_file.name,
        "type": uploaded_file.type,
        "bytes": uploaded_file.getvalue(),
    }


def get_uploaded_file_state():
    """Return the currently remembered upload, if any."""
    return st.session_state.get(UPLOADED_FILE_STATE_KEY)


def clear_uploaded_file_state() -> None:
    """Forget the remembered upload and clear the widget state."""
    st.session_state.pop(UPLOADED_FILE_STATE_KEY, None)
    st.session_state.pop("uploaded_file_widget", None)


def init_session_state(defaults=None):
    """Seed every key we rely on so the first render never ``KeyError``s."""
    # Imported lazily to avoid a circular import between state and history.
    from webapp.history import load_history_from_disk

    if defaults is None:
        defaults = {}
    if "history" not in st.session_state:
        st.session_state.history = []
        if defaults.get("keep_history"):
            output_dir = defaults.get("output_dir", "summaries")
            st.session_state.history = load_history_from_disk(output_dir)
    if "current_summary" not in st.session_state:
        st.session_state.current_summary = None
    if "show_history_item" not in st.session_state:
        st.session_state.show_history_item = None
    if "theme" not in st.session_state:
        st.session_state.theme = "system"
    if UPLOADED_FILE_STATE_KEY not in st.session_state:
        st.session_state[UPLOADED_FILE_STATE_KEY] = None

    # Apply a pending theme change requested on the previous run.
    if "theme_restart" in st.session_state:
        st.session_state.theme = st.session_state.theme_restart
        del st.session_state.theme_restart
