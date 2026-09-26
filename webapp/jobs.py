"""Background summarization jobs for the Streamlit UI.

Streamlit interrupts the running script whenever the user touches a
widget (for example the theme toggle), which used to abort an in-flight
summarization and lose all of its progress. The pipeline now runs on a
worker thread owned by the session, so reruns can re-attach to the
running job instead of starting over.
"""

import threading
import traceback


class JobStatus:
    """Status shim that records pipeline messages instead of drawing them.

    :func:`webapp.summarization.run_summarization` writes its progress
    lines to ``status_container.write(...)``. Inside a job there is no
    Streamlit element to write to, so the shim collects the lines and
    the UI drains them on every rerun.
    """

    def __init__(self, job: "SummarizeJob"):
        self._job = job

    def write(self, message: str) -> None:
        self._job.append_log(message)

    def update(self, **kwargs) -> None:  # noqa: D102 - parity with st.status
        pass


class SummarizeJob:
    """Run one summarization pipeline call off the Streamlit script thread.

    The job keeps running even when the script run that started it is
    interrupted; a later run re-attaches via ``st.session_state`` and
    drains :meth:`drain_logs` until :attr:`done` is set.
    """

    def __init__(self, runner, context=None):
        self.context = dict(context or {})
        self.result = None
        self.error = None
        self.traceback_text = None
        self.done = False
        self._logs = []
        self._cursor = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, args=(runner,), daemon=True)
        self._thread.start()

    def _run(self, runner) -> None:
        try:
            self.result = runner(JobStatus(self))
        except BaseException as exc:  # noqa: BLE001 - surfaced in the UI
            self.error = exc
            self.traceback_text = traceback.format_exc()
        finally:
            self.done = True

    def append_log(self, message: str) -> None:
        with self._lock:
            self._logs.append(message)

    def drain_logs(self):
        """Return the messages appended since the previous call."""
        with self._lock:
            lines = self._logs[self._cursor:]
            self._cursor = len(self._logs)
        return lines

    def wait(self, timeout=None) -> bool:
        """Block until the job finishes or ``timeout`` seconds elapse."""
        self._thread.join(timeout)
        return self.done
