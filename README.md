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

## Documentation

Full docs live at [summarize.martino.im](https://summarize.martino.im).

## License

[MIT](LICENSE)
