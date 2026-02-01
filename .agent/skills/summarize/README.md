# Video Summarizer Skill

AI agent skill for transcribing and summarizing videos using various LLM providers.

## Quick Start

```bash
# 1. Get free API key from https://openrouter.ai/keys

# 2. Test it
python -m summarizer \
  --source "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
  --base-url "https://openrouter.ai/api/v1" \
  --model "google/gemini-2.0-flash-exp:free" \
  --api-key "sk-or-v1-YOUR_KEY"

# 3. Read result
cat summaries/watch_*.md
```

## Documentation

- **[SKILL.md](SKILL.md)** - Complete skill documentation for AI agents
- **[../../TESTING.md](../../TESTING.md)** - Testing guide with examples
- **[../../ROADMAP.md](../../ROADMAP.md)** - Future features and roadmap

## Features

- ✅ YouTube videos (captions or audio)
- ✅ Local video/audio files
- ✅ 11 summarization styles
- ✅ Multiple LLM providers (OpenRouter, Groq, Gemini, OpenAI, etc.)
- ✅ Batch processing
- ✅ Customizable output

## Supported Platforms

**Currently:**
- YouTube (videos, shorts)
- Google Drive videos
- Dropbox videos
- Local files (mp4, mp3, wav, m4a, webm)

**Coming Soon:**
- Instagram (via Cobalt)
- TikTok (via Cobalt)
- Twitter/X (via Cobalt)
- Reddit (via Cobalt)
- YouTube playlists

## Summarization Styles

1. Questions and Answers (default)
2. Summarization
3. Distill Wisdom
4. DNA Extractor
5. Research
6. Tutorial
7. Reflections
8. Fact Checker
9. Essay Writing in Paul Graham Style
10. Only grammar correction with highlights
11. Mermaid Diagram

## Testing

Run automated tests:

```bash
# Linux/Mac
export OPENROUTER_API_KEY='sk-or-v1-YOUR_KEY'
./test_skill.sh

# Windows
set OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY
test_skill.bat
```

See [TESTING.md](../../TESTING.md) for detailed testing guide.

## For AI Agents

This skill is designed to be used by AI agents. The [SKILL.md](SKILL.md) file contains:
- Complete CLI documentation
- All parameters and options
- Usage examples
- Multi-step workflow patterns
- Error handling
- Tips for optimization

AI agents can:
1. Call the CLI to generate summaries
2. Read output files from `summaries/` folder
3. Chain multiple styles for comprehensive analysis
4. Process multiple videos in batch

## Examples

**Extract key insights:**
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=xxx" \
  --base-url "https://openrouter.ai/api/v1" \
  --model "google/gemini-2.0-flash-exp:free" \
  --prompt-type "Distill Wisdom"
```

**Create tutorial:**
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=xxx" \
  --base-url "https://openrouter.ai/api/v1" \
  --model "google/gemini-2.0-flash-exp:free" \
  --prompt-type "Tutorial"
```

**Fact-check content:**
```bash
python -m summarizer \
  --source "https://youtube.com/watch?v=xxx" \
  --base-url "https://api.perplexity.ai" \
  --model "sonar-pro" \
  --prompt-type "Fact Checker"
```

## License

See main repository for license information.
