# -*- coding: utf-8 -*-
"""候選評測 attempt 的狀態分類與品質分數防偽。"""
import json
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
