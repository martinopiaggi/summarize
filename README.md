# Video Summarizer

<p align="center">
    <img alt="sample" src="./summarize_sample.gif">
</p>

<p align="center">
  <a href="https://summarize.martino.im"><strong>Try the docs</strong></a> ·
  <a href="#quick-start">Run locally in 60s</a> ·
  <a href="https://github.com/martinopiaggi/summarize/stargazers"><img src="https://img.shields.io/github/stars/martinopiaggi/summarize?style=social" alt="GitHub stars"></a>
</p>

**Local-first multi-source video summarization** (YouTube, social, drives, files) with any OpenAI-compatible LLM, optional vision path, and NotebookLM-style workflows.

> **Not [steipete/summarize](https://github.com/steipete/summarize)** — This is a **self-hosted video pipeline** with transcript cache, Cobalt fallback, Streamlit workspace, and an agent skill. Steipete's project is a generic URL clipper. 

Bring your own API keys. Full docs live at [summarize.martino.im](https://summarize.martino.im).

## Quick Start 

You need any openai compatible API key in `.env` (for example [Groq](https://groq.com/) `GROQ_API_KEY` is free-tier friendly; `OPENAI_API_KEY` works with `--provider openai`).

```bash
pip install martino-summarize
summarizer --init-config
echo "GROQ_API_KEY=your_key_here" > .env
summarizer --source "https://www.youtube.com/watch?v=arj7oStGLkU"
```

The summary is saved to `summaries/watch_YYYYMMDD_HHMMSS.md`.

Install extras as needed:

```bash
pipx install "martino-summarize[server]"   # HTTP API
pipx install "martino-summarize[all]"     # server + whisper + litellm
```

### Quick Start (Docker)

```bash
git clone https://github.com/martinopiaggi/summarize.git
cd summarize
cp summarizer.example.yaml summarizer.yaml   # first time only
echo "GROQ_API_KEY=your_key_here" > .env     # or OPENAI_API_KEY, etc.
docker compose up -d
```

Open **http://localhost:8501**, paste a URL, and summarize.

Or pull the pre-built image:

```bash
docker pull ghcr.io/martinopiaggi/summarize:latest
```

`docker-compose.yml` mounts `.env`, `summarizer.yaml`, and `./summaries/` for persistence. Cobalt runs as a sidecar for TikTok, Instagram, and other yt-dlp fallbacks.

## Interfaces

| Interface | Command |
|-----------|---------|
| **Streamlit GUI** | `docker compose up -d` → `http://localhost:8501` |
| **CLI** | `summarizer --source <source>` |
| **HTTP API** | `summarizer serve` → `http://localhost:8000/docs` |
| **Docker** | `docker compose up -d` |
| **Agent Skill** | [`.agent/skills/summarize/SKILL.md`](./.agent/skills/summarize/SKILL.md) |
| **Raycast** | [`extensions/raycast-summarize/`](./extensions/raycast-summarize/) |

## Documentation

Full docs live at [summarize.martino.im](https://summarize.martino.im).

## How It Works

```text
               +--------------------+
               |  Video URL/Path    |
               +---------+----------+
                         |
                         v
               +---------+----------+
               |    Source Type?    |
               +---------+----------+
                         |
        +----------------+--------------------+
        | visual flag                         |
        v                                     v
+-------+--------+                  +---------+----------+
|  Visual Mode   |                  | Transcript Cache   |-------------> HIT ---+
|  base64 / url  |                  +---------+----------+                      |  
+-------+--------+                            | MISS                            |  
        |                                     |                                 |  
        |                                     v                                 |  
        |         +-------+ +-------+ +-------+ +-------+                       |  
        |         |YouTube| |yt-dlp | | Local | |Dropbox|                       |  
        |         |       | |X.com  | | File  | |G.Drive|                       |  
        |         |       | |TikTok | |       | |       |                       |  
        |         |       | |etc.   | |       | |       |                       |  
        |         +---+---+ +---+---+ +---+---+ +---+---+                       |  
        |             |         |         |         |                           |  
        |             v         v         |         |                           |  
        |         +----+---+  +--+---+    |         |                           |  
        |         |Captions|  |Cobalt|    |         |                           |  
        |         | Exist? |  +--+---+    |         |                           |  
        |         +---+----+         |    |         |                           |  
        |          Yes  No           |    |         |                           |  
        |          +----+            |    +--------+--------------+             |  
        |            |               |                            |             |  
        |            +-------------->|                            v             |  
        |                            |                   +--------+--------+    |  
        |                            |                   |     Whisper     |    |  
        |                            |                   |    endpoint?    |    |  
        |                            |                   +--------+--------+    |  
        |                            |                            |             |  
        |                            |                +-----------+-----------+ |  
        |                            |                |                       | |  
        |                            |                |  Cloud Whisper Local  | |  
        |                            |                |                       | |  
        |                            |                +----------+------------+ |  
        |                            |                           |              |  
        |                            +------------------------|--+              |  
        |                                                     v                 |  
        |                                               store in cache          |  
        |                                                     |                 |  
        |                                                     +-----------------+  
        |                                                     |                    
        |                                                     |         Transcript 
        |                                                     |                    
        |                                                     v                        
        |                                summarizer.yaml -> +------------+----------+
        |                                 prompts.json  ->  |    Prompt + LLM       |
        |                                                   |    Merge              |
        |                                                   +------------+----------+
        |                                                            |
        |                                                            v
        v                                                   +------------+----------+
+-------+--------+                                          |                       |
| Vision-capable |                                          |          Output       |
|     model      |----------------------------------------->+                       |
+-------+--------+                                          +-----------------------+
        ^ 
        | 
        +----- prompts.json
```

- **Transcript path** (default): downloads audio/video, transcribes with Whisper or captions, caches the transcript, then summarizes with an LLM.
- **Visual path** (`--visual`): sends the video directly to a vision-capable model, skipping transcription. Uses the same prompts, provider config, and `.env` keys as the transcript path. Supports `base64` chunks (default) and `url` passthrough for YouTube.

## Troubleshooting

- **yt-dlp / platform errors:** ensure Cobalt is running (`docker compose` includes it) or set `COBALT_BASE_URL`
- **Missing API key:** add the provider key to `.env` (see `summarizer.example.yaml` for provider names)
- **No config file:** run `summarizer --init-config` or pass `--base-url` and `--model` with `--no-config`

Full guide: [summarize.martino.im](https://summarize.martino.im) 

## Contributing

```bash
git clone https://github.com/martinopiaggi/summarize.git
cd summarize
pip install -e ".[all]"
pip install pytest
pytest tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md). 

## License

[MIT](LICENSE)
