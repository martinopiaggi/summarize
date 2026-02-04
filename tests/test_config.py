"""Tests for config module."""
import pytest
import os
from unittest.mock import patch
from summarizer.config import get_api_key, API_PROVIDERS, validate_config
from summarizer.exceptions import APIKeyError, ConfigurationError


class TestGetApiKey:
    """Tests for API key retrieval."""
    
    def test_explicit_api_key_in_config(self):
        """If api_key is in config, use it directly."""
        cfg = {"api_key": "test-key-123", "base_url": "https://api.openai.com/v1"}
        assert get_api_key(cfg) == "test-key-123"
    
    @patch.dict(os.environ, {"groq": "groq-test-key"})
    def test_groq_url_matches_groq_env(self):
        cfg = {"base_url": "https://api.groq.com/openai/v1"}
        assert get_api_key(cfg) == "groq-test-key"
    
    @patch.dict(os.environ, {"openai": "openai-test-key"})
    def test_openai_url_matches_openai_env(self):
        cfg = {"base_url": "https://api.openai.com/v1"}
        assert get_api_key(cfg) == "openai-test-key"
    
    @patch.dict(os.environ, {"generativelanguage": "gemini-test-key"})
    def test_gemini_url_matches_gemini_env(self):
        cfg = {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai"}
        assert get_api_key(cfg) == "gemini-test-key"
    
    @patch.dict(os.environ, {"deepseek": "deepseek-test-key"})
    def test_deepseek_url_matches_deepseek_env(self):
        cfg = {"base_url": "https://api.deepseek.com/v1"}
        assert get_api_key(cfg) == "deepseek-test-key"
    
    @patch.dict(os.environ, {"perplexity": "pplx-test-key"})
    def test_perplexity_url_matches_perplexity_env(self):
        cfg = {"base_url": "https://api.perplexity.ai"}
        assert get_api_key(cfg) == "pplx-test-key"
    
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_raises_error(self):
        cfg = {"base_url": "https://api.unknown-provider.com/v1"}
        with pytest.raises(APIKeyError):
            get_api_key(cfg)
    
    def test_missing_base_url_raises_error(self):
        cfg = {}
        with pytest.raises(ConfigurationError):
            get_api_key(cfg)


class TestApiProviders:
    """Tests for API provider configuration."""
    
    def test_common_providers_are_defined(self):
        expected = ["groq", "openai", "perplexity", "deepseek", "anthropic", "generativelanguage"]
        for provider in expected:
            # Check that either the provider name is a key, or at least related patterns exist
            matching = [k for k in API_PROVIDERS.keys() if provider in k.lower() or provider in API_PROVIDERS.get(k, "").lower()]
            assert len(matching) > 0 or provider in API_PROVIDERS.values(), f"{provider} not found"


class TestValidateConfig:
    """Tests for configuration validation."""
    
    def test_valid_config_passes(self):
        cfg = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "source_url_or_path": "https://youtube.com/watch?v=xxx"
        }
        # Should not raise
        validate_config(cfg)
    
    def test_missing_base_url_raises(self):
        cfg = {
            "model": "llama-3.3-70b-versatile",
            "source_url_or_path": "https://youtube.com/watch?v=xxx"
        }
        with pytest.raises(ConfigurationError):
            validate_config(cfg)
    
    def test_missing_model_raises(self):
        cfg = {
            "base_url": "https://api.groq.com/openai/v1",
            "source_url_or_path": "https://youtube.com/watch?v=xxx"
        }
        with pytest.raises(ConfigurationError):
            validate_config(cfg)
    
    def test_chunk_size_too_small_raises(self):
        cfg = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "source_url_or_path": "https://youtube.com/watch?v=xxx",
            "chunk_size": 100
        }
        with pytest.raises(ConfigurationError):
            validate_config(cfg)
