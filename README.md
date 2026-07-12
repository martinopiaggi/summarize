# Video Summarizer

<p align="center">
    <img alt="Video summarizer demo" src="./summarize_sample.gif">
</p>

> Turn any video — a lecture, TikTok, or Drive recording — into distilled markdown: Q&A, fact-checks, tutorials, Mermaid diagrams, essays, and more. 

- **11+ sources**: Local-first summarization for YouTube, Instagram, TikTok, X, Reddit, Facebook, Drive, Dropbox, local files
- **Bring your own API keys**: Works with any OpenAI-compatible LLM, Perplexity models, LiteLLM
- **CLI · Streamlit · HTTP API · Docker · Raycast · Agent skill**
- **Transcript cache** + optional Cobalt sidecar for yt-dlp fallbacks + optional vision mode
- **Documentation**: https://summarize.martino.im
- **Background**: [more on this project](https://martino.im/Summarize.html)

## Quick Start

Requires Python 3.7+, **ffmpeg** on `PATH`, and an OpenAI-compatible API key in `.env`. 
Recommended: install with `pipx` for an isolated environment.

[Groq](https://groq.com/) (`GROQ_API_KEY`) offers a free tier; `OPENAI_API_KEY` works with `--provider openai`.

```bash
pipx install martino-summarize
summarizer --init-config
echo "GROQ_API_KEY=your_key_here" > .env
summarizer --source "https://www.youtube.com/watch?v=arj7oStGLkU"
```

Output: `summaries/watch_YYYYMMDD_HHMMSS.md`. 

Configuration lives in `summarizer.yaml` and `.env`. 

Prefer Docker? 

```bash
git clone https://github.com/martinopiaggi/summarize.git && cd summarize
cp summarizer.docker.yaml summarizer.yaml
echo "GROQ_API_KEY=your_key_here" > .env
docker compose up -d    # → http://localhost:8501
```

Or pull the pre-built image: `docker pull ghcr.io/martinopiaggi/summarize:latest`. 

## Contributing

```bash
git clone https://github.com/martinopiaggi/summarize.git && cd summarize
pip install -e ".[all]" pytest && pytest tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md). License: [MIT](LICENSE).