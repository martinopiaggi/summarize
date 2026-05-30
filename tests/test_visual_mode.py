"""Tests for visual mode provider profiles, validation, and API building."""

import base64
import os
import tempfile
from unittest.mock import patch

import pytest

from summarizer.exceptions import VisualModeError, VideoValidationError
from summarizer.visual import (
    VIDEO_PROVIDER_PROFILES,
    get_visual_provider_profile,
    resolve_video_source,
    encode_video_base64,
    validate_video_limits,
    normalize_video,
    probe_video,
    build_visual_segments,
    split_video_segments,
)
from summarizer.visual_api import (
    build_visual_messages,
    build_visual_payload,
    process_video_segments,
)


class TestGetVisualProviderProfile:
    def test_detects_nvidia(self):
        profile = get_visual_provider_profile({
            "base_url": "https://integrate.api.nvidia.com/v1",
            "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        })
        assert profile["name"] == "nvidia"

    def test_unsupported_provider_raises(self):
        with pytest.raises(VisualModeError, match="does not support visual mode"):
            get_visual_provider_profile({
                "base_url": "https://api.groq.com/openai/v1",
                "model": "llama-3.3-70b-versatile",
            })

    def test_unknown_provider_raises(self):
        with pytest.raises(VisualModeError, match="does not support visual mode"):
            get_visual_provider_profile({
                "base_url": "https://example.com",
                "model": "some-model",
            })


class TestResolveVideoSource:
    def test_local_file_returns_path_and_no_cleanup(self):
        path, should_delete = resolve_video_source({
            "type_of_source": "Local File",
            "source_url_or_path": __file__,
        })
        assert path == __file__
        assert should_delete is False

    def test_missing_local_file_raises(self):
        from summarizer.exceptions import SourceNotFoundError
        with pytest.raises(SourceNotFoundError):
            resolve_video_source({
                "type_of_source": "Local File",
                "source_url_or_path": "/nonexistent/file.mp4",
            })

    def test_txt_rejected(self):
        with pytest.raises(VisualModeError, match="TXT sources"):
            resolve_video_source({
                "type_of_source": "TXT",
                "source_url_or_path": "/fake/file.txt",
            })

    def test_unsupported_source_type_raises(self):
        with pytest.raises(VisualModeError, match="does not support source type"):
            resolve_video_source({
                "type_of_source": "Unsupported",
                "source_url_or_path": "/fake/file.mp4",
            })


class TestProbeVideo:
    def test_missing_file_returns_empty_probe(self):
        result = probe_video("/nonexistent/file.mp4")
        assert result["duration"] is None
        assert result["size_mb"] is None

    def test_existing_file_without_ffprobe(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"not a real video")
            path = f.name
        try:
            result = probe_video(path)
            assert result["size_mb"] is not None
            assert result["container"] == "mp4"
        finally:
            os.remove(path)


class TestValidateVideoLimits:
    def test_duration_over_limit_raises(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 200.0, "size_mb": 50.0, "container": "mp4"
        }):
            with pytest.raises(VideoValidationError, match="duration is 200s"):
                validate_video_limits("/fake.mp4", {
                    "name": "nvidia", "max_duration_seconds": 120,
                    "max_file_mb": 100, "formats": {"mp4"}
                }, {})

    def test_size_over_limit_raises(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 60.0, "size_mb": 150.0, "container": "mp4"
        }):
            with pytest.raises(VideoValidationError, match="file size is 150.0 MB"):
                validate_video_limits("/fake.mp4", {
                    "name": "nvidia", "max_duration_seconds": 120,
                    "max_file_mb": 100, "formats": {"mp4"}
                }, {})

    def test_format_not_supported_raises(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 60.0, "size_mb": 50.0, "container": "avi"
        }):
            with pytest.raises(VideoValidationError, match="container 'avi' is not supported"):
                validate_video_limits("/fake.avi", {
                    "name": "nvidia", "max_duration_seconds": 120,
                    "max_file_mb": 100, "formats": {"mp4"}
                }, {})

    def test_within_limit_passes(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 60.0, "size_mb": 50.0, "container": "mp4"
        }):
            validate_video_limits("/fake.mp4", {
                "name": "nvidia", "max_duration_seconds": 120,
                "max_file_mb": 100, "formats": {"mp4"}
            }, {})

    def test_config_override_limits(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 130.0, "size_mb": 50.0, "container": "mp4"
        }):
            # 130s exceeds default 120s but config override allows 200s
            validate_video_limits("/fake.mp4", {
                "name": "nvidia", "max_duration_seconds": 120,
                "max_file_mb": 100, "formats": {"mp4"}
            }, {"visual_max_duration_seconds": 200})

    def test_unknown_duration_raises(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": None, "size_mb": 50.0, "container": "mp4"
        }):
            with pytest.raises(VideoValidationError, match="Could not determine video duration"):
                validate_video_limits("/fake.mp4", {
                    "name": "nvidia", "max_duration_seconds": 120,
                    "max_file_mb": 100, "formats": {"mp4"}
                }, {})


