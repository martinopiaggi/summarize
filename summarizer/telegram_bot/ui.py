"""Texts and inline keyboards of the Telegram bot (pure functions).

UI messages use Telegram's classic HTML parse mode; only summaries are rich
Markdown messages. Callback data stays under Telegram's 64-byte limit:

    set:open:<field>  set:val:<field>:<i>  set:tog:<field>  set:reset|home|close
    cfg:open:<field>  cfg:val:<field>:<i>  cfg:dl|home|close
    res:<result>:md|tx|rs|back  res:<result>:rs:<i>
    up:<token>:ok|no
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..prompts import get_available_prompts
from ..sidecars import SIDECAR_CHOICES, SIDECARS
from .formatting import escape_html as esc
from .runtime import providers_of

OUTPUT_LANGUAGES = (
    "English", "Italian", "Spanish", "French", "German", "Portuguese",
    "Chinese", "Japanese", "Korean", "Russian", "Arabic", "Hindi",
)
# Caption/transcription language codes, as in the Streamlit sidebar.
TRANSCRIPT_LANGUAGES = (
    ("en", "English"), ("es", "Spanish"), ("fr", "French"), ("de", "German"), ("it", "Italian"),
    ("pt", "Portuguese"), ("zh", "Chinese"), ("ja", "Japanese"), ("ko", "Korean"),
)

CHAT_FIELDS = {"prov": "provider", "style": "prompt_type", "olang": "output_language", "lang": "language"}
CHAT_TOGGLES = {"visual": "visual", "captions": "force_download", "mdfile": "attach_markdown"}
FIELD_TITLES = {
    "prov": "Provider",
    "style": "Style",
    "olang": "Summary language",
    "lang": "Transcript language",
    "side": "Transcript sidecar",
}

Choice = Tuple[Any, str]  # (value stored, button label)


def button(text: str, data: str) -> Dict[str, str]:
    return {"text": text, "callback_data": data}


def keyboard(rows: Sequence[Sequence[Dict[str, str]]]) -> Dict[str, Any]:
    return {"inline_keyboard": [list(row) for row in rows if row]}


def _grid(buttons: List[Dict[str, str]], columns: int = 2) -> List[List[Dict[str, str]]]:
    return [buttons[i : i + columns] for i in range(0, len(buttons), columns)]


def _on_off(value: Any) -> str:
    return "on" if value else "off"


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def short_model(model: Any) -> str:
    return str(model or "").split("/")[-1]


# ── help ──


def group_usage(username: str, reads_all: bool = False) -> str:
    """How to ask for a summary in a group, in the shortest form Telegram delivers.

    In privacy mode (the default) a bot gets plain commands only while it is
    the last bot that posted, so the @name form stays as the fallback. With
    privacy mode off Telegram delivers everything, including a plain @mention.
    """
    name = esc(username)
    if reads_all and username:
        return f"Reply to a video, voice message or link with @{name} (or /s) and I'll post a summary here."
    text = "Reply to a video, voice message or link with /s (short for /summarize) and I'll post a summary here."
    if username:
        text += f"\nIf I stay silent because another bot spoke last, add my name: /s@{name}"
    return text


def help_text(is_admin: bool, in_group: bool, username: str = "", reads_all: bool = False) -> str:
    lines = [
        "<b>Summarize</b>",
        "Send me a video link, a video, an audio file or a voice message and I'll reply "
        "with a Markdown summary.",
        "",
        "<b>What I accept</b>",
        "• Links: YouTube, X, TikTok, Instagram, Reddit, Facebook, Google Drive, Dropbox "
        "and other video pages",
        "• Videos, round video messages, audio files and voice messages",
        "• Text files (.txt, .srt, .vtt, .md…) and long pasted text",
        "",
        "Under each summary: <b>Markdown</b> sends the .md file, <b>Transcript</b> the "
        "transcript, <b>Restyle</b> redoes it in another style (fast: the transcript is cached).",
        "",
        "<b>Commands</b>",
        "/settings – provider, style and languages for this chat",
        "/style – pick the summary style",
        "/summarize – summarize a link, or reply to a message with it (short: /s)",
        "/status – what is running and queued",
        "/cancel – drop your queued jobs",
        "/id – your Telegram user and chat IDs",
    ]
    if is_admin:
        lines += [
            "",
            "<b>Admin</b>",
            "/config – view, download or replace summarizer.yaml",
            "/set key value – change one value in summarizer.yaml",
        ]
    if in_group:
        lines += ["", "<b>In this group</b>", group_usage(username, reads_all)]
    return "\n".join(lines)


# One line, comma-separated: with the same key twice in .env, only the last line counts.
ALLOW_CHAT_HINT = "to TELEGRAM_ALLOWED_CHATS in .env (one line, IDs separated by commas)"


def add_to_group_link(username: str) -> str:
    """Telegram asks which group to use and adds exactly this bot."""
    return f"https://t.me/{username}?startgroup=summarize"


def add_to_group_keyboard(username: str) -> Optional[Dict[str, Any]]:
    if not username:
        return None
    return {"inline_keyboard": [[{"text": "➕ Add me to a group", "url": add_to_group_link(username)}]]}


def setup_text(user_id: int, setup_mode: bool) -> str:
    if setup_mode:
        return (
            "👋 This Summarize bot is not linked to anyone yet.\n\n"
            f"Your Telegram user ID is <code>{user_id}</code>. Add this line to the "
            ".env file next to summarizer.yaml and restart the bot:\n\n"
            f"<code>TELEGRAM_ALLOWED_USERS={user_id}</code>\n\n"
            "The first allowed user is also the admin who can edit summarizer.yaml."
        )
    return (
        "Sorry, this is a private Summarize bot.\n"
        f"Your Telegram user ID is <code>{user_id}</code>; ask the owner to add it to "
        "TELEGRAM_ALLOWED_USERS."
    )


def group_greeting(
    username: str, chat_id: int, user_id: Optional[int], options: Any, reads_all: bool = False
) -> str:
    if not options.is_allowed(user_id, chat_id):
        return (
            "This Summarize bot is private, so I won't answer here yet.\n"
            f"This group's ID is <code>{chat_id}</code>: the bot owner can allow everyone in it "
            f"{ALLOW_CHAT_HINT}."
        )
    if chat_id in options.allowed_chats:
        who = "Everyone in this group can use me."
    else:
        who = (
            f"Only allowed users can use me here. To let everyone in this group use me, add "
            f"<code>{chat_id}</code> {ALLOW_CHAT_HINT}, then restart the bot."
        )
    return (
        f"👋 Hi! {group_usage(username, reads_all)}\n"
        f"{who}\n\n"
        f"Settings for this group: /settings@{esc(username)}"
    )


def group_denied_text(user_id: Optional[int], chat_id: int) -> str:
    if user_id is None:
        return (
            "You are posting anonymously (or as a channel), so I can't tell who you are. "
            "Turn off “Remain anonymous” in your admin rights, or the bot owner can allow this "
            f"whole group by adding <code>{chat_id}</code> {ALLOW_CHAT_HINT}."
        )
    return (
        "Sorry, this is a private Summarize bot.\n"
        f"Your user ID is <code>{user_id}</code> and this group's ID is <code>{chat_id}</code>: "
        "the bot owner can add you to TELEGRAM_ALLOWED_USERS, or everyone here with "
        "TELEGRAM_ALLOWED_CHATS."
    )


# ── chat settings ──


def chat_choices(field: str, file_config: Dict[str, Any]) -> List[Choice]:
    """Options of a settings picker; ``None`` restores the summarizer.yaml default."""
    if field == "prov":
        return [(None, "Default")] + [(name, name) for name in providers_of(file_config)]
    if field == "style":
        return [(None, "Default")] + [(name, name) for name in get_available_prompts()]
    if field == "olang":
        return [(None, "Default"), ("auto", "Same as video")] + [(name, name) for name in OUTPUT_LANGUAGES]
    if field == "lang":
        return [(None, "Default"), ("auto", "Detect")] + [(code, name) for code, name in TRANSCRIPT_LANGUAGES]
    raise KeyError(field)


def settings_text(chat: Dict[str, Any], file_config: Dict[str, Any], effective: Dict[str, Any]) -> str:
    providers = providers_of(file_config)
    default_mark = " <i>(default)</i>"

    provider = chat.get("provider") if chat.get("provider") in providers else None
    provider_name = provider or file_config.get("default_provider") or "none"
    model = short_model((providers.get(provider_name) or {}).get("model") or effective.get("model"))
    rows = [
        ("Provider", f"<b>{esc(provider_name)}</b>{'' if provider else default_mark}"
         + (f" · {esc(model)}" if model else "")),
        ("Style", f"<b>{esc(effective.get('prompt_type', ''))}</b>"
         + ("" if chat.get("prompt_type") else default_mark)),
        ("Summary language", f"<b>{esc(effective.get('output_language', 'auto'))}</b>"
         + ("" if chat.get("output_language") else default_mark)),
        ("Transcript language", f"<b>{esc(effective.get('language', 'auto'))}</b>"
         + ("" if chat.get("language") else default_mark)),
        ("Visual mode", f"<b>{_on_off(effective.get('visual'))}</b>"),
        ("YouTube captions", f"<b>{_on_off(not chat.get('force_download'))}</b>"),
        ("Attach .md file", f"<b>{_on_off(chat.get('attach_markdown'))}</b>"),
    ]
    body = "\n".join(f"{label}: {value}" for label, value in rows)
    return (
        "<b>⚙️ Settings for this chat</b>\n\n"
        f"{body}\n\n"
        "<i>Defaults come from summarizer.yaml; changes here only affect this chat.</i>"
    )


def settings_keyboard(chat: Dict[str, Any], effective: Dict[str, Any]) -> Dict[str, Any]:
    return keyboard(
        [
            [button("🔌 Provider", "set:open:prov"), button("🎨 Style", "set:open:style")],
            [button("🌐 Summary language", "set:open:olang"), button("🗣 Transcript language", "set:open:lang")],
            [
                button(f"👁 Visual: {_on_off(effective.get('visual'))}", "set:tog:visual"),
                button(f"💬 Captions: {_on_off(not chat.get('force_download'))}", "set:tog:captions"),
            ],
            [
                button(f"📄 .md file: {_on_off(chat.get('attach_markdown'))}", "set:tog:mdfile"),
                button("↺ Reset", "set:reset"),
            ],
            [button("✓ Done", "set:close")],
        ]
    )


def picker_keyboard(prefix: str, choices: List[Choice], current: Any, back: str) -> Dict[str, Any]:
    buttons = [
        button(("✓ " if value == current else "") + label[:40], f"{prefix}:{index}")
        for index, (value, label) in enumerate(choices)
    ]
    return keyboard(_grid(buttons) + [[button("« Back", back)]])


# ── results ──


def result_keyboard(result_id: str) -> Dict[str, Any]:
    return keyboard(
        [[
            button("📄 Markdown", f"res:{result_id}:md"),
            button("📝 Transcript", f"res:{result_id}:tx"),
            button("🎨 Restyle", f"res:{result_id}:rs"),
        ]]
    )


def restyle_keyboard(result_id: str, current: str) -> Dict[str, Any]:
    styles = [(name, name) for name in get_available_prompts()]
    return picker_keyboard(f"res:{result_id}:rs", styles, current, f"res:{result_id}:back")


# ── admin: summarizer.yaml ──


def config_choices(field: str, file_config: Dict[str, Any]) -> List[Choice]:
    if field == "prov":
        return [(name, name) for name in providers_of(file_config)]
    if field == "style":
        return [(name, name) for name in get_available_prompts()]
    if field == "side":
        return [(name, SIDECARS[name].LABEL if name in SIDECARS else "None") for name in SIDECAR_CHOICES]
    raise KeyError(field)


def config_text(path: Any, file_config: Dict[str, Any], effective: Optional[Dict[str, Any]], error: str = "") -> str:
    lines = ["<b>summarizer.yaml</b>", f"<code>{esc(path)}</code>", ""]
    if error:
        lines += [f"⚠️ {esc(error)}", ""]
    if not file_config:
        lines += [
            "No config file yet. Send a summarizer.yaml here to create it "
            "(or run <code>summarizer --init-config</code> on the server).",
        ]
        return "\n".join(lines)
    providers = providers_of(file_config)
    effective = effective or {}
    lines += [
        f"Default provider: <b>{esc(file_config.get('default_provider') or 'none')}</b>"
        + (f" · {esc(short_model(effective.get('model')))}" if effective.get("model") else ""),
        f"Providers: {esc(', '.join(providers) or 'none')}",
        f"Style: <b>{esc(effective.get('prompt_type', ''))}</b> · "
        f"Summary language: {esc(effective.get('output_language', 'auto'))}",
        f"Chunk size: {esc(effective.get('chunk_size'))} · Parallel calls: "
        f"{esc(effective.get('parallel_api_calls'))} · Max tokens: {esc(effective.get('max_output_tokens'))}",
        f"Sidecar: {esc(effective.get('sidecar') or 'none')} ({esc(effective.get('sidecar_order') or 'fallback')})"
        f" · Keep history: {_on_off(effective.get('keep_history'))}",
        "",
        "Change one value: <code>/set chunk-size 50000</code> (send /set for the list).",
        "Replace the whole file: send an edited summarizer.yaml here.",
    ]
    return "\n".join(lines)


def config_keyboard() -> Dict[str, Any]:
    return keyboard(
        [
            [button("⬇️ Download summarizer.yaml", "cfg:dl")],
            [button("🔌 Default provider", "cfg:open:prov"), button("🎨 Default style", "cfg:open:style")],
            [button("🛰 Sidecar", "cfg:open:side"), button("✓ Done", "cfg:close")],
        ]
    )


def set_usage_text(settings, effective: Dict[str, Any], normalize) -> str:
    lines = ["<b>/set key value</b> changes summarizer.yaml for every chat.", ""]
    for setting in settings.values():
        current = effective.get("default_provider") if setting.top_level else effective.get(normalize(setting.key))
        shown = "" if current in (None, "") else f" = <code>{esc(current)}</code>"
        lines.append(f"<code>{esc(setting.key)}</code>{shown} – {esc(setting.help)}")
    lines += ["", "Example: <code>/set prompt-type Distill Wisdom</code>"]
    return "\n".join(lines)


def upload_keyboard(token: str) -> Dict[str, Any]:
    return keyboard([[button("✅ Replace summarizer.yaml", f"up:{token}:ok"), button("✖ Cancel", f"up:{token}:no")]])
