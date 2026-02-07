---
name: Video Summarizer
description: Transcribe and summarize videos from YouTube, local files, Google Drive, and Dropbox using any OpenAI-compatible LLM provider via the CLI.
dependencies: python>=3.7, youtube-transcript-api, pytubefix, groq, openai, aiohttp, pyyaml, ffmpeg-python
---

## Overview

This skill transcribes and summarizes video content by running the `python -m summarizer` CLI tool. It handles YouTube (captions or audio), local files, Google Drive, and Dropbox. Transcripts are chunked, processed in parallel through an OpenAI-compatible LLM, and merged into a final summary.

**IMPORTANT: Always use the CLI command below. Never try to fetch, scrape, or download video URLs directly (e.g., with webfetch or curl). The CLI handles all downloading, transcription, and summarization internally.**

## Quick Start (Step-by-Step)

Follow these steps exactly:

**Step 1 -- Run the CLI:**

```bash
python -m summarizer --source "VIDEO_URL"
```

The tool uses the default provider from `summarizer.yaml` (already configured). No extra flags needed for basic usage.

**Step 2 -- Read the output file:**

The CLI prints the output filename on success. It is always saved inside the `summaries/` subdirectory relative to the project working directory. For example:

```
[+] Saved watch_20260207_234533.md
```

The full path to read is: `summaries/watch_20260207_234533.md`

**Step 3 -- Show the result to the user.**

That's it. Three steps.

## Where Files Live

All paths are relative to the **project working directory** (where `summarizer.yaml` and `setup.py` are).

| File | Location |
|------|----------|
| Config | `./summarizer.yaml` |
| API keys | `./.env` |
| Prompt templates | `./summarizer/prompts.json` |
| Output summaries | `./summaries/<filename>.md` |
| CLI entry point | `python -m summarizer` |

Do NOT look for `.env` or config files in your home directory or in the skill directory. They are in the project root.

## CLI Reference

```
python -m summarizer [OPTIONS]
```

### Required

| Flag | Description |
|------|-------------|
| `--source` | One or more video URLs or file paths |

### Provider Options

| Flag | Description | Default |
|------|-------------|---------|
| `--provider` | Named provider from `summarizer.yaml` | `default_provider` from YAML |
| `--base-url` | API endpoint URL (overrides provider) | From YAML |
| `--model` | Model identifier (overrides provider) | From YAML |
| `--api-key` | API key (overrides `.env` auto-matching) | Auto from `.env` |

### Source Options

| Flag | Description | Default |
|------|-------------|---------|
| `--type` | `YouTube Video`, `Video URL`, `Local File`, `Google Drive Video Link`, `Dropbox Video Link` | `YouTube Video` |
| `--force-download` | Skip YouTube captions, download audio instead | `False` |
| `--transcription` | `Cloud Whisper` (Groq API) or `Local Whisper` | `Cloud Whisper` |
| `--whisper-model` | `tiny`, `base`, `small`, `medium`, `large` | `tiny` |
| `--language` | Language code for captions (e.g., `en`, `it`, `es`) | `auto` |

### Processing Options

| Flag | Description | Default |
|------|-------------|---------|
| `--prompt-type` | Summary style (see Styles below) | From YAML defaults |
| `--chunk-size` | Characters per text chunk | From YAML defaults |
| `--parallel-calls` | Concurrent API requests | `30` |
| `--max-tokens` | Max output tokens per chunk | `4096` |

### Output Options

| Flag | Description | Default |
|------|-------------|---------|
| `--output-dir` | Directory to save summaries | `summaries` |
| `--output-format` | `markdown`, `json`, or `html` | `markdown` |
| `--no-save` | Print to stdout only, don't save file | `False` |
| `--verbose`, `-v` | Detailed progress output | `False` |

**Warning:** Do NOT use `--no-save` on Windows. There is a known encoding bug where Unicode characters in the summary crash stdout output. Always let the tool save to a file, then read the file.

### Config Options

| Flag | Description |
|------|-------------|
| `--config` | Path to config file (default: auto-detect) |
| `--no-config` | Ignore config file, use CLI args only |
| `--init-config` | Generate example `summarizer.yaml` and exit |

