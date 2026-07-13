# -*- coding: utf-8 -*-
"""tests/test_experiment_report.py — scripts/experiment_report.py 單元測試（tmp_path 隔離、無網路）。"""
import json
import os
import sys

import pytest

import scripts.experiment_report as er


# ---------- fixtures / helpers ----------

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """把 ROOT / RUNS_DIR / BASELINE_META 全指到 tmp_path，隔離真實 repo。"""
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(er, "ROOT", str(tmp_path))
    monkeypatch.setattr(er, "RUNS_DIR", str(runs))
    monkeypatch.setattr(er, "BASELINE_META", str(tmp_path / "prompts" / "baseline.meta.json"))
    return tmp_path


def write_run(tmp_path, name, summary, decision_text=None):
    run_dir = tmp_path / "runs" / name
    run_dir.mkdir(parents=True)
    with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)
    if decision_text is not None:
        with open(run_dir / "decision.md", "w", encoding="utf-8") as f:
            f.write(decision_text)
    return run_dir


def summary(dataset="dev", score=85.0, risk=100.0, word_rate=90.0, errors=0,
            types=None, failures=None):
    return {
        "question_file": f"data/{dataset}_questions.jsonl",
        "prompt_file": "prompts/current.txt",
        "prompt_hash": "abc123",
        "average_score": score,
        "risk_perfect_rate": risk,
        "word_count_pass_rate": word_rate,
        "char_count": 1000,
        "elapsed_seconds": 12.5,
        "estimated_api_calls": 30,
        "error_count": errors,
        "type_averages": types if types is not None else {"事實": 88.0, "推理": 82.0},
        "failure_counts": failures if failures is not None else {},
    }


# ---------- 純函式 ----------

def test_load_json_missing_and_present(tmp_path):
    assert er.load_json(str(tmp_path / "nope.json")) == {}
    p = tmp_path / "a.json"
    p.write_text('{"k": 1}', encoding="utf-8")
    assert er.load_json(str(p)) == {"k": 1}


def test_read_text_missing_and_present(tmp_path):
    assert er.read_text(str(tmp_path / "nope.md")) == ""
    p = tmp_path / "a.md"
    p.write_text("hello", encoding="utf-8")
    assert er.read_text(str(p)) == "hello"


