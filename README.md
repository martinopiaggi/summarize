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

## Optional JEV prefilter

Check **Use JEV prefiltering** to reveal two optional fields:

- **I want to include only…** — e.g. `a particular concept about this video to filter`. Selects that subject even when it is not the main topic. Blank means general relevance to the video.
- **I want to exclude…** — e.g. `Sponsorship and self-promotion`. Removes matching passages. Blank means no additional exclusions. Exclusions win when a passage matches both fields.

JEV selects original passages **before** the existing LLM request. It does not rewrite the transcript, change the summary prompt/model, or modify the cached transcript. The selected passages stay in source order. With JEV off, the existing pipeline is unchanged.

```yaml
defaults:
  use-jev-prefiltering: true
  jev-provider: openrouter
  jev-include: "a particular concept about this video to filter"
  jev-exclude: "Sponsorship and self-promotion"
  jev-keep-ratio: 0.35
  chunk-size: 10000
```

Uses the existing OpenRouter (default) or TypeSafe provider's API key, with a JEV model instead of its chat model. [`/systemone`](https://openrouter.ai/docs/guides/community/typesafe-sdk) is the structured scoring endpoint, not a system prompt. No separate provider entry is needed.

CLI: `--use-jev-prefiltering --jev-include "X" --jev-exclude "Sponsorship"`. YAML accepts `jev-include` / `jev-exclude`; HTTP single/batch/upload requests accept `jev_include` / `jev_exclude`. Empty strings clear configured rules.

**Compression and limits:**
- One batched scoring request per eligible existing chunk, with bounded concurrency and no retries. Independent inclusion/exclusion scores prevent a high inclusion score from overriding an exclusion.
- The default budget is about **35% of each original chunk**, including when using exclusion only. It is a ceiling, not a quota: irrelevant text never fills unused space. Whole units are retained; one best matching unit can exceed the budget. Set `jev-keep-ratio: 1.0` in YAML to retain all qualifying units instead of ranking down to 35%.
- All-rejected chunks are omitted; if none remain, return a no-match message without calling the LLM.
- Explicit rules also filter tiny chunks and single units. On timeout, malformed response, HTTP error or request-budget overflow, stop before any summary request rather than sending unfiltered text. With both fields blank, the existing tiny-chunk bypass and warning/original-text fallback remain.
- Visual mode and grammar correction bypass JEV entirely, with a warning that selection rules do not apply.
- Use `chunk-size: 10000`; provider-level chunk sizes override defaults. Conservative limits are 28 KB state / 60 KB total JSON per request. If many short captions inflate the questions, adjacent units are merged locally until the request fits, without deleting source text or adding requests. Explicit-rule requests are all checked before sending any chunk; genuinely oversized source text still requires a smaller chunk size.
- Semantic classification is not guaranteed. Long chunks use roughly 800–1,200-character units; an exclusion in a mixed unit drops the whole unit, potentially losing useful neighboring text. Compare with an unfiltered summary for important material.

Progress reports retained characters, requests, exclusions, fallbacks and elapsed time. Automated tests use mocked scores; live classification quality, cost and latency are not benchmarked.

## Contributing

```bash
git clone https://github.com/martinopiaggi/summarize.git && cd summarize
pip install -e ".[all]" pytest && pytest tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md). License: [MIT](LICENSE).