"""Streamlit session-state bootstrap and upload persistence.

Streamlit reruns the whole script on every interaction. We stash the
current upload (bytes + metadata) in ``st.session_state`` so RUN can
use it even after widget state churn.
"""

import streamlit as st

UPLOADED_FILE_STATE_KEY = "uploaded_file_state"


def remember_uploaded_bytes(
    name: str,
    data: bytes,
    mime: str = "text/plain",
    origin: str = "upload",
) -> None:
    """Persist raw bytes as the current upload.

    Used for the file uploader and for text pasted from the clipboard,
    which enters the app through a hidden input instead of an upload.
    ``origin`` lets the UI tell a pasted source apart from a real file.
    """
    st.session_state[UPLOADED_FILE_STATE_KEY] = {
        "name": name,
        "type": mime,
        "bytes": data,
        "origin": origin,
    }


def remember_uploaded_file(uploaded_file) -> None:
    """Persist uploaded files across Streamlit reruns."""
    if uploaded_file is None:
        return

    remember_uploaded_bytes(uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)


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
    if "current_transcript" not in st.session_state:
        st.session_state.current_transcript = None
    if "show_history_item" not in st.session_state:
        st.session_state.show_history_item = None
    if "theme" not in st.session_state:
        st.session_state.theme = "system"
    if "tinypaste_results" not in st.session_state:
        st.session_state.tinypaste_results = {}
    if UPLOADED_FILE_STATE_KEY not in st.session_state:
        st.session_state[UPLOADED_FILE_STATE_KEY] = None
