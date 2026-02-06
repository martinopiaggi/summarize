# Video Transcript Summarizer

Transcribe and summarize videos from YouTube, Instagram, TikTok, Twitter, Reddit, Facebook, Google Drive, Dropbox, and local files.

Works with any OpenAI-compatible LLM provider (even locally hosted).

## How It Works

```
               +--------------------+
               |  Video URL/Path    |
               +---------+----------+
                         |
                         v
               +---------+----------+
               |    Source Type?     |
               +---------+----------+
                         |
       +-----------------+-------------+
       |                 |             |
       |             X.com/IG     Local File
    YouTube           TikTok     Google Drive
       |                etc.       Dropbox
       |                 |             |
       v            +----+-----+       |
+------+----------+ | Cobalt   |       |
| Captions Exist? | +----+-----+       |
+----+----+-------+      |             |
    Yes   No             |             |
     |    +--------------+--------+----+
     |                            |
     |                            v
     |                   +--------+--------+
     |                   |     Whisper     |
     |                   |    endpoint?    |
     |                   +--------+--------+
     |                            |
     |                +-----------+-----------+
     |                |                       |
     |           Cloud Whisper          Local Whisper
     |                |                       |
     |                +----------+------------+
     |                           |
     +---------------------------+
                                 |
                            Transcript
                                 |
                                 v
                    +------------+----------+
 summarizer.yaml -> |    Prompt + LLM       |
 prompts.json    -> |    Merge              |
 .env            -> +------------+----------+
                                 |
                                 v
                          +------+-------+
                          |    Output    |
                          +--------------+
```

1. **Video URL/Path** enters the pipeline
2. **Source detection**: YouTube, x.com/Instagram/TikTok, or local file
3. **YouTube path**: Check captions → Use directly OR download audio
4. **Non-YouTube**: Cobalt downloads audio
5. **Transcription**: Cloud Whisper (Groq Cloud API) or Local Whisper
6. **Processing**: Apply prompt template → Parallel LLM → Merge results
7. **Output**: merge of chuncks and summary

**Configuration:**
- [`summarizer.yaml`](./summarizer.yaml): Provider settings (base_url, model, chunk-size) and defaults
- [`.env`](./.env): API keys matched by URL keyword
- [`prompts.json`](./summarizer/prompts.json): Summary style templates

**Notes:**
- Cloud Whisper uses **Groq Cloud API** (requires free Groq API key)
- Docker image does **not** include Local Whisper (designed for VPS deployment without GPU)

## Installation & Configuration

```bash
git clone https://github.com/martinopiaggi/summarize.git
cd summarize
pip install -e .
```

### Providers ([`summarizer.yaml`](./summarizer.yaml))

Define your LLM providers and defaults. CLI flags override everything.

```yaml
default_provider: gemini

providers:
  gemini:
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    model: gemini-2.5-flash-lite
    chunk-size: 128000

  groq:
    base_url: https://api.groq.com/openai/v1
    model: openai/gpt-oss-20b

  deepseek:
    base_url: https://api.deepseek.com/v1
    model: deepseek-chat

  openrouter:
    base_url: https://openrouter.ai/api/v1
    model: google/gemini-2.0-flash-001

defaults:
  prompt-type: Questions and answers
  chunk-size: 10000
  parallel-calls: 30
  max-tokens: 4096
  output-dir: summaries
```

### API Keys ([`.env`](./.env))

```ini
groq = gsk_YOUR_KEY
openai = sk-proj-YOUR_KEY
generativelanguage = YOUR_GOOGLE_KEY
deepseek = YOUR_DEEPSEEK_KEY
openrouter = YOUR_OPENROUTER_KEY
```

If you pass endpoint url with `--base-url` flag in CLI, the api key selected from `.env` is auto-matched by URL keyword: for example, `https://generativelanguage.googleapis.com/...` matches `generativelanguage`.

## Usage

### Streamlit GUI

```bash
python -m streamlit run app.py
```

Visit port 8501 .

### CLI

With a configured [`summarizer.yaml`](./summarizer.yaml), the CLI is simple:

