import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from summarizer.api import process_chunks
from summarizer.api_utils import build_runtime_config
from summarizer.config import get_api_key
from summarizer.config_file import merge_configs
from summarizer.exceptions import APIError, ConfigurationError
from summarizer.jev import (
    build_payload,
    enabled,
    parse_scores,
    prefilter_chunks,
    resolve_provider,
    score_units,
    select_units,
    split_units,
    validate_settings,
    video_context,
)

OPENROUTER = {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "google/gemini-2.5-flash",
    "api_key": "or-key",
}
PROVIDER = {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "jev-latest",
    "api_key": "or-key",
}
CONFIG = {"use_jev_prefiltering": True, "jev_provider_config": PROVIDER}
TEXT = "\n".join(f"00:00:0{i} " + f"Meaningful information number {i} " * 12 + "." for i in range(4))


def scores_for(units, keep=0.9):
    return {f"keep_{index}": keep for index in range(len(units))}


@pytest.mark.parametrize("override", [
    {"use_jev_prefiltering": False},
    {"visual": True},
    {"prompt_type": "Only grammar correction with highlights"},
])
def test_bypass_does_not_call_jev(override):
    chunks = [("", TEXT)]
    with patch("summarizer.jev.score_units", new_callable=AsyncMock) as score:
        result = asyncio.run(prefilter_chunks(chunks, {**CONFIG, **override}))
    assert result is chunks
    score.assert_not_called()


def test_custom_grammar_template_bypasses():
    assert not enabled(CONFIG, "Correct grammatical errors in {text}")


@pytest.mark.parametrize("text", ["Tiny transcript.", "x" * 1500, "x" * 600 + ".\n" + "y" * 600])
def test_tiny_or_two_units_skip_without_provider(text):
    chunks = [("", text)]
    assert asyncio.run(prefilter_chunks(chunks, {"use_jev_prefiltering": True})) == chunks


def test_sentence_and_long_paragraph_units():
    assert split_units("First. Second!\nThird?") == ["First.", "Second!", "Third?"]
    text = " ".join(f"word{i}" for i in range(1200))
    units = split_units(text)
    assert all(len(unit) <= 1200 for unit in units)
    assert " ".join(units) == text
    assert len(units) > 2


def test_selection_keeps_top_relevant_units_in_order():
    units = ["a" * 100, "b" * 100, "c" * 100, "d" * 100, "e" * 100, "f" * 100]
    scores = scores_for(units, keep=0.6)
    scores["keep_4"] = 0.99
    scores["keep_1"] = 0.98
    assert select_units(units, scores, {}) == units[1] + "\n" + units[4]


def test_one_whole_unit_may_exceed_budget():
    units = ["a" * 100, "b" * 100, "c" * 100]
    assert select_units(units, scores_for(units), {"jev_keep_ratio": 0.01}) == units[0]


def test_drops_filler_ads_and_unrelated():
    units = ["Sponsor", "uh um", "unrelated", "main topic"]
    scores = scores_for(units, keep=0.9)
    scores["keep_0"] = 0.01
    scores["keep_1"] = 0.02
    scores["keep_2"] = 0.03
    assert select_units(units, scores, {}) == "main topic"
    assert select_units(units, scores_for(units, keep=0.0), {}) == ""


def test_payload_scores_relevance_to_rest_of_video():
    payload = build_payload(["A", "B", "C"], "video topic", "jev-latest")
    assert payload["state"] == {
        "units": ["A", "B", "C"], "video_context": "video topic",
        "include_request": "", "exclude_request": "",
    }
    assert payload["model"] == "jev-latest"
    assert set(payload["questions"]) == {"keep_0", "keep_1", "keep_2"}
    assert "video_context" in payload["questions"]["keep_0"]["instructions"]
    assert "shorter summary" in payload["questions"]["keep_0"]["instructions"]


@pytest.mark.parametrize("value", [None, True, "0.9", -0.1, 1.1, float("nan"), float("inf")])
def test_rejects_invalid_probabilities(value):
    payload = {"questions": {"test": {}}}
    with pytest.raises(ValueError):
        parse_scores({"answers": {"test": {"type": "noul", "noul": value}}}, payload)


@pytest.mark.parametrize("result", [{}, {"answers": {}}, {"answers": {"wrong": {}}}, []])
def test_rejects_missing_or_wrong_ids(result):
    with pytest.raises(ValueError):
        parse_scores(result, {"questions": {"expected": {}}})


@pytest.mark.parametrize("base_url", ["https://api.typesafe.ai/v1", "https://openrouter.ai/api/v1"])
def test_posts_to_systemone_not_chat(base_url):
    payload = build_payload(["A"], "", "jev-latest")
    scores = scores_for(["A"])
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"answers": {key: {"type": "noul", "noul": value} for key, value in scores.items()}})
    session = MagicMock()
    session.post.return_value.__aenter__ = AsyncMock(return_value=response)
    session.post.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("summarizer.jev.should_proxy_url", return_value=True), patch("summarizer.jev.get_proxy_url", return_value="http://proxy"):
        result = asyncio.run(score_units(session, payload, {**PROVIDER, "base_url": base_url}, {"jev_timeout": 2}))
    assert result == scores
    args, kwargs = session.post.call_args
    assert args == (base_url + "/systemone",)
    assert kwargs["headers"]["Authorization"] == "Bearer or-key"
    assert kwargs["json"] == payload
    assert kwargs["timeout"].total == 2
    assert kwargs["proxy"] == "http://proxy"


