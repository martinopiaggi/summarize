"""FastAPI HTTP server for the summarizer package.

Exposes all CLI functionality via a REST API. Auto-generated docs at /docs.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from summarizer.config_file import load_config_file, merge_configs, find_config_file
from summarizer.core import main
from summarizer.exceptions import SummarizerError
from summarizer.prompts import get_available_prompts
from summarizer.api_utils import (
    build_runtime_config,
    format_output,
    SOURCE_TYPES,
    OUTPUT_FORMATS,
    TRANSCRIPTION_METHODS,
    WHISPER_MODELS,
    DEFAULT_MAX_UPLOAD_MB,
    redact_config_response,
)


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ──────────────────────────────────────────────────────────────────────────────

SourceType = Literal[tuple(SOURCE_TYPES)]  # type: ignore[misc]
OutputFormat = Literal[tuple(OUTPUT_FORMATS)]  # type: ignore[misc]
TranscriptionMethod = Literal[tuple(TRANSCRIPTION_METHODS)]  # type: ignore[misc]
WhisperModel = Literal[tuple(WHISPER_MODELS)]  # type: ignore[misc]


class SummarizeRequest(BaseModel):
    source: str = Field(..., description="Video URL or file path")
    type: SourceType = Field("YouTube Video", description="Source type")
    provider: Optional[str] = Field(None, description="Provider name from config")
    prompt_type: Optional[str] = Field(None, description="Summary style")
    chunk_size: Optional[int] = Field(
        None, ge=100, le=500_000, description="Characters per chunk"
    )
    parallel_calls: Optional[int] = Field(
        None, ge=1, le=200, description="Concurrent API requests"
    )
    max_tokens: Optional[int] = Field(
        None, ge=1, le=1_000_000, description="Max output tokens per chunk"
    )
    language: Optional[str] = Field(None, description="Caption/transcription language")
    output_language: Optional[str] = Field(None, description="Summary output language")
    force_download: bool = Field(False, description="Skip captions, download audio")
    transcription: Optional[TranscriptionMethod] = Field(
        None, description="Cloud Whisper or Local Whisper"
    )
    whisper_model: Optional[WhisperModel] = Field(None, description="Whisper model size")
    audio_speed: Optional[float] = Field(
        None, gt=0.0, le=10.0, description="Pre-transcription speed-up"
    )
    output_format: OutputFormat = Field("markdown", description="markdown, json, or html")
    visual: bool = Field(False, description="Send video directly to vision model")
    use_proxy: Optional[bool] = Field(None, description="Route through Webshare proxy")
    api_key: Optional[str] = Field(None, description="Override API key")
    base_url: Optional[str] = Field(None, description="Override API base URL")
    model: Optional[str] = Field(None, description="Override model name")
    cobalt_url: Optional[str] = Field(None, description="Cobalt base URL")
    verbose: bool = Field(False, description="Verbose progress output")


class SummarizeResponse(BaseModel):
    success: bool
    source: str
    summary: str
    format: str
    model: Optional[str] = None
    prompt_type: Optional[str] = None
    processing_time_seconds: float
    error: Optional[str] = None
    error_type: Optional[str] = None


class BatchRequest(BaseModel):
    sources: List[str] = Field(..., min_length=1, description="List of URLs or file paths")
    type: SourceType = Field("YouTube Video", description="Source type for all items")
    provider: Optional[str] = Field(None, description="Provider name from config")
    prompt_type: Optional[str] = Field(None, description="Summary style")
    chunk_size: Optional[int] = Field(
        None, ge=100, le=500_000, description="Characters per chunk"
    )
    parallel_calls: Optional[int] = Field(
        None, ge=1, le=200, description="Concurrent API requests"
    )
    max_tokens: Optional[int] = Field(
        None, ge=1, le=1_000_000, description="Max output tokens per chunk"
    )
    language: Optional[str] = Field(None, description="Caption/transcription language")
    output_language: Optional[str] = Field(None, description="Summary output language")
    force_download: bool = Field(False, description="Skip captions, download audio")
    transcription: Optional[TranscriptionMethod] = Field(
        None, description="Cloud Whisper or Local Whisper"
    )
    whisper_model: Optional[WhisperModel] = Field(None, description="Whisper model size")
    audio_speed: Optional[float] = Field(
        None, gt=0.0, le=10.0, description="Pre-transcription speed-up"
    )
    output_format: OutputFormat = Field("markdown", description="markdown, json, or html")
    visual: bool = Field(False, description="Send video directly to vision model")
    use_proxy: Optional[bool] = Field(None, description="Route through Webshare proxy")
    api_key: Optional[str] = Field(None, description="Override API key")
    base_url: Optional[str] = Field(None, description="Override API base URL")
    model: Optional[str] = Field(None, description="Override model name")
    cobalt_url: Optional[str] = Field(None, description="Cobalt base URL")
    verbose: bool = Field(False, description="Verbose progress output")


class BatchResult(BaseModel):
    source: str
    success: bool
    summary: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    processing_time_seconds: float


class BatchResponse(BaseModel):
    success_count: int
    total_count: int
    results: List[BatchResult]
    overall_processing_time_seconds: float


class ProviderInfo(BaseModel):
    name: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    chunk_size: Optional[int] = None


class ConfigResponse(BaseModel):
    default_provider: Optional[str] = None
    providers: Dict[str, Any]
    defaults: Dict[str, Any]
    config_file_path: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers
# ──────────────────────────────────────────────────────────────────────────────

SNAKE_OVERRIDES = {
    "provider": "provider",
    "api_key": "api_key",
    "base_url": "base_url",
    "model": "model",
    "prompt_type": "prompt_type",
    "chunk_size": "chunk_size",
    "parallel_calls": "parallel_api_calls",
    "max_tokens": "max_output_tokens",
    "language": "language",
    "output_language": "output_language",
    "transcription": "transcription_method",
    "whisper_model": "whisper_model",
    "audio_speed": "audio_speed",
    "cobalt_url": "cobalt_base_url",
    "use_proxy": "use_proxy",
    "visual": "visual",
}


def _build_overrides(req: SummarizeRequest) -> Dict[str, Any]:
    """Build a CLI-args-style dict from a request for merge_configs."""
    overrides: Dict[str, Any] = {}
    for field, target in SNAKE_OVERRIDES.items():
        value = getattr(req, field)
        if value is not None:
            overrides[target] = value
    return overrides


def _build_runtime_config_from_request(
    req: SummarizeRequest,
    source_override: Optional[str] = None,
    type_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Build runtime config from request, using the same merge path as CLI."""
    file_config = load_config_file()
    overrides = _build_overrides(req)
    merged = merge_configs(file_config, overrides)
    # Ensure per-request overrides win even when merge_configs is mocked in tests.
    merged.update(overrides)
    return build_runtime_config(
        merged=merged,
        source=source_override or req.source,
        type_of_source=type_override or req.type,
        verbose=req.verbose,
        force_download=req.force_download,
    )


