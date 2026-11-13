# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-11-13

### Added

- `Concise Tweets` summary style: turns a transcript into one tweet or a short series, in the compressed voice of Naval, levelsio, and other short-form X accounts
- Optional transcript sidecar for video URLs, with [TranscriptFetch](https://transcriptfetch.com) built in: `sidecar` and `sidecar-order` (`fallback` or `first`) in `summarizer.yaml`, `--sidecar` and `--sidecar-order` on the CLI, the same fields in the HTTP API, Streamlit settings that are saved to `summarizer.yaml`, and Raycast preferences. New sidecars are one module in `summarizer/sidecars/`. See [Transcript sidecar](https://summarize.martino.im/integrations/transcript-sidecar)

### Changed

- Streamlit interface: sentence-case labels and buttons, a text-only theme switch (the emoji rendered as missing glyphs), quiet outlined secondary actions, coral reserved for Run and active states, and the provider name, chunk size and parallel calls collapsed into one monospace slate instead of three uppercase captions

### Fixed

- Dark mode: checked sidebar boxes (e.g. "Visual mode") fill with the accent color again, so the dark check mark is visible instead of black on the dark panel
- Dark mode: the help (?) icons inside checkbox labels (e.g. next to "Visual mode") no longer disappear; the check-mark rule now only targets the box so the icons keep the muted text color
- Docs: links between sections of [summarize.martino.im](https://summarize.martino.im) no longer lead to 404 pages, the summary styles list no longer includes `DNA Extractor` (it never existed), and the documented Python requirement is 3.10+, matching the package

## [0.4.0] - 2026-09-27

### Added

- FILE tab: a "PASTE FROM CLIPBOARD" button above the uploader, plus a paste field that accepts Ctrl+V when the browser blocks clipboard reads. Pasted text always enters the pipeline as a plain `.txt` source, so a copied video URL is summarized as text rather than parsed as a video; a green status line under the button confirms each paste and stays visible (reporting which upload it replaced, or that nothing changed), and a blocked clipboard read reports the failure and asks for Ctrl+V

### Changed

- The summarization pipeline runs on a worker thread owned by the session. Toggling the theme (or any other widget) reruns the page but no longer aborts and loses an in-flight run; the rerun re-attaches to the running job and keeps streaming its progress.
- The sidebar starts collapsed, and the sidebar expand/collapse arrows use the accent color in light and dark mode
- The Streamlit result panel no longer shows a redundant COMPLETE banner; the status bar already says Complete and the summary is the signal that work finished

### Fixed

- Switching theme mid-run no longer duplicates the Processing status box: new and resumed jobs share one status renderer outside the URL/FILE tabs
- Dark-mode contrast for the expandable status bar (circular spinner + "Processing..."), which kept Streamlit's white summary background behind theme-colored text
- Dark-mode contrast for the header Stop button, which was dark text over the dark header
- Light-mode contrast for checkboxes (e.g. Visual mode), which were white over white

## [0.3.2] - 2026-09-25

### Changed

- Streamlit and Fern docs use the RaggioProietto palette, including matching dark surfaces, coral accents, and the header logo
- Streamlit theme control is a full-width Auto / Light / Dark segmented switch

### Fixed

- Dark-mode contrast for Streamlit widgets that Streamlit 1.64 no longer styles with the old selectors, including the file upload button, help tooltips, and primary buttons
- Fern docs contrast for the dark filled button and light-mode code comments, numbers, and strings

## [0.3.1] - 2026-09-22

### Fixed

- Dark-mode transcript field contrast. The field now uses the theme text and background colors.

## [0.3.0] - 2026-09-22

### Added

- Optional JEV transcript prefiltering, including include-only and exclude selection before the summary model
- Documentation page: [JEV Prefiltering](https://summarize.martino.im/features/jev-prefiltering)
- Streamlit OUTPUT and TRANSCRIPT tabs with download, clipboard, and Tinypaste actions for each result

### Changed

- Fern dark colors match the Streamlit dark theme

## [0.2.0] - 2026-06-28

### Added

- PyPI distribution as **`martino-summarize`** (`pipx install martino-summarize`; CLI command remains `summarizer`)
- Published Docker image at `ghcr.io/martinopiaggi/summarize`
- `pyproject.toml` for modern Python packaging
- `CONTRIBUTING.md`and GitHub issue/PR templates
- PyPI and GHCR publish workflows (triggered by GitHub Releases)

### Changed

- Default documented install path: Docker pull → `pipx install` → clone for contributors
- Version bumped from `0.1.0` to `0.2.0`

### Notes

- No breaking changes to `summarizer.core.main()` or `summarizer.yaml` config schema
- `brew install summarize` installs [steipete/summarize](https://github.com/steipete/summarize), not this project

## [0.1.0] - prior releases

Initial public development: multi-source video ingest, transcript + visual summarization paths, CLI, FastAPI, Streamlit, Docker, Raycast extension, and agent skill.

[0.5.0]: https://github.com/martinopiaggi/summarize/releases/tag/v0.5.0
[0.4.0]: https://github.com/martinopiaggi/summarize/releases/tag/v0.4.0
[0.3.2]: https://github.com/martinopiaggi/summarize/releases/tag/v0.3.2
[0.3.1]: https://github.com/martinopiaggi/summarize/releases/tag/v0.3.1
[0.3.0]: https://github.com/martinopiaggi/summarize/releases/tag/v0.3.0
[0.2.0]: https://github.com/martinopiaggi/summarize/releases/tag/v0.2.0