@pytest.mark.parametrize("fname,expected", [
    ("data/smoke_q.jsonl", "smoke"),
    ("DEV_questions.jsonl", "dev"),
    ("holdout.jsonl", "holdout"),
    ("final_set.jsonl", "final"),
    ("other.jsonl", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
])
def test_dataset_name(fname, expected):
    assert er.dataset_name(fname) == expected


def test_parse_decision():
    text = "# 標題\n- decision: ACCEPT\n- direction: 精簡風格\n沒有匹配的行\n  - score_diff: +2.3  \n"
    data = er.parse_decision(text)
    assert data == {"decision": "ACCEPT", "direction": "精簡風格", "score_diff": "+2.3"}
    assert er.parse_decision("") == {}


def test_format_table():
    out = er.format_table(["a", "b"], [[1, "x"]])
    assert out.splitlines() == ["| a | b |", "| --- | --- |", "| 1 | x |"]


def test_best_worst_type():
    assert er.best_worst_type({}) == ("-", "-")
    best, worst = er.best_worst_type({"事實": 90.0, "推理": "70.5"})
    assert best == "事實 90.00"
    assert worst == "推理 70.50"


def test_gate_notes_all_and_none():
    clean = {"dataset": "dev", "word_rate": 90.0, "risk": 100.0, "errors": 0}
    assert er.gate_notes(clean) == []
    bad = {"dataset": "dev", "word_rate": 50.0, "risk": 80.0, "errors": 2}
    notes = er.gate_notes(bad)
    assert len(notes) == 3
    unknown = {"dataset": "unknown", "word_rate": 0.0, "risk": 100.0, "errors": 0}
    assert er.gate_notes(unknown) == []  # unknown 無字數門檻


def test_top_rows_sorts_and_limits():
    rows = [
        {"dataset": "dev", "score": 70.0},
        {"dataset": "dev", "score": 90.0},
        {"dataset": "smoke", "score": 99.0},
        {"dataset": "dev", "score": 80.0},
    ]
    top = er.top_rows(rows, "dev", 2)
    assert [r["score"] for r in top] == [90.0, 80.0]


def test_collect_decisions():
    rows = [
        {"decision": {"direction": "d1", "decision": "ACCEPT"}},
        {"decision": {"direction": "d1", "decision": "REVERT"}},
        {"decision": {"decision": "REJECT"}},
        {"decision": {"direction": "d2"}},
        {"decision": {}},
    ]
    totals, by_direction = er.collect_decisions(rows)
    assert totals == {"ACCEPT": 1, "REVERT": 1, "REJECT": 1, "UNKNOWN": 1}
    assert by_direction["d1"] == {"ACCEPT": 1, "REVERT": 1}
    assert by_direction["未標記"] == {"REJECT": 1}
    assert by_direction["d2"] == {"UNKNOWN": 1}


def test_collect_failure_trends():
    rows = [
        {"dataset": "dev", "failures": {"F01": 2}, "types": {"事實": 80.0, "推理": 60.0}},
        {"dataset": "dev", "failures": {"F01": 1, "F02": 3}, "types": {"事實": 90.0}},
        {"dataset": "smoke", "failures": {"F99": 9}, "types": {"事實": 10.0}},
    ]
    failures, weak = er.collect_failure_trends(rows)
    assert failures == {"F01": 3, "F02": 3}
    assert weak[0] == (60.0, "推理", 1)  # 最弱在前
    assert weak[1] == (85.0, "事實", 2)


# ---------- list_runs ----------

def test_list_runs_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(er, "RUNS_DIR", str(tmp_path / "nonexistent"))
    assert er.list_runs() == []


def test_list_runs_filters_and_parses(sandbox):
    write_run(sandbox, "20260101-ok", summary(score=88.5),
              decision_text="- decision: ACCEPT\n- direction: 精簡\n")
    write_run(sandbox, "20260102-nodecision", summary(dataset="smoke"))
    (sandbox / "runs" / "20260103-empty").mkdir()  # 無 summary.json → 跳過
    (sandbox / "runs" / "latest").mkdir()  # latest → 跳過
    (sandbox / "runs" / "afile.txt").write_text("x", encoding="utf-8")  # 非目錄 → 跳過

    rows = er.list_runs()
    assert [r["name"] for r in rows] == ["20260101-ok", "20260102-nodecision"]
    r0 = rows[0]
    assert r0["dataset"] == "dev"
    assert r0["score"] == 88.5
    assert r0["decision"] == {"decision": "ACCEPT", "direction": "精簡"}
    assert r0["run_dir"] == os.path.join("runs", "20260101-ok")
    assert rows[1]["dataset"] == "smoke"
    assert rows[1]["decision"] == {}


def test_list_runs_handles_null_fields(sandbox):
    write_run(sandbox, "20260104-null", {
        "question_file": None,
        "average_score": None,
        "risk_perfect_rate": None,
        "word_count_pass_rate": None,
        "char_count": None,
        "elapsed_seconds": None,
        "estimated_api_calls": None,
        "error_count": None,
        "type_averages": None,
        "failure_counts": None,
    })
    rows = er.list_runs()
    assert len(rows) == 1
    assert rows[0]["score"] == 0.0
    assert rows[0]["types"] == {}
    assert rows[0]["dataset"] == "unknown"


# ---------- build_report ----------

def test_build_report_empty(sandbox):
    report = er.build_report([], limit=5)
    assert "_無資料_" in report
    assert "_尚無 decision.md 可統計_" in report
    assert "_沒有明顯治理門檻違規_" in report
    assert "常見 F-code：無" in report
    assert "baseline prompt hash：`-`" in report


def test_build_report_full(sandbox):
    meta_dir = sandbox / "prompts"
    meta_dir.mkdir()
    (meta_dir / "baseline.meta.json").write_text(json.dumps({
        "prompt_hash": "deadbeef",
        "dev_run": "runs/x",
        "dev_avg": 85.0,
        "holdout_run": "runs/y",
        "holdout_avg": 84.0,
    }), encoding="utf-8")

    write_run(sandbox, "20260101-dev-good", summary(score=90.0),
              decision_text="- decision: ACCEPT\n- direction: 精簡\n")
    write_run(sandbox, "20260102-dev-bad",
              summary(score=70.0, risk=80.0, word_rate=50.0, errors=1,
                      failures={"F12": 4, "F03": 1}),
              decision_text="- decision: REVERT\n- direction: 精簡\n")
    write_run(sandbox, "20260103-smoke", summary(dataset="smoke", score=75.0))
    write_run(sandbox, "20260104-holdout",
              summary(dataset="holdout", score=83.0, types={}))

    rows = er.list_runs()
    report = er.build_report(rows, limit=10)

    assert "baseline prompt hash：`deadbeef`" in report
    assert "掃描 runs：4" in report
    assert "ACCEPT=1" in report and "REVERT=1" in report
    assert "F12:4" in report
    assert "推理:" in report  # 平均最弱題型
    assert "字數合格率 50.0% < 85%" in report
    assert "風險滿分率 80.0% < 100%" in report
    assert "評估錯誤 1 筆" in report
    assert "通過治理檢查" in report
    assert "## 5. 下一輪 loop 建議" in report


# ---------- main ----------

def test_main_stdout_only(sandbox, monkeypatch, capsys):
    write_run(sandbox, "20260101-dev", summary())
    monkeypatch.setattr(sys, "argv", ["experiment_report.py"])
    er.main()
    out = capsys.readouterr().out
    assert "# Prompt AutoResearch 實驗治理報告" in out


def test_main_with_out_and_limit(sandbox, monkeypatch, capsys):
    write_run(sandbox, "20260101-dev", summary())
    monkeypatch.setattr(sys, "argv",
                        ["experiment_report.py", "--out", "output/report.md", "--limit", "1"])
    er.main()
    out_file = sandbox / "output" / "report.md"
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert content == capsys.readouterr().out.rstrip("\n") + "\n"
    assert "掃描 runs：1" in content
