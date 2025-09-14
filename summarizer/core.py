"""Core functionality for video transcription and summarization."""
from typing import Any, Dict, List, Optional, Tuple
import os
import re
import json
import tempfile
import asyncio
import aiohttp
import subprocess
import logging
from pathlib import Path
from contextlib import contextmanager
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import pytubefix as pytube

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoSourceHandler:
    def __init__(self, source_path: str, temp_dir: Optional[str] = None):
        self.source_path = source_path
        self.temp_dir = temp_dir or tempfile.gettempdir()
        
    def get_processed_audio(self) -> Tuple[str, bool]:
        """Returns tuple of (processed_audio_path, should_delete)"""
        raise NotImplementedError
        
    def cleanup(self, file_path: str) -> None:
        if os.path.exists(file_path):
            os.remove(file_path)

def process_audio_file(input_path: str, output_path: str) -> None:
    """Convert audio to MP3 with reduced quality for API limits."""
    command = [
        'ffmpeg', '-y', '-i', input_path,
        '-ar', '8000',
        '-ac', '1',
        '-b:a', '16k',
        output_path
    ]
    subprocess.run(command, check=True, capture_output=True)

class LocalFileHandler(VideoSourceHandler):
    def get_processed_audio(self) -> Tuple[str, bool]:
        if not os.path.exists(self.source_path):
            raise FileNotFoundError(f"Local file not found: {self.source_path}")
            
        temp_wav = os.path.join(self.temp_dir, "local_audio.wav")
        convert_to_wav(self.source_path, temp_wav)
        processed_path = os.path.join(self.temp_dir, "local_processed.mp3")
        process_audio_file(temp_wav, processed_path)
        self.cleanup(temp_wav)
        
        return processed_path, True

class GoogleDriveHandler(VideoSourceHandler):
    def get_processed_audio(self) -> Tuple[str, bool]:
        try:
            from google.colab import drive
            drive.mount('/content/drive')
        except ImportError:
            raise ImportError("Google Drive operations require Google Colab environment")
            
        if not self.source_path.startswith('/content/drive'):
            self.source_path = f"/content/drive/MyDrive/{self.source_path}"
            
        if not os.path.exists(self.source_path):
            raise FileNotFoundError(f"File not found in Google Drive: {self.source_path}")
            
        temp_wav = os.path.join(self.temp_dir, "gdrive_audio.wav")
        convert_to_wav(self.source_path, temp_wav)
        processed_path = os.path.join(self.temp_dir, "gdrive_processed.mp3")
        process_audio_file(temp_wav, processed_path)
        self.cleanup(temp_wav)
        
        return processed_path, True

class DropboxHandler(VideoSourceHandler):
    def get_processed_audio(self) -> Tuple[str, bool]:
        import wget
        
        temp_video = os.path.join(self.temp_dir, "dropbox_video.mp4")
        wget.download(self.source_path, temp_video)
        
        temp_wav = os.path.join(self.temp_dir, "dropbox_audio.wav")
        convert_to_wav(temp_video, temp_wav)
        processed_path = os.path.join(self.temp_dir, "dropbox_processed.mp3")
        process_audio_file(temp_wav, processed_path)
        self.cleanup(temp_video)
        self.cleanup(temp_wav)
        
        return processed_path, True

def get_handler(source_type: str, source_path: str) -> VideoSourceHandler:
    handlers = {
        "Local File": LocalFileHandler,
        "Google Drive Video Link": GoogleDriveHandler,
        "Dropbox Video Link": DropboxHandler
    }
    
    handler_class = handlers.get(source_type)
    if not handler_class:
        raise ValueError(f"Unsupported source type: {source_type}")
        
    return handler_class(source_path)

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
    base_url = cfg.get("base_url", "").lower()
    if "openai" in base_url:
        key = os.getenv("openai")
    elif "groq" in base_url:
        key = os.getenv("groq")
    elif "perplexity" in base_url:
        key = os.getenv("perplexity")
    elif "generativelanguage" in base_url:
        key = os.getenv("generativelanguage")
    else:
        raise ValueError(f"No matching service found for base_url: {cfg.get('base_url')}")
    if not key:
        raise ValueError(f"API key not found in environment for base_url: {cfg.get('base_url')}")
    logger.info(f"Using API service: {cfg.get('base_url')}")
    return key



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
        return "\n".join(f"{format_timestamp(entry['start'])} {entry['text'].strip()}" for entry in transcript)
    except Exception as e:
        raise Exception(f"Failed to get YouTube transcript. Try using --force-download instead. Error: {str(e)}")

