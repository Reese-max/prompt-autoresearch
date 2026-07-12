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
import threading
import time
import urllib.request

from lib.config import get

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
    for attempt in range(max_retry):
        with semaphore:
            _rate_wait()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    res_data = response.read()
                    res_json = json.loads(res_data.decode("utf-8"))
                    return res_json["choices"][0]["message"]["content"].strip()
            except Exception as e:
                if attempt == max_retry - 1:
                    raise e
                time.sleep(2 ** attempt)
    return ""
