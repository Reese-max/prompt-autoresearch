# -*- coding: utf-8 -*-
"""正向驗證：_translate_error（lib/api.py:29-41）各分支轉譯正確性。

確認 call_minimax 在不同外部失敗來源下皆經 _translate_error 轉譯為
統一的內部錯誤型別與一致的中文訊息，不洩漏原始例外或回傳不一致訊息。
"""
import socket
from unittest import mock
from urllib.error import HTTPError, URLError

import pytest

import lib.api as api


def _make_fake_get(retry=1):
    def fake_get(section, key=None, default=None):
        defaults = {
            "url": "https://api.example.local/v1/chat",
            "model": "MiniMax-M2.7",
            "timeout": 1,
            "retry": retry,
            "rate_limit": {"max_concurrent": 1, "min_interval_ms": 0},
        }
        if section != "api":
            return default
        if key is None:
            return defaults
        return defaults.get(key, default)
    return fake_get


@pytest.fixture
def env(monkeypatch):
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


def _assert_api_error(err, expected_code=None, *, retry="1", cause):
    assert isinstance(err, api.APIError)
    assert isinstance(err, RuntimeError)
    assert not isinstance(err, api.APITimeoutError)
    if expected_code:
        assert str(expected_code) in str(err)
    assert f"retry={retry}" in str(err)
    assert err.__cause__ is cause


def _assert_api_timeout_error(err, *, retry="1", cause):
    assert isinstance(err, api.APITimeoutError)
    assert isinstance(err, RuntimeError)
    assert isinstance(err, TimeoutError)
    assert "逾時" in str(err)
    assert f"retry={retry}" in str(err)
    assert err.__cause__ is cause


class TestTranslateErrorPositiveVerify:

    def test_http_error_yields_api_error(self, env, mock_urlopen):
        original = HTTPError("url", 502, "Bad Gateway", None, None)
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_error(excinfo.value, expected_code=502, cause=original)
        assert "MiniMax API 回應錯誤" in str(excinfo.value)

    def test_socket_timeout_yields_api_timeout_error(self, env, mock_urlopen):
        original = socket.timeout("read timed out")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APITimeoutError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_timeout_error(excinfo.value, cause=original)

    def test_timeout_error_yields_api_timeout_error(self, env, mock_urlopen):
        original = TimeoutError("operation timed out")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APITimeoutError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_timeout_error(excinfo.value, cause=original)

    def test_urlerror_with_timeout_reason_yields_api_timeout_error(self, env, mock_urlopen):
        original = URLError(socket.timeout("connect timeout"))
        mock_urlopen.side_effect = original

        with pytest.raises(api.APITimeoutError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_timeout_error(excinfo.value, cause=original)

    def test_urlerror_with_non_timeout_reason_yields_api_error(self, env, mock_urlopen):
        original = URLError(ConnectionRefusedError(111, "connection refused"))
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_error(excinfo.value, cause=original)
        assert "連線失敗" in str(excinfo.value)

    def test_connection_error_base_yields_api_error(self, env, mock_urlopen):
        original = ConnectionError("connection lost")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_error(excinfo.value, cause=original)
        assert "連線失敗" in str(excinfo.value)
        assert "ConnectionError" in str(excinfo.value)

    def test_connection_reset_error_yields_api_error(self, env, mock_urlopen):
        original = ConnectionResetError("connection reset by peer")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_error(excinfo.value, cause=original)
        assert "連線失敗" in str(excinfo.value)
        assert "ConnectionResetError" in str(excinfo.value)

    def test_connection_aborted_error_yields_api_error(self, env, mock_urlopen):
        original = ConnectionAbortedError("connection aborted")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_error(excinfo.value, cause=original)
        assert "連線失敗" in str(excinfo.value)
        assert "ConnectionAbortedError" in str(excinfo.value)

    def test_generic_exception_yields_api_error_with_type_name(self, env, mock_urlopen):
        original = ValueError("bad value")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_error(excinfo.value, cause=original)
        assert "呼叫失敗" in str(excinfo.value)
        assert "ValueError" in str(excinfo.value)

    def test_os_error_yields_api_error_with_type_name(self, env, mock_urlopen):
        original = OSError("system error")
        mock_urlopen.side_effect = original

        with pytest.raises(api.APIError) as excinfo:
            api.call_minimax("s", "u")

        _assert_api_error(excinfo.value, cause=original)
        assert "呼叫失敗" in str(excinfo.value)
        assert "OSError" in str(excinfo.value)
