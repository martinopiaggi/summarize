# Video Transcript Summarizer

A tool to transcribe and summarize videos from various sources using AI. Supports YouTube, Google Drive, Dropbox, and local files.

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
  - Uses YouTube captions when available (faster & free)
  - Falls back to audio download & transcription if needed
  - Processes multiple videos in one command

- **Output Options**:
  - Automatic saving to markdown files
  - Customizable output directory
  - Timestamped summaries

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/summarize.git
cd summarize

# Install the package
pip install -e .
```

## Usage Examples

1. **Basic Usage** (using YouTube captions):
```bash
python -m summarizer \
    --urls "https://www.youtube.com/watch?v=VIDEO_ID" \
    --base-url "https://api.deepseek.com/v1" \
    --model "deepseek-chat" \
    --api-key "your-api-key"
```

```bash
python -m summarizer --urls "./lecture.mp4" --type "Local File"  --base-url "https://api.deepseek.com/v1" --model "deepseek-chat"
```

2. **Process Multiple Videos**:
```bash
python -m summarizer \
    --urls "https://youtube.com/watch?v=ID1" "https://youtube.com/watch?v=ID2" \
    --base-url "https://api.deepseek.com/v1" \
    --model "deepseek-chat"
```

3. **Force Audio Download** (instead of captions):
```bash
python -m summarizer \
    --urls "https://youtube.com/watch?v=VIDEO_ID" \
    --base-url "https://api.deepseek.com/v1" \
    --model "deepseek-chat" \
    --force-download
```

4. **Custom Output Directory**:
```bash
python -m summarizer \
    --urls "https://youtube.com/watch?v=VIDEO_ID" \
    --base-url "https://api.deepseek.com/v1" \
    --model "deepseek-chat" \
    --output-dir "my_summaries"
```

5. **Different Summary Styles**:
```bash
python -m summarizer \
    --urls "https://youtube.com/watch?v=VIDEO_ID" \
    --base-url "https://api.deepseek.com/v1" \
    --model "deepseek-chat" \
    --prompt-type "Distill Wisdom"
```

## Other examples:

```bash
python -m summarizer --urls "https://www.youtube.com/watch?v=z5W74QC3v2I" --base-url "https://api.openai.com/v1" --model "gpt-4o"

python -m summarizer --urls "https://www.youtube.com/watch?v=z5W74QC3v2I" --base-url "https://api.deepseek.com/v1" --model "deepseek-chat"

python -m summarizer --urls "https://www.youtube.com/watch?v=z5W74QC3v2I" --base-url "https://api.hyperbolic.xyz/v1" --model "meta-llama/Llama-3.3-70B-Instruct"

python -m summarizer --urls "./lecture.mp4" "./lecture2.mp4" "./lecture3.mp4" --type "Local File"  --base-url "https://api.deepseek.com/v1" --model "deepseek-chat"
```


## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| --urls | One or more video URLs | Required |
| --base-url | API endpoint URL | Required |
| --model | Model to use | Required |
| --api-key | API key (or use .env) | Optional |
| --type | Source type | "YouTube Video" |
| --force-download | Skip captions, use audio | False |
| --output-dir | Save directory | "summaries" |
| --no-save | Don't save to files | False |
| --prompt-type | Summary style | "Questions and answers" |
| --language | Language code | "auto" |
| --chunk-size | Text chunk size | 10000 |
| --parallel-calls | Parallel API calls | 30 |
| --max-tokens | Max output tokens | 4096 |

## Summary Styles

1. **Summarization**: Concise overview
2. **Grammar Correction**: Cleaned transcript
3. **Distill Wisdom**: Key insights & quotes
4. **Q&A**: Key questions & answers
5. **Essay**: Paul Graham style essay

## Environment Setup

You can set default API keys in a `.env` file:
```env
api_key=your_default_api_key
```

Or provide them directly via --api-key parameter.

## Notes

- YouTube videos use captions by default (faster & free)
- Summaries are automatically saved to markdown files
- Each summary includes source URL and timestamp
- Non-YouTube sources always use audio download