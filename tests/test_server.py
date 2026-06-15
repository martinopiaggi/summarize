"""Tests for the FastAPI HTTP server and shared API utilities."""

import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from summarizer.api_utils import (
    format_output,
    build_runtime_config,
    redact_config_response,
    redact_provider_config,
    OUTPUT_FORMATS,
    SOURCE_TYPES,
)


# ── FastAPI-dependent imports (endpoint tests) ──
try:
    from fastapi.testclient import TestClient
    from summarizer.server import app, create_app, _build_runtime_config_from_request
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    TestClient = None
    app = None
    create_app = None


@pytest.fixture
def client():
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed. Run: pip install 'summarizer[server]'")
    return TestClient(app)


# ── Health ──

class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "summarize"


# ── Providers ──

class TestProvidersEndpoint:
    @patch("summarizer.server.load_config_file")
    def test_providers_returns_configured_providers(self, mock_load, client):
        mock_load.return_value = {
            "providers": {
                "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile"},
                "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash-lite"},
            }
        }
        response = client.get("/providers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {p["name"] for p in data}
        assert names == {"groq", "gemini"}
        groq = next(p for p in data if p["name"] == "groq")
        assert groq["model"] == "llama-3.3-70b-versatile"

    @patch("summarizer.server.load_config_file")
    def test_providers_empty_when_no_config(self, mock_load, client):
        mock_load.return_value = {}
        response = client.get("/providers")
        assert response.status_code == 200
        assert response.json() == []


# ── Prompts ──

class TestPromptsEndpoint:
    @patch("summarizer.server.get_available_prompts")
    def test_prompts_returns_list(self, mock_prompts, client):
        mock_prompts.return_value = ["Questions and answers", "Summarization", "Distill Wisdom"]
        response = client.get("/prompts")
        assert response.status_code == 200
        assert response.json() == ["Questions and answers", "Summarization", "Distill Wisdom"]


# ── Config (redacted) ──

class TestConfigEndpoint:
    @patch("summarizer.server.load_config_file")
    @patch("summarizer.server.find_config_file")
    def test_config_returns_redacted_config(self, mock_find, mock_load, client):
        mock_find.return_value = Path("/fake/summarizer.yaml")
        mock_load.return_value = {
            "default_provider": "groq",
            "providers": {
                "groq": {
                    "base_url": "https://api.groq.com/openai/v1",
                    "model": "llama-3.3-70b-versatile",
                    "api_key": "sk-secret-key",
                }
            },
            "defaults": {"chunk_size": 10000, "prompt_type": "Questions and answers"},
        }
        response = client.get("/config")
        assert response.status_code == 200
        data = response.json()
        assert data["default_provider"] == "groq"
        assert data["providers"]["groq"]["model"] == "llama-3.3-70b-versatile"
        assert data["providers"]["groq"]["api_key"] == "***REDACTED***"
        assert "sk-secret-key" not in json.dumps(data)
        assert data["defaults"]["chunk_size"] == 10000
        assert data["config_file_path"] == "/fake/summarizer.yaml"  # returned as POSIX path


# ── Summarize ──

class TestSummarizeEndpoint:
    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_summarize_url_success(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "This is a test summary."

        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "type": "YouTube Video",
            "provider": "groq",
            "prompt_type": "Summarization",
            "output_format": "markdown",
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source"] == "https://youtube.com/watch?v=dQw4w9WgXcQ"
        assert "This is a test summary" in data["summary"]
        assert data["format"] == "markdown"
        assert data["processing_time_seconds"] >= 0

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_summarize_json_format(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "JSON test summary."

        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "output_format": "json",
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["format"] == "json"
        summary_json = json.loads(data["summary"])
        assert summary_json["summary"] == "JSON test summary."

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_summarize_html_format(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "HTML test summary."

        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "output_format": "html",
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["format"] == "html"
        assert "<!DOCTYPE html>" in data["summary"]

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_summarize_with_all_options(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 5000,
            "parallel_api_calls": 10,
            "max_output_tokens": 2048,
            "prompt_type": "Distill Wisdom",
            "language": "en",
            "output_language": "Spanish",
            "transcription_method": "Local Whisper",
            "whisper_model": "small",
            "audio_speed": 2.0,
            "cobalt_base_url": "http://localhost:9000",
            "use_proxy": True,
            "api_key": "sk-test-key",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "Full options summary."

        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "type": "YouTube Video",
            "provider": "groq",
            "prompt_type": "Distill Wisdom",
            "chunk_size": 5000,
            "parallel_calls": 10,
            "max_tokens": 2048,
            "language": "en",
            "output_language": "Spanish",
            "force_download": True,
            "transcription": "Local Whisper",
            "whisper_model": "small",
            "audio_speed": 2.0,
            "output_format": "markdown",
            "visual": False,
            "use_proxy": True,
            "api_key": "sk-test-key",
            "base_url": "https://custom.api.com/v1",
            "model": "custom-model",
            "cobalt_url": "http://localhost:9000",
            "verbose": True,
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_main.assert_called_once()
        config = mock_main.call_args[0][0]
        assert config["source_url_or_path"] == "https://youtube.com/watch?v=dQw4w9WgXcQ"
        assert config["type_of_source"] == "YouTube Video"
        assert config["prompt_type"] == "Distill Wisdom"
        assert config["chunk_size"] == 5000
        assert config["parallel_api_calls"] == 10
        assert config["max_output_tokens"] == 2048
        assert config["language"] == "en"
        assert config["output_language"] == "Spanish"
        assert config["use_youtube_captions"] is False  # force_download=True
        assert config["transcription_method"] == "Local Whisper"
        assert config["whisper_model"] == "small"
        assert config["audio_speed"] == 2.0
        assert config["use_proxy"] is True
        assert config["api_key"] == "sk-test-key"
        assert config["base_url"] == "https://custom.api.com/v1"
        assert config["model"] == "custom-model"
        assert config["cobalt_base_url"] == "http://localhost:9000"
        assert config["verbose"] is True

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_summarize_error_handling(self, mock_load, mock_merge, mock_main, client):
        from summarizer.exceptions import TranscriptError
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.side_effect = TranscriptError("No captions available")

        payload = {"source": "https://youtube.com/watch?v=INVALID", "output_format": "markdown"}
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "TranscriptError"
        assert "No captions available" in data["error"]

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_summarize_unexpected_error(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.side_effect = RuntimeError("Something went wrong")

        payload = {"source": "https://youtube.com/watch?v=dQw4w9WgXcQ", "output_format": "markdown"}
        response = client.post("/summarize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "RuntimeError"
        assert "Something went wrong" in data["error"]


# ── Validation ──

class TestValidation:
    def test_invalid_output_format_rejected(self, client):
        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "output_format": "xml",
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 422

    def test_invalid_audio_speed_rejected(self, client):
        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "audio_speed": 0,
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 422

    def test_negative_chunk_size_rejected(self, client):
        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "chunk_size": -1,
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 422

    def test_invalid_source_type_rejected(self, client):
        payload = {
            "source": "https://youtube.com/watch?v=dQw4w9WgXcQ",
            "type": "Invalid Type",
        }
        response = client.post("/summarize", json=payload)
        assert response.status_code == 422

    def test_batch_empty_sources_rejected(self, client):
        payload = {
            "sources": [],
            "output_format": "markdown",
        }
        response = client.post("/summarize/batch", json=payload)
        assert response.status_code == 422


# ── Upload ──

class TestSummarizeUploadEndpoint:
    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_upload_video_file(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "Video file summary."

        file_content = b"fake video data"
        response = client.post(
            "/summarize/upload",
            files={"file": ("test_video.mp4", BytesIO(file_content), "video/mp4")},
            data={"prompt_type": "Summarization", "output_format": "markdown"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source"] == "test_video.mp4"
        assert "Video file summary" in data["summary"]
        config = mock_main.call_args[0][0]
        assert config["type_of_source"] == "Local File"

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_upload_text_file(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "Text file summary."

        file_content = b"This is a transcript text file."
        response = client.post(
            "/summarize/upload",
            files={"file": ("transcript.txt", BytesIO(file_content), "text/plain")},
            data={"prompt_type": "Summarization", "output_format": "markdown"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source"] == "transcript.txt"
        config = mock_main.call_args[0][0]
        assert config["type_of_source"] == "TXT"

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_upload_with_explicit_type(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "Custom type summary."

        file_content = b"fake data"
        response = client.post(
            "/summarize/upload",
            files={"file": ("data.bin", BytesIO(file_content), "application/octet-stream")},
            data={"type": "Local File", "output_format": "markdown"},
        )
        assert response.status_code == 200
        config = mock_main.call_args[0][0]
        assert config["type_of_source"] == "Local File"

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_upload_error_handling(self, mock_load, mock_merge, mock_main, client):
        from summarizer.exceptions import SourceNotFoundError
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.side_effect = SourceNotFoundError("File not found")

        file_content = b"fake video"
        response = client.post(
            "/summarize/upload",
            files={"file": ("missing.mp4", BytesIO(file_content), "video/mp4")},
            data={"output_format": "markdown"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "SourceNotFoundError"


# ── Batch ──

class TestBatchEndpoint:
    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_batch_all_success(self, mock_load, mock_merge, mock_main, client):
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        mock_main.return_value = "Batch summary."

        payload = {
            "sources": [
                "https://youtube.com/watch?v=VIDEO1",
                "https://youtube.com/watch?v=VIDEO2",
            ],
            "type": "YouTube Video",
            "provider": "groq",
            "prompt_type": "Summarization",
            "output_format": "markdown",
        }
        response = client.post("/summarize/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success_count"] == 2
        assert data["total_count"] == 2
        assert len(data["results"]) == 2
        for result in data["results"]:
            assert result["success"] is True
            assert "Batch summary" in result["summary"]
        assert data["overall_processing_time_seconds"] >= 0

    @patch("summarizer.server.main")
    @patch("summarizer.server.merge_configs")
    @patch("summarizer.server.load_config_file")
    def test_batch_partial_failure(self, mock_load, mock_merge, mock_main, client):
        from summarizer.exceptions import TranscriptError
        mock_load.return_value = {}
        mock_merge.return_value = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }

        def side_effect(config):
            if "VIDEO1" in config.get("source_url_or_path", ""):
                return "Summary for video 1"
            raise TranscriptError("No captions for video 2")

        mock_main.side_effect = side_effect

        payload = {
            "sources": [
                "https://youtube.com/watch?v=VIDEO1",
                "https://youtube.com/watch?v=VIDEO2",
            ],
            "output_format": "markdown",
        }
        response = client.post("/summarize/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["success_count"] == 1
        assert data["total_count"] == 2
        assert data["results"][0]["success"] is True
        assert data["results"][1]["success"] is False
        assert data["results"][1]["error_type"] == "TranscriptError"


# ── Format output (shared module) ──

class TestFormatOutput:
    def test_format_markdown(self):
        result = format_output("Test summary.", "https://example.com", "markdown", {"prompt_type": "Q&A", "model": "gpt-4"})
        assert "# Summary for: https://example.com" in result
        assert "Test summary." in result
        assert "Generated on:" in result

    def test_format_json(self):
        result = format_output("Test summary.", "https://example.com", "json", {"prompt_type": "Q&A", "model": "gpt-4"})
        parsed = json.loads(result)
        assert parsed["source"] == "https://example.com"
        assert parsed["summary"] == "Test summary."
        assert parsed["model"] == "gpt-4"
        assert parsed["prompt_type"] == "Q&A"
        assert "generated_at" in parsed

    def test_format_html(self):
        result = format_output("Test summary.", "https://example.com", "html", {"prompt_type": "Q&A", "model": "gpt-4"})
        assert "<!DOCTYPE html>" in result
        assert "Test summary." in result
        assert "https://example.com" in result


# ── Build runtime config (shared module) ──

class TestBuildRuntimeConfig:
    def test_build_config_with_defaults(self):
        merged = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        config = build_runtime_config(merged, "https://youtube.com/watch?v=TEST", "YouTube Video")
        assert config["base_url"] == "https://api.groq.com/openai/v1"
        assert config["model"] == "llama-3.3-70b-versatile"
        assert config["chunk_size"] == 10000
        assert config["parallel_api_calls"] == 30
        assert config["max_output_tokens"] == 4096
        assert config["prompt_type"] == "Questions and answers"

    def test_build_config_with_overrides(self):
        merged = {
            "base_url": "https://custom.api.com/v1",
            "model": "custom-model",
            "chunk_size": 5000,
            "api_key": "sk-test",
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        config = build_runtime_config(merged, "https://youtube.com/watch?v=TEST", "YouTube Video")
        assert config["base_url"] == "https://custom.api.com/v1"
        assert config["model"] == "custom-model"
        assert config["chunk_size"] == 5000
        assert config["api_key"] == "sk-test"

    def test_build_config_force_download_youtube(self):
        merged = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        config = build_runtime_config(merged, "https://youtube.com/watch?v=TEST", "YouTube Video", force_download=True)
        assert config["use_youtube_captions"] is False

    def test_build_config_youtube_captions_default(self):
        merged = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        config = build_runtime_config(merged, "https://youtube.com/watch?v=TEST", "YouTube Video", force_download=False)
        assert config["use_youtube_captions"] is True

    def test_build_config_non_youtube_no_captions(self):
        merged = {
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
            "chunk_size": 10000,
            "parallel_api_calls": 30,
            "max_output_tokens": 4096,
            "prompt_type": "Questions and answers",
            "language": "auto",
            "output_language": "auto",
            "transcription_method": "Cloud Whisper",
            "whisper_model": "tiny",
            "audio_speed": 1.0,
            "cobalt_base_url": "http://localhost:9000",
            "cache_transcript": True,
            "visual": False,
            "visual_compression": "off",
            "visual_chunk_seconds": "auto",
            "visual_chunk_overlap_seconds": 0,
        }
        config = build_runtime_config(merged, "https://example.com/video.mp4", "Video URL", force_download=False)
        assert config["use_youtube_captions"] is False


# ── Config redaction ──

class TestRedaction:
    def test_redact_provider_config(self):
        cfg = {"base_url": "https://api.example.com", "api_key": "sk-secret", "model": "gpt-4"}
        redacted = redact_provider_config(cfg)
        assert redacted["api_key"] == "***REDACTED***"
        assert redacted["base_url"] == "https://api.example.com"
        assert redacted["model"] == "gpt-4"

    def test_redact_config_response(self):
        file_config = {
            "default_provider": "groq",
            "providers": {
                "groq": {"base_url": "https://api.groq.com", "api_key": "sk-secret"},
                "gemini": {"base_url": "https://api.gemini.com", "api_key": "sk-secret2"},
            },
            "defaults": {"chunk_size": 10000},
        }
        result = redact_config_response(file_config)
        assert result["providers"]["groq"]["api_key"] == "***REDACTED***"
        assert result["providers"]["gemini"]["api_key"] == "***REDACTED***"
        assert result["defaults"]["chunk_size"] == 10000


# ── CORS ──

class TestCors:
    def test_cors_disabled_by_default(self, client):
        # With no CORS middleware, preflight requests are handled as a normal
        # route mismatch and return 405; regular requests carry no CORS headers.
        response = client.options(
            "/summarize",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 405
        assert "access-control-allow-origin" not in response.headers

    def test_cors_enabled_for_specific_origin(self):
        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not installed")
        _app = create_app(allow_origins=["http://localhost:3000"])
        client = TestClient(_app)
        response = client.options(
            "/summarize",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    def test_cors_wildcard_origin(self):
        if not FASTAPI_AVAILABLE:
            pytest.skip("FastAPI not installed")
        _app = create_app(allow_origins=["*"])
        client = TestClient(_app)
        response = client.options(
            "/summarize",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "*"
