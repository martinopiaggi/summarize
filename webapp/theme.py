"""Theme CSS generation for the Streamlit UI.

The visual rules live in ``theme.css`` next to this module. This keeps
the Python side tiny: we just pick the right CSS custom-property block
for the active theme and prepend it to the shared stylesheet.

Tokens are a warm graphite ramp with one coral grease-pencil accent
(#ff6363); Inter carries the interface and JetBrains Mono is reserved for
the slate metadata under the provider.
"""

from pathlib import Path

_CSS_PATH = Path(__file__).parent / "theme.css"

_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Inter:wght@100..900&"
    "family=JetBrains+Mono:wght@100..800&display=swap');"
)

_DARK_VARS = """:root {
    --bg: #141312;
    --text: #f3efe9;
    --secondary: #1b1917;
    --elevated: #24211d;
    --row: rgba(255, 248, 240, 0.05);
    --border: rgba(255, 248, 240, 0.10);
    --border-strong: #322e29;
    --muted: #a59d94;
    --faint: #8f877d;
    --accent: #ff6363;
    --accent-hover: #ff8577;
    --on-accent: #141312;
    --link: #f29183;
    --link-hover: #ffb0a5;
    --selection: rgba(255, 99, 99, 0.26);
    --focus: rgba(255, 99, 99, 0.55);
    --radius-s: 6px;
    --radius-m: 8px;
    --radius-l: 12px;
    --font-ui: Inter, "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    --font-mono: "JetBrains Mono", "SF Mono", ui-monospace, Consolas, monospace;
}"""

_LIGHT_VARS = """:root {
    --bg: #fbfaf8;
    --text: #1c1a17;
    --secondary: #f5f2ee;
    --elevated: #eeeae4;
    --row: rgba(28, 25, 22, 0.05);
    --border: rgba(28, 25, 22, 0.10);
    --border-strong: #e0dbd3;
    --muted: #6a645c;
    --faint: #766f66;
    --accent: #ff6363;
    --accent-hover: #ec4f45;
    --on-accent: #1c1a17;
    --link: #9d332b;
    --link-hover: #7f2822;
    --selection: rgba(255, 99, 99, 0.18);
    --focus: rgba(255, 99, 99, 0.45);
    --radius-s: 6px;
    --radius-m: 8px;
    --radius-l: 12px;
    --font-ui: Inter, "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    --font-mono: "JetBrains Mono", "SF Mono", ui-monospace, Consolas, monospace;
}"""

_SYSTEM_VARS = (
    f"{_LIGHT_VARS}\n"
    "@media (prefers-color-scheme: dark) {"
    f"{_DARK_VARS}"
    "}"
)


def _theme_vars(theme: str) -> str:
    if theme == "dark":
        return _DARK_VARS
    if theme == "light":
        return _LIGHT_VARS
    return _SYSTEM_VARS


def get_custom_css(theme: str = "system") -> str:
    """Return the full ``<style>`` block for the given theme."""
    css_body = _CSS_PATH.read_text(encoding="utf-8")
    return (
        "<style>\n"
        f"{_FONT_IMPORT}\n\n"
        f"{_theme_vars(theme)}\n\n"
        f"{css_body}\n"
        "</style>"
    )


def mermaid_theme_vars(theme: str) -> str:
    """Return CSS variable definitions used by the embedded Mermaid frame.

    The Mermaid iframe uses ``--bg`` / ``--fg`` (not ``--text`` /
    ``--secondary``), so it needs its own block.
    """
    if theme == "dark":
        return ":root { --bg: #141312; --fg: #f3efe9; }"
    if theme == "light":
        return ":root { --bg: #fbfaf8; --fg: #1c1a17; }"
    return (
        ":root { --bg: #fbfaf8; --fg: #1c1a17; }\n"
        "@media (prefers-color-scheme: dark) {"
        " :root { --bg: #141312; --fg: #f3efe9; }"
        " }"
    )
