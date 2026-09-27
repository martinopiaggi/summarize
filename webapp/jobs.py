"""Session-owned workers; UI reruns replay progress without restarting work."""

import threading
import traceback


class JobStatus:
    """Collect progress without calling Streamlit from the worker thread."""

    def __init__(self, job):
        self._job = job

    def write(self, message):
        self._job.append_log(message)

    def update(self, **kwargs):
        pass


class SummarizeJob:
    def __init__(self, runner, context=None):
        self.context = dict(context or {})
        self.result = None
        self.error = None
        self.traceback_text = None
        self.done = False
        self._logs = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, args=(runner,), daemon=True)
        self._thread.start()

    def _run(self, runner):
        try:
            self.result = runner(JobStatus(self))
        except BaseException as exc:
            self.error = exc
            self.traceback_text = traceback.format_exc()
        finally:
            try:
                cleanup = self.context.get("cleanup")
                if cleanup:
                    cleanup()
            finally:
                self.done = True

    def append_log(self, message):
        with self._lock:
            self._logs.append(message)

    def logs_since(self, offset=0):
        """Each UI render has its own cursor, so reruns replay earlier logs."""
        with self._lock:
            return self._logs[offset:]

    def wait(self, timeout=None):
        self._thread.join(timeout)
        return self.done
