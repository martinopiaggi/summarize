from unittest.mock import Mock, patch

import pytest
import requests

from webapp.tinypaste import TinypastePublishError, publish_to_tinypaste


def make_response(status_code=201, text="", json_value=None, json_error=False, headers=None):
    response = Mock()
    response.status_code = status_code
    response.text = text
    response.headers = headers or {}

    if json_error:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_value

    return response


@patch("webapp.tinypaste.requests.post")
def test_publish_json_response_returns_url(post):
    post.return_value = make_response(json_value={"id": "abc", "url": "https://tnypst.xyz/abc"})

    url = publish_to_tinypaste("# Summary", base_url="https://example.test")

    assert url == "https://tnypst.xyz/abc"
    post.assert_called_once_with(
        "https://example.test/api/pastes",
        json={"markdown": "# Summary"},
        headers={"Accept": "application/json"},
        timeout=15,
    )


@patch("webapp.tinypaste.requests.post")
def test_publish_plain_text_response_returns_url(post):
    post.return_value = make_response(
        text="https://tnypst.xyz/plain\n",
        json_error=True,
    )

    assert publish_to_tinypaste("# Summary") == "https://tnypst.xyz/plain"


@patch("webapp.tinypaste.requests.post")
def test_publish_rate_limit_reports_retry_after(post):
    post.return_value = make_response(
        status_code=429,
        text="Rate limit exceeded.",
        headers={"Retry-After": "42"},
    )

    with pytest.raises(TinypastePublishError, match="Retry after 42 seconds"):
        publish_to_tinypaste("# Summary")


@patch("webapp.tinypaste.requests.post")
def test_publish_network_error_is_explicit(post):
    post.side_effect = requests.Timeout("slow")

    with pytest.raises(TinypastePublishError, match="timed out"):
        publish_to_tinypaste("# Summary")


@patch("webapp.tinypaste.requests.post")
def test_publish_empty_markdown_rejected_before_http(post):
    with pytest.raises(TinypastePublishError, match="empty summary"):
        publish_to_tinypaste("   ")

    post.assert_not_called()


@patch("webapp.tinypaste.requests.post")
def test_publish_malformed_json_is_explicit(post):
    post.return_value = make_response(json_value={"id": "abc"})

    with pytest.raises(TinypastePublishError, match="valid url"):
        publish_to_tinypaste("# Summary")
