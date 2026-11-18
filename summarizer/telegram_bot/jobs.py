"""Queue and run summarization jobs for the Telegram bot.

Jobs run one at a time on a worker thread through ``summarizer.core.main``,
like every other interface. One worker is deliberate: the local-file handlers
use fixed temp file names, so concurrent runs would overwrite each other.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from ..api_utils import format_output, get_file_extension
from ..exceptions import SummarizerError
from ..progress import clear_progress_callback, set_progress_callback
from ..transcript_cache import cache_info, clear_cache, get_cached_transcript
from .api import TelegramAPI, TelegramError
from .formatting import build_footer, prepare_markdown
from .options import BotOptions, ensure_private_dir
from .runtime import build_job_config, load_file_config
from .sender import MessageSender
from .sources import Source, short_url
from .store import ChatSettingsStore
from .ui import format_duration, result_keyboard, short_model

logger = logging.getLogger(__name__)

MAX_QUEUED_PER_USER = 5
# The transcript cache lives in process memory; a long-running bot drops it
# past this size (persisted transcripts stay on disk).
TRANSCRIPT_CACHE_MAX_CHARS = 50_000_000

_NOISE = (
    "Starting summarization",
    "API configuration validated",
    "Template loaded",
    "Summarization completed",
    "Finalizing summary output",
)
_ICONS = {"SUCCESS": "✓", "ERROR": "✗", "WARNING": "⚠", "PROCESSING": "›", "INFO": "·"}


@dataclass
class Job:
    chat_id: int
    user_id: int
    source: Source
    reply_to: Optional[int] = None
    thread_id: Optional[int] = None
    overrides: Dict[str, Any] = field(default_factory=dict)  # e.g. a Restyle's prompt_type
    status_message_id: Optional[int] = None
    id: str = field(default_factory=lambda: secrets.token_hex(4))

    def describe(self) -> str:
        if self.source.kind == "url":
            return f"🎬 {short_url(self.source.url)}"
        icon = {"voice": "🎙", "audio": "🎵"}.get(self.source.media, "📝" if self.source.is_text else "🎬")
        return f"{icon} {self.source.label}"


@dataclass
class Result:
    """A delivered summary, kept so its buttons keep working for a while."""

    id: str
    job: Job
    summary: str
    config: Dict[str, Any]  # runtime config without the API key
    prompt_type: str
    created: float = field(default_factory=time.time)


class ResultStore:
    def __init__(self, limit: int = 300):
        self._limit = limit
        self._items: "OrderedDict[str, Result]" = OrderedDict()
        self._lock = threading.Lock()

    def add(self, result: Result) -> None:
        with self._lock:
            self._items[result.id] = result
            while len(self._items) > self._limit:
                self._items.popitem(last=False)

    def get(self, result_id: str) -> Optional[Result]:
        with self._lock:
            return self._items.get(result_id)


class JobQueue:
    def __init__(self, run_job: Callable[[Job], None], on_advance: Optional[Callable[[List[Job]], None]] = None):
        self._run_job = run_job
        self._on_advance = on_advance
        self._pending: Deque[Job] = deque()
        self._running: Optional[Job] = None
        self._cond = threading.Condition()
        self._stopped = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="summarize-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._cond:
            self._stopped = True
            self._cond.notify_all()

    def ahead(self) -> int:
        """Jobs a newly submitted job would wait for."""
        with self._cond:
            return len(self._pending) + (1 if self._running else 0)

    def submit(self, job: Job) -> None:
        with self._cond:
            self._pending.append(job)
            self._cond.notify()

    def count_for_user(self, user_id: int) -> int:
        with self._cond:
            jobs = list(self._pending) + ([self._running] if self._running else [])
            return sum(1 for job in jobs if job.user_id == user_id)

    def cancel(self, chat_id: int, user_id: int) -> List[Job]:
        with self._cond:
            cancelled = [job for job in self._pending if job.chat_id == chat_id and job.user_id == user_id]
            self._pending = deque(job for job in self._pending if job not in cancelled)
            return cancelled

    def snapshot(self):
        with self._cond:
            return self._running, list(self._pending)

    def run_pending(self) -> None:
        """Run everything queued on the calling thread (tests, one-shot use)."""
        while True:
            with self._cond:
                if not self._pending:
                    return
                job = self._pending.popleft()
                self._running = job
            self._execute(job)

    def _loop(self) -> None:
        while True:
            with self._cond:
                while not self._pending and not self._stopped:
                    self._cond.wait()
                if self._stopped:
                    return
                job = self._pending.popleft()
                self._running = job
                waiting = list(self._pending)
            if self._on_advance and waiting:
                self._on_advance(waiting)
            self._execute(job)

    def _execute(self, job: Job) -> None:
        try:
            self._run_job(job)
        except Exception:  # the runner reports errors; never kill the worker
            logger.exception("Job %s crashed", job.id)
        finally:
            with self._cond:
                self._running = None


class StatusReporter:
    """Keeps a job's status message current from a small background thread.

    The pipeline's progress callback only records lines, so it never waits
    on Telegram; edits are throttled to stay well inside rate limits.
    """

    def __init__(self, sender: MessageSender, job: Job, interval: float = 4.0):
        self.sender = sender
        self.job = job
        self.interval = interval
        self.title: List[str] = [job.describe()]
        self._lines: Deque[str] = deque(maxlen=3)
        self._lock = threading.Lock()
        self._dirty = True
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started = time.monotonic()

    def set_title(self, lines: List[str]) -> None:
        with self._lock:
            self.title = list(lines)
            self._dirty = True

    def progress(self, message: str, status: str = "INFO") -> None:
        text = " ".join(str(message).split())
        if not text or text.startswith(_NOISE):
            return
        with self._lock:
            self._lines.append(f"{_ICONS.get(status, '·')} {text[:200]}")
            self._dirty = True

    def render(self) -> str:
        with self._lock:
            self._dirty = False
            head = f"⏳ Summarizing… {format_duration(time.monotonic() - self._started)}"
            parts = [head, *self.title]
            if self._lines:
                parts += ["", *self._lines]
            return "\n".join(parts)

    def start(self) -> None:
        self._started = time.monotonic()
        self.flush()
        self._thread = threading.Thread(target=self._loop, name=f"status-{self.job.id}", daemon=True)
        self._thread.start()

    def flush(self) -> None:
        if self.job.status_message_id:
            self.sender.edit_plain(self.job.chat_id, self.job.status_message_id, self.render())

    def _loop(self) -> None:
        last_edit = last_typing = time.monotonic()
        while not self._stop.wait(1.0):
            now = time.monotonic()
            if now - last_typing >= 5:
                self.sender.typing(self.job.chat_id, self.job.thread_id)
                last_typing = now
            if (self._dirty and now - last_edit >= self.interval) or now - last_edit >= 15:
                self.flush()
                last_edit = now

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)


def summary_file(result: Result) -> tuple:
    """(file name, bytes) of a summary in the CLI's saved-markdown format."""
    data = format_output(
        result.summary,
        result.job.source.label,
        "markdown",
        {"prompt_type": result.prompt_type, "model": result.config.get("model", "")},
    )
    return f"{_slug(result.job.source)}_{datetime.now():%Y%m%d_%H%M%S}.md", data.encode("utf-8")


