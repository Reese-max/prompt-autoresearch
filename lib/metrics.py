# -*- coding: utf-8 -*-
"""
lib/metrics.py — 結構化指標記錄。

記錄每輪演化關鍵指標到 metrics.jsonl，供分析與前端展示。
用法：
    from lib.metrics import record_round, record_event
    record_round(round=1, direction="D01", smoke_score=82.5, dev_score=78.3, accept=True)
    record_event("start", {"baseline_dev_score": 75.0})
"""
import os
import time

from lib.io import append_jsonl

METRICS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metrics.jsonl")


def record_event(event_type, data=None):
    """記錄一個事件。"""
    payload = {
        "event": event_type,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if data:
        payload.update(data)
    append_jsonl(METRICS_PATH, payload)


def record_round(
    round_no,
    direction="",
    target_failures=None,
    smoke_score=None,
    dev_score=None,
    holdout_score=None,
    accept=False,
    score_diff=None,
    api_calls=None,
    elapsed_seconds=None,
    error="",
    candidates_count=1,
):
    """記錄一輪演化結果。"""
    payload = {
        "event": "round",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "round": round_no,
        "direction": direction,
        "target_failures": target_failures or [],
        "smoke_score": smoke_score,
        "dev_score": dev_score,
        "holdout_score": holdout_score,
        "accept": accept,
        "score_diff": score_diff,
        "api_calls": api_calls,
        "elapsed_seconds": elapsed_seconds,
        "error": error,
        "candidates_count": candidates_count,
    }
    append_jsonl(METRICS_PATH, payload)
    return payload
