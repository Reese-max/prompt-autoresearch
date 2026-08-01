# -*- coding: utf-8 -*-
"""候選比較前的產出完整性回歸測試。"""
import json

import pytest

import scripts.compare_runs as compare_runs


def _record(score, answer):
    return {
        "id": "q1",
        "type": "事實",
        "answer": answer,
        "total_score": score,
        "failures": [],
        "char_count": 1000,
        "risk_score": 10,
    }


def _write_details(run_dir, record):
    run_dir.mkdir(parents=True, exist_ok=True)
    details = run_dir / "details.jsonl"
    details.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return details


def _prepare_runs(tmp_path):
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    _write_details(baseline, _record(80, "基準答案"))
    details = _write_details(candidate, _record(86, "有效候選答案"))
    return baseline, candidate, details


def test_unchanged_valid_output_remains_eligible_for_selection(tmp_path):
    """產出內容與驗證結果未變時，應維持既有完成與選優流程。"""
    baseline, candidate, _details = _prepare_runs(tmp_path)

    passed, average, difference = compare_runs.compare(str(candidate), str(baseline))

    assert (passed, average, difference) == (True, 86.0, 6.0)
    assert compare_runs.LAST_COMPARISON["type_breakthroughs"]


@pytest.mark.parametrize("mutation", ["deleted", "cleared", "tampered"])
def test_changed_output_loses_completion_and_selection_eligibility(tmp_path, mutation):
    """候選比較前產出被刪除、清空或竄改時，不得沿用先前的有效結果。"""
    baseline, candidate, details = _prepare_runs(tmp_path)

    initial = compare_runs.compare(str(candidate), str(baseline))
    assert initial == (True, 86.0, 6.0)

    if mutation == "deleted":
        details.unlink()
    elif mutation == "cleared":
        details.write_text("", encoding="utf-8")
    else:
        _write_details(candidate, _record(0, ""))

    compare_runs.LAST_COMPARISON = {}
    if mutation in {"deleted", "cleared"}:
        with pytest.raises(SystemExit) as exc_info:
            compare_runs.compare(str(candidate), str(baseline))
        assert exc_info.value.code == 1
        assert compare_runs.LAST_COMPARISON == {}
    else:
        rejected = compare_runs.compare(str(candidate), str(baseline))
        assert rejected == (False, 0.0, 0.0)
        assert compare_runs.LAST_COMPARISON["completion_status"] == "failed"
        assert compare_runs.LAST_COMPARISON["reason_code"] == "NO_VALID_OUTPUT"
        assert compare_runs.LAST_COMPARISON["type_breakthroughs"] == []
