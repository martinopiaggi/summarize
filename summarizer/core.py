"""Core functionality for video transcription and summarization."""
from typing import Dict, List, Optional, Tuple
import os
import re
import json
import tempfile
import asyncio
import aiohttp
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import pytubefix as pytube

# Load environment variables
load_dotenv()

# Default configuration
CONFIG = {
    "type_of_source": "YouTube Video",
    "use_youtube_captions": True,
    "transcription_method": "Cloud Whisper",
    "language": "auto",
    "prompt_type": "Questions and answers",
    "chunk_size": 10000,
    "parallel_api_calls": 30,
    "max_output_tokens": 4096
}

def get_api_key(cfg: Dict) -> str:
    """Get API key from config or environment."""
    if "api_key" in cfg:
        return cfg["api_key"]
    
    key_map = {
        "deepseek": "deepseek_key",
        "groq": "api_key_groq",
        "openai": "api_key_openai"
    }
    
    for service, env_key in key_map.items():
        if service in cfg["base_url"].lower():
            api_key = os.getenv(env_key)
            if api_key:
                return api_key
    
    api_key = os.getenv("api_key")
    if not api_key:
        raise ValueError("API key not found in config or environment")
    return api_key

def extract_youtube_id(url: str) -> str:
    """Extract YouTube video ID from URL."""
    regex = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(regex, url)
    if not match:
        raise ValueError("Could not extract YouTube video ID")
    return match.group(1)

def get_youtube_transcript(video_id: str, language: str = "en") -> str:
    """Get transcript from YouTube captions."""
    try:
        if language == "auto":
            language = "en"
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=[language])
        return "\n".join(f"{entry['text'].strip()}" for entry in transcript)
    except Exception as e:
        raise Exception(
            f"Failed to get YouTube transcript. Try using --force-download instead. Error: {str(e)}"
        )

def download_youtube_audio(url: str) -> str:
    """Download YouTube video audio."""
    try:
        yt = pytube.YouTube(url)
        stream = yt.streams.get_audio_only()
        
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "audio.mp4")
        
        stream.download(output_path=temp_dir, filename="audio.mp4")
        return temp_path
    except Exception as e:
        raise Exception(f"Failed to download YouTube audio: {str(e)}")

def transcribe_audio(audio_path: str, method: str = "Cloud Whisper") -> str:
    """Transcribe audio file."""
    try:
        if method == "Cloud Whisper":
            import openai
            with open(audio_path, "rb") as f:
                return openai.Audio.transcribe("whisper-1", f)["text"]
        elif method == "Local Whisper":
            import whisper
            model = whisper.load_model("base")
            return model.transcribe(audio_path)["text"]
        else:
            raise ValueError(f"Unknown transcription method: {method}")
    except Exception as e:
        raise Exception(f"Transcription failed: {str(e)}")

def chunk_text(text: str, chunk_size: int) -> List[str]:
    """Split text into chunks."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    
    for word in words:
        word_size = len(word) + 1
        if current_size + word_size > chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_size = word_size
        else:
            current_chunk.append(word)
            current_size += word_size
            
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    return chunks

def load_prompt_template(prompt_type: str) -> str:
    """Load prompt template."""
    try:
        path = os.path.join(os.path.dirname(__file__), "prompts.json")
        with open(path) as f:
            return json.load(f)[prompt_type]
    except Exception as e:
        raise Exception(f"Failed to load prompt template: {str(e)}")

async def process_chunk(chunk: str, template: str, config: Dict) -> str:
    """Process a single chunk using API."""
    headers = {
        "Authorization": f"Bearer {get_api_key(config)}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": "You are a helpful assistant specializing in video content analysis."},
            {"role": "user", "content": template.format(text=chunk)}
        ],
        "max_tokens": config["max_output_tokens"]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=data
        ) as response:
            if response.status != 200:
                raise Exception(f"API request failed: {await response.text()}")
            result = await response.json()
            return result["choices"][0]["message"]["content"]


async def process_chunk(chunk: str, template: str, config: Dict) -> str:
    """Process a single chunk using API."""
    # Ensure chunk is not empty and contains actual content
    if not chunk.strip():
        return ""
        
    headers = {
        "Authorization": f"Bearer {get_api_key(config)}",
        "Content-Type": "application/json"
    }
    
    processed_template = template.format(text=chunk.strip())
    
    data = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant specializing in video content analysis. Always provide direct responses based on the given transcript without asking for more content."
            },
            {
                "role": "user",
                "content": processed_template
            }
        ],
        "max_tokens": config["max_output_tokens"]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=data
        ) as response:
            if response.status != 200:
                raise Exception(f"API request failed: {await response.text()}")
            result = await response.json()
            content = result["choices"][0]["message"]["content"].strip()
            # Remove any "please provide text" responses
            if "please provide" in content.lower() or "please share" in content.lower():
                return ""
            return content

def chunk_text(text: str, chunk_size: int) -> List[str]:
    """Split text into chunks."""
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
            # Join with newlines to preserve formatting
            chunks.append('\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size
            
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
        
    # Ensure chunks are not too small
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

async def process_chunks(chunks: List[str], template: str, config: Dict) -> List[str]:
    """Process chunks in parallel."""
    tasks = []
    for chunk in chunks:
        if chunk.strip():  # Only process non-empty chunks
            task = asyncio.create_task(process_chunk(chunk, template, config))
            tasks.append(task)
            
    if not tasks:
        raise Exception("No valid content chunks to process")
        
    results = await asyncio.gather(*tasks)
    # Filter out empty results
    return [r for r in results if r.strip()]

def main(config: Dict) -> str:
    """Main processing function."""
    try:
        if config["type_of_source"] == "YouTube Video":
            video_id = extract_youtube_id(config["source_url_or_path"])
            if config.get("use_youtube_captions", True):
                transcript = get_youtube_transcript(
                    video_id,
                    config.get("language", "en")
                )
            else:
                audio_path = download_youtube_audio(config["source_url_or_path"])
                transcript = transcribe_audio(
                    audio_path,
                    config.get("transcription_method", "Cloud Whisper")
                )
                os.remove(audio_path)
                
        if not transcript.strip():
            raise Exception("No transcript content to process")
            
        chunks = chunk_text(transcript, config.get("chunk_size", 10000))
        if not chunks:
            raise Exception("Failed to create content chunks")
            
        template = load_prompt_template(config.get("prompt_type", "Questions and answers"))
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            summaries = loop.run_until_complete(
                process_chunks(chunks, template, config)
            )
            if not summaries:
                raise Exception("No valid summaries generated")
            return "\n\n".join(summaries)
        finally:
            loop.close()
            
    except Exception as e:
        raise Exception(f"Processing failed: {str(e)}")
