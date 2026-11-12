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
            --copy-bg: transparent;
            --copy-border: #322e29;
            --copy-text: #f3efe9;
            --copy-hover-bg: #1c1a17;
            --copy-success-bg: #7fc6a8;
            --copy-success-text: #141312;
            --copy-danger-bg: #ff6363;
            --copy-danger-text: #141312;
        }
        """
    if theme == "light":
        return """
        :root {
            --copy-bg: transparent;
            --copy-border: #e0dbd3;
            --copy-text: #1c1a17;
            --copy-hover-bg: #eeeae4;
            --copy-success-bg: #2f6f57;
            --copy-success-text: #ffffff;
            --copy-danger-bg: #9d332b;
            --copy-danger-text: #ffffff;
        }
        """
    return """
    :root {
        --copy-bg: transparent;
        --copy-border: #e0dbd3;
        --copy-text: #1c1a17;
        --copy-hover-bg: #eeeae4;
        --copy-success-bg: #2f6f57;
        --copy-success-text: #ffffff;
        --copy-danger-bg: #9d332b;
        --copy-danger-text: #ffffff;
    }

    @media (prefers-color-scheme: dark) {
        :root {
            --copy-bg: transparent;
            --copy-border: #322e29;
            --copy-text: #f3efe9;
            --copy-hover-bg: #1c1a17;
            --copy-success-bg: #7fc6a8;
            --copy-success-text: #141312;
            --copy-danger-bg: #ff6363;
            --copy-danger-text: #141312;
        }
    }
    """


def _button_style(button_id: str) -> str:
    """Shared CSS for the clipboard buttons injected with ``st.html``."""
    return f'''#{button_id} {{
        width: 100%;
        min-height: 44px;
        padding: 0 16px;
        background: var(--copy-bg);
        color: var(--copy-text);
        border: 1px solid var(--copy-border);
        border-radius: 8px;
        box-sizing: border-box;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        font-family: 'Inter', -apple-system, system-ui, sans-serif;
        font-weight: 500;
        font-size: 13px;
        letter-spacing: 0;
        line-height: 1.2;
        text-transform: none;
        cursor: pointer;
        transition: background-color 0.12s ease, color 0.12s ease, border-color 0.12s ease;
    }}

    #{button_id}:hover {{
        background: var(--copy-hover-bg);
        color: var(--copy-text);
    }}'''


def copy_to_clipboard(text: str, theme: str = "system"):
    """Render a "Copy to clipboard" button wired to the given text."""
    json_text = json.dumps(text)
    theme_vars = _theme_vars(theme)

    html = f'''
    <style>
    {theme_vars}

    {_button_style("copyBtn")}
    </style>
    <div style="width: 100%;">
        <textarea id="copyBuffer" style="
            position: fixed;
            left: -9999px;
            top: 0;
            opacity: 0;
            pointer-events: none;
        "></textarea>
        <button id="copyBtn">Copy to clipboard</button>
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
                    setButtonState("Copied", successBackground, successColor);
                    return;
                }}

                if (fallbackCopy()) {{
                    setButtonState("Copied", successBackground, successColor);
                    return;
                }}

                setButtonState("Use download", dangerBackground, dangerColor);
            }} catch (error) {{
                if (fallbackCopy()) {{
                    setButtonState("Copied", successBackground, successColor);
                    return;
                }}

                setButtonState(
                    window.isSecureContext ? "Failed" : "Use download",
                    dangerBackground,
                    dangerColor,
                );
            }}
        }});
    }})();
    </script>
    '''
    st.html(html, unsafe_allow_javascript=True)


def paste_from_clipboard_button(
    target_key: str = "clipboard_paste",
    theme: str = "system",
    notice: str = "",
):
    """Render a "Paste from clipboard" button that fills a hidden input.

    Browsers only expose the clipboard to page scripts, so this is raw
    HTML/JS (``st.html`` is not iframed). The click reads the clipboard,
    writes the text into the Streamlit input whose container carries
    ``st-key-<target_key>`` and dispatches an ``input`` event -- that
    event is what makes Streamlit rerun with the pasted value.

    ``notice`` is the server's record of the last paste. It is drawn in a
    status line under the button, because the paste's own rerun wipes any
    button label before the user can read it.

    Clipboard reads need a secure context (HTTPS or localhost). Anywhere
    else the button reports failure so the user can paste with Ctrl+V.
    """
    json_target = json.dumps(target_key)
    json_notice = json.dumps(notice)
    theme_vars = _theme_vars(theme)

    html = f'''
    <style>
    {theme_vars}

    {_button_style("pasteBtn")}

    #pasteStatus {{
        display: none;
        margin-top: 0.4rem;
        font-family: 'Inter', -apple-system, system-ui, sans-serif;
        font-size: 12px;
        letter-spacing: 0;
        line-height: 1.5;
    }}

    #pasteStatus.visible {{
        display: block;
    }}

    #pasteStatus.ok {{
        color: var(--copy-success-bg);
    }}

    #pasteStatus.bad {{
        color: var(--copy-danger-bg);
    }}
    </style>
    <div style="width: 100%;">
        <button id="pasteBtn">Paste from clipboard</button>
        <div id="pasteStatus" role="status" aria-live="polite"></div>
    </div>
    <script>
    (() => {{
        const button = document.getElementById("pasteBtn");
        const target = {json_target};
        const status = document.getElementById("pasteStatus");
        const initialNotice = {json_notice};

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

        const fail = () => {{
            setButtonState("Failed, use Ctrl+V", dangerBackground, dangerColor);
            setStatus("Could not read the clipboard. Press Ctrl+V instead.", "bad");
        }};

        const setStatus = (message, tone) => {{
            status.innerText = message;
            status.className = message ? `visible ${{tone}}` : "";
        }};

        if (initialNotice) setStatus(initialNotice, "ok");

        const fillStreamlitInput = (text) => {{
            const input = document.querySelector(
                `.st-key-${{target}} input, .st-key-${{target}} textarea`
            );
            if (!input) return false;

            const proto = input.tagName === "TEXTAREA"
                ? HTMLTextAreaElement.prototype
                : HTMLInputElement.prototype;
            const setValue = Object.getOwnPropertyDescriptor(proto, "value").set;
            setValue.call(input, text);
            input.dispatchEvent(new Event("input", {{ bubbles: true }}));
            input.dispatchEvent(new Event("change", {{ bubbles: true }}));
            return true;
        }};

        button.addEventListener("click", async () => {{
            if (!window.isSecureContext || !navigator.clipboard?.readText) {{
                fail();
                return;
            }}

            try {{
                const text = await navigator.clipboard.readText();
                if (!text.trim()) {{
                    setButtonState("Clipboard is empty", dangerBackground, dangerColor);
                    setStatus("The clipboard is empty - copy something first.", "bad");
                    return;
                }}
                if (!fillStreamlitInput(text)) {{
                    fail();
                    return;
                }}
                setButtonState("Pasted", successBackground, successColor);
                setStatus(
                    `\u2713 Pasted ${{text.length.toLocaleString()}} characters`,
                    "ok",
                );
            }} catch (error) {{
                fail();
            }}
        }});
    }})();
    </script>
    '''
    st.html(html, unsafe_allow_javascript=True)
