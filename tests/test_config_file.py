"""Tests for config file loading and merging."""

import pytest

from summarizer.config_file import merge_configs
from summarizer.exceptions import ConfigurationError


class TestMergeConfigsSpeed:
    def test_cli_speed_merged(self):
        merged = merge_configs({}, {"speed": 2.5})
        assert merged["speed"] == 2.5

    def test_file_speed_merged(self):
        file_config = {"defaults": {"speed": 2.0}}
        merged = merge_configs(file_config, {})
        assert merged["speed"] == 2.0

    def test_cli_speed_overrides_file_speed(self):
        file_config = {"defaults": {"speed": 2.0}}
        merged = merge_configs(file_config, {"speed": 3.0})
        assert merged["speed"] == 3.0

    def test_legacy_audio_speed_in_yaml_rejected(self):
        file_config = {"defaults": {"audio_speed": 2.0}}
        with pytest.raises(ConfigurationError, match="audio-speed / audio_speed"):
            merge_configs(file_config, {})

    def test_legacy_audio_speed_in_default_provider_rejected(self):
        file_config = {
            "default_provider": "groq",
            "providers": {
                "groq": {
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile",
                    "audio-speed": 2.0,
                }
            },
        }
        with pytest.raises(ConfigurationError, match="audio-speed / audio_speed"):
            merge_configs(file_config, {})

    def test_legacy_audio_speed_kebab_case_in_yaml_rejected(self):
        file_config = {"defaults": {"audio-speed": 2.0}}
        with pytest.raises(ConfigurationError, match="audio-speed / audio_speed"):
            merge_configs(file_config, {})

    def test_legacy_audio_speed_in_cli_rejected(self):
        with pytest.raises(ConfigurationError, match="audio-speed / audio_speed"):
            merge_configs({}, {"audio_speed": 2.0})
