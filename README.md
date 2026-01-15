# Video Transcript Summarizer

A tool to transcribe and summarize videos from various sources using AI. Supports YouTube, Google Drive, Dropbox, and local files.

How to use it ?

- **CLI** - Command line interface for batch processing and automation
- **Google Colab** - [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/martinopiaggi/summarize/blob/main/Summarize.ipynb) Interactive notebook with visual interface
- **(roadmap) Streamlit** - Web-based GUI for easy video summarization

https://github.com/user-attachments/assets/4641743a-2d0e-4b54-9f82-8195431db3cb

## Features

- **Multiple Video Sources**:
  - YouTube (with automatic caption support)
  - Google Drive
  - Dropbox
  - Local files

- **Flexible API Support**:
  - Works with any OpenAI-compatible API endpoint
  - Configurable models and parameters

- **Smart Processing**:
  - YouTube videos use captions by default (faster & free)
  - Falls back to audio download & transcription if needed
  - Non-YouTube sources always use audio download
  - Processes multiple videos in one command

- **Output Options**:
  - Summaries are automatically saved to markdown files
  - Each summary includes source URL and timestamp
  - Customizable output directory
  - Timestamped summaries

## CLI Installation

```bash
# Clone the repository
git clone https://github.com/martinopiaggi/summarize.git
cd summarize

# Install the package
pip install -e .
```

## CLI Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `--source` | One or more video sources (URLs or filenames) | Required |
| `--base-url` | API endpoint URL | Required |
| `--model` | Model to use | Required |
| `--api-key` | API key (or use .env) | Optional |
| `--type` | Source type | "YouTube Video" |
| `--force-download` | Skip captions, use audio | False |
| `--output-dir` | Save directory | "summaries" |
| `--no-save` | Don't save to files | False |
| `--prompt-type` | Summary style | "Questions and answers" |
| `--language` | Language code | "auto" |
| `--chunk-size` | **Input** text chunk size | 10000 |
| `--parallel-calls` | Parallel API calls | 30 |
| `--max-tokens` | Max **output** tokens for each chunk | 4096 |
| `--verbose`, `-v` | Enable detailed progress output | False |


## CLI Examples

- Basic (YouTube captions)
  - `python -m summarizer --source "https://www.youtube.com/watch?v=VIDEO_ID" --base-url "https://generativelanguage.googleapis.com/v1beta/openai" --model "gemini-2.5-flash-lite"`

- Multiple videos
  - `python -m summarizer --source "https://youtube.com/watch?v=ID1" "https://youtube.com/watch?v=ID2" --base-url "https://api.groq.com/openai/v1" --model "openai/gpt-oss-20b"`

- Force audio (skip captions)
  - `python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID" --base-url "https://api.deepseek.com/v1" --model "deepseek-chat" --force-download`

- Choose style
  - `python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID" --base-url "https://api.deepseek.com/v1" --model "deepseek-chat" --prompt-type "Distill Wisdom"`

- Verbose logs
  - `python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID" --base-url "https://api.deepseek.com/v1" --model "deepseek-chat" --verbose`

- Providers quick picks
  - OpenAI: `python -m summarizer --base-url "https://api.openai.com/v1" --model "gpt-5-nano-2025-08-07" --source "https://www.youtube.com/watch?v=VIDEO_ID"`
  - Groq: `python -m summarizer --base-url "https://api.groq.com/openai/v1" --model "openai/gpt-oss-20b" --source "https://www.youtube.com/watch?v=VIDEO_ID"`
  - Deepseek: `python -m summarizer --base-url "https://api.deepseek.com/v1" --model "deepseek-chat" --source "https://www.youtube.com/watch?v=VIDEO_ID"`
  - Hyperbolic (Llama): `python -m summarizer --base-url "https://api.hyperbolic.xyz/v1" --model "meta-llama/Llama-3.3-70B-Instruct" --source "https://www.youtube.com/watch?v=VIDEO_ID"`
  - Ollama (Local): `python -m summarizer --base-url "http://127.0.0.1:11434/v1" --model "qwen:32b" --api-key "ollama" --source "https://www.youtube.com/watch?v=VIDEO_ID"`

