import json
import socket
from unittest import mock
from urllib.error import HTTPError

import pytest

import lib.api as api


class FakeHTTPResponse:
    """輕量 mock 回應物件：提供 context manager 與 read()。"""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def _mock_api_runtime(monkeypatch):
    def fake_get(section, key=None, default=None):
        defaults = {
            "url": "https://api.example.local/v1/chat",
            "model": "MiniMax-M2.7",
            "timeout": 1,
            "retry": 1,
            "rate_limit": {
                "max_concurrent": 1,
                "min_interval_ms": 0,
            },
        }
        if section != "api":
            return default
        if key is None:
            return defaults
        return defaults.get(key, default)

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(api, "get", fake_get)
    monkeypatch.setattr(api, "_rate_wait", lambda: None)
    monkeypatch.setattr(api, "_semaphore", None)
    monkeypatch.setattr(api, "_last_call_ts", 0.0)


@pytest.fixture
def mock_urlopen(monkeypatch):
    mocked = mock.Mock()
    monkeypatch.setattr(api.urllib.request, "urlopen", mocked)
    return mocked


def test_call_minimax_success_parses_and_returns_trimmed_content(
    _mock_api_runtime,
    mock_urlopen,
):
    mock_urlopen.return_value = FakeHTTPResponse(
        json.dumps(
            {
                "choices": [
                    {"message": {"content": "  這是一段回應  "}},
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )

    ans = api.call_minimax("system prompt", "user prompt")

    assert ans == "這是一段回應"
    assert mock_urlopen.call_count == 1

    request = mock_urlopen.call_args.args[0]
    assert request.full_url == "https://api.example.local/v1/chat"
    assert request.get_header("Authorization") == "Bearer test-key"

    sent_payload = json.loads(request.data.decode("utf-8"))
    assert sent_payload["model"] == "MiniMax-M2.7"
    assert sent_payload["temperature"] == 0.7
    assert sent_payload["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]


def test_call_minimax_request_headers_and_payload_match_expectations(
    _mock_api_runtime,
    mock_urlopen,
):
    mock_urlopen.return_value = FakeHTTPResponse(
        json.dumps(
            {
                "choices": [
                    {"message": {"content": "回應"}},
                ]
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )

    api.call_minimax("s", "u", temperature=0.4)

    request = mock_urlopen.call_args.args[0]
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.get_header("Content-type") == "application/json"

    sent_payload = json.loads(request.data.decode("utf-8"))
    assert sent_payload["model"] == "MiniMax-M2.7"
    assert sent_payload["temperature"] == 0.4
    assert sent_payload["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]


def test_call_minimax_non_200_raises_http_error(_mock_api_runtime, mock_urlopen):
    mock_urlopen.side_effect = HTTPError(
        url="https://api.example.local/v1/chat",
        code=500,
        msg="internal",
        hdrs=None,
        fp=None,
    )

    with pytest.raises(HTTPError):
        api.call_minimax("system", "user")

    assert mock_urlopen.call_count == 1
    assert mock_urlopen.call_args.args[0].full_url == "https://api.example.local/v1/chat"


def test_call_minimax_timeout_raises(_mock_api_runtime, mock_urlopen):
    mock_urlopen.side_effect = socket.timeout("request timed out")

    with pytest.raises(socket.timeout):
        api.call_minimax("system", "user")

    assert mock_urlopen.call_count == 1
    assert mock_urlopen.call_args.args[0].full_url == "https://api.example.local/v1/chat"


def test_call_minimax_missing_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="缺少 MINIMAX_API_KEY 環境變數"):
        api.call_minimax("system", "user")


def test_call_minimax_invalid_json_raises(_mock_api_runtime, mock_urlopen):
    mock_urlopen.return_value = FakeHTTPResponse(b"not json")

    with pytest.raises(json.JSONDecodeError):
        api.call_minimax("system", "user")

    assert mock_urlopen.call_count == 1
    assert mock_urlopen.call_args.args[0].full_url == "https://api.example.local/v1/chat"


def test_call_minimax_exception_is_propagated(_mock_api_runtime, mock_urlopen):
    mock_urlopen.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        api.call_minimax("system", "user")

    assert mock_urlopen.call_count == 1
    assert mock_urlopen.call_args.args[0].full_url == "https://api.example.local/v1/chat"
