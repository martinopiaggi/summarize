"""Custom exceptions for the summarizer package."""


class SummarizerError(Exception):
    """Base exception for all summarizer errors."""
    pass


class TranscriptError(SummarizerError):
    """Raised when transcript extraction fails."""
    pass


class APIError(SummarizerError):
    """Raised when API requests fail."""
    pass


class APIKeyError(SummarizerError):
    """Raised when API key is missing or invalid."""
    pass


class ConfigurationError(SummarizerError):
    """Raised when configuration is invalid."""
    pass


class AudioProcessingError(SummarizerError):
    """Raised when audio processing fails."""
    pass


class SourceNotFoundError(SummarizerError):
    """Raised when the source file/URL is not found."""
    pass


class UnsupportedSourceError(SummarizerError):
    """Raised when the source type is not supported."""
    pass
