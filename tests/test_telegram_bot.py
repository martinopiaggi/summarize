"""Tests for the Telegram bot interface (no network: a fake Bot API records calls)."""

import os
import stat
from pathlib import Path

import pytest
import yaml

from summarizer import transcript_cache
from summarizer.exceptions import ConfigurationError
from summarizer.telegram_bot import config_admin
from summarizer.telegram_bot.api import TelegramError
from summarizer.telegram_bot.bot import SummarizeBot
from summarizer.telegram_bot.formatting import (
    build_footer,
    prepare_markdown,
    split_markdown,
    split_plain,
    utf16_len,
)
from summarizer.telegram_bot.options import BotOptions, default_work_dir, ensure_private_dir, parse_id_list
from summarizer.telegram_bot.sources import (
    UnsupportedMessage,
    extract_urls,
    sources_from_message,
    url_source_type,
)
from summarizer.telegram_bot.store import ChatSettingsStore

OWNER, FRIEND, STRANGER = 111, 222, 999

CONFIG_YAML = """# my config
default_provider: groq

providers:
  groq:
    base_url: https://api.groq.com/openai/v1
    model: openai/gpt-oss-120b
  gemini:
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    model: gemini-3.5-flash-lite

defaults:
  prompt-type: Questions and answers  # house style
  chunk-size: 10000
  parallel-calls: 4
"""


# ── fakes ────────────────────────────────────────────────────────────────────


class FakeAPI:
    token = "123:SECRET"
    api_url = "https://api.telegram.org"
    reads_all = False  # True: privacy mode is off (@BotFather → Group Privacy)

    def __init__(self):
        self.calls = []
        self.failures = {}  # method -> TelegramError raised once per call while present
        self.files = {}  # file_id -> bytes
        self.next_id = 1000

    def call(self, method, params=None, files=None, timeout=None, retries=2):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        self.calls.append((method, params, files))
        if method in self.failures:
            raise self.failures[method]
        if method == "getMe":
            return {"id": 42, "username": "SumBot", "can_read_all_group_messages": self.reads_all}
        if method.startswith("send"):
            self.next_id += 1
            return {"message_id": self.next_id, "chat": {"id": params.get("chat_id")}}
        return True

    def download_file(self, file_id, destination, max_bytes=None):
        self.calls.append(("download", {"file_id": file_id, "path": destination}, None))
        Path(destination).write_bytes(self.files.get(file_id, b"media"))
        return destination

    def sent(self, method):
        return [params for name, params, _ in self.calls if name == method]


class FakeCore:
    def __init__(self, summary="# Title\n\nIt costs $5.\n\n- point one"):
        self.summary = summary
        self.configs = []
        self.seen_files = []

    def __call__(self, config):
        self.configs.append(dict(config))
        path = config["source_url_or_path"]
        if config["type_of_source"] in ("Local File", "TXT"):
            self.seen_files.append(Path(path).read_bytes())
        transcript_cache.put_cached_transcript(config, "00:00:00 hello transcript")
        return self.summary


@pytest.fixture(autouse=True)
def _clear_transcript_cache():
    transcript_cache.clear_cache()
    yield
    transcript_cache.clear_cache()


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "summarizer.yaml"
    path.write_text(CONFIG_YAML, encoding="utf-8")
    return path


def make_bot(tmp_path, config_path, allowed=(OWNER, FRIEND), core=None, **extra):
    options = BotOptions(
        token=FakeAPI.token,
        config_path=config_path,
        state_file=tmp_path / "state" / "chats.json",
        allowed_users=tuple(allowed),
        work_dir=tmp_path / "work",
        **extra,
    )
    api = FakeAPI()
    bot = SummarizeBot(options, api=api, core_main=core or FakeCore())
    bot.setup()
    return bot, api


def message(text=None, user=OWNER, chat=None, chat_type="private", message_id=1, **fields):
    chat_id = chat if chat is not None else user
    msg = {
        "message_id": message_id,
        "from": {"id": user, "is_bot": False, "username": f"user{user}"},
        "chat": {"id": chat_id, "type": chat_type},
        **fields,
    }
    if text is not None:
        msg["text"] = text
    return msg


def callback(data, chat=OWNER, user=OWNER, message_id=500):
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": user},
            "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat, "type": "private"}},
        }
    }


# ── formatting ───────────────────────────────────────────────────────────────


def test_prepare_markdown_escapes_accidental_telegram_syntax_outside_code():
    md = prepare_markdown(
        "It costs $5, takes ~10 min, a==b, x || y, <think>x</think>, keeps <br>.\n"
        "Code `a == b $5 <x>` stays."
    )
    assert "\\$5" in md and "\\~10" in md and "a=\\=b" in md and "|\\|" in md
    assert "\\<think>" in md and "<br>" in md
    assert "`a == b $5 <x>`" in md


