"""Config file support for the summarizer package."""
import os
from pathlib import Path
from typing import Dict, Optional, Any
from .exceptions import ConfigurationError


def find_config_file() -> Optional[Path]:
    """
    Find the config file in standard locations.
    
    Search order:
    1. ./summarizer.yaml (current directory)
    2. ~/.summarizer.yaml (home directory)
    3. ~/.config/summarizer/config.yaml (XDG style)
    
    Returns:
        Path to config file or None if not found
    """
    locations = [
        Path.cwd() / "summarizer.yaml",
        Path.cwd() / "summarizer.yml",
        Path.home() / ".summarizer.yaml",
        Path.home() / ".summarizer.yml",
        Path.home() / ".config" / "summarizer" / "config.yaml",
        Path.home() / ".config" / "summarizer" / "config.yml",
    ]
    
    for path in locations:
        if path.exists():
            return path
    
    return None


def load_config_file(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        path: Optional explicit path to config file
        
    Returns:
        Configuration dictionary
    """
    if path is None:
        path = find_config_file()
    
    if path is None:
        return {}
    
    try:
        import yaml
    except ImportError:
        # YAML is optional - fail silently if not installed
        return {}
    
    # If an explicit path is provided but doesn't exist, return empty dict
    if not path.exists():
        return {}
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)
            config = loaded if loaded is not None else {}
        return config
    except Exception as e:
        raise ConfigurationError(f"Failed to load config file {path}: {str(e)}")


def get_provider_config(config: Dict, provider_name: str) -> Dict[str, Any]:
    """
    Get configuration for a specific provider.
    
    Args:
        config: Full config dictionary
        provider_name: Name of the provider (e.g., 'groq', 'gemini')
        
    Returns:
        Provider-specific config dictionary
    """
    providers = config.get("providers", {})
    
    if provider_name not in providers:
        available = list(providers.keys())
        if available:
            raise ConfigurationError(
                f"Unknown provider: '{provider_name}'. "
                f"Available: {', '.join(available)}"
            )
        else:
            raise ConfigurationError(
                f"No providers configured. Add providers to your config file."
            )
    
    return providers[provider_name]


def merge_configs(file_config: Dict, cli_args: Dict) -> Dict:
    """
    Merge file config with CLI arguments.
    CLI arguments take precedence.
    
    Args:
        file_config: Configuration from file
        cli_args: Configuration from CLI arguments
        
    Returns:
        Merged configuration dictionary
    """
    # Start with defaults
    merged = {
        "chunk_size": 10000,
        "parallel_api_calls": 30,
        "max_output_tokens": 4096,
        "prompt_type": "Questions and answers",
        "language": "auto",
        "transcription_method": "Cloud Whisper",
        "output_dir": "summaries",
    }
    
    # Apply file config defaults
    defaults = file_config.get("defaults", {})
    for key, value in defaults.items():
        # Convert kebab-case to snake_case
        snake_key = key.replace("-", "_")
        merged[snake_key] = value
    
    # Apply provider config if specified
    provider_name = cli_args.get("provider") or file_config.get("default_provider")
    if provider_name:
        try:
            provider_config = get_provider_config(file_config, provider_name)
            merged["base_url"] = provider_config.get("base_url")
            merged["model"] = provider_config.get("model")
            # Provider-specific defaults
            for key, value in provider_config.items():
                if key not in ("base_url", "model"):
                    merged[key.replace("-", "_")] = value
        except ConfigurationError:
            pass  # Will be caught later if required
    
    # CLI args override everything (skip None values)
    for key, value in cli_args.items():
        if value is not None:
            merged[key] = value
    
    return merged


def create_example_config() -> str:
    """
    Generate example config file content.
    
    Returns:
        YAML string with example configuration
    """
    return '''# Summarizer Configuration
# Save as ~/.summarizer.yaml or ./summarizer.yaml

# Default provider to use when --provider is not specified
default_provider: groq

# Provider configurations
providers:
  groq:
    base_url: https://api.groq.com/openai/v1
    model: llama-3.3-70b-versatile
  
  gemini:
    base_url: https://generativelanguage.googleapis.com/v1beta/openai
    model: gemini-2.5-flash-lite
  
  deepseek:
    base_url: https://api.deepseek.com/v1
    model: deepseek-chat
  
  openai:
    base_url: https://api.openai.com/v1
    model: gpt-4o-mini

# Default settings (can be overridden by CLI)
defaults:
  prompt-type: Questions and answers
  chunk-size: 10000
  parallel-calls: 30
  max-tokens: 4096
  output-dir: summaries
'''
