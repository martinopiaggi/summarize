"""Tests for API module."""
import pytest
from summarizer.api import chunk_text, extract_and_clean_chunks, parse_response_content


class TestChunkText:
    """Tests for text chunking."""
    
    def test_short_text_single_chunk(self):
        text = "This is a short text."
        chunks = chunk_text(text, 1000)
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_long_text_multiple_chunks(self):
        # Create text with multiple paragraphs
        text = "\n".join([f"Paragraph {i} with some content." for i in range(100)])
        chunks = chunk_text(text, 500)
        assert len(chunks) > 1
    
    def test_preserves_paragraph_boundaries(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, 100)
        # Each chunk should contain complete paragraphs
        for chunk in chunks:
            # No chunk should start/end mid-sentence
            assert not chunk.startswith(" ")
    
    def test_minimum_chunk_size_enforced(self):
        text = "Short."
        chunks = chunk_text(text, 10)  # Below minimum
        assert len(chunks) == 1  # Should still work
    
    def test_empty_text(self):
        chunks = chunk_text("", 1000)
        assert len(chunks) == 1
        assert chunks[0] == ""


class TestExtractAndCleanChunks:
    """Tests for timestamp extraction and chunking."""
    
    def test_extracts_timestamp(self):
        text = "00:01:30 Some transcript text here.\n00:02:45 More text."
        chunks = extract_and_clean_chunks(text, 10000)
        assert len(chunks) == 1
        timestamp, content = chunks[0]
        assert timestamp == "00:01:30"
    
    def test_no_timestamp_returns_empty(self):
        text = "Just some text without timestamps."
        chunks = extract_and_clean_chunks(text, 10000)
        assert len(chunks) == 1
        timestamp, content = chunks[0]
        assert timestamp == ""
    
    def test_multiple_chunks_each_get_timestamp(self):
        lines = [f"{i:02d}:00:00 Content for hour {i}" for i in range(10)]
        text = "\n".join(lines)
        chunks = extract_and_clean_chunks(text, 100)
        # Each chunk should have its first timestamp extracted
        for timestamp, content in chunks:
            if content.strip():
                # Timestamp should be in HH:MM:SS format if present
                if timestamp:
                    assert len(timestamp.split(":")) == 3


class TestParseResponseContent:
    """Tests for API response parsing."""
    
    def test_standard_response(self):
        response = {
            "choices": [{
                "message": {
                    "content": "This is the summary."
                }
            }]
        }
        result = parse_response_content(response, "https://api.groq.com")
        assert result == "This is the summary."
    
    def test_strips_whitespace(self):
        response = {
            "choices": [{
                "message": {
                    "content": "  Content with spaces  \n"
                }
            }]
        }
        result = parse_response_content(response, "https://api.openai.com")
        assert result == "Content with spaces"
    
    def test_perplexity_removes_think_tags(self):
        response = {
            "choices": [{
                "message": {
                    "content": "<think>reasoning here</think>The actual answer."
                }
            }]
        }
        result = parse_response_content(response, "https://api.perplexity.ai")
        assert result == "The actual answer."
    
    def test_perplexity_removes_code_fences(self):
        response = {
            "choices": [{
                "message": {
                    "content": "```json\n{\"key\": \"value\"}\n```"
                }
            }]
        }
        result = parse_response_content(response, "https://api.perplexity.ai")
        assert "```" not in result
    
    def test_empty_response(self):
        response = {"choices": [{}]}
        result = parse_response_content(response, "https://api.openai.com")
        assert result == ""
    
    def test_missing_choices(self):
        response = {}
        result = parse_response_content(response, "https://api.openai.com")
        assert result == ""
