"""Sidebar history: in-memory list + on-disk archive of summaries."""

from datetime import datetime
from pathlib import Path

import streamlit as st


def _extract_label(text: str, source: str) -> str:
    """Extract a short display label from summary content, falling back to source domain."""
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # Skip timestamps (00:00:00 ...), URLs, code fences
        if len(stripped) > 2 and stripped[:2].isdigit() and ":" in stripped[:8]:
            continue
        if stripped.startswith("http"):
            continue
        if stripped.startswith("```"):
            continue
        # Skip ASCII art (low letter ratio)
        alpha = sum(1 for c in stripped if c.isalpha())
        if len(stripped) > 5 and alpha < len(stripped) * 0.4:
            continue
        # Strip markdown formatting
        label = stripped.replace("**", "").strip()
        label = label.lstrip("#-|>*~`").strip()
        # Skip short all-caps section labels (TITLE, IDEAS, STEPS, etc.)
        if label.isupper() and len(label) < 20:
            continue
        if label:
            return label
    # Fall back to domain name from source URL
    if source.startswith("http"):
        try:
            return source.split("/")[2].split(".")[-2]
        except (IndexError, ValueError):
            pass
    return ""


def add_to_history(source: str, provider: str, prompt_type: str, summary: str):
    """Push a new summary onto the in-memory history (most-recent first, capped at 10)."""
    label = _extract_label(summary, source) or provider
    st.session_state.history.insert(
        0,
        {
            "source": source[:50],
            "provider": label[:30],
            "prompt_type": prompt_type,
            "summary": summary,
            "timestamp": datetime.now().strftime("%H:%M"),
        },
    )
    st.session_state.history = st.session_state.history[:10]


def load_history_from_disk(output_dir: str) -> list:
    """Load summary history from the output directory."""
    history = []
    output_path = Path(output_dir)
    if not output_path.exists():
        return history

    md_files = sorted(
        output_path.glob("*.md"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    for f in md_files[:10]:
        try:
            content = f.read_text(encoding="utf-8")
            lines = content.split("\n")

            source = ""
            if lines and lines[0].startswith("# Summary for: "):
                source = lines[0][len("# Summary for: "):]

            timestamp = ""
            if len(lines) > 2 and lines[2].startswith("Generated on: "):
                ts_str = lines[2][len("Generated on: "):]
                try:
                    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    timestamp = dt.strftime("%b %d %H:%M")
                except ValueError:
                    timestamp = ts_str[:16]

            summary_text = "\n".join(lines[4:]).strip() if len(lines) > 4 else content

            label = _extract_label(summary_text, source)
            if not label:
                label = f.stem.rsplit("_", 2)[0]
            label = label[:30]

            history.append({
                "source": source[:50] if source else f.stem[:50],
                "provider": label,
                "prompt_type": "",
                "summary": summary_text,
                "timestamp": timestamp or datetime.fromtimestamp(f.stat().st_mtime).strftime("%b %d %H:%M"),
            })
        except Exception:
            continue

    return history


def save_summary_to_disk(source: str, summary: str, output_dir: str):
    """Save summary to the output directory (same format as CLI)."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    ts = datetime.now()
    clean_source = source.split("?")[0].split("/")[-1]
    if not clean_source:
        clean_source = "summary"
    filename = f"{clean_source}_{ts.strftime('%Y%m%d_%H%M%S')}.md"

    header = f"# Summary for: {source}\n\nGenerated on: {ts.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    (output_path / filename).write_text(header + summary, encoding="utf-8")
