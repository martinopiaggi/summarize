"""
SUMMARIZE - Video Summarizer
"""

import streamlit as st
import yaml
import traceback
import tempfile
import os
from pathlib import Path
from datetime import datetime
from summarizer.downloaders import is_youtube_url
from summarizer.prompts import get_available_prompts

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@400;700&display=swap');

.stApp {
    font-family: 'Space Grotesk', sans-serif !important;
}

.main-header {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 2.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.05em !important;
    text-transform: uppercase !important;
    border-bottom: 2px solid #fff !important;
    padding-bottom: 0.5rem !important;
    margin-bottom: 2rem !important;
}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
}

.stButton > button {
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
}

.stSelectbox > div > div {
    border-radius: 0 !important;
}

.stTabs [data-baseweb="tab"] {
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase !important;
}

.streamlit-expanderHeader {
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase !important;
    border-radius: 0 !important;
}

.stCaption {
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase !important;
}

.element-container .stMarkdown h1,
.element-container .stMarkdown h2,
.element-container .stMarkdown h3 {
    font-family: 'JetBrains Mono', monospace !important;
}
</style>
"""

LANGUAGES = [
    ("auto", "Auto-detect"),
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

CONFIG_PATH = Path.cwd() / "summarizer.yaml"


def load_config():
    """Load config from YAML. Returns (providers, default_provider, defaults) where
    defaults is a normalized dict with snake_case keys."""
    config_paths = [CONFIG_PATH, Path.home() / ".summarizer.yaml"]
    for path in config_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                defaults = config.get("defaults", {})
                normalized = {
                    key.replace("-", "_"): value for key, value in defaults.items()
                }
                return (
                    config.get("providers", {}),
                    config.get("default_provider", ""),
                    normalized,
                )
    return (
        {
            "gemini": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "gemini-2.5-flash-lite",
            }
        },
        "gemini",
        {},
    )


def get_cobalt_url():
    """Resolve Cobalt URL. Environment variable wins, then YAML, then default."""
    env_url = os.environ.get("COBALT_BASE_URL")
    if env_url:
        return env_url
    # Try reading from YAML
    config_paths = [CONFIG_PATH, Path.home() / ".summarizer.yaml"]
    for path in config_paths:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
                defaults = config.get("defaults", {})
                url = defaults.get("cobalt-base-url") or defaults.get("cobalt_base_url")
                if url:
                    return url
    return "http://localhost:9000"


def load_config_raw():
    if CONFIG_PATH.exists():
        return CONFIG_PATH.read_text(encoding="utf-8")
    return ""


def save_config_raw(content: str):
    CONFIG_PATH.write_text(content, encoding="utf-8")


def run_summarization(
    source: str,
    provider_config: dict,
    prompt_type: str,
    chunk_size: int,
    force_download: bool,
    language: str,
    source_type: str = "YouTube Video",
    transcription_method: str = "Cloud Whisper",
    whisper_model: str = "tiny",
) -> str:
    from summarizer.core import main

    config = {
        "source_url_or_path": source,
        "type_of_source": source_type,
        "use_youtube_captions": not force_download and source_type == "YouTube Video",
        "transcription_method": transcription_method,
        "whisper_model": whisper_model,
        "language": language,
        "prompt_type": prompt_type,
        "chunk_size": chunk_size,
        "parallel_api_calls": 30,
        "max_output_tokens": 4096,
        "cobalt_base_url": get_cobalt_url(),
        "base_url": provider_config.get("base_url"),
        "model": provider_config.get("model"),
        "verbose": False,
    }
    return main(config)


def init_session_state():
    if "history" not in st.session_state:
        st.session_state.history = []
    if "current_summary" not in st.session_state:
        st.session_state.current_summary = None
    if "show_history_item" not in st.session_state:
        st.session_state.show_history_item = None


def add_to_history(source: str, provider: str, prompt_type: str, summary: str):
    st.session_state.history.insert(
        0,
        {
            "source": source[:50],
            "provider": provider,
            "prompt_type": prompt_type,
            "summary": summary,
            "timestamp": datetime.now().strftime("%H:%M"),
        },
    )
    st.session_state.history = st.session_state.history[:10]


def copy_to_clipboard(text: str):
    """Render a button that copies text to clipboard using JavaScript."""
    import base64

    b64_text = base64.b64encode(text.encode()).decode()

    html = f'''
    <script>
    function copyText() {{
        const text = atob("{b64_text}");
        navigator.clipboard.writeText(text).then(function() {{
            document.getElementById("copyBtn").innerText = "COPIED";
            document.getElementById("copyBtn").style.background = "#333";
        }}).catch(function() {{
            document.getElementById("copyBtn").innerText = "FAILED";
        }});
    }}
    </script>
    <button id="copyBtn" onclick="copyText()" style="
        width: 100%;
        padding: 0.6rem 1rem;
        background: #fff;
        color: #000;
        border: none;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.875rem;
        text-transform: uppercase;
        cursor: pointer;
        transition: all 0.2s;
    ">COPY TO CLIPBOARD</button>
    '''
    st.components.v1.html(html, height=45)


def main():
    st.set_page_config(page_title="SUMMARIZE", page_icon="S", layout="wide")
    init_session_state()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Load config from YAML -- this is re-read every run so EDIT CONFIG changes apply immediately
    providers, default_provider, defaults = load_config()
    provider_names = list(providers.keys())

    # Get prompt types from prompts.json (single source of truth)
    prompt_types = get_available_prompts()

    # Resolve defaults from YAML (snake_case keys)
    default_prompt = defaults.get("prompt_type", "Questions and answers")
    default_chunk_size = defaults.get("chunk_size", 10000)

    with st.sidebar:
        st.markdown("### CONFIG")
        st.divider()

        # -- Provider --
        default_idx = (
            provider_names.index(default_provider)
            if default_provider in provider_names
            else 0
        )
        selected_provider = st.selectbox("PROVIDER", provider_names, index=default_idx)
        provider_config = providers[selected_provider] if selected_provider else {}

        # Show model and provider-level chunk-size if set
        model_label = provider_config.get("model", "n/a")
        st.caption(f"model: {model_label}")

        # Use provider-level chunk-size if defined, else global default
        effective_chunk_size = provider_config.get("chunk-size", default_chunk_size)

        st.divider()

        # -- Style --
        prompt_idx = 0
        if default_prompt in prompt_types:
            prompt_idx = prompt_types.index(default_prompt)
        prompt_type = st.selectbox("STYLE", prompt_types, index=prompt_idx)

        # -- Language --
        language = st.selectbox(
            "LANGUAGE",
            options=[code for code, name in LANGUAGES],
            format_func=lambda x: dict(LANGUAGES)[x],
            index=0,
        )

        # -- Chunk size: number input, no arbitrary cap --
        chunk_size = st.number_input(
            "CHUNK SIZE",
            min_value=500,
            max_value=1000000,
            value=int(effective_chunk_size),
            step=1000,
            help="Characters per chunk. Increase for models with large context windows.",
        )

        st.divider()

        # -- Settings (less common options) --
        with st.expander("SETTINGS"):
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
                    f"{item['timestamp']} / {item['provider']}",
                    key=f"hist_{i}",
                    use_container_width=True,
                ):
                    st.session_state.show_history_item = i
                    st.session_state.current_summary = None

    # -- Main area --
    st.markdown('<h1 class="main-header">SUMMARIZE</h1>', unsafe_allow_html=True)

    tab_url, tab_file = st.tabs(["URL", "FILE"])

    with tab_url:
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
            else:
                with st.spinner("Processing..."):
                    try:
                        source_type = (
                            "YouTube Video"
                            if is_youtube_url(video_url)
                            else "Video URL"
                        )
                        summary = run_summarization(
                            video_url,
                            provider_config,
                            prompt_type,
                            chunk_size,
                            force_download,
                            language,
                            source_type,
                            transcription_method,
                            whisper_model,
                        )
                        add_to_history(
                            video_url, selected_provider, prompt_type, summary
                        )
                        st.session_state.current_summary = summary
                        st.session_state.show_history_item = None
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        with st.expander("DETAILS"):
                            st.code(traceback.format_exc())

    with tab_file:
        uploaded = st.file_uploader(
            "Drop file",
            type=["mp4", "mp3", "wav", "m4a", "webm"],
            label_visibility="collapsed",
        )
        if st.button("RUN", type="primary", disabled=uploaded is None, key="run_file"):
            if uploaded:
                with st.spinner("Processing..."):
                    try:
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=Path(uploaded.name).suffix
                        ) as tmp:
                            tmp.write(uploaded.read())
                            tmp_path = tmp.name
                        summary = run_summarization(
                            tmp_path,
                            provider_config,
                            prompt_type,
                            chunk_size,
                            True,
                            language,
                            "Local File",
                            transcription_method,
                            whisper_model,
                        )
                        add_to_history(
                            uploaded.name, selected_provider, prompt_type, summary
                        )
                        st.session_state.current_summary = summary
                        st.session_state.show_history_item = None
                        os.unlink(tmp_path)
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                        with st.expander("DETAILS"):
                            st.code(traceback.format_exc())

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

    if display_summary:
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
        st.markdown(display_summary)

    st.divider()
    st.caption("github.com/martinopiaggi/summarize")


if __name__ == "__main__":
    main()
