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

def get_custom_css(theme="system"):
    if theme == "dark":
        theme_vars = ":root { --bg: #0a0a0a; --text: #e8e8e8; --secondary: #141414; }"
    elif theme == "light":
        theme_vars = ":root { --bg: #ffffff; --text: #1a1a1a; --secondary: #f0f0f0; }"
    else:
        theme_vars = (
            ":root { --bg: #ffffff; --text: #1a1a1a; --secondary: #f0f0f0; }\n"
            "@media (prefers-color-scheme: dark) {"
            ":root { --bg: #0a0a0a; --text: #e8e8e8; --secondary: #141414; }"
            "}"
        )

    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@400;700&display=swap');

{theme_vars}

.stApp {{
    font-family: 'Space Grotesk', sans-serif !important;
    background-color: var(--bg) !important;
    color: var(--text) !important;
}}

.stApp [data-testid="stAppViewContainer"] {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
}}

.stApp [data-testid="stSidebar"] {{
    background-color: var(--secondary) !important;
    color: var(--text) !important;
}}

header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
}}

[data-testid="stHeader"] svg,
[data-testid="stToolbar"] svg {{
    fill: var(--text) !important;
    color: var(--text) !important;
}}

.main-header {{
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 2.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.05em !important;
    text-transform: uppercase !important;
    border-bottom: 2px solid var(--text) !important;
    color: var(--text) !important;
    padding-bottom: 0.5rem !important;
    margin-bottom: 2rem !important;
}}

.stTextInput > div > div > input,
.stNumberInput > div {{
    border-radius: 0 !important;
    background-color: var(--secondary) !important;
    border: 1px solid var(--text) !important;
    color: var(--text) !important;
    caret-color: var(--text) !important;
}}

.stTextInput [data-baseweb="input"] input {{
    background-color: transparent !important;
    color: var(--text) !important;
    caret-color: var(--text) !important;
}}

.stTextInput [data-baseweb="input"],
.stTextInput [data-baseweb="input"] > div {{
    background-color: var(--secondary) !important;
    border: 1px solid var(--text) !important;
    border-radius: 0 !important;
}}

.stNumberInput > div > div > input {{
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    background-color: transparent !important;
    color: var(--text) !important;
    border: none !important;
}}

/* Number input (BaseWeb) background fix */
.stNumberInput [data-baseweb="input"] {{
    background-color: var(--secondary) !important;
    border: 1px solid var(--text) !important;
    border-radius: 0 !important;
}}

.stNumberInput [data-baseweb="input"] > div {{
    background-color: transparent !important;
}}

.stNumberInput [data-baseweb="input"] input {{
    background-color: transparent !important;
    color: var(--text) !important;
}}

.stButton > button {{
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    background-color: var(--secondary) !important;
    color: var(--text) !important;
    border: 1px solid var(--text) !important;
}}

.stSelectbox > div > div {{
    border-radius: 0 !important;
    background-color: var(--secondary) !important;
    color: var(--text) !important;
    border: 1px solid var(--text) !important;
}}

.stSelectbox [data-baseweb="select"] > div {{
    background-color: var(--secondary) !important;
    color: var(--text) !important;
}}

.stSelectbox input {{
    cursor: pointer !important;
    caret-color: transparent !important;
    user-select: none !important;
    color: var(--text) !important;
}}

.stSelectbox [role="button"], 
.stSelectbox [data-baseweb="select"] [data-baseweb="popover"] {{
    background-color: var(--secondary) !important;
    color: var(--text) !important;
}}

/* Dropdown menu items */
.stSelectbox ul[data-baseweb="menu"],
.stSelectbox li[data-baseweb="menu"] {{
    background-color: var(--secondary) !important;
    color: var(--text) !important;
}}

/* Selectbox menu popover (portal) */
[data-baseweb="popover"] ul[data-baseweb="menu"],
[data-baseweb="popover"] li[data-baseweb="menu"],
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="option"] {{
    background-color: var(--secondary) !important;
    color: var(--text) !important;
}}

.stSelectbox [data-baseweb="select"] span {{
    color: var(--text) !important;
}}

/* Button hover states */
.stButton > button:hover {{
    background-color: var(--text) !important;
    color: var(--bg) !important;
}}

/* Selectbox hover */
.stSelectbox > div > div:hover {{
    border: 1px solid var(--text) !important;
}}

.stRadio [data-baseweb="radio"] > div > div {{
    border: 1px solid var(--text) !important;
    background-color: transparent !important;
}}

.stCheckbox [data-baseweb="checkbox"] > div > div {{
    border: 1px solid var(--text) !important;
    background-color: transparent !important;
}}

