# -*- coding: utf-8 -*-
"""tests/test_compare_runs.py — scripts/compare_runs.py 單元測試（無網路、tmp_path 隔離）。"""
import json
import os
import runpy
import sys

import pytest

import scripts.compare_runs as cr

SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "compare_runs.py",
)


def make_run(dirpath, records):
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "details.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.write("\n")  # 空行分支
    return str(dirpath)


def rec(qid, qtype="事實", score=80.0, failures=None, char_count=1000, risk=10):
    return {
        "id": qid,
        "type": qtype,
        "total_score": score,
        "failures": failures or [],
        "char_count": char_count,
        "risk_score": risk,
    }


# ---------- acceptance_mode ----------

def test_acceptance_mode_default(monkeypatch):
    monkeypatch.delenv("AUTORESEARCH_ACCEPTANCE_MODE", raising=False)
    assert cr.acceptance_mode() == "pragmatic"


def test_acceptance_mode_env_and_empty(monkeypatch):
    monkeypatch.setenv("AUTORESEARCH_ACCEPTANCE_MODE", " STRICT ")
    assert cr.acceptance_mode() == "strict"
    monkeypatch.setenv("AUTORESEARCH_ACCEPTANCE_MODE", "   ")
    assert cr.acceptance_mode() == "pragmatic"


# ---------- load_details ----------

def test_load_details_from_dir(tmp_path):
    d = make_run(tmp_path / "run", [rec("q1"), rec("q2")])
    data = cr.load_details(d)
    assert set(data) == {"q1", "q2"}


def test_load_details_direct_file(tmp_path):
    d = make_run(tmp_path / "run", [rec("q1")])
    data = cr.load_details(os.path.join(d, "details.jsonl"))
    assert set(data) == {"q1"}


def test_load_details_missing(tmp_path):
    assert cr.load_details(str(tmp_path / "nope")) is None


# ---------- compare：接受路徑 ----------

def test_compare_accept_with_breakthrough(tmp_path, capsys):
    base = make_run(tmp_path / "base", [
        rec("q1", "事實", 80.0), rec("q2", "推理", 78.0),
    ])
    new = make_run(tmp_path / "new", [
        rec("q1", "事實", 86.0), rec("q2", "推理", 84.0),
    ])
    passed, avg_new, diff = cr.compare(new, base, mode="pragmatic")
    assert passed is True
    assert avg_new == pytest.approx(85.0)
    assert diff == pytest.approx(6.0)
    out = capsys.readouterr().out
    assert "ACCEPT" in out
    assert "局部突破候選" in out  # diff >= 5 且風險率不降
    lc = cr.LAST_COMPARISON
    assert lc["passed"] is True
    assert lc["risk_rate"] == 100.0
    assert len(lc["type_breakthroughs"]) == 2


def test_compare_accept_high_score_no_improvement(tmp_path, capsys):
    base = make_run(tmp_path / "base", [rec("q1", score=93.0)])
    new = make_run(tmp_path / "new", [rec("q1", score=93.0)])
    passed, avg_new, diff = cr.compare(new, base, mode="pragmatic")
    assert passed is True  # 均分 >= 92 且不退步
    assert diff == pytest.approx(0.0)


# ---------- compare：拒絕路徑 ----------

def test_compare_reject_all_criteria(tmp_path, capsys):
    base = make_run(tmp_path / "base", [
        rec("q1", "事實", 90.0), rec("q2", "推理", 88.0, failures=["F03"]),
    ])
    new = make_run(tmp_path / "new", [
        rec("q1", "事實", 70.0, failures=["F12"], char_count=100, risk=5),
        rec("q2", "推理", 72.0, failures=["F12", "F12", ""], char_count=2000, risk=5),
    ])
    passed, avg_new, diff = cr.compare(new, base, mode="pragmatic")
    assert passed is False
    out = capsys.readouterr().out
    assert "REVERT" in out
    assert "警告" in out  # c4 字數合格率警告分支
    lc = cr.LAST_COMPARISON
    assert lc["passed"] is False
    assert lc["failure_new"]["F12"] == 3
    assert lc["word_rate"] == 0.0
    assert lc["type_breakthroughs"] == []


def test_compare_strict_mode_risk_gate(tmp_path):
    base = make_run(tmp_path / "base", [rec("q1", risk=10)])
    new = make_run(tmp_path / "new", [rec("q1", score=90.0, risk=9)])
    passed, _, _ = cr.compare(new, base, mode="strict")
    assert passed is False  # strict 要求風險滿分率 100%
    assert cr.LAST_COMPARISON["acceptance_mode"] == "strict"


