"""Cobalt downloader for non-YouTube platforms."""

import os
import tempfile
import uuid
from typing import Optional
from urllib.parse import urlparse
import requests
from ..exceptions import AudioProcessingError, TranscriptError
from ..handlers import process_audio_file
from ..progress import ProgressSpinner, print_status
from .base import BaseDownloader


class CobaltDownloader(BaseDownloader):
    """Downloader that proxies through a Cobalt instance."""

    def __init__(self, base_url: str):
        self.base_url = (base_url or "").rstrip("/")

    def supports(self, url: str) -> bool:
        parsed = urlparse(url or "")
        return parsed.scheme in ("http", "https")

    def _resolve_download_url(self, url: str, verbose: bool) -> str:
        if not self.base_url:
            raise TranscriptError("Cobalt base URL not configured")

        spinner = ProgressSpinner("Requesting Cobalt download", verbose)
        try:
            spinner.start()
            response = requests.post(
                f"{self.base_url}/api/json",
                json={"url": url},
                headers={"Accept": "application/json"},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            spinner.stop()
        except Exception as e:
            spinner.stop()
            raise TranscriptError(f"Cobalt request failed: {str(e)}")

        if isinstance(payload, dict):
            if payload.get("status") == "error":
                raise TranscriptError(payload.get("text") or "Cobalt returned an error")

            download_url = (
                payload.get("url")
                or payload.get("download")
                or payload.get("audio")
                or payload.get("file")
            )
            if not download_url and isinstance(payload.get("links"), list):
                first_link = payload["links"][0] if payload["links"] else {}
                download_url = first_link.get("url")

            if download_url:
                print_status("Cobalt download link ready", "SUCCESS", verbose)
                return download_url

        raise TranscriptError("Cobalt response did not include a download URL")

    def download_audio(
        self, url: str, temp_dir: Optional[str] = None, verbose: bool = False
    ) -> str:
        download_url = self._resolve_download_url(url, verbose)
        temp_root = temp_dir or tempfile.gettempdir()
        temp_name = f"cobalt_audio_{uuid.uuid4().hex}"
        temp_path = os.path.join(temp_root, f"{temp_name}.bin")
        processed_path = os.path.join(temp_root, f"{temp_name}.mp3")

        spinner = ProgressSpinner("Downloading audio from Cobalt", verbose)
        try:
            spinner.start()
            with requests.get(download_url, stream=True, timeout=120) as response:
                response.raise_for_status()
                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
            spinner.stop()
            print_status("Cobalt download completed", "SUCCESS", verbose)

            spinner = ProgressSpinner("Processing audio file", verbose)
            spinner.start()
            process_audio_file(temp_path, processed_path)
            spinner.stop()
            print_status("Audio processing completed", "SUCCESS", verbose)
            os.remove(temp_path)
            return processed_path
        except Exception as e:
            spinner.stop()
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists(processed_path):
                os.remove(processed_path)
            raise AudioProcessingError(f"Cobalt audio download failed: {str(e)}")
