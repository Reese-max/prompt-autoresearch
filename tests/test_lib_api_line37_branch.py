# -*- coding: utf-8 -*-
"""lib/api.py 第 37 行分支測試：URLError（非 timeout reason）→ APIError「連線失敗」。

TDD 脈絡：修補前 call_minimax 會把原生 urllib.error.URLError 直接漏給呼叫端
（無統一型別、無 retry 情境、無「連線失敗」語意），本檔原本應以
xfail(strict=True) 固化該落差；因錯誤轉譯層已於 lib/api.py 補上
（_translate_error 第 37 行），此處直接以正式測試固化修補後契約：

1. 錯誤型別：APIError（RuntimeError 子類），且「不是」APITimeoutError——
   非 timeout 的連線失敗不得偽裝成逾時。
2. 錯誤訊息：含「連線失敗」語意、retry 設定值、原始 reason 內容。
3. 例外鏈：raise ... from e 保留原生 URLError 供除錯（__cause__）。
"""
from unittest import mock
from urllib.error import URLError

import pytest

import lib.api as api


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


def test_urlerror_non_timeout_should_raise_apierror_connection_failed(
    _mock_api_runtime, monkeypatch
):
    original = URLError(ConnectionRefusedError(111, "connection refused"))
    monkeypatch.setattr(
        api.urllib.request, "urlopen", mock.Mock(side_effect=original)
    )

    with pytest.raises(api.APIError, match="連線失敗") as excinfo:
        api.call_minimax("system", "user")

    err = excinfo.value
    assert not isinstance(err, api.APITimeoutError), (
        "非 timeout 的 URLError 不得轉譯為 APITimeoutError"
    )
    assert isinstance(err, RuntimeError)
    assert "retry=1" in str(err)
    assert "connection refused" in str(err)
    assert err.__cause__ is original, "應以 raise ... from e 保留原始 URLError"
