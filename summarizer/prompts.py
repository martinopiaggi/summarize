"""Prompt template management for the summarizer package."""
import os
import json
from typing import Dict
from .exceptions import ConfigurationError

# Cache for loaded prompts
_prompts_cache: Dict[str, str] = {}


def load_prompts() -> Dict[str, str]:
    """
    Load all prompt templates from prompts.json.
    
    Returns:
        Dictionary of prompt_type -> template
    """
    global _prompts_cache
    
    if _prompts_cache:
        return _prompts_cache
    
    try:
        path = os.path.join(os.path.dirname(__file__), "prompts.json")
        with open(path, encoding="utf-8") as f:
            _prompts_cache = json.load(f)
        return _prompts_cache
    except FileNotFoundError:
        raise ConfigurationError("prompts.json not found in summarizer package")
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in prompts.json: {str(e)}")


def load_prompt_template(prompt_type: str) -> str:
    """
    Load a specific prompt template.
    
    Args:
        prompt_type: Name of the prompt template to load
        
    Returns:
        Prompt template string
        
    Raises:
        ConfigurationError: If the prompt type is not found
    """
    prompts = load_prompts()
    
    if prompt_type not in prompts:
        available = ", ".join(prompts.keys())
        raise ConfigurationError(
            f"Unknown prompt type: '{prompt_type}'. "
            f"Available types: {available}"
        )
    
    return prompts[prompt_type]


def get_available_prompts() -> list:
    """
    Get list of available prompt types.
    
    Returns:
        List of prompt type names
    """
    return list(load_prompts().keys())
