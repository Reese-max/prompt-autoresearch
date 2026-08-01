# -*- coding: utf-8 -*-
"""完成紀錄中的檔案證據清單與工作區邊界驗證。"""
import hashlib
import json

import pytest

from lib import completion_gate


def _task(root, artifact):
    return {
        "exit_code": 0,
        "artifacts": {"report": {"path": str(artifact)}},
        "results": [],
        "summary": {},
        "workspace_root": str(root),
    }


def test_completion_persists_relative_size_hash_and_verification(tmp_path):
    report = tmp_path / "runs" / "report.json"
    report.parent.mkdir()
    report.write_bytes(b"evidence\n")

    disposition = completion_gate.completion_disposition(_task(tmp_path, report))

    assert disposition["status"] == "completed"
    assert disposition["evidence_errors"] == []
    assert disposition["evidence_manifest"] == [{
        "path": "runs/report.json",
        "size": report.stat().st_size,
        "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "verified": True,
    }]


@pytest.mark.parametrize("content,expected", [(b"", "empty"), (None, "outside")])
def test_invalid_file_evidence_is_rejected(tmp_path, content, expected):
    root = tmp_path / "repo"
    root.mkdir()
    if expected == "empty":
        artifact = root / "empty.json"
        artifact.write_bytes(content)
    else:
        artifact = tmp_path / "outside.json"
        artifact.write_bytes(b"outside")

    disposition = completion_gate.completion_disposition(_task(root, artifact))

    assert disposition["status"] == "failed"
    assert disposition["evidence_manifest"] == []
    assert expected in disposition["evidence_errors"][0]


def test_unreadable_file_evidence_is_rejected(tmp_path, monkeypatch):
    report = tmp_path / "report.json"
    report.write_text("report", encoding="utf-8")

    def fail_open(*_args, **_kwargs):
        raise OSError("read denied")

    monkeypatch.setattr(completion_gate, "open", fail_open, raising=False)
    disposition = completion_gate.completion_disposition(_task(tmp_path, report))

    assert disposition["status"] == "failed"
    assert "unreadable" in disposition["evidence_errors"][0]


def test_saved_summary_contains_verified_evidence_manifest(tmp_path, monkeypatch):
    from scripts import evaluate

    monkeypatch.chdir(tmp_path)
    summary = {
        "timestamp": "2026-08-01 00:00:00",
        "prompt_file": "prompt.md",
        "prompt_hash": "a" * 64,
        "question_file": "questions.jsonl",
        "total_questions": 1,
        "average_score": 80.0,
        "type_averages": {},
        "failure_counts": {},
        "word_count_pass_rate": 100.0,
        "risk_perfect_rate": 100.0,
        "elapsed_seconds": 0.1,
        "char_count": 10,
    }
    result = {"id": 1, "type": "案例題", "total_score": 80, "char_count": 10, "failures": []}

    run_dir = evaluate.save_run_results(summary, [result])
    saved = json.loads((tmp_path / run_dir / "summary.json").read_text(encoding="utf-8"))
    run_rel = run_dir.replace("\\", "/")

    assert saved["evidence_manifest"]
    assert {item["path"] for item in saved["evidence_manifest"]} == {
        f"{run_rel}/details.jsonl",
        f"{run_rel}/summary.md",
    }
    assert all(item["size"] > 0 and item["verified"] for item in saved["evidence_manifest"])
