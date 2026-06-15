# Summarize Clipboard for Raycast

Send the current clipboard content to the [Summarize](https://github.com/martinopiaggi/summarize) HTTP API and view the result in Raycast.

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

2. Open Raycast Preferences → Extensions → Summarize Clipboard.
3. Set the **Summarize API Endpoint** (default: `http://localhost:8000`).
4. Optionally set a **Provider** and **Prompt Type**.

## Usage

1. Copy a video URL to the clipboard.
2. Run the **Summarize Clipboard** command in Raycast.
3. The summary appears in a detail view. Copy or paste it with the action buttons.

## Development

```bash
cd extensions/raycast-summarize
npm install
npm run dev
```

Use `npm run build` to validate the extension before publishing or importing into Raycast.
