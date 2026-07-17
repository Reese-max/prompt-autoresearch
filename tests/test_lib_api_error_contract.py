# -*- coding: utf-8 -*-
"""lib/api.py 錯誤契約測試（對照 docs/lib-api-error-branch-audit.md）。

每個測試斷言統一錯誤契約：呼叫端拿到統一的 APIError（RuntimeError 子類）、
訊息含情境描述、HTTP 錯誤含狀態碼、逾時一律為 APITimeoutError（兼具
TimeoutError）、retry=0 不得靜默吞錯。錯誤轉譯層已在 lib/api.py 補上，
原 xfail(strict=True) 標記已移除、轉為正式測試。
"""
import json
import socket
from unittest import mock
from urllib.error import HTTPError, URLError

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


def _make_fake_get(retry):
    def fake_get(section, key=None, default=None):
        defaults = {
            "url": "https://api.example.local/v1/chat",
            "model": "MiniMax-M2.7",
            "timeout": 1,
            "retry": retry,
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

    return fake_get


@pytest.fixture
def _mock_api_runtime(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(api, "get", _make_fake_get(retry=1))
    monkeypatch.setattr(api, "_rate_wait", lambda: None)
    monkeypatch.setattr(api, "_semaphore", None)
    monkeypatch.setattr(api, "_last_call_ts", 0.0)


@pytest.fixture
def mock_urlopen(monkeypatch):
    mocked = mock.Mock()
    monkeypatch.setattr(api.urllib.request, "urlopen", mocked)
    return mocked


def test_http_error_response_should_raise_runtime_error_with_status_code(
    _mock_api_runtime, mock_urlopen
):
    mock_urlopen.side_effect = HTTPError(
        url="https://api.example.local/v1/chat",
        code=500,
        msg="internal",
        hdrs=None,
        fp=None,
    )

    with pytest.raises(RuntimeError, match="500"):
        api.call_minimax("system", "user")


def test_read_timeout_should_raise_runtime_error_with_timeout_message(
    _mock_api_runtime, mock_urlopen
):
    mock_urlopen.side_effect = socket.timeout("request timed out")

    with pytest.raises(RuntimeError, match="逾時|timeout"):
        api.call_minimax("system", "user")


def test_connect_timeout_urlerror_form_should_raise_same_type_as_read_timeout(
    _mock_api_runtime, mock_urlopen
):
    mock_urlopen.side_effect = URLError(socket.timeout("connect timed out"))

    with pytest.raises(TimeoutError):
        api.call_minimax("system", "user")


def test_connection_exception_should_be_wrapped_with_api_context(
    _mock_api_runtime, mock_urlopen
):
    mock_urlopen.side_effect = ConnectionResetError("connection reset by peer")

    with pytest.raises(RuntimeError, match="MiniMax"):
        api.call_minimax("system", "user")


def test_retry_exhaustion_wraps_final_dependency_error(
    _mock_api_runtime, mock_urlopen, monkeypatch
):
    monkeypatch.setattr(api, "get", _make_fake_get(retry=2))
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    first = ConnectionError("temporary failure")
    final = ConnectionError("connection lost")
    mock_urlopen.side_effect = [first, final]

    with pytest.raises(api.APIError, match="連線失敗") as excinfo:
        api.call_minimax("system", "user")

    err = excinfo.value
    assert "retry=2" in str(err)
    assert mock_urlopen.call_count == 2
    assert err.__cause__ is final


def test_retry_zero_should_raise_instead_of_silent_empty_string(
    _mock_api_runtime, mock_urlopen, monkeypatch
):
    monkeypatch.setattr(api, "get", _make_fake_get(retry=0))

    with pytest.raises(RuntimeError, match="retry"):
        api.call_minimax("system", "user")

    assert mock_urlopen.call_count > 0, "retry=0 時完全沒有發出 API 請求"
