"""API interaction functionality for LLM summarization."""
import re
import asyncio
import aiohttp
import logging
from typing import Dict, List, Tuple, Any
from .exceptions import APIError, ConfigurationError
from .progress import ProgressBar, SimpleProgress, print_status

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int) -> List[str]:
    """
    Split text into chunks while preserving paragraph boundaries.
    
    Args:
        text: Text to split
        chunk_size: Maximum size of each chunk
        
    Returns:
        List of text chunks
    """
    # Ensure minimum chunk size
    if chunk_size < 1000:
        chunk_size = 1000
        
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = []
    current_size = 0
    
    for para in paragraphs:
        para_size = len(para) + 1
        if current_size + para_size > chunk_size and current_chunk:
            chunks.append('\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size
            
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
        
    # Merge small chunks
    merged_chunks = []
    temp_chunk = []
    temp_size = 0
    
    for chunk in chunks:
        if temp_size + len(chunk) < chunk_size/2:
            temp_chunk.append(chunk)
            temp_size += len(chunk)
        else:
            if temp_chunk:
                merged_chunks.append('\n'.join(temp_chunk))
            temp_chunk = [chunk]
            temp_size = len(chunk)
            
    if temp_chunk:
        merged_chunks.append('\n'.join(temp_chunk))
        
    return merged_chunks


def extract_and_clean_chunks(text: str, chunk_size: int) -> List[Tuple[str, str]]:
    """
    Split text into chunks and extract timestamps.
    
    Args:
        text: Text to split
        chunk_size: Maximum size of each chunk
        
    Returns:
        List of (timestamp, chunk_text) tuples
    """
    timestamp_pattern = re.compile(r'(\d{2}:\d{2}:\d{2})')
    chunks = chunk_text(text, chunk_size)
    chunk_data = []
    
    for chunk in chunks:
        match = timestamp_pattern.search(chunk)
        timestamp = match.group(1) if match else ""
        chunk_data.append((timestamp, chunk.strip()))
        
    return chunk_data


def parse_response_content(response: Dict[str, Any], base_url: str) -> str:
    """
    Parse response content from API, handling provider-specific formatting.
    
    Args:
        response: Raw API response
        base_url: API base URL for provider detection
        
    Returns:
        Cleaned content string
    """
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    
    # Handle Perplexity's chain-of-thought reasoning
    if "perplexity" in base_url.lower():
        marker = "</think>"
        idx = content.rfind(marker)
        if idx != -1:
            content = content[idx + len(marker):].strip()
        # Remove markdown code fences
        if content.startswith("```json"):
            content = content[len("```json"):].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
            
    return content


async def process_chunk(
    chunk: str, 
    template: str, 
    config: Dict, 
    max_retries: int = 3
) -> str:
    """
    Process a single chunk using the API.
    
    Args:
        chunk: Text chunk to process
        template: Prompt template with {text} placeholder
        config: Configuration with API details
        max_retries: Number of retry attempts
        
    Returns:
        Generated summary text
    """
    if not chunk.strip():
        return ""

    required_keys = ["api_key", "model", "base_url", "max_output_tokens"]
    for key in required_keys:
        if key not in config:
            raise ConfigurationError(f"Missing required config parameter: {key}")

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }

    processed_template = template.format(text=chunk.strip())

    data = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant specializing in video content analysis. "
                    "Always provide direct responses based on the given transcript without asking for more content."
                )
            },
            {
                "role": "user",
                "content": processed_template
            }
        ],
        "max_tokens": config["max_output_tokens"]
    }

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{config['base_url']}/chat/completions"

                async with session.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        if attempt < max_retries - 1:
                            logger.warning(f"API request failed (attempt {attempt + 1}/{max_retries}): {error_text}")
                            await asyncio.sleep(2 ** attempt)
                            continue
                        else:
                            raise APIError(f"API request failed after {max_retries} attempts: {error_text}")

                    result = await response.json()
                    content = parse_response_content(result, config.get("base_url", ""))

                    # Append citations for Perplexity models
                    citations = result.get("citations", [])
                    if citations:
                        sources_text = "\n\nSources:\n"
                        for idx, citation in enumerate(citations, start=1):
                            sources_text += f"{idx}. {citation}\n"
                        content += sources_text

                    if "please provide" in content.lower() or "please share" in content.lower():
                        return ""
                    return content

        except asyncio.CancelledError:
            return ""
        except APIError:
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Error processing chunk (attempt {attempt + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error(f"Error processing chunk after {max_retries} attempts: {str(e)}")
                return ""
    
    return ""


async def process_chunks(
    chunks: List[Tuple[str, str]], 
    template: str, 
    config: Dict
) -> List[Tuple[str, str]]:
    """
    Process all chunks in parallel with rate limiting.
    
    Args:
        chunks: List of (timestamp, chunk_text) tuples
        template: Prompt template
        config: Configuration dictionary
        
    Returns:
        List of (timestamp, summary) tuples
    """
    verbose = config.get("verbose", False)
    semaphore = asyncio.Semaphore(config.get("parallel_api_calls", 5))
    completed = [0]  # Using list to allow mutation in nested function

    # Initialize progress
    if verbose:
        progress = ProgressBar(len(chunks), "Processing chunks", 50)
    else:
        progress = SimpleProgress(len(chunks), "Summarizing")
        progress.start()

    async def process_with_semaphore(chunk_data: Tuple[str, str]) -> Tuple[str, str]:
        timestamp, chunk_text = chunk_data
        async with semaphore:
            summary = await process_chunk(chunk_text, template, config)
            completed[0] += 1
            if verbose:
                progress.update(completed[0])
            else:
                progress.update(completed[0])
            return timestamp, summary

    tasks = []
    for chunk_data in chunks:
        if chunk_data[1].strip():
            task = asyncio.create_task(process_with_semaphore(chunk_data))
            tasks.append(task)

    if not tasks:
        raise APIError("No valid content chunks to process")

    try:
        print_status(f"Processing {len(tasks)} chunks using {config.get('model', 'unknown model')}", "PROCESSING", verbose)
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Chunk processing error: {result}")
            elif result[1] and result[1].strip():
                valid_results.append(result)

        if not verbose:
            progress.finish(len(valid_results) > 0)
            
        print_status(f"Completed processing {len(valid_results)}/{len(tasks)} chunks", "SUCCESS", verbose)
        return valid_results
    except Exception as e:
        if not verbose:
            progress.finish(False)
        logger.error(f"Error in gather: {str(e)}")
        print_status(f"Error during chunk processing: {str(e)}", "ERROR", verbose)
        return []


def format_youtube_timestamp(timestamp: str, url: str) -> str:
    """Convert timestamp to YouTube URL format with deep link."""
    try:
        hours, minutes, seconds = map(int, timestamp.split(':'))
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return f"{timestamp} - {url}&t={total_seconds}"
    except:
        return timestamp


def format_summary_with_timestamps(summaries: List[Tuple[str, str]], config: Dict) -> str:
    """
    Format summaries with appropriate timestamp links.
    
    Args:
        summaries: List of (timestamp, summary) tuples
        config: Configuration dictionary
        
    Returns:
        Formatted summary string
    """
    formatted_pieces = []
    source_url = config.get("source_url_or_path", "")
    is_youtube = config.get("type_of_source") == "YouTube Video"
    
    for timestamp, summary in summaries:
        if timestamp:
            if is_youtube:
                timestamp_text = format_youtube_timestamp(timestamp, source_url)
            else:
                timestamp_text = timestamp
            formatted_pieces.append(f"{timestamp_text}\n\n{summary}")
        else:
            formatted_pieces.append(summary)
            
    return "\n\n".join(formatted_pieces)
