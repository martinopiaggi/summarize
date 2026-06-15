# Video Summarizer

<p align="center">
    <img alt="sample" src="./summarize_sample.gif">
</p>

Transcribe and summarize videos from YouTube, Instagram, TikTok, Twitter, Reddit, Facebook, Google Drive, Dropbox, and local files.

Works with any OpenAI-compatible LLM provider, including locally hosted endpoints.


## Interfaces

Pick your poison:

| Interface | Command |
|-----------|---------|
| **CLI** | `python -m summarizer --source <source>` |
| **HTTP API** | `python -m summarizer serve` → `http://localhost:8000/docs` |
| **Streamlit GUI** | `python -m streamlit run app.py` |
| **Docker** | `docker compose up -d` → `http://localhost:8501` |
| **Agent Skill** | [`.agent/skills/summarize/SKILL.md`](./.agent/skills/summarize/SKILL.md) |


## Quick Start

```bash
git clone https://github.com/martinopiaggi/summarize.git
cd summarize
pip install -e .
python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID"
```

The summary is saved to `summaries/watch_YYYYMMDD_HHMMSS.md`.

### HTTP API

Install server dependencies:

```bash
pip install -e ".[server]"
```

Start the server:

```bash
python -m summarizer serve
```

The API docs are available at `http://localhost:8000/docs`.

Sample requests:

```bash
# Summarize a YouTube video
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"source": "https://youtube.com/watch?v=VIDEO_ID", "provider": "groq"}'

# List configured providers
curl http://localhost:8000/providers

# Upload and summarize a local video
curl -X POST http://localhost:8000/summarize/upload \
  -F "file=@video.mp4" \
  -F "provider=groq"
```

By default the server binds to `127.0.0.1:8000`. To allow cross-origin requests, set `SUMMARIZER_CORS_ORIGINS`:

```bash
# Allow a specific origin
SUMMARIZER_CORS_ORIGINS=http://localhost:3000 python -m summarizer serve

# Allow all origins (not recommended for production)
SUMMARIZER_CORS_ORIGINS=* python -m summarizer serve
```

## Documentation

Full docs live at [summarize.martino.im](https://summarize.martino.im).

## License

[MIT](LICENSE)
