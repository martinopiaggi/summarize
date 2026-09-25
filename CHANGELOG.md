# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.3.2]: https://github.com/martinopiaggi/summarize/releases/tag/v0.3.2
[0.3.1]: https://github.com/martinopiaggi/summarize/releases/tag/v0.3.1
[0.3.0]: https://github.com/martinopiaggi/summarize/releases/tag/v0.3.0
[0.2.0]: https://github.com/martinopiaggi/summarize/releases/tag/v0.2.0