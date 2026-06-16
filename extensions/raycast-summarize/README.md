# Summarize for Raycast

Send a video URL to the [Summarize](https://github.com/martinopiaggi/summarize) HTTP API and view the result in Raycast.

Two ways to provide the URL:
- **Summarize** — type or paste the URL directly next to the command
- **Summarize Clipboard** — use the URL currently on your clipboard

## Requirements

- [Raycast](https://www.raycast.com/)
- A running Summarize HTTP API server (see main project README)

## Setup

1. Install the Summarize server extras and start the API:

   ```bash
   pip install -e ".[server]"
   python -m summarizer serve
   ```

   The default endpoint is `http://localhost:8000`.

2. Open Raycast Preferences → Extensions → Summarize.
3. Set the **Summarize API Endpoint** (default: `http://localhost:8000`).
4. Optionally set a **Provider** and **Prompt Type**.

## Usage

You have two options:

### Option 1: Paste URL directly (recommended)
1. Open Raycast and run **Summarize**.
2. Immediately type or paste the video URL in the input field shown next to the command.
3. Press Enter. The summary appears in a detail view.

### Option 2: Use clipboard
1. Copy a video URL to the clipboard.
2. Run the **Summarize Clipboard** command in Raycast.
3. The summary appears in a detail view.

In both cases, use the action buttons (or ⌘C / ⌘V) to copy or paste the summary.

## Development

```bash
cd extensions/raycast-summarize
npm install
npm run dev
```

Use `npm run build` to validate the extension before publishing or importing into Raycast.
