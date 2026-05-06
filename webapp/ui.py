"""Top-level Streamlit page: sidebar controls, URL/FILE tabs, summary display.

This module composes everything in :mod:`webapp`. ``main()`` is the
Streamlit entry point called by ``app.py``.
"""

import os
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

import streamlit as st
import yaml

from summarizer.downloaders import is_youtube_url
from summarizer.prompts import get_available_prompts

from webapp.clipboard import copy_to_clipboard
from webapp.config import (
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    coerce_int,
    load_config,
    load_config_raw,
    save_config_raw,
)
from webapp.history import add_to_history, save_summary_to_disk
from webapp.mermaid import render_summary_with_mermaid
from webapp.state import (
    clear_uploaded_file_state,
    get_uploaded_file_state,
    init_session_state,
    remember_uploaded_file,
)
from webapp.summarization import run_summarization
from webapp.theme import get_custom_css

LANGUAGES = [
    ("auto", "Automatic"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("zh", "Chinese"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
]

# Text-based extensions that should be read directly (no audio processing)
TEXT_EXTENSIONS = {
    ".txt", ".md", ".vtt", ".srt", ".csv",
    ".log", ".rst", ".html", ".xml", ".json",
}

_UPLOAD_TYPES = [
    "mp4", "mp3", "wav", "m4a", "webm",
    "txt", "md", "vtt", "srt", "csv", "log", "rst", "html", "xml", "json",
]


def _render_sidebar(providers, default_provider, defaults, prompt_types):
    """Draw the sidebar and return the selections the main panel needs."""
    default_prompt = defaults.get("prompt_type", "Questions and answers")
    default_chunk_size = defaults.get("chunk_size", 10000)
    try:
        default_audio_speed = float(defaults.get("audio_speed", 1.0))
    except (TypeError, ValueError):
        default_audio_speed = 1.0
    if default_audio_speed <= 0:
        default_audio_speed = 1.0

    provider_names = list(providers.keys())

    with st.sidebar:
        # -- Theme Toggle --
        current_theme = st.session_state.theme
        theme_options = ["System", "Light", "Dark"]
        if current_theme == "dark":
            theme_index = 2
        elif current_theme == "light":
            theme_index = 1
        else:
            theme_index = 0

        selected_theme = st.radio(
            "THEME",
            options=theme_options,
            index=theme_index,
            horizontal=True,
            key="theme_selector",
        )

        if selected_theme == "Dark":
            new_theme = "dark"
        elif selected_theme == "Light":
            new_theme = "light"
        else:
            new_theme = "system"
        if new_theme != current_theme:
            st.session_state.theme_restart = new_theme
            st.rerun()

        st.divider()

        # -- Provider --
        default_idx = (
            provider_names.index(default_provider)
            if default_provider in provider_names
            else 0
        )
        selected_provider = st.selectbox("PROVIDER", provider_names, index=default_idx)
        provider_config = providers[selected_provider] if selected_provider else {}

        model_label = provider_config.get("model", "n/a")
        st.caption(f"model: {model_label}")

        # -- Video engine (only meaningful for IG/TikTok/X/Reddit/FB URLs) --
        engine_options = ["auto", "gemini-files", "groq-multimodal"]
        engine_default = (defaults.get("video_engine") or "auto").lower()
        engine_idx = (
            engine_options.index(engine_default)
            if engine_default in engine_options
            else 0
        )
        video_engine = st.selectbox(
            "VIDEO ENGINE",
            engine_options,
            index=engine_idx,
            help=(
                "How Instagram / TikTok / X / Reddit / FB videos are analysed. "
                "'gemini-files' uploads the full video to Gemini Files API "
                "(richer audio + visual understanding). "
                "'groq-multimodal' samples 5 frames + Whisper transcript and "
                "sends them to Llama-4-Scout. "
                "'auto' tries gemini-files first and falls back to "
                "groq-multimodal if the upload or call fails. "
                "Ignored for YouTube and local files."
            ),
        )

        # Use provider-level chunk-size if defined, else global default
        chunk_size_override = provider_config.get("chunk_size")
        chunk_size = coerce_int(
            chunk_size_override if chunk_size_override is not None else default_chunk_size,
            default_chunk_size,
            minimum=MIN_CHUNK_SIZE,
            maximum=MAX_CHUNK_SIZE,
        )
        chunk_size_source = "provider override" if chunk_size_override is not None else "default"
        st.caption(f"chunk size: {chunk_size:,} ({chunk_size_source})")

        parallel_api_calls = coerce_int(
            provider_config.get(
                "parallel_api_calls",
                defaults.get("parallel_api_calls", 30),
            ),
            30,
            minimum=1,
            maximum=100,
        )
        st.caption(f"parallel calls: {parallel_api_calls}")

        st.divider()

        # -- Style --
        prompt_idx = 0
        if default_prompt in prompt_types:
            prompt_idx = prompt_types.index(default_prompt)
        prompt_type = st.selectbox("STYLE", prompt_types, index=prompt_idx)

        # -- Language --
        language = st.selectbox(
            "LANGUAGE",
            options=[code for code, _ in LANGUAGES],
            format_func=lambda x: dict(LANGUAGES)[x],
            index=0,
        )

        st.divider()

        # -- Settings (less common options) --
        with st.expander("SETTINGS"):
            default_verbose = bool(defaults.get("verbose", False))
            verbose = st.checkbox(
                "Verbose output",
                value=default_verbose,
                help="Show detailed progress messages including fallback attempts.",
            )
            force_download = st.checkbox(
                "Force audio download",
                value=False,
                help="Skip captions and download audio for transcription instead.",
            )
            transcription_method = st.selectbox(
                "TRANSCRIPTION",
                ["Cloud Whisper", "Local Whisper"],
                index=0,
                help="Cloud Whisper uses Groq API (free). Local Whisper runs on your machine.",
            )
            whisper_model = st.selectbox(
                "WHISPER MODEL",
                ["tiny", "base", "small", "medium", "large"],
                index=0,
                help="Only used with Local Whisper. tiny=fastest, large=most accurate.",
            )
            audio_speed = st.number_input(
                "AUDIO SPEED",
                min_value=0.01,
                value=default_audio_speed,
                step=0.01,
                format="%.2f",
                help=(
                    "Speeds up audio before transcription. Use any positive value "
                    "(e.g. 1.0, 2.0, 5.0). Higher values are faster but can reduce accuracy."
                ),
            )

        # -- YAML editor --
        with st.expander("EDIT CONFIG"):
            st.caption("Edit summarizer.yaml. Save to update all defaults above.")
            yaml_content = load_config_raw()
            edited_yaml = st.text_area(
                "YAML", yaml_content, height=300, label_visibility="collapsed"
            )
            col_save, col_reset = st.columns(2)
            with col_save:
                if st.button("SAVE", use_container_width=True):
                    try:
                        yaml.safe_load(edited_yaml)
                        save_config_raw(edited_yaml)
                        st.success("Saved")
                        st.rerun()
                    except yaml.YAMLError:
                        st.error("Invalid YAML")
            with col_reset:
                if st.button("RELOAD", use_container_width=True):
                    st.rerun()

        # -- History --
        if st.session_state.history:
            st.divider()
            st.markdown("### HISTORY")
            for i, item in enumerate(st.session_state.history[:5]):
                if st.button(
                    item["provider"],
                    key=f"hist_{i}",
                    use_container_width=True,
                ):
                    st.session_state.show_history_item = i
                    st.session_state.current_summary = None

    return {
        "provider": selected_provider,
        "provider_config": provider_config,
        "prompt_type": prompt_type,
        "chunk_size": chunk_size,
        "language": language,
        "verbose": verbose,
        "force_download": force_download,
        "transcription_method": transcription_method,
        "whisper_model": whisper_model,
        "audio_speed": audio_speed,
        "video_engine": video_engine,
    }


def _run_and_store(source, display_name, source_type, force_download, sidebar, defaults, status_ctx):
    """Invoke the pipeline and persist results into session state / disk."""
    summary = run_summarization(
        source,
        sidebar["provider_config"],
        sidebar["prompt_type"],
        sidebar["chunk_size"],
        force_download,
        sidebar["language"],
        sidebar["audio_speed"],
        source_type,
        sidebar["transcription_method"],
        sidebar["whisper_model"],
        sidebar["verbose"],
        status_container=status_ctx,
        video_engine=sidebar.get("video_engine", "auto"),
    )
    status_ctx.update(label="Complete", state="complete", expanded=False)
    add_to_history(display_name, sidebar["provider"], sidebar["prompt_type"], summary)
    st.session_state.current_summary = summary
    st.session_state.show_history_item = None
    if defaults.get("keep_history"):
        save_summary_to_disk(display_name, summary, defaults.get("output_dir", "summaries"))


def _render_url_tab(sidebar, defaults):
    col1, col2 = st.columns([4, 1])
    with col1:
        video_url = st.text_input(
            "Video URL",
            placeholder="https://youtube.com/watch?v=...",
            label_visibility="collapsed",
        )
    with col2:
        url_btn = st.button(
            "RUN", type="primary", use_container_width=True, key="run_url"
        )

    if url_btn and video_url:
        if not video_url.startswith("http"):
            st.warning("URL must start with http or https")
            return
        status_ctx = st.status("Processing...", expanded=False)
        with status_ctx:
            try:
                source_type = (
                    "YouTube Video" if is_youtube_url(video_url) else "Video URL"
                )
                _run_and_store(
                    video_url,
                    video_url,
                    source_type,
                    sidebar["force_download"],
                    sidebar,
                    defaults,
                    status_ctx,
                )
            except Exception as e:
                status_ctx.update(label="Failed", state="error", expanded=True)
                st.error(f"Error: {str(e)}")
                with st.expander("DETAILS"):
                    st.code(traceback.format_exc())


def _render_file_tab(sidebar, defaults):
    uploaded = st.file_uploader(
        "Drop file",
        type=_UPLOAD_TYPES,
        label_visibility="collapsed",
        key="uploaded_file_widget",
    )
    remember_uploaded_file(uploaded)
    uploaded_state = get_uploaded_file_state()

    if uploaded_state:
        st.caption(f"Ready to rerun with: {uploaded_state['name']}")
        if st.button("CLEAR FILE", use_container_width=True, key="clear_uploaded_file"):
            clear_uploaded_file_state()
            st.rerun()

    if st.button("RUN", type="primary", disabled=uploaded_state is None, key="run_file"):
        if not uploaded_state:
            return
        file_ext = Path(uploaded_state["name"]).suffix.lower()
        is_text_file = file_ext in TEXT_EXTENSIONS
        status_ctx = st.status("Processing...", expanded=False)
        with status_ctx:
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=file_ext, mode="wb"
                ) as tmp:
                    tmp.write(uploaded_state["bytes"])
                    tmp_path = tmp.name
                _run_and_store(
                    tmp_path,
                    uploaded_state["name"],
                    "TXT" if is_text_file else "Local File",
                    not is_text_file,  # force_download only for media files
                    sidebar,
                    defaults,
                    status_ctx,
                )
            except Exception as e:
                status_ctx.update(label="Failed", state="error", expanded=True)
                st.error(f"Error: {str(e)}")
                with st.expander("DETAILS"):
                    st.code(traceback.format_exc())
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass


def _render_summary_panel():
    display_summary = None
    if st.session_state.show_history_item is not None:
        idx = st.session_state.show_history_item
        if idx < len(st.session_state.history):
            item = st.session_state.history[idx]
            st.info(f"Viewing: {item['source']}...")
            display_summary = item["summary"]
            if st.button("CLOSE"):
                st.session_state.show_history_item = None
                st.rerun()
    elif st.session_state.current_summary:
        display_summary = st.session_state.current_summary

    if not display_summary:
        return

    st.success("COMPLETE")

    col_dl, col_copy = st.columns(2)
    with col_dl:
        st.download_button(
            "DOWNLOAD",
            data=display_summary,
            file_name=f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_copy:
        copy_to_clipboard(display_summary)

    st.divider()
    render_summary_with_mermaid(display_summary)


def main():
    """Streamlit page entry point."""
    st.set_page_config(page_title="SUMMARIZE", page_icon="S", layout="centered")

    # Re-read config every run so EDIT CONFIG changes apply immediately.
    providers, default_provider, defaults = load_config()
    init_session_state(defaults)
    st.markdown(get_custom_css(st.session_state.theme), unsafe_allow_html=True)

    prompt_types = get_available_prompts()
    sidebar = _render_sidebar(providers, default_provider, defaults, prompt_types)

    # -- Main area --
    st.markdown('<h1 class="main-header">SUMMARIZE</h1>', unsafe_allow_html=True)

    tab_url, tab_file = st.tabs(["URL", "FILE"])
    with tab_url:
        _render_url_tab(sidebar, defaults)
    with tab_file:
        _render_file_tab(sidebar, defaults)

    _render_summary_panel()

    st.divider()
    st.caption("github.com/martinopiaggi/summarize")