- Local files
  - `python -m summarizer --type "Local File" --base-url "https://api.deepseek.com/v1" --model "deepseek-chat" --source "./lecture.mp4" "./lecture2.mp4" "./lecture3.mp4"`
  - Ollama (Local): `python -m summarizer --type "Local File" --base-url "http://127.0.0.1:11434/v1" --model "qwen:32b" --api-key "ollama" --transcription "Local Whisper" --source "./video.mkv"`

- Long videos (bigger chunks)
  - `python -m summarizer --base-url "https://generativelanguage.googleapis.com/v1beta/openai" --model "gemini-2.5-flash-lite" --chunk-size 28000 --source "https://www.youtube.com/watch?v=VIDEO_ID"`

- Style + provider combo
  - Gemini + Distill: `python -m summarizer --base-url "https://generativelanguage.googleapis.com/v1beta/openai" --model "gemini-2.5-flash-lite" --prompt-type "Distill Wisdom" --source "https://www.youtube.com/watch?v=VIDEO_ID"`
  - Perplexity + Fact Check: `python -m summarizer --base-url "https://api.perplexity.ai" --model "sonar-pro" --prompt-type "Fact Checker" --chunk-size 100000 --source "https://www.youtube.com/watch?v=VIDEO_ID"`

## Summary Styles
Built-in templates live in [`summarizer/prompts.json`](https://github.com/martinopiaggi/summarize/blob/main/summarizer/prompts.json). Select with `--prompt-type "<Name>"`.
Tip: Names must match exactly as in prompts.json. Easily extend or add styles by editing that file, then pass the new name via `--prompt-type`.

## Using Ollama (Local Models)

You can use Ollama to run models locally without requiring cloud API keys:

1. **Install Ollama**: Follow instructions at [ollama.ai](https://ollama.ai)
2. **Pull a model**: `ollama pull qwen:32b` (or any model you prefer)
3. **Verify Ollama is running**: `ollama list`
4. **Use with the summarizer**:
   ```bash
   python -m summarizer \
     --base-url "http://127.0.0.1:11434/v1" \
     --model "qwen:32b" \
     --api-key "ollama" \
     --source "https://www.youtube.com/watch?v=VIDEO_ID"
   ```

**Note**: For local video files, you'll need transcription. Install Local Whisper with:
```bash
pip install openai-whisper
```

Then use:
```bash
python -m summarizer \
  --type "Local File" \
  --base-url "http://127.0.0.1:11434/v1" \
  --model "qwen:32b" \
  --api-key "ollama" \
  --transcription "Local Whisper" \
  --source "./your-video.mkv"
```

Popular Ollama models for summarization:
- `qwen:32b` - Good balance of quality and speed
- `llama3.2:latest` - Meta's Llama 3.2
- `deepseek-r1:32b` - DeepSeek R1 with reasoning
- `mistral:latest` - Mistral models

## Environment Setup

You can set default API keys in a `.env` file:
```env
api_key=your_default_api_key
```
This is an example of (**randomized api keys here**) of my `.env` : 

```ini
groq = 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
openai = sk-proj-HaW8cZ_9er50L3f5Q0Nkavu3EyAb1B1EyAb1BXf5Q0Nkavr
perplexity = pplx-Na7TCdZoKyEVqRpp2xWJtUmvh63HEyAb1BqnMWPYXsJg9
generativelanguage = AIzaSyAl9bTw6XUPqKdAVFYZNXDOCPlERcTfGPk
```
Keep in mind that you can always add new services and the script will automatically pick the correct key (matching based on keywords in the API URL).
Or provide them directly via --api-key parameter.
