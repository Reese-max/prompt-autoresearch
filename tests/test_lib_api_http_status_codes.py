# -*- coding: utf-8 -*-
"""外部 API 回傳非 2xx／錯誤 payload 的錯誤轉譯測試。

既有測試只驗證 HTTP 500 且缺乏完整型別與訊息斷言；
本檔以多種 HTTP 狀態碼與非預期成功 payload 補齊缺口，
確保每種情境都產生統一的 APIError（非 APITimeoutError），
並保留狀態碼與 retry 資訊。
"""
import json
from unittest import mock
from urllib.error import HTTPError

import pytest

import lib.api as api


class FakeHTTPResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def read(self) -> bytes:
        return self._body


def _fake_get(section, key=None, default=None):
    defaults = {
        "url": "https://api.example.local/v1/chat",
        "model": "MiniMax-M2.7",
        "timeout": 1,
        "retry": 1,
        "rate_limit": {"max_concurrent": 1, "min_interval_ms": 0},
    }
    if section != "api":
        return default
    if key is None:
        return defaults
    return defaults.get(key, default)


@pytest.fixture
def _mock_api_runtime(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(api, "get", _fake_get)
    monkeypatch.setattr(api, "_rate_wait", lambda: None)
    monkeypatch.setattr(api, "_semaphore", None)
    monkeypatch.setattr(api, "_last_call_ts", 0.0)


@pytest.fixture
def mock_urlopen(monkeypatch):
    mocked = mock.Mock()
    monkeypatch.setattr(api.urllib.request, "urlopen", mocked)
    return mocked


HTTP_ERROR_CODES = [
    (400, "Bad Request"),
    (401, "Unauthorized"),
    (403, "Forbidden"),
    (429, "Too Many Requests"),
    (500, "Internal Server Error"),
    (502, "Bad Gateway"),
    (503, "Service Unavailable"),
]


@pytest.mark.parametrize("status_code,reason", HTTP_ERROR_CODES)
def test_non_2xx_status_code_raises_api_error_with_status_code(
    _mock_api_runtime, mock_urlopen, status_code, reason
):
    mock_urlopen.side_effect = HTTPError(
        url="https://api.example.local/v1/chat",
        code=status_code,
        msg=reason,
        hdrs=None,
        fp=None,
    )

    with pytest.raises(api.APIError) as excinfo:
        api.call_minimax("system", "user")

    err = excinfo.value
    assert not isinstance(err, api.APITimeoutError), (
        f"HTTP {status_code} 不得轉譯為 APITimeoutError"
    )
    assert isinstance(err, RuntimeError)
    assert str(status_code) in str(err)
    assert "retry=1" in str(err)


def test_200_empty_choices_list_raises_api_error(
    _mock_api_runtime, mock_urlopen
):
    """200 OK 但 choices 為空陣列 → IndexError → APIError。"""
    mock_urlopen.return_value = FakeHTTPResponse(
        json.dumps(
            {"choices": [], "base_resp": {"status_code": 1004}},
            ensure_ascii=False,
        ).encode("utf-8")
    )

    with pytest.raises(api.APIError) as excinfo:
        api.call_minimax("system", "user")

    err = excinfo.value
    assert not isinstance(err, api.APITimeoutError)
    assert isinstance(err, RuntimeError)
    assert "IndexError" in str(err)
    assert "retry=1" in str(err)