def _slug(source: Source) -> str:
    if source.kind == "url":
        name = source.url.split("?")[0].rstrip("/").split("/")[-1]
    elif source.kind == "file":
        name = Path(source.label).stem
    else:
        name = "text"
    return re.sub(r"[^\w.-]+", "_", name).strip("._")[:60] or "summary"


def error_text(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if len(message) > 900:
        message = message[:900] + "…"
    return message


class JobRunner:
    def __init__(
        self,
        options: BotOptions,
        api: TelegramAPI,
        sender: MessageSender,
        store: ChatSettingsStore,
        results: ResultStore,
        core_main: Optional[Callable[[Dict[str, Any]], str]] = None,
    ):
        self.options = options
        self.api = api
        self.sender = sender
        self.store = store
        self.results = results
        if core_main is None:
            from ..core import main as core_main
        self.core_main = core_main

    def run(self, job: Job) -> None:
        started = time.monotonic()
        reporter = StatusReporter(self.sender, job)
        reporter.start()
        downloaded: Optional[str] = None
        try:
            chat = self.store.get(job.chat_id)
            overrides = dict(job.overrides)
            if not job.source.has_video:
                overrides["visual"] = False  # audio and text have no frames to look at
            if job.source.kind == "url":
                location = job.source.url
            else:
                location = str(self.options.work_dir / job.source.local_name())
            config, merged = build_job_config(
                load_file_config(self.options.config_path),
                chat,
                location,
                job.source.type_of_source,
                overrides,
            )
            reporter.set_title(
                [job.describe(), f"{config.get('prompt_type')} · {short_model(config.get('model'))}"
                 + (" · visual" if config.get("visual") else "")]
            )
            if job.source.kind != "url":
                downloaded = self._materialize(job, config, reporter)

            set_progress_callback(reporter.progress)
            try:
                summary = self.core_main(config)
            finally:
                clear_progress_callback()
            elapsed = time.monotonic() - started
            reporter.stop()
            self._deliver(job, summary, config, merged, elapsed)
            self.sender.delete(job.chat_id, job.status_message_id)
            logger.info("Job %s done in %s: %s", job.id, format_duration(elapsed), job.source.label)
        except Exception as exc:
            reporter.stop()
            if not isinstance(exc, (SummarizerError, TelegramError)):
                logger.exception("Job %s failed", job.id)
            else:
                logger.info("Job %s failed: %s", job.id, exc)
            text = (
                f"❌ Failed after {format_duration(time.monotonic() - started)}\n"
                f"{job.describe()}\n\n{error_text(exc)}"
            )
            try:
                if job.status_message_id:
                    self.sender.edit_plain(job.chat_id, job.status_message_id, text)
                else:
                    self.sender.send_plain(job.chat_id, text, reply_to=job.reply_to, thread_id=job.thread_id)
            except TelegramError:
                logger.warning("Could not report the failure of job %s", job.id)
        finally:
            reporter.stop()
            if downloaded and os.path.exists(downloaded):
                try:
                    os.remove(downloaded)
                except OSError:
                    pass
            if cache_info()["total_chars"] > TRANSCRIPT_CACHE_MAX_CHARS:
                clear_cache()

    def _materialize(self, job: Job, config: Dict[str, Any], reporter: StatusReporter) -> Optional[str]:
        """Put a Telegram file or pasted text where the pipeline expects it.

        Returns the path to delete afterwards. A cached transcript skips the
        download entirely (e.g. Restyle, or the same file sent again).
        """
        path = config["source_url_or_path"]
        ensure_private_dir(self.options.work_dir)
        source = job.source
        if source.kind == "text":
            Path(path).write_text(source.text, encoding="utf-8")
            return path
        if config.get("cache_transcript", True) and not config.get("visual"):
            if get_cached_transcript(config)[0] is not None:
                return None
        if source.file_size and source.file_size > self.options.max_file_bytes:
            raise SummarizerError(too_big_message(source.file_size, self.options))
        reporter.progress("Downloading the file from Telegram", "PROCESSING")
        reporter.flush()
        try:
            self.api.download_file(source.file_id, path, max_bytes=self.options.max_file_bytes)
        except TelegramError as exc:
            if os.path.exists(path):
                os.remove(path)
            if "too big" in exc.description.lower() or "larger than" in exc.description.lower():
                raise SummarizerError(too_big_message(source.file_size, self.options)) from None
            raise SummarizerError(f"Could not download the file from Telegram: {exc.description}") from None
        return path

    def _deliver(self, job: Job, summary: str, config: Dict[str, Any], merged: Dict[str, Any], elapsed: float):
        result = Result(
            id=secrets.token_hex(4),
            job=job,
            summary=summary,
            config={key: value for key, value in config.items() if key != "api_key"},
            prompt_type=config.get("prompt_type", ""),
        )
        self.results.add(result)
        footer = build_footer([result.prompt_type, short_model(config.get("model")), format_duration(elapsed)])
        self.sender.send_summary(
            job.chat_id,
            prepare_markdown(summary),
            footer,
            reply_to=job.reply_to,
            thread_id=job.thread_id,
            reply_markup=result_keyboard(result.id),
        )
        if self.store.get(job.chat_id).get("attach_markdown"):
            name, data = summary_file(result)
            self.sender.send_document(job.chat_id, name, data, reply_to=job.reply_to, thread_id=job.thread_id)
        if merged.get("keep_history"):
            self._save_to_disk(result, merged.get("output_dir") or "summaries")

    @staticmethod
    def _save_to_disk(result: Result, output_dir: str) -> None:
        """Same file layout as the CLI and the Streamlit history."""
        try:
            os.makedirs(output_dir, exist_ok=True)
            name, data = summary_file(result)
            stem = Path(name).stem
            Path(output_dir, f"{stem}{get_file_extension('markdown')}").write_bytes(data)
        except OSError as exc:
            logger.warning("Could not save summary to %s: %s", output_dir, exc)


def too_big_message(size: int, options: BotOptions) -> str:
    size_mb = f"{size / 1024 / 1024:.0f} MB" if size else "This file"
    return (
        f"{size_mb} is over the {options.max_file_mb:g} MB download limit. "
        "Telegram only lets bots download files up to 20 MB: send a link to the video "
        "instead (YouTube, Drive, Dropbox…), or run a local Bot API server "
        "(TELEGRAM_API_URL) to lift the limit."
    )
