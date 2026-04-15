"""Theme CSS generation for the Streamlit UI.

The visual rules live in ``theme.css`` next to this module. This keeps
the Python side tiny: we just pick the right CSS custom-property block
for the active theme and prepend it to the shared stylesheet.
"""

from pathlib import Path

_CSS_PATH = Path(__file__).parent / "theme.css"

_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=JetBrains+Mono:wght@400;700&"
    "family=Space+Grotesk:wght@400;700&display=swap');"
)

_DARK_VARS = ":root { --bg: #0a0a0a; --text: #e8e8e8; --secondary: #141414; }"
_LIGHT_VARS = ":root { --bg: #ffffff; --text: #1a1a1a; --secondary: #f0f0f0; }"
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
        return ":root { --bg: #0a0a0a; --fg: #e8e8e8; }"
    if theme == "light":
        return ":root { --bg: #ffffff; --fg: #1a1a1a; }"
    return (
        ":root { --bg: #ffffff; --fg: #1a1a1a; }\n"
        "@media (prefers-color-scheme: dark) {"
        " :root { --bg: #0a0a0a; --fg: #e8e8e8; }"
        " }"
    )