def test_prepare_markdown_leaves_code_blocks_tables_and_math_alone():
    md = prepare_markdown("```python\nx = a == b  # $5\n```\n| a || b |\n|---|---|\n\n$E = mc^2$")
    assert "x = a == b  # $5" in md
    assert "| a || b |" in md
    assert "$E = mc^2$" in md


def test_prepare_markdown_links_timestamps_and_closes_open_fences():
    md = prepare_markdown("00:01:23 - https://youtu.be/abc&t=83\n\ntext\n```\nunclosed")
    assert md.startswith("**[⏱ 00:01:23](https://youtu.be/abc?t=83)**")
    assert md.endswith("```")
    assert prepare_markdown("00:00:00\n\nonly chunk") == "only chunk"
    assert prepare_markdown("00:00:00\n\na\n\n00:10:00\n\nb").count("**⏱") == 2


def test_split_markdown_respects_limits_and_keeps_code_fenced():
    sections = "\n\n".join(f"## S{i}\n" + "\n".join(f"- item {j} " + "w " * 40 for j in range(20)) for i in range(60))
    parts = split_markdown(sections, max_bytes=20000, max_blocks=100)
    assert len(parts) > 1
    assert all(len(p.encode()) <= 20000 for p in parts)
    assert "\n\n".join(parts).count("- item") == 60 * 20

    code_parts = split_markdown("```py\n" + "print(1)\n" * 4000 + "```", max_bytes=10000)
    assert len(code_parts) > 1
    assert all(p.startswith("```py\n") and p.endswith("\n```") for p in code_parts)


def test_split_markdown_repeats_table_header():
    table = "| h1 | h2 |\n|---|---|\n" + "\n".join(f"| r{i} | v |" for i in range(300))
    parts = split_markdown(table, max_bytes=100000, max_blocks=100)
    assert len(parts) > 1
    assert all(p.startswith("| h1 | h2 |\n|---|---|") for p in parts)


def test_split_plain_counts_utf16_units():
    chunks = split_plain(("😀" * 3000 + " ") * 3)
    assert all(utf16_len(chunk) <= 4096 for chunk in chunks)
    assert sum(chunk.count("😀") for chunk in chunks) == 9000


def test_footer_is_escaped_html_block():
    footer = build_footer(["Q <&> A", "", "42s"])
    assert footer.rich == "<footer>Q &lt;&amp;&gt; A · 42s</footer>"
    assert footer.plain == "— Q <&> A · 42s"


# ── sources ──────────────────────────────────────────────────────────────────


def test_extract_urls_from_utf16_entities_and_hidden_links():
    text = "😀 watch youtu.be/abc123 and this"
    entities = [
        {"type": "url", "offset": 9, "length": 15},
        {"type": "text_link", "offset": 29, "length": 4, "url": "https://x.com/a/status/1"},
    ]
    assert extract_urls(text, entities) == ["https://youtu.be/abc123", "https://x.com/a/status/1"]
    assert extract_urls("see https://example.com/v.mp4).") == ["https://example.com/v.mp4"]


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=abc", "YouTube Video"),
        ("https://drive.google.com/file/d/x/view", "Google Drive Video Link"),
        ("https://www.dropbox.com/s/x/v.mp4", "Dropbox Video Link"),
        ("https://www.tiktok.com/@a/video/1", "Video URL"),
    ],
)
def test_url_source_type(url, expected):
    assert url_source_type(url) == expected


def test_sources_cover_media_documents_and_text():
    voice = sources_from_message({"voice": {"file_id": "v", "file_unique_id": "U1", "duration": 65}})[0]
    assert (voice.type_of_source, voice.extension, voice.label) == ("Local File", ".ogg", "voice message (1:05)")
    assert not voice.has_video

    srt = sources_from_message({"document": {"file_id": "d", "file_unique_id": "U2", "file_name": "talk.srt"}})[0]
    assert srt.type_of_source == "TXT"

    video = sources_from_message({"caption": "https://youtu.be/x", "video": {"file_id": "f", "file_unique_id": "U3"}})
    assert video[0].kind == "file" and video[0].has_video  # media wins over caption links

    assert sources_from_message({"text": "hi there"}) == []
    assert sources_from_message({"text": "hi there"}, explicit=True)[0].kind == "text"
    assert sources_from_message({"text": "long " * 300})[0].kind == "text"

    with pytest.raises(UnsupportedMessage):
        sources_from_message({"document": {"file_id": "d", "file_name": "slides.pdf", "mime_type": "application/pdf"}})


# ── options and store ────────────────────────────────────────────────────────


