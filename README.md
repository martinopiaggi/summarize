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

## Documentation

Full docs live at [summarize.martino.im](https://summarize.martino.im).

## License

[MIT](LICENSE)
