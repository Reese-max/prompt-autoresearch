# -*- coding: utf-8 -*-
"""封存前驗證：reevaluation-derived benchmark 世系完整性與一致性。"""
import hashlib
import json

import auto_evolve


def _candidate_with_lineage(
    path="prompts/candidates/test.md",
    benchmark_id="benchmarks/a.jsonl",
    lineage=None,
    stage="dev",
    score=90.0,
):
    evaluation = {
        "stage": stage,
        "score": score,
        "comparable": True,
        "basis": {
            "stage": stage,
            "dataset": benchmark_id,
            "metric": "average_score",
            "evaluator_version": "evaluate-v1",
            "measurement_settings": {"score_scale": "0-100"},
        },
    }
    candidate = {
        "candidate_path": path,
        "benchmark_id": benchmark_id,
        "status": "evaluated",
        "stage_evaluations": [evaluation],
    }
    if lineage is not None:
        candidate["lineage"] = lineage
    return candidate


def _valid_lineage(
    baseline_id="benchmarks/a.jsonl",
    parent_version="v1",
    run_id="run-001",
    timestamp="2026-08-01 00:00:00",
    content_hash="abc123",
):
    return {
        "source_baseline_id": baseline_id,
        "parent_version": parent_version,
        "execution_run_id": run_id,
        "timestamp": timestamp,
        "content_hash": content_hash,
    }


# --- _validate_benchmark_lineage ---


def test_no_lineage_passes_validation():
    candidate = {"candidate_path": "prompts/candidates/test.md"}
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is True
    assert result["lineage_validated"] is False
    assert result["lineage_exclusion_reasons"] == []


def test_empty_lineage_dict_passes_validation():
    candidate = {"candidate_path": "prompts/candidates/test.md", "lineage": {}}
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is True
    assert result["lineage_validated"] is False


def test_valid_lineage_passes(tmp_path):
    prompt = tmp_path / "prompts" / "candidates" / "test.md"
    prompt.parent.mkdir(parents=True)
    content = "測試 prompt 內容"
    prompt.write_text(content, encoding="utf-8")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    lineage = _valid_lineage(content_hash=content_hash)
    candidate = _candidate_with_lineage(
        path=str(prompt),
        lineage=lineage,
    )
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is True
    assert result["lineage_validated"] is True
    assert result["lineage_exclusion_reasons"] == []


def test_missing_source_baseline_id_fails():
    lineage = _valid_lineage()
    del lineage["source_baseline_id"]
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_field_missing:source_baseline_id" in result["lineage_exclusion_reasons"]


def test_missing_parent_version_fails():
    lineage = _valid_lineage()
    del lineage["parent_version"]
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_field_missing:parent_version" in result["lineage_exclusion_reasons"]


def test_missing_execution_run_id_fails():
    lineage = _valid_lineage()
    del lineage["execution_run_id"]
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_field_missing:execution_run_id" in result["lineage_exclusion_reasons"]


def test_missing_timestamp_fails():
    lineage = _valid_lineage()
    del lineage["timestamp"]
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_field_missing:timestamp" in result["lineage_exclusion_reasons"]


def test_missing_content_hash_fails():
    lineage = _valid_lineage()
    del lineage["content_hash"]
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_field_missing:content_hash" in result["lineage_exclusion_reasons"]


def test_empty_string_fields_fail():
    lineage = _valid_lineage(
        baseline_id="",
        parent_version="",
        run_id="",
        timestamp="",
        content_hash="",
    )
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert len(result["lineage_exclusion_reasons"]) == 5


