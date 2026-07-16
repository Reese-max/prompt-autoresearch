# -*- coding: utf-8 -*-
"""lib/api.py 外部 API 呼叫路徑的可重現失敗測試。

覆蓋三個外部 API 呼叫失敗情境，全部透過 mock urllib.request.urlopen
確保不發真實請求、測試可重現：

1. HTTP 非 2xx 錯誤 → _translate_error 轉譯為 APIError（含狀態碼、retry 資訊）
2. 逾時（TimeoutError）→ _translate_error 轉譯為 APITimeoutError
3. 底層例外拋出 → 包裝為 APIError（含原始例外型別、retry 資訊）
"""

from unittest import mock
from urllib.error import HTTPError

import pytest

import lib.api as api


class _FakeHTTPResponse:
    def __init__(self, body: bytes):
        self._body = body
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
    def read(self):
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
def env(monkeypatch):
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


class TestHttpError:
    def test_non_2xx_wraps_as_api_error_with_code_and_retry(
        self, env, mock_urlopen
    ):
        original = HTTPError(
            url="https://api.example.local/v1/chat",
            code=502,
            msg="Bad Gateway",
            hdrs=None,
            fp=None,
        )
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("system", "user")

        err = excinfo.value
        assert not isinstance(err, api.APITimeoutError)
        assert "502" in str(err)
        assert "retry=1" in str(err)
        assert err.__cause__ is original


class TestTimeout:
    def test_timeout_raises_api_timeout_error(
        self, env, mock_urlopen
    ):
        original = TimeoutError("connection timed out")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APITimeoutError) as excinfo:
            api.call_minimax("system", "user")

        err = excinfo.value
        assert isinstance(err, TimeoutError)
        assert isinstance(err, RuntimeError)
        assert "逾時" in str(err)
        assert "retry=1" in str(err)
        assert err.__cause__ is original


class TestUnderlyingException:
    def test_generic_exception_wraps_as_api_error_with_type(
        self, env, mock_urlopen
    ):
        original = ConnectionResetError("connection reset by peer")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("system", "user")

        err = excinfo.value
        assert not isinstance(err, api.APITimeoutError)
        assert "ConnectionResetError" in str(err)
        assert "retry=1" in str(err)
        assert err.__cause__ is original
