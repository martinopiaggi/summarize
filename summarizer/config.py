"""Configuration management for the summarizer package."""

import os
import re
from typing import Dict, Iterable, Tuple
from dotenv import load_dotenv
from .exceptions import APIKeyError, ConfigurationError

# Load environment variables
load_dotenv()

# Default configuration
DEFAULT_CONFIG = {
    "type_of_source": "YouTube Video",
    "use_youtube_captions": True,
    "transcription_method": "Cloud Whisper",
    "audio_speed": 1.0,
    "language": "auto",
    "prompt_type": "Questions and answers",
    "chunk_size": 10000,
    "parallel_api_calls": 30,
    "max_output_tokens": 4096,
    "cobalt_base_url": os.getenv("COBALT_BASE_URL", "http://localhost:9000"),
    "cache_transcript": True,
    "visual": False,
    "visual_compression": "off",
    "visual_max_size_mb": None,
    "visual_max_duration_seconds": None,
    "visual_chunk_seconds": "auto",
    "visual_chunk_overlap_seconds": 0,
    "visual_synthesis": False,
    "visual_provider": None,
    "visual_input_mode": None,
}

# API provider patterns - extensible mapping of URL patterns to env var names.
# Keep lower-case aliases for existing .env files, and add conventional
# *_API_KEY names where providers commonly document them.
API_PROVIDERS = {
    "generativelanguage.googleapis.com": ("GOOGLE_API_KEY", "generativelanguage"),
    "integrate.api.nvidia.com": ("NVIDIA_API_KEY", "nvidia"),
    "nvidia": ("NVIDIA_API_KEY", "nvidia"),
    "perplexity": ("PERPLEXITY_API_KEY", "perplexity"),
    "groq": ("GROQ_API_KEY", "groq"),
    "openai": ("OPENAI_API_KEY", "openai"),
    "deepseek": ("DEEPSEEK_API_KEY", "deepseek"),
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic"),
    "together": ("TOGETHER_API_KEY", "together"),
    "hyperbolic": ("HYPERBOLIC_API_KEY", "hyperbolic"),
    "mistral": ("MISTRAL_API_KEY", "mistral"),
    "cohere": ("COHERE_API_KEY", "cohere"),
    "fireworks": ("FIREWORKS_API_KEY", "fireworks"),
    "anyscale": ("ANYSCALE_API_KEY", "anyscale"),
    "replicate": ("REPLICATE_API_KEY", "replicate"),
    "huggingface": ("HUGGINGFACE_API_KEY", "huggingface"),
    "azure": ("AZURE_API_KEY", "azure"),
    "openrouter.ai": ("OPENROUTER_API_KEY", "openrouter"),
}

LITELLM_PROVIDER_ENV_ALIASES = {
    "gemini": ("GOOGLE_API_KEY", "generativelanguage"),
}


def _unique_env_vars(candidates: Iterable[str]) -> Tuple[str, ...]:
    """Return env var names in first-seen order without duplicates."""
    seen = set()
    result = []
    for env_var in candidates:
        if env_var and env_var not in seen:
            seen.add(env_var)
            result.append(env_var)
    return tuple(result)


def _known_api_key_env_vars() -> Tuple[str, ...]:
    candidates = []
    for env_vars in API_PROVIDERS.values():
        candidates.extend(env_vars)
    candidates.append("api_key")
    return _unique_env_vars(candidates)


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

    # LiteLLM can read provider env vars automatically, but this app also
    # supports lower-case .env keys such as "groq" and "openrouter".
    if cfg.get("base_url") == "litellm":
        provider = cfg.get("model", "").split("/", 1)[0].lower()
        env_candidates = []
        if provider:
            env_candidates.extend([f"{provider.upper()}_API_KEY", provider])
        env_candidates.extend(LITELLM_PROVIDER_ENV_ALIASES.get(provider, ()))

        seen = set()
        for env_var in env_candidates:
            if env_var in seen:
                continue
            seen.add(env_var)
            api_key = os.getenv(env_var)
            if api_key:
                return api_key
        return "litellm"

    base_url = cfg.get("base_url", "").lower()

    if not base_url:
        raise ConfigurationError("base_url is required but not provided")

    # Try to match provider from URL
    matched_key = None
    matched_provider = None
    tried_env_vars = []

    for pattern, env_vars in API_PROVIDERS.items():
        if pattern in base_url:
            matched_provider = pattern
            provider_env_vars = (*env_vars, pattern)
            tried_env_vars.extend(provider_env_vars)
            for env_var in provider_env_vars:
                matched_key = os.getenv(env_var)
                if matched_key:
                    break
            break

    # Fallback: try to extract domain and use it as env var name
    if not matched_key:
        # Extract domain from URL for fallback lookup
        domain_match = re.search(r"https?://(?:api\.)?([^./]+)", base_url)
        if domain_match:
            domain_name = domain_match.group(1)
            tried_env_vars.append(domain_name)
            if matched_provider is None:
                matched_provider = domain_name
            matched_key = os.getenv(domain_name)

    # Try generic api_key as last resort
    if not matched_key:
        tried_env_vars.append("api_key")
        matched_key = os.getenv("api_key")

    if not matched_key:
        env_vars = _unique_env_vars(tried_env_vars) or _known_api_key_env_vars()
        available_env_vars = ", ".join(env_vars)
        provider_hint = (
            f"Matched provider: {matched_provider}\n"
            if matched_provider
            else ""
        )
        raise APIKeyError(
            f"No API key found for base_url: {cfg.get('base_url')}\n"
            f"{provider_hint}"
            f"Set one of these .env keys: {available_env_vars}\n"
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
