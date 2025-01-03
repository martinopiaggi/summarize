def get_api_key(cfg: dict) -> str:
    """Get API key from direct config or environment"""
    # If API key provided directly in config, use it
    if "api_key" in cfg:
        return cfg["api_key"]
    
    # Get from environment based on URL pattern
    if "deepseek" in cfg["base_url"].lower():
        api_key = os.getenv("deepseek_key")
    elif "groq" in cfg["base_url"].lower():
        api_key = os.getenv("api_key_groq")
    elif "openai" in cfg["base_url"].lower():
        api_key = os.getenv("api_key_openai")
    else:
        # Default to api_key
        api_key = os.getenv("api_key")
    
    if not api_key:
        raise ValueError(
            "API key not found. Either:\n"
            "1. Provide via --api-key parameter, or\n"
            "2. Set in .env file as:\n"
            "   - deepseek_key for Deepseek API\n"
            "   - api_key_groq for Groq API\n"
            "   - api_key_openai for OpenAI API\n"
            "   - api_key for other endpoints"
        )
    
    return api_key