## Summary Styles

Use with `--prompt-type`. Defined in `summarizer/prompts.json`.

| Style | Purpose |
|-------|---------|
| `Questions and answers` | Q&A extraction from content |
| `Summarization` | Standard summary with title |
| `Distill Wisdom` | Ideas, quotes, and references extraction |
| `DNA Extractor` | Core truth distilled to 200 words max |
| `Fact Checker` | Claim verification with TRUE/FALSE/MISLEADING labels |
| `Tutorial` | Step-by-step instructions from content |
| `Research` | Deep analysis with broader context |
| `Reflections` | Philosophical extensions beyond what is said |
| `Mermaid Diagram` | Visual concept map in Mermaid.js syntax |
| `Essay Writing in Paul Graham Style` | 250-word essay in Paul Graham's style |
| `Only grammar correction with highlights` | Grammar cleanup with bold highlights |

## Examples

### Summarize a YouTube video (simplest form)

```bash
python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID"
# Output: summaries/watch_YYYYMMDD_HHMMSS.md
```

### Specify a provider

```bash
python -m summarizer --source "https://youtube.com/watch?v=VIDEO_ID" --provider gemini
# Output: summaries/watch_YYYYMMDD_HHMMSS.md
```

### Extract key insights with Distill Wisdom

```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --provider openrouter \
  --prompt-type "Distill Wisdom"
# Output: summaries/watch_YYYYMMDD_HHMMSS.md
```

### Fact-check video claims using Perplexity

```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://api.perplexity.ai" \
  --model "sonar-pro" \
  --prompt-type "Fact Checker"
# Output: summaries/watch_YYYYMMDD_HHMMSS.md
```

### Generate a Mermaid diagram from a lecture

```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --provider gemini \
  --prompt-type "Mermaid Diagram"
# Output: summaries/watch_YYYYMMDD_HHMMSS.md
```

### Summarize a local file

```bash
python -m summarizer \
  --type "Local File" \
  --source "./lecture.mp4" \
  --provider groq
# Output: summaries/lecture_YYYYMMDD_HHMMSS.md
```

### Batch-process multiple videos

```bash
python -m summarizer \
  --source "URL1" "URL2" "URL3" \
  --provider gemini \
  --prompt-type "Summarization"
# Output: one file per URL in summaries/
```

### Use without config file (all flags explicit)

```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=VIDEO_ID" \
  --base-url "https://openrouter.ai/api/v1" \
  --model "google/gemini-2.0-flash-exp:free" \
  --api-key "sk-or-v1-YOUR_KEY" \
  --prompt-type "Tutorial" \
  --no-config
# Output: summaries/watch_YYYYMMDD_HHMMSS.md
```

## Reading the Output

After running the CLI, **always read the output file from `summaries/`**:

```bash
# The CLI prints something like:
# [+] Saved watch_20260207_234533.md
#
# The file is at:
summaries/watch_20260207_234533.md
```

Use the Read tool on the full path: `summaries/<filename>` (relative to project root).

## Multi-Step Workflow

For comprehensive analysis, chain multiple styles on the same video:

1. Start with `Summarization` for a quick overview
2. Use `Distill Wisdom` to extract key insights
3. Run `Fact Checker` (ideally with Perplexity) to verify claims
4. Generate a `Mermaid Diagram` for visual reference

## Error Handling

- If no API key is found, the tool checks `.env` for a key matching the provider URL keyword
- If YouTube captions are unavailable, the tool falls back to audio download + Whisper transcription
- Use `--verbose` to see detailed progress and debug issues
- Cloud Whisper requires a Groq API key (free tier available)

## Configuration Files

All in the project working directory:

- **`summarizer.yaml`**: Provider definitions (base_url, model, chunk-size) and defaults
- **`.env`**: API keys, auto-matched by URL keyword (e.g., `generativelanguage = YOUR_KEY`)
- **`summarizer/prompts.json`**: Prompt templates using `{text}` as transcript placeholder

## Testing

```bash
python -m pytest tests/ -v
```
