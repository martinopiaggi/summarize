"""The summarization job must survive Streamlit reruns.

Streamlit aborts the running script on widget changes (theme toggle),
so the pipeline runs on a worker thread and reruns re-attach to it.
"""

from unittest.mock import patch

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from webapp.jobs import JobStatus, SummarizeJob


def test_job_collects_result_and_drains_logs_once():
    def runner(status):
        status.write("hello")
        return "summary"

    job = SummarizeJob(runner)
    assert job.wait(5)
    assert job.result == "summary"
    assert job.drain_logs() == ["hello"]
    assert job.drain_logs() == []


def test_job_keeps_running_when_nobody_waits():
    """Like a run interrupted by the theme toggle: no one polls the job,
    but it still finishes and keeps its result for the next run."""

    def runner(status):
        import time

        time.sleep(0.2)
        return "late"

    job = SummarizeJob(runner)
    assert job.wait(5)
    assert job.result == "late"
    assert job.error is None


def test_job_records_errors():
    def runner(status):
        raise RuntimeError("kaput")

    job = SummarizeJob(runner)
    assert job.wait(5)
    assert job.result is None
    assert isinstance(job.error, RuntimeError)
    assert "kaput" in job.traceback_text


def test_job_status_shim_is_not_a_streamlit_element():
    job = SummarizeJob(lambda status: "done")
    assert job.wait(5)
    JobStatus(job).update(label="ignored")  # must not raise


def test_rerun_reattaches_to_running_job_instead_of_restarting():
    script = '''
import streamlit as st
from webapp.jobs import SummarizeJob
from webapp.state import init_session_state
from webapp.ui import _run_and_store
init_session_state({})
class Status:
    def update(self, **kwargs):
        pass
    def write(self, message):
        pass
sidebar = {
    "provider_config": {}, "provider": "test", "prompt_type": "Questions and answers",
    "chunk_size": 10000, "language": "auto", "output_language": "auto",
    "speed": 1.0, "transcription_method": "Cloud Whisper", "whisper_model": "tiny",
    "verbose": False,
}
job = SummarizeJob(lambda status: "reattached summary")
job.wait(5)
job.context = {
    "source": "https://example.test/video", "display_name": "Video",
    "source_type": "Video URL", "force_download": False,
    "sidebar": sidebar, "defaults": {},
}
st.session_state["active_job"] = job
_run_and_store("https://example.test/video", "Video", "Video URL", False, sidebar, {}, Status())
'''
    with patch("webapp.ui.run_summarization") as run, patch(
        "webapp.ui._lookup_cached_transcript", return_value="cached transcript"
    ):
        app = AppTest.from_string(script).run()
    assert not app.exception
    run.assert_not_called()
    assert app.session_state.current_summary == "reattached summary"
    assert app.session_state.active_job is None
