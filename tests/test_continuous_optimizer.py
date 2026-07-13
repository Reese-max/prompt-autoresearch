# -*- coding: utf-8 -*-
"""api/continuous_optimizer.py 覆蓋補洞測試。

聚焦既有測試未覆蓋的部分：
1. run_continuous_loop 四條分支（回饋不足 / 無建議 / 優化成功 / 優化失敗）
2. __main__ CLI 入口（--analyze-only 與預設 loop 路徑），以 runpy 在行程內執行，
   透過 monkeypatch api.feedback / lib.io / time.sleep 隔離所有 I/O 與等待。
不做真實網路呼叫、不跑 subprocess（run_optimization_round 一律 stub 掉）。
"""
import runpy
import sys
import time
import warnings

import pytest

import api.continuous_optimizer as co
import api.feedback as feedback
import lib.io as lib_io


# --- run_continuous_loop ---

@pytest.fixture
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    return sleeps


def test_loop_waits_when_feedback_insufficient(monkeypatch, no_sleep, capsys):
    monkeypatch.setattr(co, "check_feedback_threshold", lambda m: (False, 3))
    called = []
    monkeypatch.setattr(co, "analyze_and_suggest", lambda: called.append(1))

    co.run_continuous_loop(max_rounds=1, min_feedback=10)

    out = capsys.readouterr().out
    assert "回饋數量不足 (3/10)" in out
    assert "持續優化迴圈結束" in out
    assert no_sleep == [60]
    assert called == []


def test_loop_skips_round_when_no_hints(monkeypatch, no_sleep, capsys):
    monkeypatch.setattr(co, "check_feedback_threshold", lambda m: (True, 12))
    monkeypatch.setattr(
        co, "analyze_and_suggest",
        lambda: {"total_feedback": 12, "hints": [], "weak_areas": {}},
    )
    runs = []
    monkeypatch.setattr(
        co, "run_optimization_round", lambda d, p: runs.append((d, p)) or True
    )

    co.run_continuous_loop(max_rounds=1)

    out = capsys.readouterr().out
    assert "無優化建議，跳過本輪" in out
    assert runs == []
    assert no_sleep == []  # 跳過本輪不會走到 sleep(5)


def test_loop_runs_optimization_success(monkeypatch, no_sleep, capsys):
    monkeypatch.setattr(co, "check_feedback_threshold", lambda m: (True, 15))
    monkeypatch.setattr(
        co, "analyze_and_suggest",
        lambda: {
            "total_feedback": 15,
            "hints": [{"target": "structure", "hint": "補強結構"}],
            "weak_areas": {},
        },
    )
    runs = []

    def fake_round(direction, parallel):
        runs.append((direction, parallel))
        return True

    monkeypatch.setattr(co, "run_optimization_round", fake_round)

    co.run_continuous_loop(max_rounds=1, parallel=4)

    out = capsys.readouterr().out
    assert "優化方向: structure (補強結構)" in out
    assert "優化成功！" in out
    assert runs == [("structure", 4)]
    assert no_sleep == [5]


def test_loop_reports_optimization_failure(monkeypatch, no_sleep, capsys):
    monkeypatch.setattr(co, "check_feedback_threshold", lambda m: (True, 20))
    monkeypatch.setattr(
        co, "analyze_and_suggest",
        lambda: {
            "total_feedback": 20,
            "hints": [{"target": "論證", "hint": "強化論證"}],
            "weak_areas": {},
        },
    )
    monkeypatch.setattr(co, "run_optimization_round", lambda d, p: False)

    co.run_continuous_loop(max_rounds=1)

    out = capsys.readouterr().out
    assert "優化失敗或未通過接受條件" in out


# --- __main__ CLI 入口（runpy 在行程內重新執行模組） ---

def run_module_as_main(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    with warnings.catch_warnings():
        # 模組已在 sys.modules，runpy 會發 RuntimeWarning，屬預期
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module("api.continuous_optimizer", run_name="__main__")


def test_main_analyze_only(monkeypatch, capsys):
    # 新執行的模組會重新 from api.feedback / lib.io import，patch 來源模組即可隔離
    monkeypatch.setattr(
        feedback, "get_feedback_summary",
        lambda: {"total_feedback": 3, "baseline_score": 80.0, "weak_areas": {"d": 1}},
    )
    monkeypatch.setattr(
        feedback, "generate_optimization_hints",
        lambda: [{"target": "structure", "hint": "補強"}],
    )
    logged = []
    monkeypatch.setattr(
        lib_io, "append_jsonl", lambda path, row: logged.append((path, row))
    )

    run_module_as_main(["continuous_optimizer.py", "--analyze-only"], monkeypatch)

    out = capsys.readouterr().out
    assert '"total_feedback": 3' in out
    assert len(logged) == 1
    assert logged[0][1]["event"] == "analysis"
    assert logged[0][1]["hints"] == [{"target": "structure", "hint": "補強"}]


def test_main_default_runs_loop(monkeypatch, capsys):
    # 預設路徑會進 run_continuous_loop；全部 stub 掉確保無 I/O、無 subprocess、不等待
    monkeypatch.setattr(
        feedback, "get_feedback_summary",
        lambda: {"total_feedback": 0, "baseline_score": None, "weak_areas": {}},
    )
    monkeypatch.setattr(feedback, "generate_optimization_hints", lambda: [])
    monkeypatch.setattr(lib_io, "append_jsonl", lambda path, row: None)
    monkeypatch.setattr(lib_io, "read_jsonl", lambda path, limit=None: [])
    monkeypatch.setattr(time, "sleep", lambda s: None)

    run_module_as_main(
        ["continuous_optimizer.py", "--max-rounds", "1", "--min-feedback", "0"],
        monkeypatch,
    )

    out = capsys.readouterr().out
    assert "持續優化迴圈" in out
    assert "持續優化迴圈結束" in out