def _error_response(
    source: str,
    output_format: str,
    elapsed: float,
    exc: Exception,
) -> SummarizeResponse:
    """Build a structured error response."""
    return SummarizeResponse(
        success=False,
        source=source,
        summary="",
        format=output_format,
        error=str(exc),
        error_type=exc.__class__.__name__,
        processing_time_seconds=round(elapsed, 2),
    )


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app factory
# ──────────────────────────────────────────────────────────────────────────────

def create_app(allow_origins: Optional[List[str]] = None) -> FastAPI:
    """Create the FastAPI application with configurable CORS origins.

    If ``allow_origins`` is not provided, origins are read from the
    ``SUMMARIZER_CORS_ORIGINS`` environment variable.
    """
    application = FastAPI(
        title="Summarize API",
        description="Transcribe and summarize videos from any source using any OpenAI-compatible LLM.",
        version="0.1.0",
    )

    if allow_origins is None:
        origins_env = os.getenv("SUMMARIZER_CORS_ORIGINS", "")
        if origins_env == "*":
            allow_origins = ["*"]
        else:
            allow_origins = [o.strip() for o in origins_env.split(",") if o.strip()]

    if allow_origins:
        # Credentials cannot be used with wildcard origins.
        allow_credentials = "*" not in allow_origins
        application.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @application.get("/health")
    async def health() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok", "service": "summarize"}

    @application.get("/providers")
    async def providers() -> List[ProviderInfo]:
        """List all configured providers from summarizer.yaml."""
        file_config = load_config_file()
        providers_cfg = file_config.get("providers", {})
        result = []
        for name, cfg in providers_cfg.items():
            result.append(ProviderInfo(
                name=name,
                base_url=cfg.get("base_url"),
                model=cfg.get("model"),
                chunk_size=cfg.get("chunk_size"),
            ))
        return result

    @application.get("/prompts")
    async def prompts() -> List[str]:
        """List all available summary prompt types."""
        return get_available_prompts()

    @application.get("/config")
    async def config() -> ConfigResponse:
        """Get the active merged configuration (sensitive keys redacted)."""
        file_config = load_config_file()
        safe_config = redact_config_response(file_config)
        defaults = safe_config.get("defaults", {})
        providers_cfg = safe_config.get("providers", {})
        default_provider = safe_config.get("default_provider")
        config_path = find_config_file()
        return ConfigResponse(
            default_provider=default_provider,
            providers=providers_cfg,
            defaults=defaults,
            config_file_path=config_path.as_posix() if config_path else None,
        )

    @application.post("/summarize", response_model=SummarizeResponse)
    async def summarize(req: SummarizeRequest) -> SummarizeResponse:
        """Summarize a video from a URL or file path."""
        start_time = time.time()

        try:
            config = _build_runtime_config_from_request(req)
            summary = await run_in_threadpool(main, config)
            formatted = format_output(
                summary,
                req.source,
                req.output_format,
                {"prompt_type": config.get("prompt_type", ""), "model": config.get("model", "")},
            )
            elapsed = time.time() - start_time

            return SummarizeResponse(
                success=True,
                source=req.source,
                summary=formatted,
                format=req.output_format,
                model=config.get("model"),
                prompt_type=config.get("prompt_type"),
                processing_time_seconds=round(elapsed, 2),
            )

        except SummarizerError as e:
            elapsed = time.time() - start_time
            return _error_response(req.source, req.output_format, elapsed, e)
        except Exception as e:
            elapsed = time.time() - start_time
            return _error_response(req.source, req.output_format, elapsed, e)

    @application.post("/summarize/upload", response_model=SummarizeResponse)
    async def summarize_upload(
        file: UploadFile = File(..., description="Video or text file to summarize"),
        type: Optional[str] = Form(None, description="Source type (auto-detected if omitted)"),
        provider: Optional[str] = Form(None),
        prompt_type: Optional[str] = Form(None),
        chunk_size: Optional[int] = Form(None),
        parallel_calls: Optional[int] = Form(None),
        max_tokens: Optional[int] = Form(None),
        language: Optional[str] = Form(None),
        output_language: Optional[str] = Form(None),
        force_download: bool = Form(False),
        transcription: Optional[str] = Form(None),
        whisper_model: Optional[str] = Form(None),
        audio_speed: Optional[float] = Form(None),
        output_format: str = Form("markdown"),
        visual: bool = Form(False),
        use_proxy: Optional[bool] = Form(None),
        api_key: Optional[str] = Form(None),
        base_url: Optional[str] = Form(None),
        model: Optional[str] = Form(None),
        cobalt_url: Optional[str] = Form(None),
        verbose: bool = Form(False),
    ) -> SummarizeResponse:
        """Summarize an uploaded file.

        Accepts video files (.mp4, .mp3, .wav, .m4a, .webm) or text files
        (.txt, .md, .vtt, .srt, .csv, .log, .rst, .html, .xml, .json).
        Text files bypass audio processing entirely.
        """
        start_time = time.time()
        tmp_path: Optional[str] = None

        # Determine source type from extension if not provided
        filename = file.filename or "upload"
        ext = Path(filename).suffix.lower()
        text_extensions = {
            ".txt", ".md", ".vtt", ".srt", ".csv",
            ".log", ".rst", ".html", ".xml", ".json",
        }
        detected_type = type or ("TXT" if ext in text_extensions else "Local File")

        try:
            # Stream upload to temp file in chunks to avoid loading large files into memory
            max_upload_bytes = DEFAULT_MAX_UPLOAD_MB * 1024 * 1024
            suffix = ext or ".bin"
            total_read = 0
            stream_chunk_size = 1024 * 1024  # 1 MB chunks

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="wb") as tmp:
                while True:
                    chunk = await file.read(stream_chunk_size)
                    if not chunk:
                        break
                    total_read += len(chunk)
                    if total_read > max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"File exceeds maximum upload size of {DEFAULT_MAX_UPLOAD_MB} MB",
                        )
                    tmp.write(chunk)
                tmp_path = tmp.name

            # Build request and config
            req = SummarizeRequest(
                source=tmp_path,
                type=detected_type,  # type: ignore[arg-type]
                provider=provider,
                prompt_type=prompt_type,
                chunk_size=chunk_size,
                parallel_calls=parallel_calls,
                max_tokens=max_tokens,
                language=language,
                output_language=output_language,
                force_download=force_download,
                transcription=transcription,  # type: ignore[arg-type]
                whisper_model=whisper_model,  # type: ignore[arg-type]
                audio_speed=audio_speed,
                output_format=output_format,  # type: ignore[arg-type]
                visual=visual,
                use_proxy=use_proxy,
                api_key=api_key,
                base_url=base_url,
                model=model,
                cobalt_url=cobalt_url,
                verbose=verbose,
            )
            config = _build_runtime_config_from_request(req, source_override=tmp_path, type_override=detected_type)
            summary = await run_in_threadpool(main, config)
            formatted = format_output(
                summary,
                filename,
                output_format,
                {"prompt_type": config.get("prompt_type", ""), "model": config.get("model", "")},
            )
            elapsed = time.time() - start_time

            return SummarizeResponse(
                success=True,
                source=filename,
                summary=formatted,
                format=output_format,
                model=config.get("model"),
                prompt_type=config.get("prompt_type"),
                processing_time_seconds=round(elapsed, 2),
            )

        except HTTPException:
            raise
        except SummarizerError as e:
            elapsed = time.time() - start_time
            return _error_response(filename, output_format, elapsed, e)
        except Exception as e:
            elapsed = time.time() - start_time
            return _error_response(filename, output_format, elapsed, e)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @application.post("/summarize/batch", response_model=BatchResponse)
    async def summarize_batch(req: BatchRequest) -> BatchResponse:
        """Summarize multiple sources in one request.

        Each source is processed sequentially. Results are returned in the same
        order as the input sources list.
        """
        overall_start = time.time()
        results: List[BatchResult] = []

        for source in req.sources:
            item_start = time.time()
            try:
                single_req = SummarizeRequest(
                    source=source,
                    type=req.type,
                    provider=req.provider,
                    prompt_type=req.prompt_type,
                    chunk_size=req.chunk_size,
                    parallel_calls=req.parallel_calls,
                    max_tokens=req.max_tokens,
                    language=req.language,
                    output_language=req.output_language,
                    force_download=req.force_download,
                    transcription=req.transcription,
                    whisper_model=req.whisper_model,
                    audio_speed=req.audio_speed,
                    output_format=req.output_format,
                    visual=req.visual,
                    use_proxy=req.use_proxy,
                    api_key=req.api_key,
                    base_url=req.base_url,
                    model=req.model,
                    cobalt_url=req.cobalt_url,
                    verbose=req.verbose,
                )
                config = _build_runtime_config_from_request(single_req)
                summary = await run_in_threadpool(main, config)
                formatted = format_output(
                    summary,
                    source,
                    req.output_format,
                    {"prompt_type": config.get("prompt_type", ""), "model": config.get("model", "")},
                )
                elapsed = time.time() - item_start
                results.append(BatchResult(
                    source=source,
                    success=True,
                    summary=formatted,
                    processing_time_seconds=round(elapsed, 2),
                ))
            except SummarizerError as e:
                elapsed = time.time() - item_start
                results.append(BatchResult(
                    source=source,
                    success=False,
                    error=str(e),
                    error_type=e.__class__.__name__,
                    processing_time_seconds=round(elapsed, 2),
                ))
            except Exception as e:
                elapsed = time.time() - item_start
                results.append(BatchResult(
                    source=source,
                    success=False,
                    error=f"Unexpected error: {str(e)}",
                    error_type=e.__class__.__name__,
                    processing_time_seconds=round(elapsed, 2),
                ))

        success_count = sum(1 for r in results if r.success)
        overall_elapsed = time.time() - overall_start

        return BatchResponse(
            success_count=success_count,
            total_count=len(req.sources),
            results=results,
            overall_processing_time_seconds=round(overall_elapsed, 2),
        )

    return application


# Default app instance used by uvicorn and production imports.
app = create_app()