class TestBuildVisualSegments:
    def test_820_seconds_creates_7_nvidia_segments(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 820.0, "size_mb": 50.0, "container": "mp4"
        }):
            segments = build_visual_segments("/fake.mp4", {
                "name": "nvidia", "max_duration_seconds": 120
            }, {})
            assert len(segments) == 7
            assert segments[0]["timestamp"] == "00:00:00"
            assert segments[-1]["timestamp"] == "00:12:00"
            assert segments[-1]["duration"] == 100

    def test_120_seconds_creates_1_segment(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 120.0, "size_mb": 50.0, "container": "mp4"
        }):
            segments = build_visual_segments("/fake.mp4", {
                "name": "nvidia", "max_duration_seconds": 120
            }, {})
            assert len(segments) == 1
            assert segments[0]["duration"] == 120

    def test_121_seconds_creates_2_segments(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 121.0, "size_mb": 50.0, "container": "mp4"
        }):
            segments = build_visual_segments("/fake.mp4", {
                "name": "nvidia", "max_duration_seconds": 120
            }, {})
            assert len(segments) == 2
            assert segments[1]["timestamp"] == "00:02:00"
            assert segments[1]["duration"] == 1

    def test_chunk_overlap(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 300.0, "size_mb": 50.0, "container": "mp4"
        }):
            segments = build_visual_segments("/fake.mp4", {
                "name": "nvidia", "max_duration_seconds": 120
            }, {"visual_chunk_overlap_seconds": 10})
            assert [segment["timestamp"] for segment in segments] == [
                "00:00:00", "00:01:50", "00:03:40"
            ]


class TestSplitVideoSegments:
    def test_single_segment_reuses_original(self):
        segments = [{
            "index": 1, "total": 1, "start": 0.0, "end": 60.0,
            "duration": 60.0, "timestamp": "00:00:00",
            "end_timestamp": "00:01:00",
        }]
        result = split_video_segments("/fake/video.mp4", segments, {})
        assert result[0]["path"] == "/fake/video.mp4"
        assert result[0]["should_delete"] is False

    def test_multiple_segments_use_ffmpeg(self):
        segments = [
            {
                "index": 1, "total": 2, "start": 0.0, "end": 120.0,
                "duration": 120.0, "timestamp": "00:00:00",
                "end_timestamp": "00:02:00",
            },
            {
                "index": 2, "total": 2, "start": 120.0, "end": 121.0,
                "duration": 1.0, "timestamp": "00:02:00",
                "end_timestamp": "00:02:01",
            },
        ]
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = split_video_segments("/fake/video.mp4", segments, {})
            assert len(result) == 2
            assert all(segment["should_delete"] for segment in result)
            assert mock_run.call_count == 2
            first_cmd = mock_run.call_args_list[0][0][0]
            assert first_cmd[:5] == [
                "ffmpeg", "-y", "-ss", "0.000", "-i"
            ]
            assert "-t" in first_cmd
            assert "120.000" in first_cmd


class TestNormalizeVideo:
    def test_mp4_returns_same_path(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 60.0, "size_mb": 50.0, "container": "mp4"
        }):
            assert normalize_video("/fake/video.mp4", {}, {}) == "/fake/video.mp4"

    def test_compression_triggered_when_over_limit(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 60.0, "size_mb": 150.0, "container": "mp4"
        }), patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = normalize_video("/fake/video.mp4", {
                "name": "nvidia", "max_file_mb": 100
            }, {"visual_compression": "auto"})
            assert "normalized" in result
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "libx264" in args

    def test_long_chunkable_video_not_compressed_before_split(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 820.0, "size_mb": 500.0, "container": "mp4"
        }), patch("subprocess.run") as mock_run:
            result = normalize_video("/fake/video.mp4", {
                "name": "nvidia",
                "max_duration_seconds": 120,
                "max_file_mb": 100,
                "supports_chunking": True,
            }, {"visual_compression": "auto"})
            assert result == "/fake/video.mp4"
            mock_run.assert_not_called()

    def test_remux_for_non_mp4(self):
        with patch("summarizer.visual.probe_video", return_value={
            "duration": 60.0, "size_mb": 50.0, "container": "avi"
        }), patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            result = normalize_video("/fake/video.avi", {
                "name": "nvidia", "formats": {"mp4"}
            }, {})
            assert "normalized" in result
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "-c" in args and "copy" in args