def test_one_batch_per_chunk_and_bounded_concurrency():
    active = 0
    peak = 0

    async def score(session, payload, provider, config):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.001)
        active -= 1
        return scores_for(payload["state"]["units"])

    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=score) as mock:
        result = asyncio.run(prefilter_chunks([("", TEXT)] * 5, {**CONFIG, "parallel_api_calls": 2}))
    assert mock.await_count == 5
    assert peak == 2
    assert all(0 < len(text) < len(TEXT) for _, text in result)


@pytest.mark.parametrize("error", [asyncio.TimeoutError(), aiohttp.ClientError(), ValueError(), APIError("HTTP 429")])
def test_failure_no_retry_keeps_original_chunk(error):
    chunks = [("", TEXT)]
    with patch("summarizer.jev.score_units", new_callable=AsyncMock, side_effect=error) as score:
        assert asyncio.run(prefilter_chunks(chunks, CONFIG)) == chunks
    score.assert_awaited_once()


def test_filtered_text_is_sent_to_llm():
    scores = scores_for(split_units(TEXT))
    scores["keep_3"] = 0.99
    with patch("summarizer.jev.score_units", new_callable=AsyncMock, return_value=scores), patch("summarizer.api.process_chunk", new_callable=AsyncMock, return_value="summary") as llm:
        result = asyncio.run(process_chunks([("00:00:00", TEXT)], "{text}", CONFIG))
    assert result == [("00:00:03", "summary")]
    assert llm.call_args.args[0] == split_units(TEXT)[3]


def test_all_rejected_does_not_call_llm():
    with patch("summarizer.jev.score_units", new_callable=AsyncMock, return_value=scores_for(split_units(TEXT), keep=0.0)), patch("summarizer.api.process_chunk", new_callable=AsyncMock) as llm:
        result = asyncio.run(process_chunks([("", TEXT)], "{text}", CONFIG))
    assert "No relevant content" in result[0][1]
    llm.assert_not_called()


def test_openrouter_is_enough_and_uses_jev_not_chat_model():
    file_config = {
        "default_provider": "openrouter",
        "providers": {"openrouter": OPENROUTER},
        "defaults": {"use-jev-prefiltering": True, "jev-include": "X", "jev-exclude": "Sponsorship"},
    }
    merged = merge_configs(file_config, {})
    config = build_runtime_config(merged, "source", "TXT")
    assert config["jev_provider"] == "openrouter"
    assert config["jev_include"] == "X"
    assert config["jev_exclude"] == "Sponsorship"
    assert config["model"] == "google/gemini-2.5-flash"
    assert config["api_key"] == "or-key"
    assert config["jev_provider_config"]["model"] == "jev-latest"
    assert config["jev_provider_config"]["api_key"] == "or-key"
    assert merge_configs(file_config, {"use_jev_prefiltering": False})["jev_provider_config"] is None


@pytest.mark.parametrize("flags,expected", [([], None), (["--use-jev-prefiltering"], True), (["--no-use-jev-prefiltering"], False)])
def test_cli_toggle_preserves_yaml_default(monkeypatch, flags, expected):
    import sys
    from summarizer.__main__ import parse_args

    monkeypatch.setattr(sys, "argv", ["summarizer"] + flags)
    assert parse_args().use_jev_prefiltering is expected


def test_streamlit_adapter_forwards_openrouter():
    from webapp.summarization import run_summarization

    with patch("webapp.summarization.load_config", return_value=({"openrouter": OPENROUTER}, "", {})), patch("summarizer.core.main", return_value="summary") as main:
        result = run_summarization(
            "source", {"base_url": "https://summary", "model": "summary", "api_key": "summary-key"},
            "Questions and answers", 10000, False, "auto", "auto", 1.0,
            use_jev_prefiltering=True, jev_provider="openrouter",
            jev_include="X", jev_exclude="Sponsorship",
        )
    config = main.call_args.args[0]
    assert result == "summary"
    assert config["jev_provider"] == "openrouter"
    assert config["jev_include"] == "X"
    assert config["jev_exclude"] == "Sponsorship"
    assert config["api_key"] == "summary-key"
    assert config["jev_provider_config"]["model"] == "jev-latest"


def test_provider_validation_is_lazy():
    assert resolve_provider({}, {}) is None
    assert resolve_provider({"use_jev_prefiltering": True, "visual": True}, {}) is None
    with pytest.raises(ConfigurationError, match="openrouter"):
        resolve_provider({"use_jev_prefiltering": True, "jev_provider": "groq"}, {"groq": {"base_url": "https://api.groq.com/openai/v1"}})


def test_openrouter_environment_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-env")
    assert get_api_key({"base_url": OPENROUTER["base_url"]}) == "or-env"


@pytest.mark.parametrize("key,value", [("jev_keep_ratio", 0), ("jev_keep_ratio", "0.35"), ("jev_timeout", float("nan")), ("jev_threshold", 2), ("jev_min_chars", -1)])
def test_invalid_settings(key, value):
    with pytest.raises(ConfigurationError):
        validate_settings({key: value})


def test_global_context_includes_end_of_video_and_is_bounded():
    context = video_context([("", "a" * 10000), ("", "z" * 10000)])
    assert context.startswith("a") and context.endswith("z")
    assert len(context) < 2100


def test_request_budget_does_not_split_into_extra_calls():
    chunks = [("", TEXT * 40)]
    with patch("summarizer.jev.score_units", new_callable=AsyncMock) as score:
        assert asyncio.run(prefilter_chunks(chunks, CONFIG)) == chunks
    score.assert_not_called()