def test_compare_strict_mode_pass(tmp_path):
    base = make_run(tmp_path / "base", [rec("q1", score=80.0)])
    new = make_run(tmp_path / "new", [rec("q1", score=85.0)])
    passed, _, _ = cr.compare(new, base, mode="strict")
    assert passed is True


def test_compare_mode_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTORESEARCH_ACCEPTANCE_MODE", "strict")
    base = make_run(tmp_path / "base", [rec("q1")])
    new = make_run(tmp_path / "new", [rec("q1", score=85.0, risk=9)])
    passed, _, _ = cr.compare(new, base)
    assert passed is False
    assert cr.LAST_COMPARISON["acceptance_mode"] == "strict"


# ---------- compare：邊界 ----------

def test_compare_missing_new_data_exits(tmp_path, capsys):
    base = make_run(tmp_path / "base", [rec("q1")])
    with pytest.raises(SystemExit) as e:
        cr.compare(str(tmp_path / "missing"), base)
    assert e.value.code == 1
    assert "無法載入新運行數據" in capsys.readouterr().out


def test_compare_missing_baseline_self_analysis(tmp_path, capsys):
    new = make_run(tmp_path / "new", [rec("q1", score=85.0)])
    passed, avg_new, diff = cr.compare(new, str(tmp_path / "missing"), mode="pragmatic")
    out = capsys.readouterr().out
    assert "無基準自我分析" in out
    assert passed is True  # diff = 85 - 0 >= 2
    assert diff == pytest.approx(85.0)
    assert cr.LAST_COMPARISON["base_risk_rate"] == 0
    assert cr.LAST_COMPARISON["type_breakthroughs"] == []  # base_avg=0 不算突破


def test_compare_type_regression_gate(tmp_path):
    base = make_run(tmp_path / "base", [
        rec("q1", "事實", 90.0), rec("q2", "推理", 60.0),
    ])
    new = make_run(tmp_path / "new", [
        rec("q1", "事實", 80.0), rec("q2", "推理", 80.0),
    ])
    passed, _, _ = cr.compare(new, base, mode="pragmatic")
    assert passed is False  # 事實退步 10 分 > 3 分限制


# ---------- CLI (__main__) ----------

def run_cli(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    runpy.run_path(SCRIPT_PATH, run_name="__main__")


def test_cli_usage_error(monkeypatch, capsys):
    with pytest.raises(SystemExit) as e:
        run_cli(["compare_runs.py"], monkeypatch)
    assert e.value.code == 1
    assert "用法" in capsys.readouterr().out


def test_cli_with_mode(tmp_path, monkeypatch, capsys):
    base = make_run(tmp_path / "base", [rec("q1")])
    new = make_run(tmp_path / "new", [rec("q1", score=85.0)])
    run_cli(["compare_runs.py", new, base, "--mode", "strict"], monkeypatch)
    assert "mode=strict" in capsys.readouterr().out


def test_cli_mode_flag_without_value(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AUTORESEARCH_ACCEPTANCE_MODE", raising=False)
    base = make_run(tmp_path / "base", [rec("q1")])
    new = make_run(tmp_path / "new", [rec("q1", score=85.0)])
    run_cli(["compare_runs.py", new, base, "--mode"], monkeypatch)
    assert "mode=pragmatic" in capsys.readouterr().out  # IndexError → 預設


def test_cli_without_mode_flag_uses_env_default(tmp_path, monkeypatch, capsys):
    """CLI 不帶 --mode → cli_mode=None，acceptance_mode() 走 env 預設 pragmatic。"""
    monkeypatch.delenv("AUTORESEARCH_ACCEPTANCE_MODE", raising=False)
    base = make_run(tmp_path / "base", [rec("q1")])
    new = make_run(tmp_path / "new", [rec("q1", score=85.0)])
    run_cli(["compare_runs.py", new, base], monkeypatch)
    assert "mode=pragmatic" in capsys.readouterr().out


def test_compare_base_falsy_failure_not_counted(tmp_path, capsys):
    """base 端 failures 含空字串時不得計入 failure_base（`if f:` 邊界）。"""
    base = make_run(tmp_path / "base", [rec("q1", failures=["F03", ""])])
    new = make_run(tmp_path / "new", [rec("q1", score=86.0)])
    cr.compare(new, base, mode="pragmatic")
    assert cr.LAST_COMPARISON["failure_base"] == {"F03": 1}
    assert "" not in cr.LAST_COMPARISON["failure_base"]
    assert cr.LAST_COMPARISON["failure_new"] == {}
