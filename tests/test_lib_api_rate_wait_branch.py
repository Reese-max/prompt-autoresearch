# -*- coding: utf-8 -*-
"""lib/api.py 第 56-62 行（_rate_wait）未覆蓋分支測試。

覆蓋目標：
1. `if wait > 0: time.sleep(wait)`（第 60-61 行）—— 連續呼叫觸發 rate limiting。
2. `_rate_wait` 真實執行 ＋ 外部 API client（urlopen）拋出例外，
   驗證例外經 _translate_error 轉譯為統一內部錯誤型別與訊息。

TDD 脈絡：現有測試全數 stub _rate_wait = lambda: None，導致第 56-62 行
完全未被執行。此處補上真實分支覆蓋，並以獨立的 _rate_wait 實例執行
確保不影響其他測試的全域狀態。
"""
import json
import time
from unittest import mock
from urllib.error import HTTPError, URLError

import pytest

import lib.api as api


class _FakeHTTPResponse:
    def __init__(self, body: bytes):
        self._body = body
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        return False
    def read(self) -> bytes:
        return self._body


@pytest.fixture
def _rate_limit_env(monkeypatch):
    """提供真實 _rate_wait 執行環境：min_interval_ms=200，不 stub _rate_wait。"""
    def fake_get(section, key=None, default=None):
        defaults = {
            "url": "https://api.example.local/v1/chat",
            "model": "MiniMax-M2.7",
            "timeout": 1,
            "retry": 1,
            "rate_limit": {
                "max_concurrent": 1,
                "min_interval_ms": 200,
            },
        }
        if section != "api":
            return default
        if key is None:
            return defaults
        return defaults.get(key, default)

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(api, "get", fake_get)
    monkeypatch.setattr(api, "_semaphore", None)
    monkeypatch.setattr(api, "_last_call_ts", 0.0)
    # 刻意不 stub _rate_wait，讓它真實執行


@pytest.fixture
def _mock_urlopen(monkeypatch):
    mocked = mock.Mock()
    monkeypatch.setattr(api.urllib.request, "urlopen", mocked)
    return mocked


def _make_success_response(text="hello"):
    return _FakeHTTPResponse(
        json.dumps(
            {"choices": [{"message": {"content": text}}]},
            ensure_ascii=False,
        ).encode("utf-8")
    )


def test_rate_wait_sleeps_on_consecutive_calls(_rate_limit_env, _mock_urlopen):
    """連續呼叫時 _rate_wait 應 sleep（if wait > 0 分支）。"""
    _mock_urlopen.return_value = _make_success_response("first")
    api.call_minimax("system", "first")

    _mock_urlopen.return_value = _make_success_response("second")
    start = time.perf_counter()
    api.call_minimax("system", "second")
    elapsed = time.perf_counter() - start

    # min_interval_ms=200，第二次呼叫應 sleep ≈ 200ms
    assert elapsed >= 0.18, (
        f"預期 rate limiting sleep ≥ 180ms，實際 {elapsed:.3f}s"
    )


def test_rate_wait_no_sleep_on_single_call(_rate_limit_env, _mock_urlopen):
    """首次呼叫不應有 rate limiting sleep。"""
    _mock_urlopen.return_value = _make_success_response("only")
    start = time.perf_counter()
    api.call_minimax("system", "only")
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, (
        f"首次呼叫不應 sleep，實際耗時 {elapsed:.3f}s"
    )


def test_error_after_rate_wait_translated_to_api_error(_rate_limit_env, _mock_urlopen):
    """_rate_wait 真實執行後 urlopen 拋 HTTPError → 轉譯為 APIError。"""
    _mock_urlopen.side_effect = HTTPError(
        url="https://api.example.local/v1/chat",
        code=502,
        msg="bad gateway",
        hdrs=None,
        fp=None,
    )

    with pytest.raises(api.APIError) as excinfo:
        api.call_minimax("system", "user")

    err = excinfo.value
    assert "502" in str(err)
    assert "retry=" in str(err)
    assert isinstance(err, RuntimeError)


def test_timeout_after_rate_wait_translated_to_api_timeout_error(
    _rate_limit_env, _mock_urlopen
):
    """_rate_wait 真實執行後 urlopen 拋 socket.timeout → 轉譯為 APITimeoutError。"""
    _mock_urlopen.side_effect = TimeoutError("timed out")

    with pytest.raises(api.APITimeoutError) as excinfo:
        api.call_minimax("system", "user")

    err = excinfo.value
    assert "逾時" in str(err)
    assert isinstance(err, TimeoutError)
    assert isinstance(err, RuntimeError)


def test_generic_exception_after_rate_wait_wrapped_with_context(
    _rate_limit_env, _mock_urlopen
):
    """通用例外經 _rate_wait 後仍正確包裝為 APIError。"""
    original = RuntimeError("unexpected failure")
    _mock_urlopen.side_effect = original

    with pytest.raises(api.APIError) as excinfo:
        api.call_minimax("system", "user")

    err = excinfo.value
    assert "unexpected failure" in str(err)
    assert err.__cause__ is original, (
        "應以 raise ... from e 保留原始例外"
    )


def test_retry_zero_after_rate_wait_still_makes_request(
    _rate_limit_env, _mock_urlopen, monkeypatch
):
    """retry=0 且 _rate_wait 真實執行時仍至少嘗試一次、錯誤照常轉譯。"""
    def fake_get_zero(section, key=None, default=None):
        defaults = {
            "url": "https://api.example.local/v1/chat",
            "model": "MiniMax-M2.7",
            "timeout": 1,
            "retry": 0,
            "rate_limit": {"max_concurrent": 1, "min_interval_ms": 200},
        }
        if section != "api":
            return default
        if key is None:
            return defaults
        return defaults.get(key, default)

    monkeypatch.setattr(api, "get", fake_get_zero)

    _mock_urlopen.side_effect = HTTPError(
        url="https://api.example.local/v1/chat",
        code=503,
        msg="service unavailable",
        hdrs=None,
        fp=None,
    )

    with pytest.raises(api.APIError, match="503"):
        api.call_minimax("system", "user")

    assert _mock_urlopen.call_count > 0
