"""Detect ```mermaid fenced blocks in summary markdown and render them.

Each block is rendered as an isolated Streamlit ``components.html``
iframe with Mermaid + svg-pan-zoom for wheel zoom, drag pan, and
fullscreen. Markdown around the blocks is passed through verbatim.
"""

import re
from html import escape as _html_escape

import streamlit as st
import streamlit.components.v1 as components

from webapp.theme import mermaid_theme_vars

_MERMAID_RE = re.compile(r"```mermaid[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _render_mermaid_diagram(code: str, theme: str) -> None:
    """Render a single Mermaid.js diagram with wheel zoom, drag pan, and fullscreen."""
    code_safe = _html_escape(code.strip())
    follow_system = "true" if theme == "system" else "false"
    forced_theme = "dark" if theme == "dark" else "default"
    theme_vars = mermaid_theme_vars(theme)

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  {theme_vars}
  html, body {{
    margin: 0; padding: 0; background: transparent;
    height: 100%; overflow: hidden;
    color: var(--fg);
  }}
  body {{ font-family: -apple-system, system-ui, 'Space Grotesk', sans-serif; }}
  .wrap {{
    position: relative;
    width: 100%;
    height: 100vh;
    min-height: 420px;
  }}
  .stage {{ width: 100%; height: 100%; }}
  .stage.panzoom {{ overflow: hidden; cursor: grab; }}
  .stage.panzoom.grabbing {{ cursor: grabbing; }}
  .mermaid {{ width: 100%; height: 100%; display: flex;
              align-items: center; justify-content: center; }}
  .mermaid svg {{ display: block; }}
  .stage.panzoom .mermaid svg {{
    width: 100% !important; height: 100% !important; max-width: none !important;
  }}
  .toolbar {{
    position: absolute; top: 8px; right: 8px;
    display: flex; gap: 0;
    background: rgba(128,128,128,0.14);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border: 1px solid rgba(128,128,128,0.4);
    padding: 0;
    font-family: 'JetBrains Mono', monospace;
    z-index: 10;
    user-select: none;
  }}
  .toolbar button {{
    background: transparent; border: 0; color: inherit;
    font-family: inherit; font-weight: 700; cursor: pointer;
    padding: 4px 10px; font-size: 14px; line-height: 1.1;
    min-width: 30px;
  }}
  .toolbar button + button {{ border-left: 1px solid rgba(128,128,128,0.4); }}
  .toolbar button:hover {{ background: rgba(128,128,128,0.25); }}
  .toolbar button:focus {{ outline: none; background: rgba(128,128,128,0.25); }}
  .hint {{
    position: absolute; bottom: 6px; right: 10px;
    font-size: 10px; font-family: 'JetBrains Mono', monospace;
    opacity: 0.45; pointer-events: none; letter-spacing: 0.03em;
  }}
  .mermaid-error {{
    color: #c33; font-family: 'JetBrains Mono', monospace;
    padding: 0.75rem; white-space: pre-wrap;
  }}
  :fullscreen, :-webkit-full-screen {{ background: var(--bg); color: var(--fg); }}
  :fullscreen .wrap, :-webkit-full-screen .wrap {{ background: var(--bg); }}
  ::backdrop {{ background: var(--bg); }}
</style>
</head>
<body>
<div class="wrap" id="wrap">
  <div class="toolbar" role="toolbar" aria-label="Diagram controls">
    <button type="button" data-action="out" title="Zoom out">\u2212</button>
    <button type="button" data-action="in" title="Zoom in">+</button>
    <button type="button" data-action="reset" title="Reset (dbl-click)">\u27f2</button>
    <button type="button" data-action="fullscreen" title="Fullscreen">\u26f6</button>
  </div>
  <div class="stage" id="stage">
    <div class="mermaid">{code_safe}</div>
  </div>
  <div class="hint" id="hint">scroll \u00b7 drag \u00b7 dbl-click</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';

  const followSystem = {follow_system};
  const prefersDark = window.matchMedia
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = followSystem ? (prefersDark ? 'dark' : 'default') : '{forced_theme}';
  mermaid.initialize({{ startOnLoad: false, theme, securityLevel: 'loose' }});

  const stage = document.getElementById('stage');
  const fsBtn = document.querySelector('[data-action="fullscreen"]');
  let panZoom = null;

  const safeFit = () => {{
    if (!panZoom) return;
    try {{ panZoom.resize(); panZoom.fit(); panZoom.center(); }} catch (e) {{}}
  }};

  (async () => {{
    try {{
      await mermaid.run({{ querySelector: '.mermaid' }});
      const svg = document.querySelector('.mermaid svg');
      if (svg && typeof window.svgPanZoom === 'function') {{
        svg.removeAttribute('style');
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        panZoom = window.svgPanZoom(svg, {{
          zoomEnabled: true,
          controlIconsEnabled: false,
          fit: true,
          center: true,
          contain: false,
          minZoom: 0.2,
          maxZoom: 12,
          zoomScaleSensitivity: 0.35,
          dblClickZoomEnabled: false,
          mouseWheelZoomEnabled: true,
          beforePan: () => {{ stage.classList.add('grabbing'); return true; }},
        }});
        stage.classList.add('panzoom');
        const releaseGrab = () => stage.classList.remove('grabbing');
        stage.addEventListener('mouseup', releaseGrab);
        stage.addEventListener('mouseleave', releaseGrab);
        svg.addEventListener('dblclick', (e) => {{
          e.preventDefault();
          if (panZoom) {{ panZoom.resetZoom(); panZoom.center(); panZoom.fit(); }}
        }});
      }}
    }} catch (err) {{
      const el = document.querySelector('.mermaid');
      el.classList.add('mermaid-error');
      el.textContent = 'Mermaid render error: '
        + (err && err.message ? err.message : err);
    }}
  }})();

  document.querySelectorAll('.toolbar button').forEach(btn => {{
    btn.addEventListener('click', async () => {{
      const a = btn.dataset.action;
      if (a === 'fullscreen') {{
        try {{
          if (document.fullscreenElement) {{
            await document.exitFullscreen();
          }} else {{
            await document.documentElement.requestFullscreen();
          }}
        }} catch (e) {{ /* fullscreen may be blocked */ }}
        return;
      }}
      if (!panZoom) return;
      if (a === 'in') panZoom.zoomBy(1.3);
      else if (a === 'out') panZoom.zoomBy(1 / 1.3);
      else if (a === 'reset') {{ panZoom.resetZoom(); panZoom.center(); panZoom.fit(); }}
    }});
  }});

  document.addEventListener('fullscreenchange', () => {{
    const active = !!document.fullscreenElement;
    if (fsBtn) fsBtn.textContent = active ? '\u2922' : '\u26f6';
    setTimeout(safeFit, 80);
  }});

  window.addEventListener('resize', safeFit);
</script>
</body>
</html>
"""
    components.html(page, height=560, scrolling=False)


def render_summary_with_mermaid(text: str) -> None:
    """Render markdown, detecting ```mermaid fenced blocks and rendering them as diagrams."""
    if not text:
        return
    theme = st.session_state.get("theme", "system")
    cursor = 0
    for match in _MERMAID_RE.finditer(text):
        before = text[cursor:match.start()]
        if before.strip():
            st.markdown(before)
        _render_mermaid_diagram(match.group(1), theme)
        cursor = match.end()
    tail = text[cursor:]
    if tail.strip():
        st.markdown(tail)