def test_content_hash_mismatch_fails(tmp_path):
    prompt = tmp_path / "prompts" / "candidates" / "test.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("實際內容", encoding="utf-8")

    lineage = _valid_lineage(content_hash="wrong_hash_value")
    candidate = _candidate_with_lineage(path=str(prompt), lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_content_hash_mismatch" in result["lineage_exclusion_reasons"]


def test_content_hash_match_passes(tmp_path):
    prompt = tmp_path / "prompts" / "candidates" / "test.md"
    prompt.parent.mkdir(parents=True)
    content = "正確的 prompt 內容"
    prompt.write_text(content, encoding="utf-8")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    lineage = _valid_lineage(content_hash=content_hash)
    candidate = _candidate_with_lineage(path=str(prompt), lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is True
    assert "lineage_content_hash_mismatch" not in result["lineage_exclusion_reasons"]


def test_cross_baseline_forgery_fails():
    lineage = _valid_lineage(baseline_id="benchmarks/a.jsonl")
    candidate = _candidate_with_lineage(
        benchmark_id="benchmarks/b.jsonl",
        lineage=lineage,
    )
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_cross_baseline_forgery" in result["lineage_exclusion_reasons"]


def test_same_baseline_no_forgery():
    lineage = _valid_lineage(baseline_id="benchmarks/a.jsonl")
    candidate = _candidate_with_lineage(
        benchmark_id="benchmarks/a.jsonl",
        lineage=lineage,
    )
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert "lineage_cross_baseline_forgery" not in result["lineage_exclusion_reasons"]


def test_circular_reference_detected():
    lineage = _valid_lineage(run_id="run-001")
    lineage["ancestor_chain"] = [
        {"execution_run_id": "run-001"},
    ]
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    assert "lineage_circular_reference" in result["lineage_exclusion_reasons"]


def test_no_circular_reference():
    lineage = _valid_lineage(run_id="run-003")
    lineage["ancestor_chain"] = [
        {"execution_run_id": "run-001"},
        {"execution_run_id": "run-002"},
    ]
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert "lineage_circular_reference" not in result["lineage_exclusion_reasons"]


def test_multiple_missing_fields_all_reported():
    lineage = {
        "source_baseline_id": None,
        "parent_version": None,
        "execution_run_id": None,
        "timestamp": None,
        "content_hash": None,
    }
    candidate = _candidate_with_lineage(lineage=lineage)
    result = auto_evolve._validate_benchmark_lineage(candidate)
    assert result["eligible"] is False
    for field in auto_evolve._LINEAGE_REQUIRED_FIELDS:
        assert f"lineage_field_missing:{field}" in result["lineage_exclusion_reasons"]


# --- Ranking exclusion ---


def _evaluation(stage, score, dataset="questions/dev.jsonl", version="evaluate-v1"):
    basis = {
        "stage": stage,
        "dataset": dataset,
        "metric": "average_score",
        "evaluator_version": version,
        "measurement_settings": {"max_workers": 24},
    }
    key = tuple(
        [stage, dataset, "average_score", version, auto_evolve._canonical_comparison_value(basis["measurement_settings"])]
    )
    return {"stage": stage, "score": score, "comparable": True, "basis": basis, "comparison_key": key}


def test_incomplete_evidence_candidate_excluded_from_ranking(tmp_path):
    prompt = tmp_path / "prompts" / "candidates" / "test.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("prompt 內容", encoding="utf-8")
    content_hash = hashlib.sha256("prompt 內容".encode("utf-8")).hexdigest()

    incomplete = _candidate_with_lineage(
        path=str(prompt),
        benchmark_id="benchmarks/a.jsonl",
        lineage=_valid_lineage(
            baseline_id="benchmarks/a.jsonl",
            content_hash=content_hash,
        ),
    )
    del incomplete["lineage"]["source_baseline_id"]

    good = _candidate_with_lineage(
        path=str(tmp_path / "prompts" / "candidates" / "good.md"),
        benchmark_id="benchmarks/a.jsonl",
    )
    (tmp_path / "prompts" / "candidates" / "good.md").write_text("good", encoding="utf-8")

    winner, report = auto_evolve._rank_candidate_evaluations([incomplete, good])

    assert winner is not None
    assert winner["candidate_path"] == str(tmp_path / "prompts" / "candidates" / "good.md")
    by_path = {row["candidate_path"]: row for row in report}
    incomplete_report = by_path[str(prompt)]
    assert incomplete_report["outcome"] == "淘汰"
    assert "incomplete_evidence" in incomplete_report["elimination_basis"]
    assert incomplete_report["lineage_validated"] is True
    assert len(incomplete_report["lineage_exclusion_reasons"]) > 0


def test_incomplete_evidence_not_in_benchmark_groups(tmp_path):
    prompt = tmp_path / "prompts" / "candidates" / "test.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("prompt 內容", encoding="utf-8")
    content_hash = hashlib.sha256("prompt 內容".encode("utf-8")).hexdigest()

    incomplete = _candidate_with_lineage(
        path=str(prompt),
        benchmark_id="benchmarks/a.jsonl",
        lineage=_valid_lineage(
            baseline_id="benchmarks/a.jsonl",
            content_hash=content_hash,
        ),
    )
    del incomplete["lineage"]["timestamp"]

    good = _candidate_with_lineage(
        path=str(tmp_path / "prompts" / "candidates" / "good.md"),
        benchmark_id="benchmarks/a.jsonl",
        score=95.0,
    )
    (tmp_path / "prompts" / "candidates" / "good.md").write_text("good", encoding="utf-8")

    winner, report = auto_evolve._rank_candidate_evaluations([incomplete, good])

    assert winner is not None
    groups = report[0].get("benchmark_groups", [])
    for group in groups:
        assert str(prompt) not in group.get("candidate_paths", [])


def test_valid_lineage_candidate_included_in_ranking(tmp_path):
    prompt = tmp_path / "prompts" / "candidates" / "test.md"
    prompt.parent.mkdir(parents=True)
    content = "有效 lineage prompt"
    prompt.write_text(content, encoding="utf-8")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    good = _candidate_with_lineage(
        path=str(prompt),
        benchmark_id="benchmarks/a.jsonl",
        lineage=_valid_lineage(
            baseline_id="benchmarks/a.jsonl",
            content_hash=content_hash,
        ),
        score=95.0,
    )

    other = _candidate_with_lineage(
        path=str(tmp_path / "prompts" / "candidates" / "other.md"),
        benchmark_id="benchmarks/a.jsonl",
        score=85.0,
    )
    (tmp_path / "prompts" / "candidates" / "other.md").write_text("other", encoding="utf-8")

    winner, report = auto_evolve._rank_candidate_evaluations([good, other])

    assert winner is not None
    assert winner["candidate_path"] == str(prompt)
    by_path = {row["candidate_path"]: row for row in report}
    assert by_path[str(prompt)]["outcome"] == "勝出"


def test_incomplete_evidence_excluded_from_historical_conclusions(tmp_path):
    prompt = tmp_path / "prompts" / "candidates" / "test.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("prompt", encoding="utf-8")

    incomplete = _candidate_with_lineage(
        path=str(prompt),
        benchmark_id="benchmarks/a.jsonl",
        lineage=_valid_lineage(
            baseline_id="benchmarks/a.jsonl",
            content_hash="wrong",
        ),
    )

    winner, report = auto_evolve._rank_candidate_evaluations([incomplete])

    assert winner is None
    by_path = {row["candidate_path"]: row for row in report}
    incomplete_report = by_path[str(prompt)]
    assert incomplete_report["outcome"] == "淘汰"
    assert "incomplete_evidence" in incomplete_report["elimination_basis"]
    assert incomplete_report.get("lineage_validated") is True


def test_scorecard_incomplete_evidence_reports(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cand_dir = tmp_path / "prompts" / "candidates"
    cand_dir.mkdir(parents=True)
    prompt = cand_dir / "lineage.md"
    prompt.write_text("candidate prompt", encoding="utf-8")
    (cand_dir / "lineage.scorecard.json").write_text(
        json.dumps({
            "candidate_path": "prompts/candidates/lineage.md",
            "status": "completed",
            "lineage": {
                "source_baseline_id": "benchmarks/a.jsonl",
                "parent_version": "v1",
                "execution_run_id": "run-001",
                "timestamp": "2026-08-01 00:00:00",
            },
            "dev": {
                "score": 90.0,
                "dataset": "questions/dev.jsonl",
                "metric": "average_score",
                "evaluator_version": "evaluate-v1",
                "measurement_settings": {"score_scale": "0-100"},
                "execution_status": "quality_measurement_obtained",
                "measurement_evidence": {"complete": True},
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    reports = auto_evolve._scorecard_elimination_reports(set())
    lineage_reports = [
        r for r in reports if r["candidate_path"] == "prompts/candidates/lineage.md"
    ]
    assert len(lineage_reports) == 1
    assert lineage_reports[0]["outcome"] == "淘汰"
    assert "incomplete_evidence" in lineage_reports[0]["elimination_basis"]
    assert lineage_reports[0]["lineage_validated"] is True