.stExpander {{
    background-color: var(--secondary) !important;
    border: 1px solid var(--text) !important;
}}

.stTabs [data-baseweb="tab"] {{
    border-radius: 0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase !important;
    color: var(--text) !important;
    border-bottom: 2px solid transparent !important;
}}

.stTabs [data-baseweb="tab"][aria-selected="true"] {{
    border-bottom: 2px solid var(--text) !important;
    color: var(--text) !important;
}}

.streamlit-expanderHeader {{
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase !important;
    border-radius: 0 !important;
    color: var(--text) !important;
    background-color: transparent !important;
}}

.streamlit-expanderHeader:hover {{
    background-color: transparent !important;
    color: var(--text) !important;
}}

.stSidebar [data-baseweb="radio"] {{
    background-color: transparent !important;
    box-shadow: none !important;
}}

.stSidebar [data-baseweb="radio"] > div {{
    background-color: transparent !important;
    box-shadow: none !important;
}}

.stSidebar [role="radiogroup"],
.stSidebar [data-baseweb="radiogroup"] {{
    background-color: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
}}

.stSidebar .stRadio [data-baseweb="button-group"],
.stSidebar .stRadio [data-baseweb="button-group"] > div {{
    background-color: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    outline: 0 !important;
}}

.stSidebar .stRadio [data-baseweb="radio"] > div > div {{
    border: none !important;
}}

/* Theme toggle - clean segmented control */
.stSidebar [key="theme_selector"] [data-baseweb="button-group"] {{
    display: flex !important;
    gap: 0 !important;
    background: transparent !important;
    border: 1px solid var(--text) !important;
    padding: 2px !important;
}}

.stSidebar [key="theme_selector"] [data-baseweb="button-group"] > div {{
    flex: 1 !important;
    margin: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    color: var(--text) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    border: none !important;
    cursor: pointer !important;
    transition: all 0.2s !important;
    padding: 0.4rem 0.2rem !important;
}}

.stSidebar [key="theme_selector"] [data-baseweb="button-group"] > div:hover {{
    background: rgba(128, 128, 128, 0.2) !important;
}}

.stSidebar [key="theme_selector"] [data-baseweb="button-group"] > div[aria-checked="true"] {{
    background: var(--text) !important;
    color: var(--bg) !important;
}}

.stSidebar [key="theme_selector"] [role="radio"] {{
    display: none !important;
}}

.stSidebar [data-testid="stExpander"] {{
    border-radius: 0 !important;
    border: 1px solid var(--text) !important;
}}

.stSidebar [data-testid="stExpander"] summary,
.stSidebar [data-testid="stExpander"] details {{
    background-color: var(--secondary) !important;
    color: var(--text) !important;
    border-radius: 0 !important;
}}

.stSidebar [data-testid="stExpander"] summary {{
    display: flex !important;
    align-items: center !important;
    padding: 0.4rem 0.6rem !important;
    text-align: left !important;
    color: var(--text) !important;
}}

.stSidebar [data-testid="stExpander"] summary p,
.stSidebar [data-testid="stExpander"] summary span {{
    color: var(--text) !important;
}}

.stSidebar [data-testid="stExpander"] summary * {{
    color: var(--text) !important;
}}

.stSidebar .stTextArea > div > div {{
    background-color: var(--secondary) !important;
}}

.stSidebar .stTextArea > div > div > textarea {{
    background-color: transparent !important;
    color: var(--text) !important;
}}

.stSidebar .stCheckbox [data-baseweb="checkbox"] > div,
.stSidebar .stCheckbox [data-baseweb="checkbox"] svg {{
    background-color: transparent !important;
    border-color: var(--text) !important;
    color: var(--text) !important;
    fill: var(--text) !important;
}}

.stCaption {{
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase !important;
    color: var(--text) !important;
}}

.stSidebar .stCaption {{
    color: var(--text) !important;
}}

.stMarkdown {{
    color: var(--text) !important;
}}

label, .stRadio label, .stCheckbox label, .stSelectbox label {{
    color: var(--text) !important;
}}

.stFileUploader label,
.stFileUploader [data-testid="stFileUploaderDropzone"] span,
.stFileUploader [data-testid="stFileUploaderDropzone"] small,
.stFileUploader [data-testid="stFileUploaderDropzone"] p {{
    color: var(--text) !important;
}}

.stFileUploader [data-testid="stFileUploaderDropzone"] {{
    background-color: var(--secondary) !important;
    border: 1px solid var(--text) !important;
}}

.stTextInput input::placeholder,
.stTextArea textarea::placeholder {{
    color: var(--text) !important;
    opacity: 0.7 !important;
}}