def test_options_from_env_and_access_rules(tmp_path):
    env = {
        "TELEGRAM_BOT_TOKEN": "t",
        "TELEGRAM_ALLOWED_USERS": "111, 222",
        "TELEGRAM_ALLOWED_CHATS": "-100500",
    }
    options = BotOptions.from_args(None, env=env, output_dir=str(tmp_path))
    assert options.admins == (111,)  # first allowed user owns the bot
    assert options.is_allowed(222, 222) and options.is_allowed(333, -100500)
    assert not options.is_allowed(333, 333) and not options.is_admin(222)
    assert options.max_file_mb == 20
    assert options.state_file == (tmp_path / ".telegram" / "chat_settings.json").resolve()

    local = BotOptions.from_args(None, env={**env, "TELEGRAM_API_URL": "http://localhost:8081"})
    assert local.max_file_mb == 2000

    with pytest.raises(ConfigurationError, match="Missing bot token"):
        BotOptions.from_args(None, env={})
    with pytest.raises(ConfigurationError, match="not a numeric"):
        parse_id_list("@someone", "TELEGRAM_ALLOWED_USERS")


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions and owners")
def test_work_dir_is_private_and_never_someone_elses(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir(mode=0o755)
    assert ensure_private_dir(work) == work and stat.S_IMODE(work.stat().st_mode) == 0o700
    assert default_work_dir().name == f"summarize-telegram-{os.getuid()}"  # one per OS user

    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ConfigurationError, match="is a link"):
        ensure_private_dir(tmp_path / "link")

    monkeypatch.setattr(os, "getuid", lambda: work.stat().st_uid + 1)
    with pytest.raises(ConfigurationError, match="another user"):
        ensure_private_dir(work)


def test_chat_settings_store_persists_only_overrides(tmp_path):
    path = tmp_path / "chats.json"
    store = ChatSettingsStore(path)
    store.update(5, prompt_type="Research", visual=True)
    store.update(5, visual=None)
    assert ChatSettingsStore(path).get(5) == {"prompt_type": "Research"}
    with pytest.raises(KeyError):
        store.update(5, api_key="nope")


# ── config admin ─────────────────────────────────────────────────────────────


def test_parse_value_validates_types_and_choices(config_path):
    file_config = yaml.safe_load(CONFIG_YAML)
    parse = lambda key, raw: config_admin.parse_value(config_admin.resolve_setting(key), raw, file_config)
    assert parse("chunk_size", "5000") == 5000
    assert parse("style", "distill wisdom") == "Distill Wisdom"
    assert parse("style", "paul graham") == "Essay Writing in Paul Graham Style"
    with pytest.raises(ConfigurationError, match="matches several"):
        parse("style", "distill")
    assert parse("provider", "GEM") == "gemini"
    assert parse("use-proxy", "on") is True
    assert parse("sidecar", "TranscriptFetch") == "transcriptfetch"
    with pytest.raises(ConfigurationError):
        parse("parallel-calls", "500")
    with pytest.raises(ConfigurationError):
        parse("provider", "openai")
    with pytest.raises(ConfigurationError, match="Unknown setting"):
        config_admin.resolve_setting("base_url")


def test_config_upload_validation_and_redaction():
    redacted = config_admin.redact_config_text("providers:\n  a:\n    api_key: sk-123  # mine\n    api-key:\n")
    assert "sk-123" not in redacted and config_admin.REDACTED in redacted
    with pytest.raises(ConfigurationError, match="REDACTED"):
        config_admin.validate_config_text(redacted)
    with pytest.raises(ConfigurationError, match="Invalid YAML"):
        config_admin.validate_config_text("providers: [")
    with pytest.raises(ConfigurationError, match="providers"):
        config_admin.validate_config_text("defaults: {}\n")
    with pytest.raises(ConfigurationError, match="not in providers"):
        config_admin.validate_config_text(CONFIG_YAML.replace("default_provider: groq", "default_provider: x"))
    assert config_admin.validate_config_text(CONFIG_YAML)["default_provider"] == "groq"


