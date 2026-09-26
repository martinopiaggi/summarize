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


@pytest.mark.parametrize("theme", ["dark", "system", "light"])
def test_sidebar_collapse_arrows_use_accent_color(theme):
    """Both sidebar arrows must be accent-colored, and beat the generic
    header-button rule that paints them with the text color."""
    css = get_custom_css(theme)
    assert any(
        "color: var(--accent) !important;" in b
        for b in _block_for(css, '[data-testid="stExpandSidebarButton"]')
    )
    assert any(
        "fill: var(--accent) !important;" in b
        for b in _block_for(css, '[data-testid="stExpandSidebarButton"] svg')
    )
    # The stronger variant is what actually outranks the header-button rule.
    assert 'button[kind="headerNoPadding"][data-testid="stExpandSidebarButton"] svg' in css
    assert css.index('[data-testid="stExpandSidebarButton"] svg') > css.index(
        'button[kind="headerNoPadding"] svg'
    )


def test_sidebar_starts_collapsed():
    import inspect

    from webapp import ui

    assert 'initial_sidebar_state="collapsed"' in inspect.getsource(ui.main)