.stSidebar .stRadio [data-baseweb="radio"] span,
.stSidebar .stRadio [data-baseweb="radio"] label,
.stSidebar .stRadio [data-baseweb="radio"] p {{
    color: var(--text) !important;
}}

.element-container .stMarkdown h1,
.element-container .stMarkdown h2,
.element-container .stMarkdown h3 {{
    font-family: 'JetBrains Mono', monospace !important;
    color: var(--text) !important;
}}
</style>
"""

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

CONFIG_PATH = Path.cwd() / "summarizer.yaml"


def _get_config_path():
    """Return the active config path."""
    return CONFIG_PATH


def load_config():
    """Load config from YAML. Returns (providers, default_provider, defaults) where
    defaults is a normalized dict with snake_case keys."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
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
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
            defaults = config.get("defaults", {})
            url = defaults.get("cobalt-base-url") or defaults.get("cobalt_base_url")
            if url:
                return url
    return "http://localhost:9000"


def load_config_raw():
    path = _get_config_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def save_config_raw(content: str):
    """Save config to the config path."""
    try:
        CONFIG_PATH.write_text(content, encoding="utf-8")
    except OSError as e:
        raise OSError(f"Cannot save config {CONFIG_PATH}: {e}")


def run_summarization(
    source: str,
    provider_config: dict,
    prompt_type: str,
    chunk_size: int,
    force_download: bool,
    language: str,
    audio_speed: float,
    source_type: str = "YouTube Video",
    transcription_method: str = "Cloud Whisper",
    whisper_model: str = "tiny",
    verbose: bool = False,
    status_container=None,
) -> str:
    from summarizer.core import main
    from summarizer.progress import set_progress_callback, clear_progress_callback
    _, _, defaults = load_config()

    config = {
        "source_url_or_path": source,
        "type_of_source": source_type,
        "use_youtube_captions": not force_download and source_type == "YouTube Video",
        "transcription_method": transcription_method,
        "whisper_model": whisper_model,
        "audio_speed": audio_speed,
        "language": language,
        "prompt_type": prompt_type,
        "chunk_size": chunk_size,
        "parallel_api_calls": 30,
        "max_output_tokens": 4096,
        "cobalt_base_url": get_cobalt_url(),
        "use_proxy": bool(defaults.get("use_proxy", False)),
        "base_url": provider_config.get("base_url"),
        "model": provider_config.get("model"),
        "verbose": verbose,
    }

    STATUS_ICONS = {
        "INFO": "ℹ",
        "SUCCESS": "✓",
        "ERROR": "✗",
        "WARNING": "⚠",
        "PROCESSING": "⟳",
    }

    if status_container is not None:
        def _callback(message: str, status: str) -> None:
            icon = STATUS_ICONS.get(status, "•")
            status_container.write(f"`{icon}` {message}")
        set_progress_callback(_callback)

    try:
        return main(config)
    finally:
        if status_container is not None:
            clear_progress_callback()



def init_session_state():
    if "history" not in st.session_state:
        st.session_state.history = []
    if "current_summary" not in st.session_state:
        st.session_state.current_summary = None
    if "show_history_item" not in st.session_state:
        st.session_state.show_history_item = None
    if "theme" not in st.session_state:
        st.session_state.theme = "system"
    
    # Check if we need to restart for theme change
    if "theme_restart" in st.session_state:
        st.session_state.theme = st.session_state.theme_restart
        del st.session_state.theme_restart


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
    import json

    json_text = json.dumps(text)

    html = f'''
    <div style="width: 100%;">
        <textarea id="copyBuffer" style="
            position: fixed;
            left: -9999px;
            top: 0;
            opacity: 0;
            pointer-events: none;
        "></textarea>
        <button id="copyBtn" style="
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
    </div>
    <script>
    (() => {{
        const button = document.getElementById("copyBtn");
        const buffer = document.getElementById("copyBuffer");
        const text = {json_text};

        const setButtonState = (label, background = "#333") => {{
            button.innerText = label;
            button.style.background = background;
        }};

        const fallbackCopy = () => {{
            buffer.value = text;
            buffer.focus();
            buffer.select();
            buffer.setSelectionRange(0, buffer.value.length);

            try {{
                return document.execCommand("copy");
            }} catch (error) {{
                return false;
            }}
        }};

        button.addEventListener("click", async () => {{
            try {{
                if (window.isSecureContext && navigator.clipboard?.writeText) {{
                    await navigator.clipboard.writeText(text);
                    setButtonState("COPIED");
                    return;
                }}

                if (fallbackCopy()) {{
                    setButtonState("COPIED");
                    return;
                }}

                setButtonState("USE DOWNLOAD", "#600");
            }} catch (error) {{
                if (fallbackCopy()) {{
                    setButtonState("COPIED");
                    return;
                }}

                setButtonState(
                    window.isSecureContext ? "FAILED" : "USE DOWNLOAD",
                    "#600",
                );
            }}
        }});
    }})();
    </script>
    '''
    st.html(html, unsafe_allow_javascript=True)


