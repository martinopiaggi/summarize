FROM python:3.12-slim

LABEL org.opencontainers.image.title="Summarizer"
LABEL org.opencontainers.image.description="Transcribe and summarize videos from YouTube, Instagram, TikTok, Twitter, and more"
LABEL org.opencontainers.image.source="https://github.com/martinopiaggi/summarize"

# Install system dependencies
# ffmpeg: required for audio/video processing (handlers.py, transcription.py)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition first for better layer caching
COPY setup.py .

# Install Python dependencies (non-editable install)
# We copy the package source before install since setup.py references it
COPY summarizer/ summarizer/
RUN pip install --no-cache-dir . "streamlit>=1.32.0"

# Copy application files
COPY app.py .
COPY .streamlit/ .streamlit/

# Create output directory
RUN mkdir -p /app/summaries

# Summaries volume for persisting output
VOLUME ["/app/summaries"]

# Streamlit default port
EXPOSE 8501

# Health check for container orchestrators (CasaOS, Portainer, etc.)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default: run Streamlit GUI
# Override with: docker run summarizer python -m summarizer --source "URL" ...
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
