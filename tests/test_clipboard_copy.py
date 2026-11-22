"""COPY TO CLIPBOARD markup tests.

``st.html`` is not iframed, so the Summary and Transcript copy buttons share
one document. With a shared DOM id both scripts bound to the first button:
it copied the transcript and the Transcript tab's button did nothing.
"""

import re
from unittest.mock import patch

import pytest

pytest.importorskip("streamlit")

from webapp.clipboard import copy_to_clipboard


def _render(text, key):
    with patch("webapp.clipboard.st.html") as html:
        copy_to_clipboard(text, "dark", key=key)
    return html.call_args.args[0]


def _declared_ids(markup):
    return set(re.findall(r'\bid="([^"]+)"', markup))


def _looked_up_ids(markup):
    return set(re.findall(r'getElementById\("([^"]+)"\)', markup))


def test_each_copy_button_binds_only_its_own_elements():
    summary = _render("Summary text", "copy_summary")
    transcript = _render("Transcript text", "copy_transcript")

    assert _declared_ids(summary) == {"copy_summary", "copy_summary_buffer"}
    assert _declared_ids(transcript) == {"copy_transcript", "copy_transcript_buffer"}
    assert _looked_up_ids(summary) == _declared_ids(summary)
    assert _looked_up_ids(transcript) == _declared_ids(transcript)
