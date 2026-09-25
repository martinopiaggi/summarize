"""Theme CSS generation for the Streamlit UI.

The visual rules live in ``theme.css`` next to this module. This keeps
the Python side tiny: we just pick the right CSS custom-property block
for the active theme and prepend it to the shared stylesheet.

Tokens mirror the RaggioProietto theme (Raycast-derived: coral #ff6363
on grayscale surfaces with hairline borders).
"""

from pathlib import Path

_CSS_PATH = Path(__file__).parent / "theme.css"

_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Inter:wght@100..900&"
    "family=JetBrains+Mono:wght@100..800&display=swap');"
)

_DARK_VARS = """:root {
    --bg: #101010;
    --text: #f4f4f6;
    --secondary: #141414;
    --elevated: #1a1a1a;
    --row: rgba(255, 255, 255, 0.06);
    --border: rgba(255, 255, 255, 0.08);
    --border-strong: #242728;
    --muted: #9c9c9d;
    --faint: #8f8f90;
    --accent: #ff6363;
    --accent-hover: #ff8585;
    --on-accent: #101010;
    --link: #ff6363;
    --link-hover: #ff8585;
    --selection: rgba(255, 99, 99, 0.28);
    --focus: rgba(255, 99, 99, 0.55);
    --radius-s: 6px;
    --radius-m: 8px;
    --radius-l: 12px;
    --font-ui: Inter, "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    --font-mono: "JetBrains Mono", "SF Mono", ui-monospace, Consolas, monospace;
}"""

_LIGHT_VARS = """:root {
    --bg: #ffffff;
    --text: #1a1a1a;
    --secondary: #f7f7f7;
    --elevated: #efefef;
    --row: rgba(0, 0, 0, 0.045);
    --border: rgba(0, 0, 0, 0.08);
    --border-strong: #e4e4e4;
    --muted: #6b6b6b;
    --faint: #707070;
    --accent: #ff6363;
    --accent-hover: #e23e3e;
    --on-accent: #101010;
    --link: #b12424;
    --link-hover: #8f1c1c;
    --selection: rgba(255, 99, 99, 0.18);
    --focus: rgba(255, 99, 99, 0.55);
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
        return ":root { --bg: #101010; --fg: #f4f4f6; }"
    if theme == "light":
        return ":root { --bg: #ffffff; --fg: #1a1a1a; }"
    return (
        ":root { --bg: #ffffff; --fg: #1a1a1a; }\n"
        "@media (prefers-color-scheme: dark) {"
        " :root { --bg: #101010; --fg: #f4f4f6; }"
        " }"
    )
