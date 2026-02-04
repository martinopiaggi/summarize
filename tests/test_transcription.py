"""Tests for transcription module."""
import pytest
from summarizer.transcription import extract_youtube_id, format_timestamp
from summarizer.exceptions import TranscriptError


class TestExtractYoutubeId:
    """Tests for YouTube ID extraction."""
    
    def test_standard_watch_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_youtube_id(url) == "dQw4w9WgXcQ"
    
    def test_short_url(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert extract_youtube_id(url) == "dQw4w9WgXcQ"
    
    def test_embed_url(self):
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert extract_youtube_id(url) == "dQw4w9WgXcQ"
    
    def test_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120"
        assert extract_youtube_id(url) == "dQw4w9WgXcQ"
    
    def test_url_with_playlist(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxxxxx"
        assert extract_youtube_id(url) == "dQw4w9WgXcQ"
    
    def test_no_protocol(self):
        url = "youtube.com/watch?v=dQw4w9WgXcQ"
        assert extract_youtube_id(url) == "dQw4w9WgXcQ"
    
    def test_invalid_url_raises_error(self):
        with pytest.raises(TranscriptError):
            extract_youtube_id("https://example.com/not-youtube")
    
    def test_empty_url_raises_error(self):
        with pytest.raises(TranscriptError):
            extract_youtube_id("")


class TestFormatTimestamp:
    """Tests for timestamp formatting."""
    
    def test_zero_seconds(self):
        assert format_timestamp(0) == "00:00:00"
    
    def test_seconds_only(self):
        assert format_timestamp(45) == "00:00:45"
    
    def test_minutes_and_seconds(self):
        assert format_timestamp(125) == "00:02:05"
    
    def test_hours_minutes_seconds(self):
        assert format_timestamp(3661) == "01:01:01"
    
    def test_large_value(self):
        assert format_timestamp(36000) == "10:00:00"
    
    def test_fractional_seconds(self):
        # Should truncate to integer
        assert format_timestamp(90.7) == "00:01:30"