def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def download_youtube_audio(url: str) -> str:
    """Download YouTube video audio."""
    try:
        yt = pytube.YouTube(url)
        stream = yt.streams.get_audio_only()
        
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "audio.mp4")
        processed_path = os.path.join(temp_dir, "audio_processed.mp3")
        
        stream.download(output_path=temp_dir, filename="audio.mp4")
        process_audio_file(temp_path, processed_path)
        os.remove(temp_path)
        
        return processed_path
    except Exception as e:
        raise Exception(f"Failed to download YouTube audio: {str(e)}")

def transcribe_audio(audio_path: str, method: str = "Cloud Whisper") -> str:
    """Transcribe audio file."""
    try:
        if method == "Cloud Whisper":
            api_key = os.getenv("groq")
            if not api_key:
                raise ValueError("Groq API key not found in environment (set 'groq' in .env)")

            from groq import Groq
            groq_client = Groq(api_key=api_key)
            
            with open(audio_path, "rb") as audio_file:
                logger.info("Starting transcription with Groq API...")
                # Use text format directly as it's more reliable
                response = groq_client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3",
                    response_format="text",
                    language="en",  # Explicitly set language
                    temperature=0.0
                )
                
                # Since we're using text format, add a timestamp at the start
                timestamp = format_timestamp(0)
                transcript = f"{timestamp} {response.strip()}\n"
                
                return transcript
            
        elif method == "Local Whisper":
            try:
                import whisper
            except ImportError:
                logger.warning("Local Whisper not available")
                raise ImportError("Local Whisper package not installed")
            
            logger.info("Loading Whisper model...")
            model = whisper.load_model("base")
            logger.info("Transcribing with local Whisper...")
            result = model.transcribe(audio_path)
            
            transcript = ""
            for segment in result["segments"]:
                time = format_timestamp(segment["start"])
                transcript += f"{time} {segment['text'].strip()}\n"
                
            return transcript
        else:
            raise ValueError(f"Unknown transcription method: {method}")
    except Exception as e:
        raise Exception(f"Transcription failed: {str(e)}")

def get_transcript(config: dict) -> str:
    """Get transcript based on source type and configuration."""
    source_type = config.get("type_of_source")
    source_path = config.get("source_url_or_path")
    
    if not source_type or not source_path:
        raise ValueError("Source type and path/URL are required")
    
    if source_type == "YouTube Video":
        if config.get("use_youtube_captions", True):
            video_id = extract_youtube_id(source_path)
            return get_youtube_transcript(
                video_id,
                config.get("language", "en")
            )
        else:
            audio_path = download_youtube_audio(source_path)
            transcript = transcribe_audio(
                audio_path,
                config.get("transcription_method", "Cloud Whisper")
            )
            os.remove(audio_path)
            return transcript
    else:
        handler = get_handler(source_type, source_path)
        try:
            audio_path, should_delete = handler.get_processed_audio()
            transcript = transcribe_audio(
                audio_path,
                config.get("transcription_method", "Cloud Whisper")
            )
            if should_delete:
                os.remove(audio_path)
            return transcript
        except Exception as e:
            raise Exception(f"Failed to process {source_type}: {str(e)}")

def convert_to_wav(input_path: str, output_wav: str, ffmpeg_args: Optional[List[str]] = None) -> None:
    args = ['ffmpeg', '-y', '-i', input_path, '-vn']
    if ffmpeg_args:
        args.extend(ffmpeg_args)
    else:
        args.extend(['-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1'])
    args.append(output_wav)
    subprocess.run(args, check=True, capture_output=True)


def load_prompt_template(prompt_type: str) -> str:
    """Load prompt template."""
    try:
        path = os.path.join(os.path.dirname(__file__), "prompts.json")
        with open(path) as f:
            return json.load(f)[prompt_type]
    except Exception as e:
        raise Exception(f"Failed to load prompt template: {str(e)}")

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