def main():
    st.set_page_config(page_title="SUMMARIZE", page_icon="S", layout="centered")
    init_session_state()
    st.markdown(get_custom_css(st.session_state.theme), unsafe_allow_html=True)

    # Load config from YAML -- this is re-read every run so EDIT CONFIG changes apply immediately
    providers, default_provider, defaults = load_config()
    provider_names = list(providers.keys())

    # Get prompt types from prompts.json (single source of truth)
    prompt_types = get_available_prompts()

    # Resolve defaults from YAML (snake_case keys)
    default_prompt = defaults.get("prompt_type", "Questions and answers")
    default_chunk_size = defaults.get("chunk_size", 10000)
    try:
        default_audio_speed = float(defaults.get("audio_speed", 1.0))
    except (TypeError, ValueError):
        default_audio_speed = 1.0
    if default_audio_speed <= 0:
        default_audio_speed = 1.0

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
            key="theme_selector"
        )

        # Update theme based on selection
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

        # Show model and provider-level chunk-size if set
        model_label = provider_config.get("model", "n/a")
        st.caption(f"model: {model_label}")

        # Use provider-level chunk-size if defined, else global default
        effective_chunk_size = provider_config.get("chunk-size", default_chunk_size)

        try:
            chunk_size = int(effective_chunk_size)
        except (TypeError, ValueError):
            chunk_size = int(default_chunk_size)
        if chunk_size < 500:
            chunk_size = 500
        elif chunk_size > 1000000:
            chunk_size = 1000000

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
                help="Speeds up audio before transcription. Use any positive value (e.g. 1.0, 2.0, 5.0). Higher values are faster but can reduce accuracy.",
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

    # Text-based extensions that should be read directly (no audio processing)
    TEXT_EXTENSIONS = {".txt", ".md", ".vtt", ".srt", ".csv", ".log", ".rst", ".html", ".xml", ".json"}

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
                status_ctx = st.status("Processing...", expanded=False)
                with status_ctx:
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
                            audio_speed,
                            source_type,
                            transcription_method,
                            whisper_model,
                            verbose,
                            status_container=status_ctx,
                        )
                        status_ctx.update(label="Complete", state="complete", expanded=False)
                        add_to_history(
                            video_url, selected_provider, prompt_type, summary
                        )
                        st.session_state.current_summary = summary
                        st.session_state.show_history_item = None
                    except Exception as e:
                        status_ctx.update(label="Failed", state="error", expanded=True)
                        st.error(f"Error: {str(e)}")
                        with st.expander("DETAILS"):
                            st.code(traceback.format_exc())

    with tab_file:
        uploaded = st.file_uploader(
            "Drop file",
            type=["mp4", "mp3", "wav", "m4a", "webm", "txt", "md", "vtt", "srt", "csv", "log", "rst", "html", "xml", "json"],
            label_visibility="collapsed",
        )
        if st.button("RUN", type="primary", disabled=uploaded is None, key="run_file"):
            if uploaded:
                file_ext = Path(uploaded.name).suffix.lower()
                is_text_file = file_ext in TEXT_EXTENSIONS
                status_ctx = st.status("Processing...", expanded=False)
                with status_ctx:
                    try:
                        with tempfile.NamedTemporaryFile(
                            delete=False, suffix=file_ext, mode="wb"
                        ) as tmp:
                            tmp.write(uploaded.read())
                            tmp_path = tmp.name
                        summary = run_summarization(
                            tmp_path,
                            provider_config,
                            prompt_type,
                            chunk_size,
                            not is_text_file,  # force_download only for media files
                            language,
                            audio_speed,
                            "TXT" if is_text_file else "Local File",
                            transcription_method,
                            whisper_model,
                            verbose,
                            status_container=status_ctx,
                        )
                        status_ctx.update(label="Complete", state="complete", expanded=False)
                        add_to_history(
                            uploaded.name, selected_provider, prompt_type, summary
                        )
                        st.session_state.current_summary = summary
                        st.session_state.show_history_item = None
                        os.unlink(tmp_path)
                    except Exception as e:
                        status_ctx.update(label="Failed", state="error", expanded=True)
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