@pytest.mark.parametrize(
    "snippet",
    [
        "    api_key: sk-live-12345678  # mine",
        "  b: {base_url: https://b/v1, model: m, api_key: sk-live-12345678}",
        '    "api_key": "sk-live-12345678"',
        "    API-KEY: 'sk-live-12345678'",
        "  more:\n    - api_key: sk-live-12345678",
        "    # api_key: sk-live-12345678",
        "    api_key: |\n      sk-live-12345678",
        "    api_key: sk-live",
    ],
)
def test_redaction_covers_every_way_yaml_can_write_a_key(snippet):
    redacted = config_admin.redact_config_text(f"providers:\n  a:\n    base_url: https://a/v1\n{snippet}\n")
    assert "sk-live" not in redacted and config_admin.REDACTED in redacted
    assert "base_url: https://a/v1" in redacted


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_config_backup_is_as_private_as_the_config(tmp_path, config_path):
    config_path.chmod(0o600)
    old_backup = tmp_path / "summarizer.yaml.bak"
    old_backup.write_text("left readable by everyone")
    old_backup.chmod(0o644)
    backup = config_admin.replace_config_file(config_path, CONFIG_YAML)
    assert backup == old_backup and backup.read_text() == CONFIG_YAML
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600 == stat.S_IMODE(config_path.stat().st_mode)


# ── bot flows ────────────────────────────────────────────────────────────────


def test_link_is_summarized_as_rich_markdown_reply(tmp_path, config_path):
    core = FakeCore()
    bot, api = make_bot(tmp_path, config_path, core=core)
    bot.handle_update({"update_id": 1, "message": message("look https://youtu.be/dQw4w9WgXcQ", message_id=7)})

    status = api.sent("sendMessage")[-1]
    assert status["text"].startswith("⏳") and status["reply_parameters"]["message_id"] == 7
    bot.queue.run_pending()

    config = core.configs[0]
    assert config["source_url_or_path"] == "https://youtu.be/dQw4w9WgXcQ"
    assert config["type_of_source"] == "YouTube Video" and config["use_youtube_captions"] is True
    assert config["prompt_type"] == "Questions and answers" and config["parallel_api_calls"] == 4

    rich = api.sent("sendRichMessage")[-1]
    markdown = rich["rich_message"]["markdown"]
    assert markdown.startswith("# Title") and "\\$5" in markdown
    assert markdown.rstrip().endswith("</footer>") and "Questions and answers" in markdown
    assert rich["reply_parameters"]["message_id"] == 7
    buttons = [b["callback_data"] for b in rich["reply_markup"]["inline_keyboard"][0]]
    assert [b.split(":")[-1] for b in buttons] == ["md", "tx", "rs"]
    assert api.sent("deleteMessage")  # the status message is removed


def test_voice_message_is_downloaded_transcribed_and_cleaned_up(tmp_path, config_path):
    core = FakeCore()
    bot, api = make_bot(tmp_path, config_path, core=core)
    bot.store.update(OWNER, visual=True)
    api.files["v1"] = b"OggS..."
    voice = {"file_id": "v1", "file_unique_id": "UNIQ", "duration": 3, "file_size": 7}
    bot.handle_update({"update_id": 1, "message": message(voice=voice)})
    bot.queue.run_pending()

    config = core.configs[0]
    assert config["type_of_source"] == "Local File"
    assert config["visual"] is False  # audio has no frames
    assert Path(config["source_url_or_path"]).name == "tg_UNIQ.ogg"
    assert core.seen_files == [b"OggS..."]
    assert not Path(config["source_url_or_path"]).exists()


def test_restyle_reuses_cached_transcript_without_downloading(tmp_path, config_path):
    core = FakeCore()
    bot, api = make_bot(tmp_path, config_path, core=core)
    video = {"file_id": "f1", "file_unique_id": "VID", "file_size": 10}
    bot.handle_update({"update_id": 1, "message": message(video=video, message_id=9)})
    bot.queue.run_pending()
    result_button = api.sent("sendRichMessage")[-1]["reply_markup"]["inline_keyboard"][0][2]["callback_data"]
    result_id = result_button.split(":")[1]

    bot.handle_update({"update_id": 2, **callback(f"res:{result_id}:rs")})
    picker = api.sent("editMessageReplyMarkup")[-1]["reply_markup"]["inline_keyboard"]
    research = next(b for row in picker for b in row if b["text"].endswith("Research"))
    bot.handle_update({"update_id": 3, **callback(research["callback_data"])})
    bot.queue.run_pending()

    assert [c["prompt_type"] for c in core.configs] == ["Questions and answers", "Research"]
    assert len([c for c in api.calls if c[0] == "download"]) == 1
    assert api.sent("sendRichMessage")[-1]["reply_parameters"]["message_id"] == 9


