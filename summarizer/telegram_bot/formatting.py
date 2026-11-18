"""Prepare summary Markdown for Telegram rich messages (Bot API 10.1+).

Rich messages render GitHub-flavoured Markdown natively (headings, lists,
tables, code blocks, quotes, footnotes), so summaries are sent almost as-is.
This module only:

* escapes Telegram-specific syntax that ordinary prose triggers by accident:
  ``$5`` (LaTeX math), ``~5`` (strikethrough), ``a==b`` (highlight),
  ``a || b`` (spoiler) and stray HTML tags such as ``<think>``;
* turns the pipeline's ``HH:MM:SS - URL`` chunk headers into links;
* splits long documents at block boundaries to stay under the per-message
  limits, plus a plain-text splitter for the fallback path.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

# Telegram allows 32768 characters and 500 blocks per rich message. Parts are
# measured in UTF-8 bytes of the Markdown source, which over-estimates both.
RICH_PART_BYTES = 30000
RICH_PART_BLOCKS = 400
# Plain messages: 4096 characters, counted in UTF-16 code units.
PLAIN_LIMIT = 4096

_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_TIMESTAMP_LINK_RE = re.compile(r"^(\d{1,2}:\d{2}:\d{2}) - (https?://\S+)$")
_TIMESTAMP_RE = re.compile(r"^(\d{1,2}:\d{2}:\d{2})$")
_SETEXT_RE = re.compile(r"^\s*=+\s*$")
_AUTOLINK_RE = re.compile(r"<(?:https?://|mailto:)[^\s<>]*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<(?=[/!?A-Za-z])/?([A-Za-z][A-Za-z0-9-]*)?")
# Inline tags Telegram supports and models sometimes emit (e.g. <br> in tables).
_ALLOWED_TAGS = frozenset(
    {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "mark", "sub", "sup", "br", "tg-spoiler"}
)


@dataclass(frozen=True)
class Footer:
    """Small print under a summary, in rich (HTML block) and plain form."""

    rich: str
    plain: str


def build_footer(items: Iterable[str]) -> Footer:
    items = [str(item) for item in items if item]
    if not items:
        return Footer("", "")
    escaped = " · ".join(html.escape(item, quote=False) for item in items)
    return Footer(f"<footer>{escaped}</footer>", "— " + " · ".join(items))


def escape_html(text: object) -> str:
    """Escape text for Telegram's classic HTML parse mode (UI messages)."""
    return html.escape(str(text), quote=False)


# ── Markdown preparation ──────────────────────────────────────────────────────


def prepare_markdown(summary: str) -> str:
    """Make LLM Markdown safe and tidy for a Telegram rich message."""
    out: List[str] = []
    fence: Optional[str] = None
    lines = (summary or "").replace("\r\n", "\n").split("\n")
    # One unlinked chunk timestamp (a single-chunk file summary) says nothing.
    bare_timestamps = sum(1 for line in lines if _TIMESTAMP_RE.match(line.strip()))
    for line in lines:
        match = _FENCE_RE.match(line)
        if fence is not None:
            out.append(line)
            if _closes_fence(match, fence):
                fence = None
            continue
        if match:
            fence = match.group(1)
            out.append(line)
            continue
        stripped = line.strip()
        timestamp = _TIMESTAMP_LINK_RE.match(stripped)
        if timestamp:
            out.append(f"**[⏱ {timestamp.group(1)}]({_fix_query(timestamp.group(2))})**")
            continue
        timestamp = _TIMESTAMP_RE.match(stripped)
        if timestamp:
            if bare_timestamps > 1:
                out.append(f"**⏱ {timestamp.group(1)}**")
            continue
        out.append(_escape_line(line))
    if fence is not None:
        out.append(fence)  # close a fence the model left open
    return "\n".join(out).strip()


def _closes_fence(match, fence: str) -> bool:
    return bool(
        match
        and match.group(1)[0] == fence[0]
        and len(match.group(1)) >= len(fence)
        and not match.group(2).strip()
    )


def _fix_query(url: str) -> str:
    # The pipeline appends "&t=" even to URLs without a query (youtu.be/ID&t=42).
    if "?" not in url and "&" in url:
        return url.replace("&", "?", 1)
    return url


def _escape_line(line: str) -> str:
    """Escape one line, leaving inline code spans untouched."""
    if _SETEXT_RE.match(line):
        return line  # "=====" under a title is a heading underline
    table_row = line.lstrip().startswith("|")
    out: List[str] = []
    i, n = 0, len(line)
    while i < n:
        tick = line.find("`", i)
        if tick == -1:
            out.append(_escape_text(line[i:], table_row))
            break
        out.append(_escape_text(line[i:tick], table_row))
        run_end = tick
        while run_end < n and line[run_end] == "`":
            run_end += 1
        run = line[tick:run_end]
        close = _find_closing_run(line, run, run_end)
        if close == -1:
            out.append(run)  # unmatched backticks are literal text
            i = run_end
        else:
            out.append(line[tick : close + len(run)])
            i = close + len(run)
    return "".join(out)


def _find_closing_run(line: str, run: str, start: int) -> int:
    pos = start
    while True:
        pos = line.find(run, pos)
        if pos == -1:
            return -1
        end = pos + len(run)
        if end < len(line) and line[end] == "`":
            while end < len(line) and line[end] == "`":
                end += 1
            pos = end  # a longer run does not close this span
            continue
        return pos


def _escape_text(text: str, table_row: bool) -> str:
    pieces: List[str] = []
    last = 0
    for match in _AUTOLINK_RE.finditer(text):  # keep <https://...> autolinks
        pieces.append(_escape_plain(text[last : match.start()], table_row))
        pieces.append(match.group(0))
        last = match.end()
    pieces.append(_escape_plain(text[last:], table_row))
    return "".join(pieces)


