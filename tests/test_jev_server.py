from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")
from fastapi.testclient import TestClient
from summarizer.server import create_app


FILE_CONFIG = {
    "default_provider": "openrouter",
    "providers": {
        "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "google/gemini-2.5-flash"},
    },
}
OPTIONS = {"use_jev_prefiltering": True, "jev_provider": "openrouter", "jev_include": "X", "jev_exclude": "Sponsorship"}


@pytest.mark.parametrize("route", ["single", "batch", "upload"])
def test_http_routes_forward_jev_options(route):
    with patch("summarizer.server.load_config_file", return_value=FILE_CONFIG), patch("summarizer.server.main", return_value="summary") as main:
        client = TestClient(create_app())
        if route == "single":
            response = client.post("/summarize", json={"source": "source", **OPTIONS})
        elif route == "batch":
            response = client.post("/summarize/batch", json={"sources": ["source"], **OPTIONS})
        else:
            response = client.post("/summarize/upload", data=OPTIONS, files={"file": ("sample.txt", b"text", "text/plain")})
    assert response.status_code == 200
    assert main.call_count == 1
    config = main.call_args.args[0]
    for key, value in OPTIONS.items():
        assert config[key] == value
    assert config["model"] == "google/gemini-2.5-flash"
    assert config["jev_provider_config"]["model"] == "jev-latest"
