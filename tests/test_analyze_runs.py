# -*- coding: utf-8 -*-
"""scripts/analyze_runs.py 單元測試（tmp_path 隔離、無網路）。"""
import json
import os

import scripts.analyze_runs as ar


def _write_run(tmp_path, name, details=None, summary=None):
    run_dir = tmp_path / "runs" / name
    run_dir.mkdir(parents=True)
    if details is not None:
        with open(run_dir / "details.jsonl", "w", encoding="utf-8") as f:
            for row in details:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.write("\n")  # 空行應被忽略
    if summary is not None:
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False), encoding="utf-8"
        )
    return run_dir


def _detail(qtype="說明題", score=3.0, failures=(), qfile="questions/dev.jsonl"):
    return {
        "type": qtype,
        "total_score": score,
        "failures": list(failures),
        "question_file": qfile,
        "prompt_hash": "abc",
    }


class TestHelpers:
    def test_list_run_dirs_no_runs(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert ar.list_run_dirs() == []

    def test_list_run_dirs_skips_latest_and_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "runs" / "20260101").mkdir(parents=True)
        (tmp_path / "runs" / "latest").mkdir()
        (tmp_path / "runs" / "note.txt").write_text("x", encoding="utf-8")
        assert ar.list_run_dirs() == [os.path.join("runs", "20260101")]

    def test_load_json_missing(self, tmp_path):
        assert ar.load_json(str(tmp_path / "nope.json")) == {}

    def test_load_json_invalid(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        assert ar.load_json(str(p)) == {}

    def test_load_json_valid(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        assert ar.load_json(str(p)) == {"a": 1}

    def test_read_details_missing(self, tmp_path):
        assert ar.read_details(str(tmp_path)) == []

    def test_read_details_reads_lines(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_dir = _write_run(tmp_path, "r1", details=[_detail(), _detail(score=5)])
        rows = ar.read_details(str(run_dir))
        assert len(rows) == 2
        assert rows[1]["total_score"] == 5

    def test_normalize(self):
        assert ar.normalize("questions\\dev.jsonl") == "questions/dev.jsonl"


class TestSummarizeRun:
    def test_no_rows_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_dir = _write_run(tmp_path, "empty")
        assert ar.summarize_run(str(run_dir)) is None

    def test_computed_from_details(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        run_dir = _write_run(
            tmp_path,
            "r1",
            details=[
                _detail("說明題", 2, ["F1", "", "F2"]),
                _detail("說明題", 4, ["F1"]),
                _detail("比較題", 3),
            ],
        )
        result = ar.summarize_run(str(run_dir))
        assert result["question_file"] == "questions/dev.jsonl"
        assert result["prompt_hash"] == "abc"
        assert result["average_score"] == 3.0
        assert result["failure_counts"] == {"F1": 2, "F2": 1}
        assert result["type_averages"] == {"說明題": 3.0, "比較題": 3.0}

    def test_summary_json_overrides(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        summary = {
            "question_file": "questions\\dev.jsonl",
            "prompt_hash": "deadbeef",
            "average_score": 9.9,
            "failure_counts": {"X": 1},
            "type_averages": {"說明題": 9.9},
        }
        run_dir = _write_run(tmp_path, "r1", details=[_detail()], summary=summary)
        result = ar.summarize_run(str(run_dir))
        assert result["prompt_hash"] == "deadbeef"
        assert result["average_score"] == 9.9
        assert result["failure_counts"] == {"X": 1}
        assert result["question_file"] == "questions/dev.jsonl"


class TestMain:
    def test_json_output(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        _write_run(tmp_path, "r1", details=[_detail("說明題", 2, ["F1"])])
        _write_run(tmp_path, "r2", details=[_detail("說明題", 4, ["F1", "F2"])])
        # 不同題庫的 run 應被過濾
        _write_run(tmp_path, "r3", details=[_detail(qfile="questions/holdout.jsonl")])
        assert ar.main(["--json"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["question_file"] == "questions/dev.jsonl"
        assert len(payload["runs"]) == 2
        assert payload["failure_trend"] == {"F1": 2, "F2": 1}
        assert payload["type_average_trend"] == {"說明題": 3.0}

    def test_limit(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        for name in ("r1", "r2", "r3"):
            _write_run(tmp_path, name, details=[_detail()])
        assert ar.main(["--json", "--limit", "2"]) == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["runs"]) == 2
        # reversed → 最新的先納入
        assert payload["runs"][0]["run_dir"] == os.path.join("runs", "r3")

    def test_text_output(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        _write_run(tmp_path, "r1", details=[_detail("比較題", 5, ["FMT_BAD"])])
        assert ar.main([]) == 0
        out = capsys.readouterr().out
        assert "Prompt AutoResearch Run Trend" in out
        assert "FMT_BAD: 1" in out
        assert "比較題: 5.00" in out

    def test_text_output_no_runs(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert ar.main([]) == 0
        assert "無" in capsys.readouterr().out
