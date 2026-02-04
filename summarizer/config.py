"""Configuration management for the summarizer package."""

import os
import re
from typing import Dict, Optional
from dotenv import load_dotenv
from .exceptions import APIKeyError, ConfigurationError

# Load environment variables
load_dotenv()

# Default configuration
DEFAULT_CONFIG = {
    "type_of_source": "YouTube Video",
    "use_youtube_captions": True,
    "transcription_method": "Cloud Whisper",
    "language": "auto",
    "prompt_type": "Questions and answers",
    "chunk_size": 10000,
    "parallel_api_calls": 30,
    "max_output_tokens": 4096,
    "cobalt_base_url": "http://localhost:9000",
}

# API provider patterns - extensible mapping of URL patterns to env var names
API_PROVIDERS = {
    "generativelanguage.googleapis.com": "generativelanguage",
    "perplexity": "perplexity",
    "groq": "groq",
    "openai": "openai",
    "deepseek": "deepseek",
    "anthropic": "anthropic",
    "together": "together",
    "hyperbolic": "hyperbolic",
    "mistral": "mistral",
    "cohere": "cohere",
    "fireworks": "fireworks",
    "anyscale": "anyscale",
    "replicate": "replicate",
    "huggingface": "huggingface",
    "azure": "azure",
    "openrouter.ai": "openrouter",
}


def get_api_key(cfg: Dict) -> str:
    """
    Get API key from config or environment variables.

    Supports extensible provider matching - checks for the provider name
    in the base_url and looks up the corresponding environment variable.

    Args:
        cfg: Configuration dictionary containing 'base_url' and optionally 'api_key'

    Returns:
        The API key string

    Raises:
        APIKeyError: If no API key is found for the provider
    """
    # If API key is explicitly provided in config, use it
    if cfg.get("api_key"):
        return cfg["api_key"]

    base_url = cfg.get("base_url", "").lower()

    if not base_url:
        raise ConfigurationError("base_url is required but not provided")

    # Try to match provider from URL
    matched_key = None
    matched_provider = None

    for pattern, env_var in API_PROVIDERS.items():
        if pattern in base_url:
            matched_provider = pattern
            matched_key = os.getenv(env_var)
            if matched_key:
                break

    # Fallback: try to extract domain and use it as env var name
    if not matched_key:
        # Extract domain from URL for fallback lookup
        domain_match = re.search(r"https?://(?:api\.)?([^./]+)", base_url)
        if domain_match:
            domain_name = domain_match.group(1)
            matched_key = os.getenv(domain_name)
            matched_provider = domain_name

    # Try generic api_key as last resort
    if not matched_key:
        matched_key = os.getenv("api_key")
        matched_provider = "generic"

    if not matched_key:
        available_providers = ", ".join(API_PROVIDERS.keys())
        raise APIKeyError(
            f"No API key found for base_url: {cfg.get('base_url')}\n"
            f"Set one of these in your .env file: {available_providers}\n"
            f"Or provide --api-key directly"
        )

    return matched_key


def validate_config(cfg: Dict) -> None:
    """
    Validate the configuration dictionary.

    Args:
        cfg: Configuration dictionary to validate

    Raises:
        ConfigurationError: If required parameters are missing
    """
    required_keys = ["base_url", "model", "source_url_or_path"]

    for key in required_keys:
        if not cfg.get(key):
            raise ConfigurationError(f"Missing required configuration: {key}")

    # Validate chunk size
    chunk_size = cfg.get("chunk_size", DEFAULT_CONFIG["chunk_size"])
    if chunk_size < 500:
        raise ConfigurationError("chunk_size must be at least 500 characters")

    # Validate parallel calls
    parallel_calls = cfg.get("parallel_api_calls", DEFAULT_CONFIG["parallel_api_calls"])
    if parallel_calls < 1 or parallel_calls > 100:
        raise ConfigurationError("parallel_api_calls must be between 1 and 100")
