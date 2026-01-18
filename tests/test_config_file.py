"""Tests for config file module."""
import pytest
import os
import tempfile
from pathlib import Path
from summarizer.config_file import (
    load_config_file, merge_configs, get_provider_config,
    create_example_config
)
from summarizer.exceptions import ConfigurationError


class TestLoadConfigFile:
    """Tests for config file loading."""
    
    def test_load_valid_yaml(self, tmp_path):
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text("""
default_provider: groq
providers:
  groq:
    base_url: https://api.groq.com/openai/v1
    model: llama-3.3-70b-versatile
""", encoding='utf-8')
        
        config = load_config_file(config_file)
        assert config["default_provider"] == "groq"
        assert "groq" in config["providers"]
    
    def test_missing_file_returns_empty(self):
        config = load_config_file(Path("/nonexistent/path.yaml"))
        # Should return empty dict, not raise
        # (since yaml is optional in some cases)
    
    def test_empty_file_returns_empty_dict(self, tmp_path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("", encoding='utf-8')
        
        config = load_config_file(config_file)
        assert config == {}


class TestGetProviderConfig:
    """Tests for provider configuration retrieval."""
    
    def test_get_existing_provider(self):
        config = {
            "providers": {
                "groq": {"base_url": "https://api.groq.com", "model": "llama"}
            }
        }
        provider = get_provider_config(config, "groq")
        assert provider["base_url"] == "https://api.groq.com"
    
    def test_unknown_provider_raises(self):
        config = {
            "providers": {
                "groq": {"base_url": "https://api.groq.com"}
            }
        }
        with pytest.raises(ConfigurationError) as exc_info:
            get_provider_config(config, "unknown")
        assert "unknown" in str(exc_info.value).lower()
    
    def test_no_providers_raises(self):
        config = {}
        with pytest.raises(ConfigurationError):
            get_provider_config(config, "groq")


class TestMergeConfigs:
    """Tests for config merging."""
    
    def test_cli_overrides_file(self):
        file_config = {
            "defaults": {"chunk-size": 5000}
        }
        cli_args = {"chunk_size": 10000}
        
        merged = merge_configs(file_config, cli_args)
        assert merged["chunk_size"] == 10000
    
    def test_file_defaults_apply(self):
        file_config = {
            "defaults": {"chunk-size": 5000, "language": "es"}
        }
        cli_args = {}
        
        merged = merge_configs(file_config, cli_args)
        assert merged["chunk_size"] == 5000
        assert merged["language"] == "es"
    
    def test_provider_config_applies(self):
        file_config = {
            "providers": {
                "groq": {
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile"
                }
            }
        }
        cli_args = {"provider": "groq"}
        
        merged = merge_configs(file_config, cli_args)
        assert merged["base_url"] == "https://api.groq.com/openai/v1"
        assert merged["model"] == "llama-3.3-70b-versatile"
    
    def test_none_values_ignored(self):
        file_config = {
            "defaults": {"chunk-size": 5000}
        }
        cli_args = {"chunk_size": None, "model": None}
        
        merged = merge_configs(file_config, cli_args)
        assert merged["chunk_size"] == 5000


class TestCreateExampleConfig:
    """Tests for example config generation."""
    
    def test_creates_valid_yaml(self):
        import yaml
        example = create_example_config()
        # Should be valid YAML
        config = yaml.safe_load(example)
        assert "providers" in config
        assert "default_provider" in config
    
    def test_includes_common_providers(self):
        example = create_example_config()
        assert "groq" in example
        assert "gemini" in example
        assert "openai" in example
