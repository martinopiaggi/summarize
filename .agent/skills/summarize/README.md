# Video Summarizer Skill

AI agent skill for transcribing and summarizing videos using various LLM providers.

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Configure provider in summarizer.yaml and API key in .env

# 3. Summarize a video
python -m summarizer --source "https://www.youtube.com/watch?v=VIDEO_ID" --provider gemini

# 4. Read result
cat summaries/*.md
```

## Documentation

- **[SKILL.md](SKILL.md)** - Complete skill documentation with CLI reference, all options, and examples

## Features

- YouTube videos (captions or audio transcription)
- Local video/audio files (mp4, mp3, wav, m4a, webm)
- Google Drive and Dropbox videos
- 11 summarization styles (Q&A, Distill Wisdom, Tutorial, Fact Checker, etc.)
- Multiple LLM providers (OpenRouter, Groq, Gemini, OpenAI, DeepSeek, Perplexity, etc.)
- Batch processing of multiple URLs
- Markdown, JSON, and HTML output formats

## Supported Platforms

- YouTube (videos, shorts)
- Google Drive videos
- Dropbox videos
- Local files (mp4, mp3, wav, m4a, webm)
- Instagram, TikTok, Twitter/X, Reddit (requires Cobalt service)

## Testing

```bash
python -m pytest tests/ -v
```
