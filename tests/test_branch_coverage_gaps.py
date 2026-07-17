# -*- coding: utf-8 -*-
"""補齊 coverage 報表列出的 partial branches。"""
import io
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

import api.feedback as feedback
import lib.api as api

# 先載入 evaluate，讓 evaluate_routed 的 runpy 測試只重跑目標腳本本身。
import scripts.evaluate_routed  # noqa: F401,E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STREAM_GUARD_SCRIPTS = (
    PROJECT_ROOT / "scripts" / "compare_runs.py",
    PROJECT_ROOT / "scripts" / "evaluate_routed.py",
    PROJECT_ROOT / "scripts" / "preflight.py",
)


def test_feedback_skips_zero_count_question_type_bucket(monkeypatch):
    """覆蓋題型平均值 guard 的 false 側。"""
    seeded = {
        "hash-a": {
            "count": 1,
            "total_score": 42,
            "scores": {},
            "question_types": {"empty": {"count": 0, "total": 0}},
        }
    }
    monkeypatch.setattr(feedback, "defaultdict", lambda factory: seeded)

    assert feedback.analyze_feedback_by_hash([]) == {
        "hash-a": {
            "count": 1,
            "avg_total": 42.0,
            "avg_scores": {},
            "avg_by_type": {},
        }
    }


def test_call_minimax_exits_when_attempt_iterator_is_empty(monkeypatch):
    """覆蓋 retry 迴圈自然離開的結構性分支，不發出外部請求。"""
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(
        api,
        "get",
        lambda section, key=None, default=None: (
            {"max_concurrent": 1, "min_interval_ms": 0}
            if section == "api" and key == "rate_limit"
            else default
        ),
    )
    monkeypatch.setattr(api, "_semaphore", None)
    monkeypatch.setattr(api, "_rate_wait", lambda: None)
    monkeypatch.setattr(api, "range", lambda _: (), raising=False)
    urlopen = Mock()
    monkeypatch.setattr(api.urllib.request, "urlopen", urlopen)

    assert api.call_minimax("system", "user") is None
    urlopen.assert_not_called()


@pytest.mark.parametrize("script_path", STREAM_GUARD_SCRIPTS, ids=lambda path: path.stem)
def test_script_stream_guards_support_streams_without_reconfigure(monkeypatch, script_path):
    """覆蓋三個腳本 stdout/stderr reconfigure guard 的 false 側。"""
    stdout = io.StringIO()
    stderr = io.StringIO()
    assert not hasattr(stdout, "reconfigure")
    assert not hasattr(stderr, "reconfigure")

    original_cwd = os.getcwd()
    original_path = sys.path[:]
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    try:
        namespace = runpy.run_path(
            str(script_path), run_name="__coverage_stream_guard__"
        )
        assert namespace["__name__"] == "__coverage_stream_guard__"
    finally:
        os.chdir(original_cwd)
        sys.path[:] = original_path
