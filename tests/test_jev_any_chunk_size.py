import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from summarizer.api import process_chunks
from summarizer.exceptions import APIError
from summarizer.jev import MAX_REQUEST_BYTES, MAX_STATE_BYTES, prefilter_chunks, split_units
from webapp.theme import get_custom_css

PROVIDER = {"base_url": "https://openrouter.ai/api/v1", "model": "jev-latest", "api_key": "test"}
CONFIG = {"use_jev_prefiltering": True, "jev_provider_config": PROVIDER, "jev_include": "X", "jev_exclude": "Sponsorship", "parallel_api_calls": 3}


def long_chunk(count):
    return "\n".join(
        f"{index // 3600:02d}:{index // 60 % 60:02d}:{index % 60:02d} "
        + (f"part {index} about X " if index in (0, count - 1) else f"part {index} neutral ")
        + ("discussion " * 70) + "."
        for index in range(count)
    )


@pytest.mark.parametrize("count", [160, 510])
def test_large_chunk_scored_in_bounded_calls_then_ranked_globally(count):
    source = long_chunk(count)
    assert len(source) > 100000
    if count == 510:
        assert len(source) > 400000
    active = 0
    peak = 0

    async def score(session, payload, provider, config):
        nonlocal active, peak
        assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= MAX_REQUEST_BYTES
        assert len(json.dumps(payload["state"], ensure_ascii=False).encode("utf-8")) <= MAX_STATE_BYTES
        active += 1
        peak = max(active, peak)
        await asyncio.sleep(0)
        active -= 1
        return {
            key: (0.01 if key.startswith("exclude_") else
                  0.99 if "about X" in payload["state"]["units"][int(key.split("_")[1])] else 0.8)
            for key in payload["questions"]
        }

    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score) as mock:
        filtered = asyncio.run(prefilter_chunks([("00:00:00", source)], CONFIG))
    assert mock.await_count > 1
    assert peak <= CONFIG["parallel_api_calls"]
    assert "part 0 about X" in filtered[0][1]
    assert f"part {count - 1} about X" in filtered[0][1]
    assert filtered[0][1].index("part 0 about X") < filtered[0][1].index(f"part {count - 1} about X")
    assert len(filtered[0][1]) <= len(source) * 0.35 + 1200
    assert "\n".join(
        "\n".join(call.args[1]["state"]["units"]) for call in mock.await_args_list
    ) == "\n".join(split_units(source))


def test_multiple_scoring_batches_still_send_one_original_chunk_to_summary_model():
    source = long_chunk(160)

    async def score(session, payload, provider, config):
        return {
            key: 0.01 if key.startswith("exclude_") else 0.9
            for key in payload["questions"]
        }

    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score) as scoring, patch("summarizer.api.process_chunk", new_callable=AsyncMock, return_value="summary") as llm:
        result = asyncio.run(process_chunks([("00:00:00", source)], "Summarize {text}", CONFIG))
    assert scoring.await_count > 1
    llm.assert_awaited_once()
    assert len(llm.call_args.args[0]) < len(source)
    assert llm.call_args.args[1] == "Summarize {text}"
    assert result == [("00:00:00", "summary")]


def test_failure_in_late_scoring_batch_never_reaches_summary_model():
    source = long_chunk(120)
    calls = 0

    async def score(session, payload, provider, config):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise APIError("HTTP 429")
        return {key: 0.9 if key.startswith("keep_") else 0.0 for key in payload["questions"]}

    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score), patch("summarizer.api.process_chunk", new_callable=AsyncMock) as llm:
        with pytest.raises(APIError, match="HTTP 429"):
            asyncio.run(process_chunks([("", source)], "{text}", CONFIG))
    llm.assert_not_called()


def test_general_filter_late_batch_failure_keeps_entire_original_chunk():
    source = long_chunk(120)
    calls = 0

    async def score(session, payload, provider, config):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise APIError("HTTP 429")
        return {key: 0.9 for key in payload["questions"]}

    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score):
        result = asyncio.run(prefilter_chunks([("", source)], {**CONFIG, "jev_include": "", "jev_exclude": ""}))
    assert result == [("", source)]


def test_sidebar_textareas_use_theme_colors_in_dark_and_system_mode():
    for theme in ("dark", "system"):
        css = get_custom_css(theme)
        assert '[data-testid="stSidebar"] [data-testid="stTextArea"] textarea' in css
        assert '[data-testid="stSidebar"] [data-testid="stTextArea"] [data-baseweb="textarea"]' in css
        assert '[data-testid="stSidebar"] [data-testid="stNumberInput"] [data-baseweb="input"]' in css
        assert '[data-testid="stSidebar"] [data-testid="stNumberInput"] button' in css
        assert "background-color: var(--secondary) !important;" in css
        assert "color: var(--text) !important;" in css
    assert "--secondary: #141414" in get_custom_css("dark")