def test_transcript_and_markdown_buttons_send_documents(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message("https://youtu.be/dQw4w9WgXcQ")})
    bot.queue.run_pending()
    result_id = api.sent("sendRichMessage")[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"].split(":")[1]

    bot.handle_update({"update_id": 2, **callback(f"res:{result_id}:md")})
    bot.handle_update({"update_id": 3, **callback(f"res:{result_id}:tx")})
    documents = [files["document"] for name, _, files in api.calls if name == "sendDocument"]
    assert documents[0][0].endswith(".md") and documents[0][1].startswith(b"# Summary for: https://youtu.be/")
    assert documents[1][0].endswith("_transcript.txt") and b"hello transcript" in documents[1][1]

    # A result only answers in the chat it was delivered to.
    bot.handle_update({"update_id": 4, **callback(f"res:{result_id}:md", chat=FRIEND, user=FRIEND)})
    assert len(api.sent("sendDocument")) == 2


def test_rich_message_rejection_falls_back_to_plain_text(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    api.failures["sendRichMessage"] = TelegramError("Bad Request: can't parse rich message", 400)
    bot.handle_update({"update_id": 1, "message": message("https://youtu.be/dQw4w9WgXcQ")})
    bot.queue.run_pending()
    plain = api.sent("sendMessage")[-1]
    assert plain["text"].startswith("# Title") and "— Questions and answers" in plain["text"]
    assert "reply_markup" in plain and bot.sender.rich_supported

    api.failures["sendRichMessage"] = TelegramError("Not Found: method not found", 404)
    bot.handle_update({"update_id": 2, "message": message("https://youtu.be/dQw4w9WgXcQ")})
    bot.queue.run_pending()
    assert not bot.sender.rich_supported


def test_failures_are_reported_in_the_status_message(tmp_path, config_path):
    def broken(config):
        raise ConfigurationError("No API key found for base_url")

    bot, api = make_bot(tmp_path, config_path, core=broken)
    bot.handle_update({"update_id": 1, "message": message("https://youtu.be/dQw4w9WgXcQ")})
    bot.queue.run_pending()
    edit = api.sent("editMessageText")[-1]
    assert edit["text"].startswith("❌ Failed") and "No API key found" in edit["text"]


def test_unauthorized_users_get_their_id_once_and_nothing_runs(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    for update_id in (1, 2):
        bot.handle_update({"update_id": update_id, "message": message("https://youtu.be/x", user=STRANGER)})
    replies = api.sent("sendMessage")
    assert len(replies) == 1 and str(STRANGER) in replies[0]["text"]
    assert bot.queue.snapshot() == (None, [])


def test_setup_mode_explains_how_to_allow_yourself(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path, allowed=())
    bot.handle_update({"update_id": 1, "message": message("/start", user=STRANGER)})
    assert f"TELEGRAM_ALLOWED_USERS={STRANGER}" in api.sent("sendMessage")[-1]["text"]


def test_groups_need_a_command_or_mention(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    group = dict(chat=-100, chat_type="group")
    bot.handle_update({"update_id": 1, "message": message("https://youtu.be/x", **group)})
    assert bot.queue.ahead() == 0

    target = message("https://youtu.be/dQw4w9WgXcQ", user=FRIEND, message_id=30, **group)
    bot.handle_update({"update_id": 2, "message": message("/summarize@SumBot", reply_to_message=target, **group)})
    bot.handle_update({"update_id": 3, "message": message("@SumBot https://youtu.be/abc", **group)})
    bot.handle_update({"update_id": 4, "message": message("/summarize@OtherBot https://youtu.be/x", **group)})
    _, pending = bot.queue.snapshot()
    assert [job.source.url for job in pending] == ["https://youtu.be/dQw4w9WgXcQ", "https://youtu.be/abc"]
    assert pending[0].reply_to == 30


def test_mention_as_a_reply_summarizes_the_replied_message(tmp_path, config_path):
    """Telegram delivers plain mentions with privacy mode off: "@bot" alone is then enough."""
    bot, api = make_bot(tmp_path, config_path)
    group = dict(chat=-100, chat_type="supergroup")
    video = message(user=FRIEND, message_id=30, video={"file_id": "f", "file_unique_id": "VID", "file_size": 10}, **group)
    link = message("look https://youtu.be/dQw4w9WgXcQ", user=FRIEND, message_id=31, **group)
    bot.handle_update({"update_id": 1, "message": message("@SumBot", reply_to_message=video, **group)})
    bot.handle_update({"update_id": 2, "message": message("@sumbot this one please", reply_to_message=link, **group)})
    # A link of its own wins over the message it replies to.
    bot.handle_update({"update_id": 3, "message": message("@SumBot https://youtu.be/own", reply_to_message=video, **group)})
    _, pending = bot.queue.snapshot()
    assert [(job.source.file_unique_id or job.source.url, job.reply_to) for job in pending] == [
        ("VID", 30),
        ("https://youtu.be/dQw4w9WgXcQ", 31),
        ("https://youtu.be/own", 1),
    ]

    # Thanking the bot under its own summary does not summarize the summary.
    mine = {"message_id": 40, "from": {"id": 42, "is_bot": True}, "text": "# An earlier summary"}
    bot.handle_update({"update_id": 4, "message": message("@SumBot thanks", reply_to_message=mine, **group)})
    assert len(bot.queue.snapshot()[1]) == 3
    assert "Send me a video link" in api.sent("sendMessage")[-1]["text"]


GROUP = dict(chat=-100777, chat_type="supergroup")


def group_texts(api):
    return [m["text"] for m in api.sent("sendMessage") if m["chat_id"] == GROUP["chat"]]


def test_joining_a_group_posts_how_to_use_it(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message(new_chat_members=[{"id": 42, "is_bot": True}], **GROUP)})
    greeting = group_texts(api)[-1]
    # The short command first; the @name form only as the fallback privacy mode can need.
    assert "with /s (short for /summarize)" in greeting and "add my name: /s@SumBot" in greeting
    assert "<code>-100777</code>" in greeting
    assert "TELEGRAM_ALLOWED_CHATS" in greeting and "commas" in greeting

    bot.handle_update({"update_id": 2, "message": message(new_chat_members=[{"id": 42}], user=STRANGER, chat=-100888, chat_type="group")})
    assert "private" in api.sent("sendMessage")[-1]["text"] and "-100888" in api.sent("sendMessage")[-1]["text"]


def test_with_privacy_mode_off_the_bot_offers_a_plain_mention(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    api.reads_all = True
    bot.setup()  # getMe says whether Telegram delivers every group message
    bot.handle_update({"update_id": 1, "message": message(new_chat_members=[{"id": 42, "is_bot": True}], **GROUP)})
    bot.handle_update({"update_id": 2, "message": message("/help", **GROUP)})
    greeting, help_text = group_texts(api)
    for text in (greeting, help_text):
        assert "with @SumBot (or /s)" in text and "/s@SumBot" not in text


def test_membership_updates_greet_once_and_ignore_channels(tmp_path, config_path, caplog):
    from summarizer.telegram_bot.bot import _describe_update

    bot, api = make_bot(tmp_path, config_path)
    join = {
        "chat": {"id": GROUP["chat"], "type": "supergroup", "title": "Team"},
        "from": {"id": OWNER},
        "old_chat_member": {"status": "left"},
        "new_chat_member": {"status": "member"},
    }
    bot.handle_update({"update_id": 1, "my_chat_member": join})
    # Telegram also sends the service message for the same join: no second greeting.
    bot.handle_update({"update_id": 2, "message": message(new_chat_members=[{"id": 42}], **GROUP)})
    assert len(group_texts(api)) == 1 and "/s@SumBot" in group_texts(api)[0]

    channel = {**join, "chat": {"id": -100999, "type": "channel"}}
    bot.handle_update({"update_id": 3, "my_chat_member": channel})
    assert not [m for m in api.sent("sendMessage") if m["chat_id"] == -100999]

    line = _describe_update({"update_id": 4, "message": message("/summarize@SumBot", reply_to_message={"message_id": 3}, **GROUP)})
    assert line == "message in supergroup -100777 from user 111 '/summarize@SumBot' replying to message 3"


def test_add_to_group_link_and_its_start_command(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message("/start")})
    button = api.sent("sendMessage")[-1]["reply_markup"]["inline_keyboard"][0][0]
    assert button["url"] == "https://t.me/SumBot?startgroup=summarize"

    # The link adds the bot (membership update), then sends /start in the group: greet once.
    join = {"chat": {"id": GROUP["chat"], "type": "supergroup"}, "from": {"id": OWNER},
            "old_chat_member": {"status": "left"}, "new_chat_member": {"status": "member"}}
    bot.handle_update({"update_id": 2, "my_chat_member": join})
    bot.handle_update({"update_id": 3, "message": message("/start@SumBot summarize", **GROUP)})
    assert len(group_texts(api)) == 1 and "/s@SumBot" in group_texts(api)[0]


def test_unauthorized_group_members_are_told_why_only_when_they_address_the_bot(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message("https://youtu.be/x", user=STRANGER, **GROUP)})
    assert group_texts(api) == []
    for update_id in (2, 3):
        bot.handle_update({"update_id": update_id, "message": message("/summarize@SumBot https://youtu.be/x", user=STRANGER, **GROUP)})
    replies = group_texts(api)
    assert len(replies) == 1 and str(STRANGER) in replies[0] and "-100777" in replies[0]
    assert bot.queue.ahead() == 0


def test_anonymous_admins_need_an_allowed_group(tmp_path, config_path):
    anonymous = {"from": {"id": 1087968824, "is_bot": True, "username": "GroupAnonymousBot"},
                 "sender_chat": {"id": GROUP["chat"], "type": "supergroup"}}
    bot, api = make_bot(tmp_path, config_path)
    msg = message("/summarize@SumBot https://youtu.be/x", **GROUP)
    msg.update(anonymous)
    bot.handle_update({"update_id": 1, "message": msg})
    assert "anonymously" in group_texts(api)[-1] and bot.queue.ahead() == 0

    bot, api = make_bot(tmp_path, config_path, allowed_chats=(GROUP["chat"],))
    bot.handle_update({"update_id": 2, "message": msg})
    assert bot.queue.ahead() == 1


def test_video_with_summarize_caption_in_a_group(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    video = {"file_id": "f", "file_unique_id": "CAP", "file_size": 10}
    bot.handle_update({"update_id": 1, "message": message(caption="/summarize", video=video, **GROUP)})
    _, pending = bot.queue.snapshot()
    assert [job.source.file_unique_id for job in pending] == ["CAP"]

    bot.handle_update({"update_id": 2, "message": message("/summarize@SumBot", **GROUP)})
    assert "<code>/s https://…</code>" in group_texts(api)[-1]  # nothing to summarize: says how


def test_chat_settings_buttons_change_only_this_chat(tmp_path, config_path):
    core = FakeCore()
    bot, api = make_bot(tmp_path, config_path, core=core)
    bot.handle_update({"update_id": 1, "message": message("/settings")})
    assert "Settings for this chat" in api.sent("sendMessage")[-1]["text"]

    bot.handle_update({"update_id": 2, **callback("set:open:prov")})
    picker = api.sent("editMessageText")[-1]["reply_markup"]["inline_keyboard"]
    gemini = next(b for row in picker for b in row if b["text"] == "gemini")
    bot.handle_update({"update_id": 3, **callback(gemini["callback_data"])})
    bot.handle_update({"update_id": 4, **callback("set:tog:captions")})
    bot.handle_update({"update_id": 5, "message": message("/style fact")})
    assert bot.store.get(OWNER) == {"provider": "gemini", "force_download": True, "prompt_type": "Fact Checker"}

    bot.handle_update({"update_id": 6, "message": message("https://youtu.be/dQw4w9WgXcQ")})
    bot.handle_update({"update_id": 7, "message": message("https://youtu.be/dQw4w9WgXcQ", user=FRIEND)})
    bot.queue.run_pending()
    mine, theirs = core.configs
    assert (mine["model"], mine["prompt_type"], mine["use_youtube_captions"]) == (
        "gemini-3.5-flash-lite", "Fact Checker", False,
    )
    assert (theirs["model"], theirs["prompt_type"]) == ("openai/gpt-oss-120b", "Questions and answers")
    assert config_path.read_text() == CONFIG_YAML  # chat settings never touch the YAML


def test_admin_set_edits_yaml_and_others_cannot(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message("/set chunk-size 50000")})
    bot.handle_update({"update_id": 2, "message": message("/set provider gemini")})
    assert "✅" in api.sent("sendMessage")[-1]["text"]
    data = yaml.safe_load(config_path.read_text())
    assert data["defaults"]["chunk-size"] == 50000 and data["default_provider"] == "gemini"
    assert "# house style" in config_path.read_text()

    bot.handle_update({"update_id": 3, "message": message("/set chunk-size 1", user=FRIEND)})
    assert "Only the bot admin" in api.sent("sendMessage")[-1]["text"]
    bot.handle_update({"update_id": 4, "message": message("/set chunk-size 10")})
    assert "at least 500" in api.sent("sendMessage")[-1]["text"]
    assert yaml.safe_load(config_path.read_text())["defaults"]["chunk-size"] == 50000


def test_admin_replaces_yaml_by_upload_after_confirmation(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    new_yaml = CONFIG_YAML.replace("default_provider: groq", "default_provider: gemini")
    api.files["doc"] = new_yaml.encode()
    upload = message(document={"file_id": "doc", "file_name": "summarizer.yaml", "file_size": len(new_yaml)})
    bot.handle_update({"update_id": 1, "message": upload})
    confirm = api.sent("sendMessage")[-1]
    assert "Replace summarizer.yaml" in confirm["text"]
    assert config_path.read_text() == CONFIG_YAML  # nothing changes before confirming

    ok = confirm["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    bot.handle_update({"update_id": 2, **callback(ok, user=FRIEND, chat=FRIEND)})  # not the uploader
    assert config_path.read_text() == CONFIG_YAML
    bot.handle_update({"update_id": 3, **callback(ok)})
    assert config_path.read_text() == new_yaml
    assert (tmp_path / "summarizer.yaml.bak").read_text() == CONFIG_YAML

    # A file non-admins send is not treated as a config.
    bot.handle_update({"update_id": 4, "message": message(user=FRIEND, document=upload["document"])})
    assert "can't summarize" in api.sent("sendMessage")[-1]["text"]


def test_config_download_hides_api_keys(tmp_path, config_path):
    config_path.write_text(CONFIG_YAML.replace("model: openai/gpt-oss-120b", "model: m\n    api_key: sk-live"))
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message("/config")})
    assert "summarizer.yaml" in api.sent("sendMessage")[-1]["text"]
    bot.handle_update({"update_id": 2, **callback("cfg:dl")})
    _, data = [files["document"] for name, _, files in api.calls if name == "sendDocument"][-1]
    assert b"sk-live" not in data and config_admin.REDACTED.encode() in data


def test_too_big_files_are_refused_before_queueing(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    video = {"file_id": "f", "file_unique_id": "BIG", "file_size": 80 * 1024 * 1024}
    bot.handle_update({"update_id": 1, "message": message(video=video)})
    assert "20 MB" in api.sent("sendMessage")[-1]["text"]
    assert bot.queue.ahead() == 0


def test_cancel_drops_only_your_queued_jobs(tmp_path, config_path):
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message("https://youtu.be/a https://youtu.be/b")})
    bot.handle_update({"update_id": 2, "message": message("https://youtu.be/c", user=FRIEND)})
    bot.handle_update({"update_id": 3, "message": message("/cancel")})
    _, pending = bot.queue.snapshot()
    assert [job.user_id for job in pending] == [FRIEND]
    assert "Cancelled 2" in api.sent("sendMessage")[-1]["text"]


def test_keep_history_saves_summary_like_the_cli(tmp_path, config_path):
    out = tmp_path / "out"
    config_path.write_text(CONFIG_YAML + f"  keep-history: true\n  output-dir: {out}\n")
    bot, api = make_bot(tmp_path, config_path)
    bot.handle_update({"update_id": 1, "message": message("https://youtu.be/dQw4w9WgXcQ")})
    bot.queue.run_pending()
    saved = list(out.glob("*.md"))
    assert len(saved) == 1 and saved[0].read_text().startswith("# Summary for: https://youtu.be/")


def test_bot_token_never_leaks_into_errors():
    from summarizer.telegram_bot.api import TelegramAPI

    api = TelegramAPI("123:SECRET", api_url="http://127.0.0.1:9")  # nothing listens there
    with pytest.raises(TelegramError) as info:
        api.call("getMe", retries=0, timeout=2)
    assert "SECRET" not in str(info.value) and "<token>" in str(info.value)


def test_cli_parses_telegram_subcommand(monkeypatch):
    import sys
    from summarizer.__main__ import parse_args

    monkeypatch.setattr(sys, "argv", ["summarizer", "telegram", "--allowed-users", "1,2", "--config", "x.yaml"])
    args = parse_args()
    assert (args.command, args.allowed_users, args.bot_config) == ("telegram", "1,2", "x.yaml")


def test_duplicate_env_keys_are_reported(tmp_path):
    from summarizer.telegram_bot import duplicate_env_keys

    env = tmp_path / ".env"
    env.write_text("TELEGRAM_ALLOWED_CHATS=-1\nexport TELEGRAM_ALLOWED_CHATS = -2\nTELEGRAM_BOT_TOKEN=x\n# TELEGRAM_BOT_TOKEN=old\n")
    assert duplicate_env_keys(str(env)) == ["TELEGRAM_ALLOWED_CHATS"]
    assert duplicate_env_keys(str(tmp_path / "missing")) == []


def test_exit_codes_tell_service_managers_whether_to_retry(monkeypatch, tmp_path):
    import summarizer.telegram_bot as telegram_bot

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert telegram_bot.run_from_args(None) == telegram_bot.EXIT_CONFIG_ERROR  # no token

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1:x")
    outcomes = {
        "bad token": ConfigurationError("Telegram rejected the bot token"),
        "offline": TelegramError("Network error during getMe"),
    }
    for name, error in outcomes.items():
        def run_forever(self, error=error):
            raise error
        monkeypatch.setattr(telegram_bot.SummarizeBot, "run_forever", run_forever)
        expected = telegram_bot.EXIT_CONFIG_ERROR if name == "bad token" else telegram_bot.EXIT_RETRY
        assert telegram_bot.run_from_args(None) == expected


def test_setup_turns_a_rejected_token_into_a_configuration_error(tmp_path, config_path):
    options = BotOptions(token="1:x", config_path=config_path, state_file=tmp_path / "s.json", work_dir=tmp_path / "w")
    api = FakeAPI()
    api.failures["getMe"] = TelegramError("Unauthorized", 401)
    with pytest.raises(ConfigurationError, match="rejected the bot token"):
        SummarizeBot(options, api=api, core_main=FakeCore()).setup()
