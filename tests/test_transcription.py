"""Tests for transcript fetching behavior."""

from unittest.mock import patch, MagicMock

import pytest

from summarizer.transcription import _fetch_transcript


class TestFetchTranscriptCaptions:
    def test_youtube_captions_used_at_default_speed(self):
        with patch("summarizer.transcription.is_youtube_url", return_value=True), \
             patch("summarizer.transcription.extract_youtube_id", return_value="VIDEO_ID"), \
             patch("summarizer.transcription.get_youtube_transcript", return_value="caption text") as mock_captions, \
             patch("summarizer.transcription.print_status"):
            result = _fetch_transcript({
                "type_of_source": "YouTube Video",
                "source_url_or_path": "https://youtube.com/watch?v=VIDEO_ID",
                "use_youtube_captions": True,
                "speed": 1.0,
                "transcription_method": "Cloud Whisper",
                "whisper_model": "tiny",
                "verbose": False,
                "use_proxy": False,
                "language": "auto",
            })
        assert result == "caption text"
        mock_captions.assert_called_once()

    def test_youtube_captions_skipped_when_speed_set(self):
        with patch("summarizer.transcription.is_youtube_url", return_value=True), \
             patch("summarizer.transcription.extract_youtube_id") as mock_extract, \
             patch("summarizer.transcription.get_youtube_transcript") as mock_captions, \
             patch("summarizer.transcription.DownloadManager") as mock_dm, \
             patch("summarizer.transcription.print_status"), \
             patch("os.path.exists", return_value=False):
            mock_download = MagicMock()
            mock_download.download_audio.return_value = "/fake/audio.mp3"
            mock_dm.return_value = mock_download
            with patch("summarizer.transcription.transcribe_audio", return_value="audio transcript") as mock_transcribe:
                result = _fetch_transcript({
                    "type_of_source": "YouTube Video",
                    "source_url_or_path": "https://youtube.com/watch?v=VIDEO_ID",
                    "use_youtube_captions": True,
                    "speed": 2.0,
                    "transcription_method": "Cloud Whisper",
                    "whisper_model": "tiny",
                    "verbose": False,
                    "use_proxy": False,
                    "language": "auto",
                    "cobalt_base_url": "http://localhost:9000",
                })
        assert result == "audio transcript"
        mock_extract.assert_not_called()
        mock_captions.assert_not_called()
        mock_download.download_audio.assert_called_once()
        mock_transcribe.assert_called_once()
