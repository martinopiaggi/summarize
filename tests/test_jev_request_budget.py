import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from summarizer.api import process_chunks
from summarizer.exceptions import APIError
from summarizer.jev import (
    MAX_REQUEST_BYTES, MAX_STATE_BYTES, JEVRequestBudgetError,
    build_payload, prepare_payload, split_units,
)

CONFIG = {
    "use_jev_prefiltering": True,
    "jev_include": "motivation for 25 yo",
    "jev_exclude": "sponsorship",
    "jev_provider_config": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "jev-latest",
        "api_key": "test",
    },
}


def size(value):
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def caption_tail():
    return "\n".join(f"00:00:{index % 60:02d} short caption line {index}" for index in range(77))


def test_short_caption_tail_groups_units_without_losing_text():
    text = caption_tail()
    assert len(text) < 4000
    units = split_units(text)
    original_units = list(units)
    context = "video context " * 140
    args = (context, "jev-latest", CONFIG["jev_include"], CONFIG["jev_exclude"])
    assert len(units) == 77
    assert size(build_payload(units, *args)) > MAX_REQUEST_BYTES
    fitted, payload = prepare_payload(units, *args)
    assert units == original_units
    assert 1 < len(fitted) < len(units)
    assert "\n".join(fitted) == text
    assert size(payload) <= MAX_REQUEST_BYTES
    assert size(payload["state"]) <= MAX_STATE_BYTES
    assert len(payload["questions"]) == 2 * len(fitted)
    assert payload["state"]["units"] == fitted


def test_fitting_request_preserves_existing_unit_granularity():
    units = ["a" * 900, "b" * 900, "c" * 900]
    expected = build_payload(units, "ctx", "jev-latest", "topic", "sponsors")
    fitted, actual = prepare_payload(units, "ctx", "jev-latest", "topic", "sponsors")
    assert fitted is units
    assert actual == expected


def test_short_caption_tail_uses_one_request_and_fitted_ids():
    async def score(session, payload, provider, config):
        assert size(payload) <= MAX_REQUEST_BYTES
        assert "\n".join(payload["state"]["units"]) == caption_tail()
        scores = {key: 0.0 for key in payload["questions"]}
        scores["keep_1"] = 0.99
        return scores

    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score) as scoring, patch("summarizer.api.process_chunk", new_callable=AsyncMock, return_value="summary") as llm:
        result = asyncio.run(process_chunks([("00:00:00", caption_tail())], "{text}", CONFIG))
    scoring.assert_awaited_once()
    selected = scoring.call_args.args[1]["state"]["units"][1]
    llm.assert_awaited_once_with(selected, "{text}", CONFIG)
    assert len(result) == 1


def test_impossible_state_rejects_before_any_chunk_is_sent():
    with patch("summarizer.jev.score_units", new_callable=AsyncMock) as scoring, patch("summarizer.api.process_chunk", new_callable=AsyncMock) as llm:
        with pytest.raises(APIError, match="state .* bytes"):
            asyncio.run(process_chunks([("", "A valid short chunk"), ("", "word " * 10000)], "{text}", CONFIG))
    scoring.assert_not_called()
    llm.assert_not_called()


def test_multibyte_limits_are_bytes_not_characters():
    with pytest.raises(JEVRequestBudgetError, match="cannot fit without removing source text"):
        prepare_payload(["漢" * 10000], "", "jev-latest", "topic", "sponsors")


def test_timeout_diagnostic_does_not_recommend_smaller_chunks():
    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()):
        with pytest.raises(APIError, match="timed out") as failure:
            asyncio.run(process_chunks([("", "short")], "{text}", CONFIG))
    assert "reduce chunk-size" not in str(failure.value)
