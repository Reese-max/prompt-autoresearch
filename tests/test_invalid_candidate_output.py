# -*- coding: utf-8 -*-
"""無有效評估產出不得成為候選比較或選優證據。"""
import json
from types import SimpleNamespace

import auto_evolve
import run_opt
import scripts.compare_runs as compare_runs
from lib.completion_gate import completion_disposition


def test_empty_completion_has_machine_readable_rejection():
    disposition = run_opt.evaluation_completion(SimpleNamespace(returncode=0), None, {})

    assert disposition["status"] == "failed"
    assert disposition["reason_code"] == "NO_VALID_OUTPUT"
    assert disposition["missing_evidence_types"]
    assert disposition["rejection_reasons"]


def test_nonzero_empty_completion_keeps_missing_evidence_types():
    disposition = completion_disposition({
        "exit_code": 1,
        "stdout": "",
        "stderr": "error",
        "artifacts": {},
        "results": [],
        "summary": {},
    })

    assert disposition["status"] == "failed"
    assert disposition["reason_code"] == "NONZERO_EXIT_CODE"
    assert disposition["missing_evidence_types"] == ["artifacts", "results", "summary"]


def test_failed_candidate_is_not_scanned_for_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidate_dir = tmp_path / "prompts" / "candidates"
    candidate_dir.mkdir(parents=True)
    candidate = candidate_dir / "candidate_failed.md"
    candidate.write_text("候選", encoding="utf-8")

    run_opt.mark_candidate_evaluation_failed(
        str(candidate),
        "smoke",
        SimpleNamespace(returncode=0),
        None,
        {},
    )
    card = json.loads(candidate.with_suffix(".scorecard.json").read_text(encoding="utf-8"))
    assert card["status"] == "failed"
    assert card["reason_code"] == "NO_VALID_OUTPUT"
    assert card["missing_evidence_types"]
    assert auto_evolve.scan_candidate_evaluations() == []


def test_rejected_candidate_with_stale_score_is_not_scanned_for_selection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidate_dir = tmp_path / "prompts" / "candidates"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "candidate_rejected.scorecard.json").write_text(
        json.dumps({
            "candidate_path": "prompts/candidates/candidate_rejected.md",
            "status": "rejected_smoke",
            "smoke": {"score": 99.0},
            "dev": {"score": 99.0},
        }),
        encoding="utf-8",
    )

    assert auto_evolve.scan_candidate_evaluations() == []


def test_empty_run_is_rejected_before_comparison(tmp_path):
    new_dir = tmp_path / "new"
    base_dir = tmp_path / "base"
    new_dir.mkdir()
    base_dir.mkdir()
    (new_dir / "details.jsonl").write_text(
        json.dumps({"id": 1, "total_score": 0, "answer": ""}) + "\n",
        encoding="utf-8",
    )
    (base_dir / "details.jsonl").write_text(
        json.dumps({"id": 1, "total_score": 80}) + "\n",
        encoding="utf-8",
    )

    passed, average, difference = compare_runs.compare(str(new_dir), str(base_dir))

    assert (passed, average, difference) == (False, 0.0, 0.0)
    assert compare_runs.LAST_COMPARISON["completion_status"] == "failed"
    assert compare_runs.LAST_COMPARISON["reason_code"] == "NO_VALID_OUTPUT"
    assert compare_runs.LAST_COMPARISON["missing_evidence_types"] == ["results"]