async def process_chunk(chunk: str, template: str, config: Dict, max_retries: int = 3) -> str:
    """Process a single chunk using API."""
    if not chunk.strip():
        return ""

    # Validate required config parameters
    required_keys = ["api_key", "model", "base_url", "max_output_tokens"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config parameter: {key}")

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
                "content": ("You are a helpful assistant specializing in video content analysis. "
                            "Always provide direct responses based on the given transcript without asking for more content.")
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
                async with session.post(
                    f"{config['base_url']}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        if attempt < max_retries - 1:
                            logger.warning(f"API request failed (attempt {attempt + 1}/{max_retries}): {error_text}")
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            raise Exception(f"API request failed after {max_retries} attempts: {error_text}")

                    result = await response.json()
                    content = parse_response_content(result, config.get("base_url", ""))

                    # Only for Perplexity models we need to append citation URLs
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
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Error processing chunk (attempt {attempt + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Error processing chunk after {max_retries} attempts: {str(e)}")
                return ""


def format_youtube_timestamp(timestamp: str, url: str) -> str:
    """Convert timestamp to YouTube URL format."""
    try:
        hours, minutes, seconds = map(int, timestamp.split(':'))
        total_seconds = hours * 3600 + minutes * 60 + seconds
        return f"{timestamp} - {url}&t={total_seconds}"
    except:
        return timestamp

def extract_and_clean_chunks(text: str, chunk_size: int) -> List[Tuple[str, str]]:
    """Split text into chunks and extract timestamps."""
    timestamp_pattern = re.compile(r'(\d{2}:\d{2}:\d{2})')
    chunks = chunk_text(text, chunk_size)
    chunk_data = []
    
    for chunk in chunks:
        # Find first timestamp in chunk
        match = timestamp_pattern.search(chunk)
        timestamp = match.group(1) if match else ""
        
        # Store both timestamp and cleaned text
        chunk_data.append((timestamp, chunk.strip()))
        
    return chunk_data

async def process_chunks(chunks: List[Tuple[str, str]], template: str, config: Dict) -> List[Tuple[str, str]]:
    """Process chunks and preserve timestamps."""
    tasks = []
    semaphore = asyncio.Semaphore(config.get("parallel_api_calls", 5))
    
    async def process_with_semaphore(chunk_data: Tuple[str, str]) -> Tuple[str, str]:
        timestamp, chunk_text = chunk_data
        async with semaphore:
            summary = await process_chunk(chunk_text, template, config)
            return timestamp, summary
    
    for chunk_data in chunks:
        if chunk_data[1].strip():
            task = asyncio.create_task(process_with_semaphore(chunk_data))
            tasks.append(task)
            
    if not tasks:
        raise Exception("No valid content chunks to process")
    
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Chunk processing error: {result}")
            elif result[1] and result[1].strip():
                valid_results.append(result)
        return valid_results
    except Exception as e:
        logger.error(f"Error in gather: {str(e)}")
        return []

def format_summary_with_timestamps(summaries: List[Tuple[str, str]], config: Dict) -> str:
    """Format summaries with appropriate timestamp links."""
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

#Only for Perplexity models we need to remove CoT reasoning part delimited by <think> marker
def parse_response_content(response: Dict[str, Any], base_url: str) -> str:
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if "perplexity" in base_url.lower():
        marker = "</think>"
        idx = content.rfind(marker)
        if idx != -1:
            content = content[idx + len(marker):].strip()
        # Remove markdown code fences if present.
        if content.startswith("```json"):
            content = content[len("```json"):].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
    return content


def main(config: Dict) -> str:
    """Main processing function."""
    try:
        config["api_key"] = get_api_key(config)
        transcript = get_transcript(config)
        if not transcript or not transcript.strip():
            raise Exception("No transcript content to process")
            
        # Extract chunks with timestamps
        chunks = extract_and_clean_chunks(transcript, config.get("chunk_size", 10000))
        if not chunks:
            raise Exception("Failed to create content chunks")
            
        template = load_prompt_template(config.get("prompt_type", "Questions and answers"))
        
        # Use nest_asyncio if in notebook environment
        try:
            import nest_asyncio
            nest_asyncio.apply()
        except ImportError:
            pass
            
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            summaries = loop.run_until_complete(process_chunks(chunks, template, config))
            if not summaries:
                raise Exception("No valid summaries generated")
                
            return format_summary_with_timestamps(summaries, config)
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            
    except Exception as e:
        raise Exception(f"Processing failed: {str(e)}")