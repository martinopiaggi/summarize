import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from summarizer.api import _build_messages, process_chunks
from summarizer.config_file import merge_configs
from summarizer.exceptions import APIError, ConfigurationError
from summarizer.jev import build_payload, parse_scores, prefilter_chunks, select_units, validate_settings

PROVIDER = {"base_url": "https://openrouter.ai/api/v1", "model": "jev-latest", "api_key": "test"}
CONFIG = {"use_jev_prefiltering": True, "jev_provider_config": PROVIDER}


def test_inclusion_scope_is_not_limited_to_main_topic():
    payload = build_payload(["He founded SpaceX."], "The podcast is mostly about nutrition", "jev-latest", "X", "sponsorship")
    assert payload["state"]["include_request"] == "X"
    assert payload["state"]["exclude_request"] == "sponsorship"
    assert set(payload["questions"]) == {"keep_0", "exclude_0"}
    assert "not the video's main topic" in payload["questions"]["keep_0"]["instructions"]
    assert "neighboring units" in payload["questions"]["keep_0"]["instructions"]
    assert isinstance(payload["questions"]["exclude_0"]["criteria"], dict)


def test_exclusion_only_uses_general_inclusion_score():
    payload = build_payload(["A"], "video", "jev-latest", exclude="sponsorship")
    assert "shorter summary" in payload["questions"]["keep_0"]["instructions"]
    assert "neutral discussion" in payload["questions"]["exclude_0"]["instructions"]


def test_exclusion_wins_and_budget_is_not_a_quota():
    units = ["Sponsor about X", "X founded SpaceX", "Irrelevant passage " * 100]
    scores = {"keep_0": 0.99, "exclude_0": 0.9, "keep_1": 0.9, "exclude_1": 0.01, "keep_2": 0.1, "exclude_2": 0.0}
    assert select_units(units, scores, {"jev_exclude": "Sponsorship"}) == units[1]
    scores["exclude_1"] = 0.5
    assert select_units(units, scores, {"jev_exclude": "Sponsorship"}) == ""


def test_missing_exclusion_answer_is_invalid_not_permission_to_keep():
    payload = build_payload(["Sponsor"], "video", "jev-latest", exclude="sponsorship")
    with pytest.raises(ValueError):
        parse_scores({"answers": {"keep_0": {"type": "noul", "noul": 0.9}}}, payload)


@pytest.mark.parametrize("rules", [{"jev_include": "X"}, {"jev_exclude": "sponsorship"}])
def test_explicit_rules_filter_even_a_single_tiny_unit(rules):
    scores = {"keep_0": 0.1, "exclude_0": 0.9}
    with patch("summarizer.jev.score_units", new_callable=AsyncMock, return_value=scores) as scoring, patch("summarizer.api.process_chunk", new_callable=AsyncMock) as llm:
        result = asyncio.run(process_chunks([("", "Irrelevant sponsor")], "{text}", {**CONFIG, **rules}))
    scoring.assert_awaited_once()
    llm.assert_not_called()
    assert "No relevant content" in result[0][1]


@pytest.mark.parametrize("rules", [{"jev_include": "X"}, {"jev_exclude": "sponsorship"}])
@pytest.mark.parametrize("failure", [asyncio.TimeoutError(), APIError("HTTP 429"), ValueError("Malformed answer")])
def test_explicit_rule_failures_stop_before_any_summary(rules, failure):
    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=failure) as scoring, patch("summarizer.api.process_chunk", new_callable=AsyncMock) as llm:
        with pytest.raises(APIError, match="without sending unfiltered text"):
            asyncio.run(process_chunks([("", "Short passage")], "{text}", {**CONFIG, **rules}))
    scoring.assert_awaited_once()
    llm.assert_not_called()


def test_partial_filter_failure_does_not_summarize_successful_chunks_either():
    async def score(session, payload, provider, config):
        if payload["state"]["units"] == ["Broken"]:
            raise APIError("HTTP 500")
        return {"keep_0": 0.99}

    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score), patch("summarizer.api.process_chunk", new_callable=AsyncMock) as llm:
        with pytest.raises(APIError):
            asyncio.run(process_chunks([("", "X"), ("", "Broken")], "{text}", {**CONFIG, "jev_include": "X"}))
    llm.assert_not_called()


def test_explicit_rules_over_budget_fail_without_extra_calls():
    with patch("summarizer.jev.score_units", new_callable=AsyncMock) as scoring:
        with pytest.raises(APIError, match="reduce chunk-size"):
            asyncio.run(prefilter_chunks([("", "word " * 10000)], {**CONFIG, "jev_exclude": "sponsorship"}))
    scoring.assert_not_called()


def test_selection_applies_across_entire_video_in_source_order():
    chunks = [("00:00:00", "Sponsor read"), ("00:05:00", "X founded SpaceX"), ("00:09:00", "Back to cooking")]

    async def score(session, payload, provider, config):
        text = payload["state"]["units"][0]
        return {"keep_0": 0.99 if text.startswith("X") else 0.01, "exclude_0": 0.99 if text.startswith("Sponsor") else 0.01}

    config = {**CONFIG, "jev_include": "X", "jev_exclude": "sponsorship"}
    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score) as scoring, patch("summarizer.api.process_chunk", new_callable=AsyncMock, return_value="summary") as llm:
        result = asyncio.run(process_chunks(chunks, "Summarize {text}", config))
    assert scoring.await_count == 3
    llm.assert_awaited_once_with(chunks[1][1], "Summarize {text}", config)
    assert result == [("00:05:00", "summary")]
    assert _build_messages("passage", "{text}", config) == _build_messages("passage", "{text}", {})


@pytest.mark.parametrize("bypass", [{"visual": True}, {"prompt_type": "Only grammar correction with highlights"}, {"use_jev_prefiltering": False}])
def test_bypass_preserves_transcript_even_with_rules(bypass):
    chunks = [("", "Anything")]
    with patch("summarizer.jev.score_units", new_callable=AsyncMock) as scoring:
        result = asyncio.run(prefilter_chunks(chunks, {**CONFIG, "jev_include": "X", **bypass}))
    assert result is chunks
    scoring.assert_not_called()


@pytest.mark.parametrize("key,value", [("jev_include", None), ("jev_exclude", 7), ("jev_include", "x" * 2001), ("jev_exclude", ["ads"])])
def test_invalid_selection_settings(key, value):
    with pytest.raises(ConfigurationError):
        validate_settings({key: value})


def test_whitespace_rules_do_not_trigger_extra_scoring():
    with patch("summarizer.jev.score_units", new_callable=AsyncMock) as scoring:
        chunks = [("", "Small")]
        assert asyncio.run(prefilter_chunks(chunks, {**CONFIG, "jev_include": "  ", "jev_exclude": "\n"})) is chunks
    scoring.assert_not_called()


def test_cli_explicit_empty_clears_yaml_rules(monkeypatch):
    from summarizer.__main__ import parse_args
    monkeypatch.setattr("sys.argv", ["summarizer", "--jev-include", "", "--jev-exclude", ""])
    args = parse_args()
    merged = merge_configs({"defaults": {"jev-include": "X", "jev-exclude": "sponsorship"}}, {"jev_include": args.jev_include, "jev_exclude": args.jev_exclude})
    assert merged["jev_include"] == merged["jev_exclude"] == ""
