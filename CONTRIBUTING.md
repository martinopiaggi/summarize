# Contributing

Thanks for helping improve [martinopiaggi/summarize](https://github.com/martinopiaggi/summarize).

## Prerequisites

- **Python** 3.7+ (3.12 recommended)
- **ffmpeg** on your `PATH`
- At least one **LLM API key** in `.env` (see `summarizer.example.yaml` for provider names)
- **Git**

Optional:

- **Docker** + Docker Compose (Streamlit + Cobalt stack)
- **Node.js** 20+ (Fern docs only)

## Local setup (contributors)

```bash
git clone https://github.com/martinopiaggi/summarize.git
cd summarize
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[all]"
pip install pytest streamlit
python -m summarizer --init-config   # or: cp summarizer.example.yaml summarizer.yaml
```

Add API keys to `.env`.

## Running the project

| Surface | Command |
|---------|---------|
| CLI | `python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID"` |
| HTTP API | `python -m summarizer serve` → http://localhost:8000/docs |
| Streamlit | `python -m streamlit run app.py` → http://localhost:8501 |
| Docker | `docker compose up -d` |

## Tests

```bash
pytest tests/
```

Run tests before opening a PR. Add or update tests when changing behavior.

## Architecture discipline

All user-facing surfaces (CLI, API, Streamlit, Docker) should call `summarizer.core.main(config)`. Do not add parallel summarization pipelines.

Config flows through `summarizer.config_file.merge_configs()` and `summarizer.api_utils.build_runtime_config()`.

## Pull requests

1. Fork and branch from `main`
2. Keep changes focused — one logical change per PR
3. **Never commit secrets** — no API keys, `.env`, or personal `summarizer.yaml` with credentials
4. Update docs/README if install paths or user-facing behavior changes
5. Describe what you tested in the PR body
