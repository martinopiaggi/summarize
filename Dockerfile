FROM python:3.12-slim

LABEL org.opencontainers.image.title="martino-summarize"
LABEL org.opencontainers.image.description="Local-first multi-source video summarization with any OpenAI-compatible LLM"
LABEL org.opencontainers.image.source="https://github.com/martinopiaggi/summarize"
LABEL org.opencontainers.image.url="https://summarize.martino.im"
LABEL org.opencontainers.image.licenses="MIT"

# Install system dependencies
# ffmpeg: required for audio/video processing (handlers.py, transcription.py)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition first for better layer caching
COPY pyproject.toml setup.py README.md ./

# Install Python dependencies (non-editable install)
COPY summarizer/ summarizer/
RUN pip install --no-cache-dir . "streamlit>=1.32.0"

# Copy application files
COPY app.py .
COPY webapp/ webapp/
COPY .streamlit/ .streamlit/

# Default config (summarizer.yaml is gitignored locally; ship example for first-run)
COPY summarizer.example.yaml ./summarizer.yaml

# Create output directory
RUN mkdir -p /app/summaries

# Volume for persisting output
VOLUME ["/app/summaries"]

# Streamlit default port
EXPOSE 8501

# Health check for container orchestrators (CasaOS, Portainer, etc.)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default: run Streamlit GUI
# Override with: docker run summarizer python -m summarizer --source "URL" ...
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
