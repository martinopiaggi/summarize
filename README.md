# Video Transcript Summarizer

Transcribe and summarize videos from YouTube, Instagram, TikTok, Twitter, Reddit, Facebook, Google Drive, Dropbox, and local files.

Requires an API key from any OpenAI-compatible LLM provider (OpenAI, Groq, Google AI, Deepseek, etc.).

## Processing Logic

1. **YouTube with captions available**: Uses existing captions directly (fast, no transcription needed, completely free)
2. **YouTube without captions or `--force-download`**: Downloads audio, then transcribes using Cloud Whisper (Groq API)
3. **Non-YouTube sources** (Instagram, TikTok, etc.): Always downloads audio via Cobalt, then transcribes
4. **Transcription method**: Default is Cloud Whisper (free Groq Whisper API with rate limits, requires free Groq API key). Alternative is Local Whisper (runs on your machine, no API needed)
5. **Text processing**: Transcript is split into chunks, each processed in parallel via LLM API
6. **Final output**: All chunk results are merged into a single summary markdown file

## Interfaces

| Interface | Command |
|-----------|---------|
| CLI | `python -m summarizer --source "URL" --base-url "..." --model "..."` |
| Streamlit GUI | `python -m streamlit run app.py` |

## Installation

**Requirements:**

- Python 3.10 or higher
- API key for at least one LLM provider (for summarization)
- Free Groq API key (for default Cloud Whisper transcription, or use Local Whisper instead)
- Docker (only required for non-YouTube platforms via Cobalt)


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
openrouter = YOUR_OPENROUTER_KEY
```

The script automatically matches API keys by searching for the provider keyword in the base URL. For example, `generativelanguage` matches `https://generativelanguage.googleapis.com/...`.

Override with `--api-key` flag.

## Summary Styles

Defined in `summarizer/prompts.json`. These are prompt templates that directly control the format and content of the final summary output.

Use the exact style name with `--prompt-type`.

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

**Custom styles**: Add your own by editing `prompts.json`. Use the `{text}` placeholder where the transcript should be injected into your prompt template.

## Non-YouTube Platforms (Cobalt)

Instagram, TikTok, Twitter, Reddit, and Facebook require Cobalt for video download. Cobalt runs as a Docker container that handles video extraction from these platforms.

Start Cobalt:
```bash
docker compose -f docker-compose.cobalt.yml up -d
```

The Cobalt API runs at `http://localhost:9000` by default. Edit `cobalt.env` to change port or other settings.

Usage:
```bash
python -m summarizer \
  --type "Video URL" \
  --source "https://www.instagram.com/reel/..." \
  --base-url "https://api.groq.com/openai/v1" \
  --model "openai/gpt-oss-20b"
```

## Local Whisper

Local Whisper runs the transcription model on your own machine instead of using the default Cloud Whisper (Groq API). This option requires no Groq API key but is slower unless you have a GPU.

**Default transcription method**: Cloud Whisper uses Groq's free Whisper API endpoint (`https://api.groq.com/openai/v1`) with rate limits. Requires a free Groq API key.

**Local Whisper alternative**: Runs OpenAI's Whisper model locally. No API key required, but needs more CPU/GPU resources.

Install Local Whisper with GPU support:
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

**Model sizes**: `tiny` (fastest, least accurate) → `base` → `small` → `medium` → `large` (slowest, most accurate)

**GPU detection**: Automatically uses CUDA GPU if available, otherwise falls back to CPU.


## CLI Examples

**YouTube with captions** (no transcription needed):
```bash
python -m summarizer \
  --source "https://www.youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://generativelanguage.googleapis.com/v1beta/openai" \
  --model "gemini-2.5-flash-lite"
```

**Multiple videos** (batch processing):
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=ID1" "https://youtube.com/watch?v=ID2" \
  --base-url "https://api.groq.com/openai/v1" \
  --model "openai/gpt-oss-20b"
```

**Force audio transcription** (downloads audio and transcribes even when captions exist):
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat" \
  --force-download
```

**Local video/audio files**:
```bash
python -m summarizer \
  --type "Local File" \
  --source "./lecture.mp4" "./lecture2.mp4" \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat"
```

**Long videos** (increase chunk size for models with larger context windows):
```bash
python -m summarizer \
  --source "https://www.youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://generativelanguage.googleapis.com/v1beta/openai" \
  --model "gemini-2.5-flash-lite" \
  --chunk-size 28000
```

**Custom summary style**:
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://api.deepseek.com/v1" \
  --model "deepseek-chat" \
  --prompt-type "Distill Wisdom"
```

### CLI Reference

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
| `--transcription` | Transcription method: `Cloud Whisper` (Groq API) or `Local Whisper` (on-device) | `Cloud Whisper` |
| `--whisper-model` | Local Whisper size: `tiny`, `base`, `small`, `medium`, `large` | `tiny` |
| `--verbose`, `-v` | Detailed output | `False` |