class TestEncodeVideoBase64:
    def test_encodes_mp4(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video data")
            path = f.name
        try:
            result = encode_video_base64(path)
            expected = "data:video/mp4;base64," + base64.b64encode(b"fake video data").decode("ascii")
            assert result == expected
        finally:
            os.remove(path)

    def test_encodes_webm(self):
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(b"fake webm data")
            path = f.name
        try:
            result = encode_video_base64(path)
            assert result.startswith("data:video/webm;base64,")
        finally:
            os.remove(path)


class TestBuildVisualMessages:
    def test_contains_video_url_and_text(self):
        messages = build_visual_messages(
            {"prompt_type": "Questions and answers"},
            "data:video/mp4;base64,abc123"
        )
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        content = messages[1]["content"]
        assert any(item.get("type") == "video_url" for item in content)
        assert any(item.get("type") == "text" for item in content)

    def test_segment_context_included(self):
        messages = build_visual_messages(
            {
                "prompt_type": "Questions and answers",
                "visual_segment_start": "00:02:00",
                "visual_segment_end": "00:04:00",
                "visual_segment_index": 2,
                "visual_segment_total": 7,
            },
            "data:video/mp4;base64,abc123",
        )
        text_parts = [
            item["text"] for item in messages[1]["content"]
            if item.get("type") == "text"
        ]
        assert "segment 2/7" in text_parts[0]
        assert "00:02:00 to 00:04:00" in text_parts[0]

    def test_includes_output_language(self):
        messages = build_visual_messages({
            "prompt_type": "Questions and answers",
            "output_language": "Spanish",
        }, "data:video/mp4;base64,abc123")
        assert "Spanish" in messages[0]["content"]

    def test_prompt_type_loaded(self):
        messages = build_visual_messages({
            "prompt_type": "Questions and answers",
        }, "data:video/mp4;base64,abc123")
        text_parts = [item["text"] for item in messages[1]["content"] if item.get("type") == "text"]
        assert len(text_parts) == 1
        assert "attached video" in text_parts[0]


class TestBuildVisualPayload:
    def test_nvidia_extra_body_merged(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake")
            path = f.name
        try:
            payload = build_visual_payload(
                {"model": "nvidia/nemotron-3-nano-omni", "prompt_type": "Questions and answers"},
                path,
                {"name": "nvidia", "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": True},
                    "mm_processor_kwargs": {"use_audio_in_video": True},
                }},
            )
            # extra_body should be merged at the top level, not nested under "extra_body"
            assert payload["mm_processor_kwargs"]["use_audio_in_video"] is True
            assert payload["chat_template_kwargs"]["enable_thinking"] is True
            assert "model" in payload
            assert "messages" in payload
            assert "extra_body" not in payload
        finally:
            os.remove(path)


class TestProcessVideoSegments:
    def test_returns_timestamped_summaries(self):
        segments = [
            {
                "index": 1, "total": 2, "path": "/fake/1.mp4",
                "timestamp": "00:00:00", "end_timestamp": "00:02:00",
            },
            {
                "index": 2, "total": 2, "path": "/fake/2.mp4",
                "timestamp": "00:02:00", "end_timestamp": "00:04:00",
            },
        ]

        async def fake_process_video(config, video_path, profile, max_retries=3):
            return f"summary for {config['visual_segment_start']}"

        with patch("summarizer.visual_api.process_video", side_effect=fake_process_video):
            import asyncio
            result = asyncio.run(process_video_segments({}, segments, {"name": "nvidia"}))

        assert result == [
            ("00:00:00", "summary for 00:00:00"),
            ("00:02:00", "summary for 00:02:00"),
        ]


class TestCoreVisualBranch:
    def test_visual_path_skips_transcript(self):
        async def fake_process_segments(config, segments, profile):
            return [("00:00:00", "visual summary")]

        with patch("summarizer.core.get_api_key", return_value="test-key"), \
             patch("summarizer.core.get_transcript") as mock_get_transcript, \
             patch("summarizer.visual.get_visual_provider_profile", return_value={
                 "name": "nvidia",
                 "max_duration_seconds": 120,
                 "max_file_mb": 100,
                 "formats": {"mp4"},
                 "supports_chunking": True,
             }), \
             patch("summarizer.visual.resolve_video_source", return_value=("/fake/video.mp4", False)), \
             patch("summarizer.visual.normalize_video", return_value="/fake/video.mp4"), \
             patch("summarizer.visual.build_visual_segments", return_value=[{
                 "index": 1,
                 "total": 1,
                 "start": 0.0,
                 "end": 60.0,
                 "duration": 60.0,
                 "timestamp": "00:00:00",
                 "end_timestamp": "00:01:00",
             }]), \
             patch("summarizer.visual.split_video_segments", return_value=[{
                 "index": 1,
                 "total": 1,
                 "path": "/fake/video.mp4",
                 "timestamp": "00:00:00",
                 "end_timestamp": "00:01:00",
                 "should_delete": False,
             }]), \
             patch("summarizer.visual.validate_video_limits"), \
             patch("summarizer.visual_api.process_video_segments", side_effect=fake_process_segments):
            from summarizer.core import main

            result = main({
                "visual": True,
                "base_url": "https://integrate.api.nvidia.com/v1",
                "model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
                "source_url_or_path": "/fake/video.mp4",
                "type_of_source": "Local File",
                "prompt_type": "Questions and answers",
                "max_output_tokens": 4096,
            })

        assert "visual summary" in result
        mock_get_transcript.assert_not_called()
