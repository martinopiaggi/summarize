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


class TestYamlAliasesAndRuntimeConfig:
    def test_kebab_case_aliases_reach_the_runtime_config(self):
        from summarizer.api_utils import build_runtime_config

        file_config = {
            "defaults": {
                "parallel-calls": 4,
                "max-tokens": 2048,
                "cache-transcript-persist": True,
                "output-dir": "out",
            }
        }
        merged = merge_configs(file_config, {"base_url": "https://x/v1", "model": "m"})
        assert merged["parallel_api_calls"] == 4
        assert merged["max_output_tokens"] == 2048

        config = build_runtime_config(merged, "https://youtu.be/x", "YouTube Video")
        assert config["parallel_api_calls"] == 4
        assert config["max_output_tokens"] == 2048
        assert config["cache_transcript_persist"] is True
        assert config["output_dir"] == "out"

    def test_cli_flags_still_override_yaml_aliases(self):
        merged = merge_configs({"defaults": {"parallel-calls": 4}}, {"parallel_api_calls": 9})
        assert merged["parallel_api_calls"] == 9


class TestUpdateConfigFile:
    YAML = (
        "# my config\n"
        "providers:\n  g:\n    base_url: https://g/v1\n    model: m\n\n"
        "defaults:\n  prompt-type: Questions and answers  # house style\n"
    )

    def test_keeps_comments_and_quotes_values_that_need_it(self, tmp_path):
        from summarizer.config_file import update_config_file
        import yaml

        path = tmp_path / "summarizer.yaml"
        path.write_text(self.YAML)
        update_config_file(path, {"prompt-type": "Distill Wisdom", "jev-include": "ads: yes # no", "visual": True})
        update_config_file(path, {"default_provider": "g"}, section=None)

        text = path.read_text()
        assert text.startswith("# my config\ndefault_provider: g\n")
        assert "  prompt-type: Distill Wisdom  # house style\n" in text
        data = yaml.safe_load(text)
        assert data["defaults"]["jev-include"] == "ads: yes # no"
        assert data["defaults"]["visual"] is True

    def test_creates_missing_block_and_fills_empty_value(self, tmp_path):
        from summarizer.config_file import update_config_file
        import yaml

        path = tmp_path / "summarizer.yaml"
        path.write_text("default_provider:\nproviders: {}\n")
        update_config_file(path, {"default_provider": "g"}, section=None)
        update_config_file(path, {"chunk_size": 5000})
        assert yaml.safe_load(path.read_text()) == {
            "default_provider": "g",
            "providers": {},
            "defaults": {"chunk-size": 5000},
        }
