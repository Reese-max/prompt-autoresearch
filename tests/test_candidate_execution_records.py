# -*- coding: utf-8 -*-
"""候選評測 attempt 的狀態分類與品質分數防偽。"""
import json
import subprocess
from types import SimpleNamespace

import pytest

import run_opt


def _result(**kwargs):
    values = {
        "returncode": 1,
        "stdout": "",
        "stderr": "",
        "execution_started_at": "2026-08-02T00:00:00.000Z",
        "execution_ended_at": "2026-08-02T00:00:01.000Z",
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _completion(status="failed", **kwargs):
    value = {
        "status": status,
        "rejection_reason": "無有效輸出",
        "rejection_reasons": ["無有效輸出"],
        "missing_evidence_types": ["quality_measurement"],
        "evidence_errors": [],
    }
    value.update(kwargs)
    return value


@pytest.mark.parametrize(
    ("result_kwargs", "completion", "expected"),
    [
        ({"timed_out": True}, _completion(), run_opt.EXECUTION_STATUS_TIMEOUT),
        ({"stderr": "HTTP 429 quota exceeded"}, _completion(), run_opt.EXECUTION_STATUS_QUOTA_ROUTING),
        ({"stderr": "evaluator crashed"}, _completion(), run_opt.EXECUTION_STATUS_MODEL_ERROR),
        ({"stderr": "invalid JSON output"}, _completion(), run_opt.EXECUTION_STATUS_INVALID_OUTPUT),
    ],
)
def test_failure_status_is_machine_readable_and_keeps_evidence(
    result_kwargs, completion, expected
):
    record = run_opt.build_candidate_execution_record(
        "dev", 1, _result(**result_kwargs), "runs/dev", {}, completion,
        candidate_id="prompts/candidates/candidate.md",
    )

    assert record["execution_status"] == expected
    assert record["failure_classification"] == expected
    assert record["model"]
    assert record["timeout"] is not None
    assert record["started_at"].endswith("Z")
    assert record["ended_at"].endswith("Z")
    assert record["error_evidence"]["stderr"] == result_kwargs.get("stderr", "")
    assert "quality_measurement" not in record


def test_success_record_is_the_only_record_with_quality_measurement():
    record = run_opt.build_candidate_execution_record(
        "smoke", 1, _result(returncode=0), "runs/smoke",
        {"score": 88.5, "error_count": 0},
        _completion("completed", rejection_reason="", rejection_reasons=[], missing_evidence_types=[]),
    )

    assert record["execution_status"] == run_opt.EXECUTION_STATUS_QUALITY_MEASUREMENT
    assert record["failure_classification"] is None
    assert record["quality_measurement"] == {"metric": "average_score", "score": 88.5}
    assert record["error_evidence"] == {}


def test_failed_scorecard_stage_has_no_stale_quality_score(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    candidate = tmp_path / "prompts" / "candidates" / "candidate.md"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("candidate", encoding="utf-8")
    candidate.with_suffix(".scorecard.json").write_text(
        json.dumps({"smoke": {"score": 99.0}}), encoding="utf-8"
    )

    run_opt.mark_candidate_evaluation_failed(
        str(candidate), "smoke", _result(stderr="invalid JSON output"), None, {}
    )

    card = json.loads(candidate.with_suffix(".scorecard.json").read_text(encoding="utf-8"))
    assert card["smoke"]["execution_status"] == run_opt.EXECUTION_STATUS_INVALID_OUTPUT
    assert "score" not in card["smoke"]
    assert len(card["execution_records"]) == 1
    assert "quality_measurement" not in card["execution_records"][0]


def test_candidate_timeout_persists_cancellation_and_attempt_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_opt, "list_run_dirs", lambda: [])

    def timeout_run(cmd, **kwargs):
        assert kwargs["timeout"] == 0.05
        error = subprocess.TimeoutExpired(cmd, kwargs["timeout"], output="partial", stderr="stuck")
        error.cancel_failed = True
        raise error

    monkeypatch.setattr(run_opt.subprocess, "run", timeout_run)
    candidate = tmp_path / "prompts" / "candidates" / "candidate.md"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("candidate", encoding="utf-8")

    result, run_dir, summary = run_opt.run_evaluate(
        str(candidate), "questions/smoke.jsonl", 1, capture=True,
        deadline_seconds=0.05, candidate_id=str(candidate),
    )
    completion = _completion(reason_code="TIMEOUT")
    record = run_opt.build_candidate_execution_record(
        "smoke", 1, result, run_dir, summary, completion,
        candidate_id=str(candidate),
    )
    run_opt.append_candidate_execution_record(str(candidate), record)

    card = json.loads(candidate.with_suffix(".scorecard.json").read_text(encoding="utf-8"))
    persisted = card["execution_records"][0]
    assert result.cancelled is False
    assert result.cancellation["status"] == "cancellation_failed"
    assert result.cancellation["residual_work"] is True
    assert persisted["execution_status"] == run_opt.EXECUTION_STATUS_TIMEOUT
    assert persisted["cancelled"] is False
    assert persisted["attempt_id"] == result.attempt_id
    assert persisted["original_attempt_id"] == result.original_attempt_id
    assert persisted["cancellation"]["status"] == "cancellation_failed"


def test_cancelled_candidate_does_not_block_next_candidate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_opt, "list_run_dirs", lambda: [])
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if len(calls) == 1:
            error = subprocess.TimeoutExpired(cmd, kwargs["timeout"])
            error.cancel_failed = True
            raise error
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run_opt.subprocess, "run", run)
    first, _, _ = run_opt._run_candidate_evaluation(
        "candidate-a", "smoke", "current.md", "questions/smoke.jsonl", 1, 0.01,
    )
    second, _, _ = run_opt._run_candidate_evaluation(
        "candidate-b", "smoke", "current.md", "questions/smoke.jsonl", 1, 0.01,
    )

    assert len(calls) == 2
    assert first.cancellation["status"] == "cancellation_failed"
    assert second.candidate_id == "candidate-b"
    assert first.attempt_id != second.attempt_id
    assert all(call[1]["timeout"] == 0.01 for call in calls)
