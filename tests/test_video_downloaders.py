"""Mock-based tests for video download methods."""

import os
import shutil
import tempfile
import uuid
from unittest.mock import patch, MagicMock

import pytest

from summarizer.downloaders import DownloadManager
from summarizer.downloaders.ytdlp import YtdlpDownloader
from summarizer.downloaders.cobalt import CobaltDownloader


class TestDownloadManagerVideo:
    def test_fallback_order(self):
        dm = DownloadManager()
        with patch.object(dm.downloaders[0], "supports", return_value=False), \
             patch.object(dm.downloaders[1], "supports", return_value=True), \
             patch.object(dm.downloaders[1], "download_video", return_value="/fake/video.mp4"):
            result = dm.download_video("http://example.com/video")
            assert result == "/fake/video.mp4"

    def test_raises_when_no_downloader_matches(self):
        dm = DownloadManager()
        with patch.object(dm.downloaders[0], "supports", return_value=False), \
             patch.object(dm.downloaders[1], "supports", return_value=False), \
             patch.object(dm.downloaders[2], "supports", return_value=False):
            from summarizer.exceptions import UnsupportedSourceError
            with pytest.raises(UnsupportedSourceError, match="No downloader available"):
                dm.download_video("http://example.com/video")


class TestYtdlpDownloaderVideo:
    def test_downloads_video_without_audio_extraction(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video")
            fake_path = f.name
        try:
            dl = YtdlpDownloader()
            with patch("summarizer.downloaders.ytdlp._load_ytdlp") as mock_load, \
                 patch("summarizer.downloaders.ytdlp._find_produced_files", return_value=[fake_path]):
                mock_ydl_class = MagicMock()
                mock_ydl_instance = mock_ydl_class.return_value
                mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
                mock_ydl_instance.__exit__ = MagicMock(return_value=False)
                mock_load.return_value.YoutubeDL = mock_ydl_class
                result = dl.download_video("https://instagram.com/reel/123")
                assert result == fake_path
                # Verify format was set to video, not audio
                call_args = mock_ydl_class.call_args
                assert call_args[0][0]["format"] == "bestvideo*+bestaudio/best"
        finally:
            os.remove(fake_path)


class TestCobaltDownloaderVideo:
    def test_requests_video_not_audio(self):
        dl = CobaltDownloader("http://localhost:9000")
        with patch.object(dl, "_resolve_download_url", return_value="http://cdn.example.com/video.mp4"), \
             patch("requests.get") as mock_get:
            resp = MagicMock()
            resp.iter_content = lambda **kwargs: [b"fake chunk"]
            resp.raise_for_status = lambda: None
            resp.status_code = 200
            mock_get.return_value.__enter__ = MagicMock(return_value=resp)
            mock_get.return_value.__exit__ = MagicMock(return_value=False)
            tmpdir = os.path.join(os.getcwd(), f"tmp_cobalt_test_{uuid.uuid4().hex}")
            os.makedirs(tmpdir)
            try:
                result = dl.download_video("https://example.com/video", temp_dir=tmpdir)
                assert os.path.exists(result)
                # Ensure the resolved URL came from the video resolver
                mock_get.assert_called_once_with(
                    "http://cdn.example.com/video.mp4", stream=True, timeout=120
                )
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

    def test_resolve_video_payload_uses_auto_mode(self):
        dl = CobaltDownloader("http://localhost:9000")
        with patch("requests.post") as mock_post:
            resp = MagicMock()
            resp.json.return_value = {
                "url": "http://cdn.example.com/video.mp4"
            }
            resp.status_code = 200
            mock_post.return_value = resp
            url = dl._resolve_download_url("https://example.com/video", verbose=False, mode="video")
            assert url == "http://cdn.example.com/video.mp4"
            payload = mock_post.call_args[1]["json"]
            assert payload["downloadMode"] == "auto"
