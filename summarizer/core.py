"""Core functionality for video transcription and summarization."""
import os
import re
import json
import tempfile
import subprocess
import asyncio
import aiohttp
from typing import Dict, List, Tuple
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi
import pytubefix as pytube

load_dotenv()

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

def get_api_key(cfg: dict) -> str:
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
    regex = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})'
    match = re.search(regex, url)
    if not match:
        raise ValueError("Could not extract YouTube video ID")
    return match.group(1)

def get_youtube_transcript(video_id: str, language: str = "en") -> str:
    try:
        if language == "auto":
            language = "en"
        
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.get_transcript([language])
        except:
            for t in transcript_list:
                if t.is_translatable:
                    transcript = t.translate(language).fetch()
                    break
                    
        return "\n".join(f"{entry['text'].strip()}" for entry in transcript)
    except Exception as e:
        raise Exception(f"Transcript error: {str(e)}")

def download_youtube_audio(url: str) -> str:
    try:
        yt = pytube.YouTube(url)
        stream = yt.streams.get_audio_only()
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, "audio.mp4")
        stream.download(output_path=temp_dir, filename="audio.mp4")
        
        processed_path = os.path.join(temp_dir, "processed.mp3")
        subprocess.run([
            'ffmpeg', '-y', '-i', temp_path,
            '-ar', '16000', '-ac', '1',
            '-c:a', 'libmp3lame', '-b:a', '32k',
            processed_path
        ], check=True)
        
        os.remove(temp_path)
        return processed_path
    except Exception as e:
        raise Exception(f"Download error: {str(e)}")

def transcribe_audio(audio_path: str, method: str = "Cloud Whisper") -> str:
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
        raise Exception(f"Transcription error: {str(e)}")

def chunk_text(text: str, chunk_size: int) -> List[str]:
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
    try:
        path = os.path.join(os.path.dirname(__file__), "prompts.json")
        with open(path) as f:
            return json.load(f)[prompt_type]
    except Exception as e:
        raise Exception(f"Template error: {str(e)}")

async def process_chunk(chunk: str, template: str, config: dict) -> str:
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
                raise Exception(f"API error: {await response.text()}")
            return (await response.json())["choices"][0]["message"]["content"]

async def process_chunks(chunks: List[str], template: str, config: dict) -> List[str]:
    tasks = [
        asyncio.create_task(process_chunk(chunk, template, config))
        for chunk in chunks
    ]
    return await asyncio.gather(*tasks)

def combine_summaries(summaries: List[str]) -> str:
    return "\n\n".join(summaries)

def main(config: Dict) -> str:
    try:
        if config["type_of_source"] == "YouTube Video":
            video_id = extract_youtube_id(config["source_url_or_path"])
            url = re.sub(r'\&t=\d+s?', '', config["source_url_or_path"])
            
            if config.get("use_youtube_captions", True):
                transcript = get_youtube_transcript(
                    video_id,
                    config.get("language", "en")
                )
            else:
                audio_path = download_youtube_audio(url)
                transcript = transcribe_audio(
                    audio_path,
                    config.get("transcription_method", "Cloud Whisper")
                )
                os.remove(audio_path)
        else:
            raise NotImplementedError("Only YouTube videos supported")
            
        chunks = chunk_text(transcript, config.get("chunk_size", 10000))
        template = load_prompt_template(
            config.get("prompt_type", "Questions and answers")
        )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            summaries = loop.run_until_complete(
                process_chunks(chunks, template, config)
            )
            return combine_summaries(summaries)
        finally:
            loop.close()
            
    except Exception as e:
        raise Exception(f"Processing failed: {str(e)}")
