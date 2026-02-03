# Video Transcript Summarizer

Transcribe and summarize videos from YouTube, Instagram, TikTok, Twitter, Reddit, Facebook, Google Drive, Dropbox, and local files.

Requires an API key from any OpenAI-compatible LLM provider (OpenAI, Groq, Google AI, Deepseek, etc.).

## Requirements

- Python 3.10+
- API key for at least one LLM provider
- Docker (only for non-YouTube platforms via Cobalt)

## Interfaces

| Interface | Command |
|-----------|---------|
| CLI | `python -m summarizer --source "URL" --base-url "..." --model "..."` |
| Streamlit GUI | `python -m streamlit run app.py` |

## Installation

```bash
git clone https://github.com/martinopiaggi/summarize.git
cd summarize
pip install -e .
```

## Configuration

Two configuration methods. Both optional. CLI flags override everything.

### 1. YAML Configuration (`summarizer.yaml`)

Define providers and defaults:

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

defaults:
  prompt-type: Questions and answers
  chunk-size: 10000
  parallel-calls: 30
  max-tokens: 4096
  output-dir: summaries
```

Provider-specific `chunk-size` overrides global default.

### 2. Environment Variables (`.env`)

API keys auto-matched by URL keyword:

```ini
groq = gsk_YOUR_KEY
openai = sk-proj-YOUR_KEY
perplexity = pplx-YOUR_KEY
generativelanguage = YOUR_GOOGLE_KEY
deepseek = YOUR_DEEPSEEK_KEY
hyperbolic = YOUR_HYPERBOLIC_KEY
```

The script matches `generativelanguage` in `https://generativelanguage.googleapis.com/...` and uses that key.

Override with `--api-key` flag.

## CLI Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--source` | Video URLs or file paths (multiple allowed) | Required |
| `--base-url` | API endpoint | Required (unless in YAML) |
| `--model` | Model identifier | Required (unless in YAML) |
| `--api-key` | API key (overrides .env) | - |
| `--type` | Source type: `YouTube Video`, `Video URL`, `Local File`, `Google Drive`, `Dropbox` | `YouTube Video` |
| `--force-download` | Skip captions, download audio | `False` |
| `--output-dir` | Output directory | `summaries` |
| `--no-save` | Print only, no file output | `False` |
| `--prompt-type` | Summary style (see below) | `Questions and answers` |
| `--language` | Language code | `auto` |
| `--chunk-size` | Input text chunk size (chars) | `10000` |
| `--parallel-calls` | Concurrent API requests | `30` |
| `--max-tokens` | Max output tokens per chunk | `4096` |
| `--transcription` | `Cloud Whisper` or `Local Whisper` | `Cloud Whisper` |
| `--whisper-model` | Local Whisper size: `tiny`, `base`, `small`, `medium`, `large` | `tiny` |
| `--verbose`, `-v` | Detailed output | `False` |

## Summary Styles

Defined in `summarizer/prompts.json`. Use exact name with `--prompt-type`.

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

Add custom styles by editing `prompts.json`. Use `{text}` placeholder for transcript injection.

## Examples

YouTube (uses captions by default):
```bash
python -m summarizer \
  --source "https://www.youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://generativelanguage.googleapis.com/v1beta/openai" \
  --model "gemini-2.5-flash-lite"
```

Multiple videos:
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=ID1" "https://youtube.com/watch?v=ID2" \
  --base-url "https://api.groq.com/openai/v1" \
  --model "openai/gpt-oss-20b"
```

Force audio transcription (skip captions):
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat" \
  --force-download
```

Local files:
```bash
python -m summarizer \
  --type "Local File" \
  --source "./lecture.mp4" "./lecture2.mp4" \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat"
```

Long videos (increase chunk size):
```bash
python -m summarizer \
  --source "https://www.youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://generativelanguage.googleapis.com/v1beta/openai" \
  --model "gemini-2.5-flash-lite" \
  --chunk-size 28000
```

Specific style:
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat" \
  --prompt-type "Distill Wisdom"
```

## Non-YouTube Platforms (Cobalt)

Instagram, TikTok, Twitter, Reddit, Facebook require Cobalt for video download.

Start Cobalt:
```bash
docker compose -f docker-compose.cobalt.yml up -d
```

API available at `http://localhost:9000`. Edit `cobalt.env` to customize.

Usage:
```bash
python -m summarizer \
  --type "Video URL" \
  --source "https://www.instagram.com/reel/..." \
  --base-url "https://api.groq.com/openai/v1" \
  --model "openai/gpt-oss-20b"
```

## Local Whisper

For local transcription without cloud API.

Install with GPU support:
```bash
pip uninstall torch torchvision torchaudio -y
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

Verify GPU:
```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```

Usage:
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://api.openai.com/v1" \
  --model "gpt-4o" \
  --force-download \
  --transcription "Local Whisper" \
  --whisper-model "small"
```

Model sizes: `tiny` (fastest) < `base` < `small` < `medium` < `large` (most accurate).

GPU auto-detected. Falls back to CPU if unavailable.

## Processing Logic

1. YouTube with captions available: Uses captions (fast, free)
2. YouTube without captions or `--force-download`: Downloads audio, transcribes
3. Non-YouTube sources: Always downloads audio, transcribes
4. Transcript split into chunks, processed in parallel
5. Results merged into final summary
