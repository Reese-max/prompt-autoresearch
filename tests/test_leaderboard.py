# -*- coding: utf-8 -*-
"""scripts/leaderboard.py 單元測試（tmp_path 隔離、無網路）。"""
import json
import sys

import scripts.leaderboard as lb


def _write_summary(tmp_path, name, **overrides):
    run_dir = tmp_path / "runs" / name
    run_dir.mkdir(parents=True)
    summary = {
        "question_file": "questions/dev.jsonl",
        "average_score": 3.5,
        "risk_perfect_rate": 10.0,
        "prompt_file": "prompts/current.md",
        "prompt_hash": "abcdef1234567890",
        "type_averages": {"說明題": 4.0, "比較題": 3.0},
        "failure_counts": {"F1": 3, "F2": 1},
    }
    summary.update(overrides)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False), encoding="utf-8"
    )
    return run_dir


class TestLoadJson:
    def test_missing(self, tmp_path):
        assert lb.load_json(str(tmp_path / "nope.json")) == {}

    def test_valid(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        assert lb.load_json(str(p)) == {"a": 1}


class TestListRuns:
    def test_no_runs_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert lb.list_runs() == []

    def test_filters_and_parses(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_summary(tmp_path, "r1")
        _write_summary(tmp_path, "r2", question_file="questions/holdout.jsonl")
        (tmp_path / "runs" / "latest").mkdir()
        (tmp_path / "runs" / "note.txt").write_text("x", encoding="utf-8")
        rows = lb.list_runs()
        assert len(rows) == 1
        row = rows[0]
        assert row["score"] == 3.5
        assert row["risk"] == 10.0
        assert row["prompt_hash"] == "abcdef123456"
        assert row["types"] == {"說明題": 4.0, "比較題": 3.0}

    def test_null_score_defaults_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_summary(tmp_path, "r1", average_score=None, risk_perfect_rate=None)
        rows = lb.list_runs()
        assert rows[0]["score"] == 0.0
        assert rows[0]["risk"] == 0.0


class TestMain:
    def test_ranked_output(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        _write_summary(tmp_path, "low", average_score=1.0)
        _write_summary(tmp_path, "high", average_score=5.0)
        monkeypatch.setattr(sys, "argv", ["leaderboard.py"])
        lb.main()
        lines = capsys.readouterr().out.strip().splitlines()
        assert lines[0].startswith("rank\tscore")
        assert "runs" in lines[1] and "high" in lines[1]  # 分數高者排前
        assert "說明題:4.00" in lines[1]
        assert "比較題:3.00" in lines[1]
        assert "F1:3" in lines[1]

    def test_limit_and_empty_types(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        _write_summary(tmp_path, "r1", type_averages={}, failure_counts={})
        _write_summary(tmp_path, "r2")
        monkeypatch.setattr(sys, "argv", ["leaderboard.py", "--limit", "1"])
        lb.main()
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 2  # header + 1 row

    def test_no_runs(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["leaderboard.py"])
        lb.main()
        lines = capsys.readouterr().out.strip().splitlines()
        assert len(lines) == 1