```bash
# Uses default provider from YAML
python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID"

# Specify a provider
python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID" --provider groq

# Multiple videos
python -m summarizer --source "URL1" "URL2" "URL3"

# Local files
python -m summarizer --type "Local File" --source "./lecture.mp4"

# Non-YouTube (requires Cobalt running)
python -m summarizer --type "Video URL" --source "https://www.instagram.com/reel/..."

# Overrides defaults and specify a language
python -m summarizer --source "URL" --prompt-type "Distill Wisdom" --chunk-size 128000 --language "it"
```

Without YAML, pass `--base-url` and `--model` explicitly:

```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://generativelanguage.googleapis.com/v1beta/openai" \
  --model "gemini-2.5-flash-lite"
```

#### CLI Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--source` | Video URLs or file paths (multiple allowed) | Required |
| `--provider` | Provider name from YAML | `default_provider` |
| `--base-url` | API endpoint (overrides provider) | From YAML |
| `--model` | Model identifier (overrides provider) | From YAML |
| `--api-key` | API key (overrides [`.env`](./.env)) | - |
| `--type` | `YouTube Video`, `Video URL`, `Local File`, `Google Drive`, `Dropbox` | `YouTube Video` |
| `--prompt-type` | Summary style (see below) | `Questions and answers` |
| `--chunk-size` | Input text chunk size (chars) | `10000` |
| `--force-download` | Skip captions, download audio | `False` |
| `--transcription` | `Cloud Whisper` (Groq API) or `Local Whisper` (local) | `Cloud Whisper` |
| `--whisper-model` | `tiny`, `base`, `small`, `medium`, `large` | `tiny` |
| `--language` | Language code for captions from yt (often useful if Youtube can't found correct captions) | `auto` |
| `--parallel-calls` | Concurrent API requests | `30` |
| `--max-tokens` | Max output tokens per chunk | `4096` |
| `--output-dir` | Output directory | `summaries` |
| `--no-save` | Print only, no file output | `False` |
| `--verbose`, `-v` | Detailed output | `False` |

## Summary Styles

Defined in [`summarizer/prompts.json`](./summarizer/prompts.json). Use with `--prompt-type`.

| Style | Purpose |
|-------|---------|
| `Questions and answers` | Q&A extraction from content |
| `Summarization` | Standard summary with title |
| `Distill Wisdom` | Ideas, quotes, references extraction |
| `DNA Extractor` | Core truth in 200 words max |
| `Fact Checker` | Claim verification with sources |
| `Tutorial` | Step-by-step instructions |
| `Research` | Deep analysis with context |
| `Reflections` | Philosophical extensions |
| `Mermaid Diagram` | Visual concept map in Mermaid.js |
| `Essay Writing in Paul Graham Style` | 250-word essay |
| `Only grammar correction with highlights` | Text cleanup |

Add custom styles by editing [`prompts.json`](./summarizer/prompts.json). Use `{text}` as the transcript placeholder.

## Docker

```bash
git clone https://github.com/martinopiaggi/summarize.git
cd summarize
# Create [.env](./.env) with your API keys, then:
docker compose up -d
```

Open `http://localhost:8501` for the GUI. Summaries are saved to `./summaries/`.

CLI via Docker: `docker compose run --rm summarizer python -m summarizer --source "URL"`

Cobalt standalone: `docker compose -f docker-compose.cobalt.yml up -d`

## Local Whisper

Runs transcription on your machine instead of using Cloud Whisper (Groq API). No Groq API key needed, but slower without a GPU.

```bash
# Install with GPU support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Use it
python -m summarizer --source "URL" --force-download --transcription "Local Whisper" --whisper-model "small"
```

**Why not in Docker?** I decided to not include local whsiper in the Docker image because in VPS deployment, GPUs are typically unavailable. Local Whisper without GPU is too slow for production use. Use Cloud Whisper (Groq API, there is also free tier) in Docker, or install locally with GPU.

Model sizes: `tiny` (fastest) / `base` / `small` / `medium` / `large` (most accurate). GPU should be auto-detected.
