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
            --copy-border: #242728;
            --copy-text: #f4f4f6;
            --copy-hover-bg: #1a1a1a;
            --copy-success-bg: #59d499;
            --copy-success-text: #101010;
            --copy-danger-bg: #ff6363;
            --copy-danger-text: #101010;
        }
        """
    if theme == "light":
        return """
        :root {
            --copy-bg: #f7f7f7;
            --copy-border: #e4e4e4;
            --copy-text: #1a1a1a;
            --copy-hover-bg: #efefef;
            --copy-success-bg: #006b4f;
            --copy-success-text: #ffffff;
            --copy-danger-bg: #b12424;
            --copy-danger-text: #ffffff;
        }
        """
    return """
    :root {
        --copy-bg: #f7f7f7;
        --copy-border: #e4e4e4;
        --copy-text: #1a1a1a;
        --copy-hover-bg: #efefef;
        --copy-success-bg: #006b4f;
        --copy-success-text: #ffffff;
        --copy-danger-bg: #b12424;
        --copy-danger-text: #ffffff;
    }

    @media (prefers-color-scheme: dark) {
        :root {
            --copy-bg: #141414;
            --copy-border: #242728;
            --copy-text: #f4f4f6;
            --copy-hover-bg: #1a1a1a;
            --copy-success-bg: #59d499;
            --copy-success-text: #101010;
            --copy-danger-bg: #ff6363;
            --copy-danger-text: #101010;
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
        border: 1px solid var(--copy-border);
        border-radius: 6px;
        box-sizing: border-box;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 500;
        font-size: 0.6875rem;
        letter-spacing: 0.02em;
        line-height: 1.5;
        text-transform: uppercase;
        cursor: pointer;
        transition: background-color 0.12s ease, color 0.12s ease, border-color 0.12s ease;
    }}

    #copyBtn:hover {{
        background: var(--copy-hover-bg);
        color: var(--copy-text);
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
        const successBackground = styles.getPropertyValue("--copy-success-bg").trim();
        const successColor = styles.getPropertyValue("--copy-success-text").trim();
        const dangerBackground = styles.getPropertyValue("--copy-danger-bg").trim();
        const dangerColor = styles.getPropertyValue("--copy-danger-text").trim();

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
                    setButtonState("COPIED", successBackground, successColor);
                    return;
                }}

                if (fallbackCopy()) {{
                    setButtonState("COPIED", successBackground, successColor);
                    return;
                }}

                setButtonState("USE DOWNLOAD", dangerBackground, dangerColor);
            }} catch (error) {{
                if (fallbackCopy()) {{
                    setButtonState("COPIED", successBackground, successColor);
                    return;
                }}

                setButtonState(
                    window.isSecureContext ? "FAILED" : "USE DOWNLOAD",
                    dangerBackground,
                    dangerColor,
                );
            }}
        }});
    }})();
    </script>
    '''
    st.html(html, unsafe_allow_javascript=True)
