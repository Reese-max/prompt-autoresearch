# -*- coding: utf-8 -*-
"""
lib/api.py — 統一 API 呼叫層。

合併所有 call_minimax 重複實作，統一 retry / timeout / rate limiting。
用法：
    from lib.api import call_minimax
    answer = call_minimax("你是專家。", "請回答...", temperature=0.3)
"""
import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request

from lib.config import get


class APIError(RuntimeError):
    """MiniMax API 呼叫失敗的統一內部錯誤型別。"""


class APITimeoutError(APIError, TimeoutError):
    """MiniMax API 呼叫逾時（connect / read 階段一律轉為此型別）。"""


def _translate_error(e, max_retry):
    """把外部原生例外轉譯為統一內部錯誤，保留狀態碼與原始訊息。"""
    if isinstance(e, urllib.error.HTTPError):
        return APIError(f"MiniMax API 回應錯誤 HTTP {e.code}（retry={max_retry}）：{e.reason}")
    if isinstance(e, (socket.timeout, TimeoutError)):
        return APITimeoutError(f"MiniMax API 呼叫逾時（retry={max_retry}）：{e}")
    if isinstance(e, urllib.error.URLError):
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            return APITimeoutError(f"MiniMax API 呼叫逾時（retry={max_retry}）：{e.reason}")
        return APIError(f"MiniMax API 連線失敗（retry={max_retry}）：{e.reason}")
    if isinstance(e, ConnectionError):
        return APIError(f"MiniMax API 連線失敗（retry={max_retry}）：{type(e).__name__}: {e}")
    return APIError(f"MiniMax API 呼叫失敗（retry={max_retry}）：{type(e).__name__}: {e}")

# --- Rate Limiter ---
_semaphore = None
_rate_lock = threading.Lock()
_last_call_ts = 0.0


def _get_semaphore():
    global _semaphore
    if _semaphore is None:
        max_concurrent = get("api", "rate_limit", {}).get("max_concurrent", 8)
        _semaphore = threading.Semaphore(max_concurrent)
    return _semaphore


def _rate_wait():
    global _last_call_ts
    min_interval = get("api", "rate_limit", {}).get("min_interval_ms", 100) / 1000.0
    with _rate_lock:
        now = time.time()
        wait = min_interval - (now - _last_call_ts)
        if wait > 0:
            time.sleep(wait)
        _last_call_ts = time.time()


def call_minimax(system_prompt, user_content, temperature=0.7):
    """
    呼叫 MiniMax API 生成內容。
    統一 retry=4、timeout=180、exponential backoff。
    """
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        raise RuntimeError("缺少 MINIMAX_API_KEY 環境變數，無法呼叫 MiniMax API。")

    api_url = get("api", "url", "https://api.minimaxi.chat/v1/text/chatcompletion_v2")
    model = get("api", "model", "MiniMax-M2.7")
    timeout = get("api", "timeout", 180)
    max_retry = get("api", "retry", 4)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
    }
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=req_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    semaphore = _get_semaphore()
    # retry<1 視同 1：至少嘗試一次，失敗時錯誤訊息帶出 retry 設定值
    attempts = max(1, max_retry)
    for attempt in range(attempts):
        with semaphore:
            _rate_wait()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    res_data = response.read()
                    res_json = json.loads(res_data.decode("utf-8"))
                    return res_json["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if attempt == attempts - 1:
                    raise _translate_error(e, max_retry) from e
                time.sleep(2 ** attempt)
