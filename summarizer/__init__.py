"""Video Transcript Summarizer package."""
from .core import main, CONFIG
from .exceptions import (
    SummarizerError, TranscriptError, APIError, APIKeyError,
    ConfigurationError, AudioProcessingError, SourceNotFoundError
)

__version__ = "0.5.0"
__all__ = ["main", "CONFIG", "SummarizerError"]