def _escape_plain(text: str, table_row: bool) -> str:
    if not text:
        return text
    text = _TAG_RE.sub(_escape_tag, text)
    text = re.sub(r"(?<!\\)\$(?=\d)", r"\\$", text)  # $5 is money, not math
    text = re.sub(r"(?<![~\\])~(?=\d)", r"\\~", text)  # ~5 means "about"
    text = text.replace("==", "=\\=")
    if not table_row:  # "||" is an empty cell inside tables
        text = text.replace("||", "|\\|")
    return text


def _escape_tag(match) -> str:
    tag = (match.group(1) or "").lower()
    if tag in _ALLOWED_TAGS:
        return match.group(0)
    return "\\" + match.group(0)


# ── Splitting ─────────────────────────────────────────────────────────────────


def split_markdown(
    markdown: str, max_bytes: int = RICH_PART_BYTES, max_blocks: int = RICH_PART_BLOCKS
) -> List[str]:
    """Split Markdown into rich-message parts at block boundaries."""
    parts: List[str] = []
    current: List[str] = []
    size = count = 0
    for block in _blocks(markdown):
        for piece in _split_block(block, max_bytes, max_blocks):
            piece_size, piece_count = _size(piece) + 2, _block_count(piece)
            if current and (size + piece_size > max_bytes or count + piece_count > max_blocks):
                parts.append("\n\n".join(current))
                current, size, count = [], 0, 0
            current.append(piece)
            size += piece_size
            count += piece_count
    if current:
        parts.append("\n\n".join(current))
    return parts


def halve_markdown(markdown: str) -> List[str]:
    """Split a part roughly in half (used when Telegram still finds it too big)."""
    blocks = sum(_block_count(block) for block in _blocks(markdown))
    return split_markdown(markdown, max(500, _size(markdown) // 2 + 1), max(2, blocks // 2 + 1))


def split_plain(text: str, limit: int = PLAIN_LIMIT) -> List[str]:
    """Split text into chunks of at most ``limit`` UTF-16 code units."""
    chunks: List[str] = []
    current: List[str] = []
    length = 0
    for line in text.split("\n"):
        for piece in _hard_split(line, limit):
            piece_length = utf16_len(piece) + 1
            if current and length + piece_length > limit:
                chunks.append("\n".join(current))
                current, length = [], 0
            current.append(piece)
            length += piece_length
    if current:
        chunks.append("\n".join(current))
    return [chunk for chunk in chunks if chunk.strip()] or ["(empty)"]


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def _blocks(markdown: str) -> List[str]:
    """Top-level blocks separated by blank lines; fenced code stays whole."""
    blocks: List[str] = []
    current: List[str] = []
    fence: Optional[str] = None
    for line in markdown.split("\n"):
        match = _FENCE_RE.match(line)
        if fence is not None:
            current.append(line)
            if _closes_fence(match, fence):
                fence = None
            continue
        if match:
            fence = match.group(1)
            current.append(line)
            continue
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _block_count(block: str) -> int:
    """Upper bound of the Telegram blocks a Markdown block produces."""
    lines = block.split("\n")
    if _is_fenced(lines):
        return 1
    return 1 + sum(1 for line in lines if line.strip())


def _is_fenced(lines: List[str]) -> bool:
    return len(lines) > 1 and bool(_FENCE_RE.match(lines[0])) and bool(_FENCE_RE.match(lines[-1]))


def _is_table_delimiter(line: str) -> bool:
    stripped = line.strip()
    return "-" in stripped and set(stripped) <= set("|:- ")


def _split_block(block: str, max_bytes: int, max_blocks: int) -> List[str]:
    if _size(block) <= max_bytes and _block_count(block) <= max_blocks:
        return [block]
    lines = block.split("\n")
    if _is_fenced(lines):
        opener, closer = lines[0], lines[-1]
        budget = max_bytes - _size(opener) - _size(closer) - 2
        return [
            "\n".join([opener, *chunk, closer]) for chunk in _group_lines(lines[1:-1], budget, 10**9)
        ]
    header: List[str] = []
    if len(lines) > 2 and lines[0].lstrip().startswith("|") and _is_table_delimiter(lines[1]):
        header, lines = lines[:2], lines[2:]  # repeat the table header in every piece
    budget = max_bytes - _size("\n".join(header)) - 1
    groups = _group_lines(lines, budget, max(1, max_blocks - len(header) - 1))
    return ["\n".join(header + group) for group in groups]


def _group_lines(lines: List[str], max_bytes: int, max_lines: int) -> List[List[str]]:
    groups: List[List[str]] = []
    current: List[str] = []
    size = 0
    for line in lines:
        for piece in _hard_split(line, max(1, max_bytes), measure=_size):
            piece_size = _size(piece) + 1
            if current and (size + piece_size > max_bytes or len(current) >= max_lines):
                groups.append(current)
                current, size = [], 0
            current.append(piece)
            size += piece_size
    if current:
        groups.append(current)
    return groups or [[]]


def _hard_split(line: str, limit: int, measure=utf16_len) -> List[str]:
    """Split one over-long line, preferring whitespace boundaries."""
    if measure(line) <= limit:
        return [line]
    pieces: List[str] = []
    rest = line
    while measure(rest) > limit:
        cut = _max_prefix(rest, limit, measure)
        space = rest.rfind(" ", 0, cut)
        if space > cut // 2:
            cut = space
        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return pieces


def _max_prefix(text: str, limit: int, measure) -> int:
    """Longest prefix length (in characters) whose measure fits ``limit``."""
    low, high = 1, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if measure(text[:mid]) <= limit:
            low = mid
        else:
            high = mid - 1
    return low
