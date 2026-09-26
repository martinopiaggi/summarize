"""Theme CSS regression checks for widget contrast fixes."""

import pytest

pytest.importorskip("streamlit")

from webapp.theme import get_custom_css


def _block_for(css, selector):
    """Return the declaration blocks whose selector list mentions ``selector``."""
    blocks = []
    for chunk in css.split("}"):
        head, sep, body = chunk.partition("{")
        if sep and selector in head:
            blocks.append(body)
    return blocks


@pytest.mark.parametrize("theme", ["dark", "system", "light"])
def test_status_bar_uses_theme_background(theme):
    """The expandable status bar (spinner + "Processing...") must not keep
    Streamlit's baked-in white summary background."""
    css = get_custom_css(theme)
    blocks = _block_for(css, '[data-testid="stExpander"] summary')
    assert any("background-color: var(--secondary) !important;" in b for b in blocks)


@pytest.mark.parametrize("theme", ["dark", "system", "light"])
def test_header_stop_button_uses_theme_colors(theme):
    """The header "Stop" button is button[kind="header"]; it must be themed
    so it is not dark text on the dark header."""
    css = get_custom_css(theme)
    assert any(
        "color: var(--text) !important;" in b
        for b in _block_for(css, 'button[kind="header"]')
    )
    assert any(
        "fill: var(--text) !important;" in b
        for b in _block_for(css, 'button[kind="header"] svg')
    )


@pytest.mark.parametrize("theme", ["dark", "system", "light"])
def test_checkbox_box_uses_theme_colors(theme):
    """Checkbox box / check mark must be visible in light mode too
    (Streamlit's white box was white over white)."""
    css = get_custom_css(theme)
    assert '[data-testid="stCheckbox"] .e15oan335' in css
    assert any(
        "background-color: var(--secondary) !important;" in b
        for b in _block_for(css, '[data-testid="stCheckbox"] .e15oan335')
    )
    assert "stroke: var(--on-accent) !important;" in css
