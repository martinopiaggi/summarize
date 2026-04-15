"""Clipboard button rendered as raw HTML + JS.

Streamlit has no native clipboard widget; we inject a <button> that
uses ``navigator.clipboard`` with an ``execCommand('copy')`` fallback
for non-secure contexts.
"""

import json

import streamlit as st


def copy_to_clipboard(text: str):
    """Render a "COPY TO CLIPBOARD" button wired to the given text."""
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

        const setButtonState = (label, background = "#fff", color = "#000") => {{
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
