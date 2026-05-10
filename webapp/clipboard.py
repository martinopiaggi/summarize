"""Clipboard button rendered as raw HTML + JS.

Streamlit has no native clipboard widget; we inject a <button> that
uses ``navigator.clipboard`` with an ``execCommand('copy')`` fallback
for non-secure contexts.
"""

import json

import streamlit as st


def _theme_vars(theme: str) -> str:
    if theme == "dark":
        return """
        :root {
            --copy-bg: #141414;
            --copy-text: #e8e8e8;
            --copy-hover-bg: #e8e8e8;
            --copy-hover-text: #0a0a0a;
        }
        """
    if theme == "light":
        return """
        :root {
            --copy-bg: #f0f0f0;
            --copy-text: #1a1a1a;
            --copy-hover-bg: #1a1a1a;
            --copy-hover-text: #ffffff;
        }
        """
    return """
    :root {
        --copy-bg: #f0f0f0;
        --copy-text: #1a1a1a;
        --copy-hover-bg: #1a1a1a;
        --copy-hover-text: #ffffff;
    }

    @media (prefers-color-scheme: dark) {
        :root {
            --copy-bg: #141414;
            --copy-text: #e8e8e8;
            --copy-hover-bg: #e8e8e8;
            --copy-hover-text: #0a0a0a;
        }
    }
    """


def copy_to_clipboard(text: str, theme: str = "system"):
    """Render a "COPY TO CLIPBOARD" button wired to the given text."""
    json_text = json.dumps(text)
    theme_vars = _theme_vars(theme)

    html = f'''
    <style>
    {theme_vars}

    #copyBtn {{
        width: 100%;
        min-height: 2.5rem;
        padding: 0.55rem 0.65rem;
        background: var(--copy-bg);
        color: var(--copy-text);
        border: 1px solid var(--copy-text);
        border-radius: 0;
        box-sizing: border-box;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        font-size: 0.8125rem;
        line-height: 1.15;
        text-transform: uppercase;
        cursor: pointer;
        transition: all 0.2s;
    }}

    #copyBtn:hover {{
        background: var(--copy-hover-bg);
        color: var(--copy-hover-text);
    }}
    </style>
    <div style="width: 100%;">
        <textarea id="copyBuffer" style="
            position: fixed;
            left: -9999px;
            top: 0;
            opacity: 0;
            pointer-events: none;
        "></textarea>
        <button id="copyBtn">COPY TO CLIPBOARD</button>
    </div>
    <script>
    (() => {{
        const button = document.getElementById("copyBtn");
        const buffer = document.getElementById("copyBuffer");
        const text = {json_text};

        const styles = getComputedStyle(document.documentElement);
        const defaultBackground = styles.getPropertyValue("--copy-bg").trim();
        const defaultColor = styles.getPropertyValue("--copy-text").trim();

        const setButtonState = (
            label,
            background = defaultBackground,
            color = defaultColor,
        ) => {{
            button.innerText = label;
            button.style.background = background;
            button.style.color = color;
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
                    setButtonState("COPIED", "#22c55e", "#fff");
                    return;
                }}

                if (fallbackCopy()) {{
                    setButtonState("COPIED", "#22c55e", "#fff");
                    return;
                }}

                setButtonState("USE DOWNLOAD", "#600");
            }} catch (error) {{
                if (fallbackCopy()) {{
                    setButtonState("COPIED", "#22c55e", "#fff");
                    return;
                }}

                setButtonState(
                    window.isSecureContext ? "FAILED" : "USE DOWNLOAD",
                    "#600",
                    "#fff",
                );
            }}
        }});
    }})();
    </script>
    '''
    st.html(html, unsafe_allow_javascript=True)
