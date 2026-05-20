"""Tests for LiteLLM provider integration in the summarizer API."""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# Stub litellm before importing
_fake_litellm = types.ModuleType("litellm")
_fake_exceptions = types.ModuleType("litellm.exceptions")


class _AuthenticationError(Exception):
    pass


class _BadRequestError(Exception):
    pass


class _NotFoundError(Exception):
    pass


class _RateLimitError(Exception):
    __module__ = "litellm.exceptions"
    __qualname__ = "RateLimitError"


class _Timeout(Exception):
    __module__ = "litellm.exceptions"
    __qualname__ = "Timeout"


_fake_exceptions.AuthenticationError = _AuthenticationError
_fake_exceptions.BadRequestError = _BadRequestError
_fake_exceptions.NotFoundError = _NotFoundError
_fake_exceptions.RateLimitError = _RateLimitError
_fake_exceptions.Timeout = _Timeout

_fake_litellm.exceptions = _fake_exceptions
_fake_litellm.acompletion = AsyncMock()

sys.modules["litellm"] = _fake_litellm
sys.modules["litellm.exceptions"] = _fake_exceptions


def _make_response(content):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture(autouse=True)
def reset_mocks():
    _fake_litellm.acompletion.reset_mock()
    _fake_litellm.acompletion.side_effect = None
    _fake_litellm.acompletion.return_value = _make_response("This is a test summary.")
    yield


LITELLM_CONFIG = {
    "base_url": "litellm",
    "model": "anthropic/claude-sonnet-4-6",
    "api_key": "sk-test-123",
    "max_output_tokens": 4096,
}

LITELLM_CONFIG_NO_KEY = {
    "base_url": "litellm",
    "model": "openai/gpt-4o-mini",
    "max_output_tokens": 4096,
}

TEMPLATE = "Summarize the following text:\n{text}"


class TestLiteLLMProcessChunk:
    """Unit tests for the LiteLLM path in process_chunk."""

    def test_basic_call(self):
        from summarizer.api import process_chunk

        result = asyncio.run(process_chunk("Hello world", TEMPLATE, LITELLM_CONFIG))
        assert result == "This is a test summary."
        _fake_litellm.acompletion.assert_called_once()

    def test_drop_params_always_true(self):
        from summarizer.api import process_chunk

        asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        assert call_kwargs["drop_params"] is True

    def test_model_forwarded(self):
        from summarizer.api import process_chunk

        asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "anthropic/claude-sonnet-4-6"

    def test_provider_prefixed_model(self):
        from summarizer.api import process_chunk

        asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        assert "/" in call_kwargs["model"]

    def test_api_key_forwarded(self):
        from summarizer.api import process_chunk

        asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        assert call_kwargs["api_key"] == "sk-test-123"

    def test_api_key_omitted_when_none(self):
        from summarizer.api import process_chunk

        asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG_NO_KEY))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        assert "api_key" not in call_kwargs

    def test_max_tokens_forwarded(self):
        from summarizer.api import process_chunk

        asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        assert call_kwargs["max_tokens"] == 4096

    def test_messages_structure(self):
        from summarizer.api import process_chunk

        asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "video content analysis" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "Hello" in messages[1]["content"]

    def test_output_language_in_system_prompt(self):
        from summarizer.api import process_chunk

        config = {**LITELLM_CONFIG, "output_language": "Spanish"}
        asyncio.run(process_chunk("Hello", TEMPLATE, config))
        call_kwargs = _fake_litellm.acompletion.call_args[1]
        assert "Spanish" in call_kwargs["messages"][0]["content"]

    def test_empty_chunk_returns_empty(self):
        from summarizer.api import process_chunk

        result = asyncio.run(process_chunk("   ", TEMPLATE, LITELLM_CONFIG))
        assert result == ""
        _fake_litellm.acompletion.assert_not_called()


class TestLiteLLMErrors:
    """Tests for error handling with litellm-specific exceptions."""

    def test_auth_error_raises_api_error(self):
        from summarizer.api import process_chunk
        from summarizer.exceptions import APIError

        _fake_litellm.acompletion.side_effect = _AuthenticationError("Invalid key")
        with pytest.raises(APIError, match="LiteLLM request failed"):
            asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert _fake_litellm.acompletion.call_count == 1

    def test_not_found_error_raises_api_error(self):
        from summarizer.api import process_chunk
        from summarizer.exceptions import APIError

        _fake_litellm.acompletion.side_effect = _NotFoundError("Model not found")
        with pytest.raises(APIError, match="LiteLLM request failed"):
            asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert _fake_litellm.acompletion.call_count == 1

    def test_bad_request_error_raises_api_error(self):
        from summarizer.api import process_chunk
        from summarizer.exceptions import APIError

        _fake_litellm.acompletion.side_effect = _BadRequestError("context_length_exceeded")
        with pytest.raises(APIError, match="LiteLLM request failed"):
            asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert _fake_litellm.acompletion.call_count == 1

    def test_rate_limit_retried(self):
        from summarizer.api import process_chunk
        from summarizer.exceptions import APIError

        _fake_litellm.acompletion.side_effect = _RateLimitError("429")
        with pytest.raises(APIError, match="after 3 attempts"):
            asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert _fake_litellm.acompletion.call_count == 3

    def test_timeout_retried(self):
        from summarizer.api import process_chunk
        from summarizer.exceptions import APIError

        _fake_litellm.acompletion.side_effect = _Timeout("timed out")
        with pytest.raises(APIError, match="after 3 attempts"):
            asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert _fake_litellm.acompletion.call_count == 3

    def test_empty_response_returns_empty(self):
        from summarizer.api import process_chunk

        _fake_litellm.acompletion.return_value = _make_response("")
        result = asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert result == ""

    def test_null_content_returns_empty(self):
        from summarizer.api import process_chunk

        resp = _make_response(None)
        resp.choices[0].message.content = None
        _fake_litellm.acompletion.return_value = resp
        result = asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert result == ""

    def test_please_provide_filtered(self):
        from summarizer.api import process_chunk

        _fake_litellm.acompletion.return_value = _make_response(
            "Please provide the transcript so I can summarize it."
        )
        result = asyncio.run(process_chunk("Hello", TEMPLATE, LITELLM_CONFIG))
        assert result == ""


class TestLiteLLMConfig:
    """Tests for config-level LiteLLM support."""

    def test_get_api_key_litellm_returns_placeholder(self):
        from summarizer.config import get_api_key

        result = get_api_key({"base_url": "litellm", "model": "openai/gpt-4o"})
        assert result == "litellm"

    def test_get_api_key_litellm_with_explicit_key(self):
        from summarizer.config import get_api_key

        result = get_api_key({"base_url": "litellm", "api_key": "sk-real"})
        assert result == "sk-real"

    def test_non_litellm_base_url_uses_original_path(self):
        from summarizer.api import process_chunk

        config = {**LITELLM_CONFIG, "base_url": "https://api.openai.com/v1"}
        # This should NOT use litellm path (would fail without aiohttp mock)
        # We just verify litellm.acompletion is NOT called
        try:
            asyncio.run(process_chunk("Hello", TEMPLATE, config))
        except Exception:
            pass  # Expected to fail without aiohttp mock
        _fake_litellm.acompletion.assert_not_called()
