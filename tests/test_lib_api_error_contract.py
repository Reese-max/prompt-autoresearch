# -*- coding: utf-8 -*-
"""lib/api.py 錯誤契約 failing tests（對照 docs/lib-api-error-branch-audit.md）。

每個測試斷言「期望的統一錯誤契約」：呼叫端應拿到統一的 RuntimeError、
訊息含情境描述、HTTP 錯誤須含狀態碼、retry=0 不得靜默吞錯。
目前 call_minimax()（api.py:84-88）只原樣重拋原生例外或靜默回空字串，
與期望不一致，故全部以 xfail(strict=True) 標記：
- 現況下穩定失敗（記為 xfail，可重現不一致處）；
- 一旦錯誤轉譯層補上，XPASS 會炸出來，提醒移除標記轉為正式測試。
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


@pytest.mark.xfail(
    strict=True,
    raises=HTTPError,
    reason="稽核 #2：HTTP 5xx 原樣重拋 HTTPError，未轉譯為含狀態碼的 RuntimeError",
)
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


@pytest.mark.xfail(
    strict=True,
    raises=socket.timeout,
    reason="稽核 #3：read 階段 timeout 原樣重拋 socket.timeout，未轉譯為統一 RuntimeError",
)
def test_read_timeout_should_raise_runtime_error_with_timeout_message(
    _mock_api_runtime, mock_urlopen
):
    mock_urlopen.side_effect = socket.timeout("request timed out")

    with pytest.raises(RuntimeError, match="逾時|timeout"):
        api.call_minimax("system", "user")


@pytest.mark.xfail(
    strict=True,
    raises=URLError,
    reason="稽核 #4：連線階段 timeout 以 URLError(reason=timeout) 形態拋出，"
    "與 read 階段的 socket.timeout 不同型別，呼叫端只 catch 其一會漏接",
)
def test_connect_timeout_urlerror_form_should_raise_same_type_as_read_timeout(
    _mock_api_runtime, mock_urlopen
):
    mock_urlopen.side_effect = URLError(socket.timeout("connect timed out"))

    with pytest.raises(TimeoutError):
        api.call_minimax("system", "user")


@pytest.mark.xfail(
    strict=True,
    raises=ConnectionResetError,
    reason="稽核 #7：底層例外原樣重拋，未包裝為含 API 呼叫上下文訊息的統一錯誤",
)
def test_connection_exception_should_be_wrapped_with_api_context(
    _mock_api_runtime, mock_urlopen
):
    mock_urlopen.side_effect = ConnectionResetError("connection reset by peer")

    with pytest.raises(RuntimeError, match="MiniMax"):
        api.call_minimax("system", "user")


@pytest.mark.xfail(
    strict=True,
    reason="稽核 #9：retry=0 時迴圈不進入，不呼叫 API、不報錯、靜默回空字串（api.py:88），"
    "與「API 回了空內容」無法區分；期望應拋出設定錯誤",
)
def test_retry_zero_should_raise_instead_of_silent_empty_string(
    _mock_api_runtime, mock_urlopen, monkeypatch
):
    monkeypatch.setattr(api, "get", _make_fake_get(retry=0))

    with pytest.raises(RuntimeError, match="retry"):
        api.call_minimax("system", "user")

    assert mock_urlopen.call_count > 0, "retry=0 時完全沒有發出 API 請求"
