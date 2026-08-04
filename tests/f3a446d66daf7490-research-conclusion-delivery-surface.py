# -*- coding: utf-8 -*-
"""研究結論交付表面：正常交付與 wedge 阻擋的最小正反案例。"""
import hashlib
import json
import re

import auto_evolve
import scripts.best_version_report as bvr
from scripts.research_validation_executor import (
    StagedValidationExecutor,
    WedgeDetected,
)


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _sandbox(tmp_path, monkeypatch):
    candidates = tmp_path / "prompts" / "candidates"
    candidates.mkdir(parents=True)
    (tmp_path / "prompts" / "champions").mkdir(parents=True)
    (tmp_path / "runs").mkdir()

    monkeypatch.setattr(bvr, "ROOT", str(tmp_path))
    monkeypatch.setattr(bvr, "BASELINE_META_PATH", str(tmp_path / "prompts" / "baseline.meta.json"))
    monkeypatch.setattr(bvr, "CHAMPIONS_DIR", str(tmp_path / "prompts" / "champions"))
    monkeypatch.setattr(bvr, "CANDIDATES_DIR", str(candidates))
    monkeypatch.setattr(bvr, "EVOLUTION_LOG_PATH", str(tmp_path / "evolution_log.jsonl"))
    monkeypatch.setattr(bvr, "CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(bvr, "RUNS_DIR", str(tmp_path / "runs"))

    baseline_prompt = tmp_path / "prompts" / "baseline.md"
    baseline_prompt.write_text("baseline research prompt\n", encoding="utf-8")
    _write_json(
        tmp_path / "prompts" / "baseline.meta.json",
        {
            "prompt_path": "prompts/baseline.md",
            "prompt_hash": bvr.sha256_file(str(baseline_prompt)),
            "smoke_avg": 80.0,
            "dev_avg": 80.0,
            "holdout_avg": 80.0,
        },
    )
    (tmp_path / "config.yaml").write_text(
        "thresholds:\n"
        "  dev_min_improvement: 2.0\n"
        "  type_max_regression: 3.0\n"
        "  word_rate_min: 85.0\n",
        encoding="utf-8",
    )
    (tmp_path / "evolution_log.jsonl").write_text(
        '{"event": "start", "timestamp": "2026-08-04 00:00:00"}\n'
        '{"event": "stop", "timestamp": "2026-08-04 00:01:00"}\n',
        encoding="utf-8",
    )
    return tmp_path


def _basis():
    return {
        "dataset": "questions/dev.jsonl",
        "metric": "average_score",
        "evaluator_version": "evaluate-v1",
        "measurement_settings": {"score_scale": "0-100"},
    }


def _successful_stage(score):
    return {
        "score": score,
        "execution_status": "quality_measurement_obtained",
        "measurement_evidence": {"complete": True},
    }


def _write_candidate(workspace, name, scores, execution_records, decision="ACCEPT", extra=None):
    prompt = workspace / "prompts" / "candidates" / f"{name}.md"
    prompt.write_text(f"{name} research candidate\n", encoding="utf-8")
    card = {
        "candidate_path": f"prompts/candidates/{name}.md",
        "candidate_hash": bvr.sha256_file(str(prompt)),
        "status": "completed",
        "final_decision": decision,
        "smoke": _successful_stage(scores["smoke"]),
        "dev": _successful_stage(scores["dev"]),
        "holdout": _successful_stage(scores["holdout"]),
        "execution_records": execution_records,
    }
    if extra:
        card.update(extra)
    _write_json(
        workspace / "prompts" / "candidates" / f"{name}.scorecard.json",
        card,
    )
    return card


def _ranking_card(name, score, execution_records):
    card = {
        "candidate_path": name,
        "status": "completed",
        "dev": {
            "score": score,
            **_basis(),
            "execution_status": "quality_measurement_obtained",
            "measurement_evidence": {"complete": True},
        },
        "execution_records": execution_records,
    }
    card["stage_evaluations"] = auto_evolve._candidate_stage_evaluations(
        card, require_execution=True,
    )
    return card


def _git_snapshot(head_commit, *, untracked=(), status_paths=(), diff_tracked="", diff_paths=(), porcelain=""):
    untracked = sorted(str(p).replace("\\", "/") for p in untracked)
    status_paths = sorted(str(p).replace("\\", "/") for p in status_paths)
    diff_paths = sorted(str(p).replace("\\", "/") for p in diff_paths)
    payload = {
        "head_commit": head_commit,
        "status_porcelain": porcelain,
        "diff_tracked": diff_tracked,
        "diff_paths": diff_paths,
        "untracked_files": untracked,
    }
    return {
        "head_commit": head_commit,
        "status_porcelain": porcelain,
        "diff_tracked": diff_tracked,
        "diff_paths": diff_paths,
        "untracked_files": untracked,
        "status_paths": status_paths,
        "changed_paths": sorted(set(status_paths + untracked)),
        "snapshot_hash": hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "captured_at": "2026-08-04T00:00:00Z",
        "workspace": "/sandbox",
    }


def _success_records():
    return [{
        "stage": "dev",
        "attempt": 1,
        "execution_status": "quality_measurement_obtained",
        "quality_measurement": {"metric": "average_score", "score": 92.0},
    }]


# ---------------------------------------------------------------------------
# 正常案例：兩個可比較候選成功排名，交付一致性通過
# ---------------------------------------------------------------------------


def test_normal_conclusion_delivery_ranks_and_produces_valid_report(tmp_path, monkeypatch):
    """正常路徑：兩個可比較候選成功排名，報告產生 valid 結論。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    commit = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"

    _write_candidate(
        workspace, "winner-candidate",
        {"smoke": 93.0, "dev": 92.0, "holdout": 91.0}, _success_records(),
    )
    _write_candidate(
        workspace, "runner-up-candidate",
        {"smoke": 87.0, "dev": 86.0, "holdout": 85.0}, _success_records(),
    )

    winner, ranking_report = auto_evolve._rank_candidate_evaluations([
        _ranking_card("winner-candidate", 92.0, _success_records()),
        _ranking_card("runner-up-candidate", 86.0, _success_records()),
    ])

    assert winner is not None
    assert winner["candidate_path"] == "winner-candidate"
    assert winner["score"] == 92.0
    assert winner["best_status"] == "proven"
    assert winner["best_scope"] == "global"

    report_rows = {row["candidate_path"]: row for row in ranking_report}
    assert report_rows["winner-candidate"]["outcome"] == "勝出"
    assert report_rows["runner-up-candidate"]["outcome"] == "落敗"
    assert len(report_rows) == 2

    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: _git_snapshot(commit))
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: commit)
    report = bvr.build_structured_report()

    assert report["decision"]["status"] == "valid"
    assert report["decision"]["code"] == "VALID"
    assert report["decision"]["best_candidate_id"] is not None
    assert report["delivery_consistency"]["valid"] is True
    assert report["delivery_consistency"]["status"] == "proven"
    assert report["quality_ranking"]["best_status"] == "proven"
    assert report["quality_ranking"]["best_scope"] == "global"
    assert len(report["quality_ranking"]["eligible_candidate_ids"]) == 2


def test_normal_conclusion_delivery_preserves_execution_reliability(tmp_path, monkeypatch):
    """正常路徑：失敗 attempt 的可靠性證據不影響排名但被保留。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    commit = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"

    failed_attempts = [
        {"stage": "dev", "attempt": 1, "execution_status": "timeout",
         "score": 999.0, "error_evidence": {"stderr": "timed out"}},
        {"stage": "dev", "attempt": 2, "execution_status": "model_or_evaluator_error",
         "score": 1000.0, "error_evidence": {"stderr": "model request failed"}},
    ]
    success_attempt = {
        "stage": "dev", "attempt": 3,
        "execution_status": "quality_measurement_obtained",
        "quality_measurement": {"metric": "average_score", "score": 91.0},
    }
    all_records = failed_attempts + [success_attempt]

    _write_candidate(
        workspace, "resilient-candidate",
        {"smoke": 92.0, "dev": 91.0, "holdout": 90.0}, all_records,
    )
    _write_candidate(
        workspace, "simple-candidate",
        {"smoke": 91.0, "dev": 90.0, "holdout": 89.0}, [success_attempt],
    )

    winner, ranking_report = auto_evolve._rank_candidate_evaluations([
        _ranking_card("resilient-candidate", 91.0, all_records),
        _ranking_card("simple-candidate", 90.0, [success_attempt]),
    ])

    assert winner["candidate_path"] == "resilient-candidate"
    resilient_row = next(r for r in ranking_report if r["candidate_path"] == "resilient-candidate")
    assert resilient_row["execution_reliability"]["attempt_count"] == 3
    assert resilient_row["execution_reliability"]["failed_attempt_count"] == 2
    assert resilient_row["execution_reliability"]["timeout_attempt_count"] == 1
    assert len(resilient_row["execution_reliability"]["failed_attempts"]) == 2

    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: _git_snapshot(commit))
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: commit)
    report = bvr.build_structured_report()

    delivered = next(
        row for row in report["candidate_comparison"]
        if "resilient-candidate" in row["path"]
    )
    assert delivered["execution_reliability"]["attempt_count"] == 3
    assert delivered["execution_reliability"]["failed_attempt_count"] == 2
    assert delivered["quality_eligible"] is True


# ---------------------------------------------------------------------------
# Wedge 案例：executor 偵測到 wedge 時阻擋交付
# ---------------------------------------------------------------------------


def test_wedge_blocks_ensure_delivery_allowed(tmp_path):
    """Wedge 狀態觸發 WedgeDetected，阻止報告寫入結論。"""
    state_path = tmp_path / "validation.json"

    def stalled(context):
        import time as _time
        _time.sleep(0.08)

    state = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={stage: 1 for stage in (
            "candidate_evaluation", "evidence_validation", "ranking", "report_delivery",
        )},
        no_progress_seconds=0.02,
        monitor_interval_seconds=0.005,
    ).run({"candidate_evaluation": stalled})

    assert state["status"] == "wedge"
    assert state["wedge"]["stage"] == "candidate_evaluation"
    assert state["wedge"]["code"] == "INCOMPLETE_EVIDENCE"
    assert state["global_best_allowed"] is False
    assert state["deliverable_allowed"] is False
    assert state["decision"]["code"] == "INCOMPLETE_EVIDENCE"


def test_wedge_stage_context_raises_on_heartbeat_check(tmp_path):
    """已 wedge 的 executor 在 check_stage_health 時拋出 WedgeDetected。"""
    state_path = tmp_path / "validation.json"

    def candidate(context):
        import time as _time
        _time.sleep(0.08)

    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={stage: 1 for stage in (
            "candidate_evaluation", "evidence_validation", "ranking", "report_delivery",
        )},
        no_progress_seconds=0.02,
        monitor_interval_seconds=0.005,
    )
    executor.run({"candidate_evaluation": candidate})

    assert executor.state["status"] == "wedge"
    assert executor.state.get("deliverable_allowed") is False


def test_wedge_prevents_later_stages_from_running(tmp_path):
    """Wedge 發生在第一階段後，後續階段不會執行 callback。"""
    state_path = tmp_path / "validation.json"
    called = []

    def stalled(context):
        import time as _time
        _time.sleep(0.08)

    def must_not_run(context):
        called.append(context.stage)

    state = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={stage: 1 for stage in (
            "candidate_evaluation", "evidence_validation", "ranking", "report_delivery",
        )},
        no_progress_seconds=0.02,
        monitor_interval_seconds=0.005,
    ).run({
        "candidate_evaluation": stalled,
        "evidence_validation": must_not_run,
        "ranking": must_not_run,
        "report_delivery": must_not_run,
    })

    assert state["status"] == "wedge"
    assert called == []
    for stage in ("evidence_validation", "ranking", "report_delivery"):
        assert state["stages"][stage]["status"] == "blocked"


# ---------------------------------------------------------------------------
# Wedge 案例：全失敗候選不得產生結論
# ---------------------------------------------------------------------------


def test_all_failed_candidates_blocks_conclusion(tmp_path, monkeypatch):
    """只有逾時/模型失敗的候選不得產生最佳版本結論。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    failed_records = [
        {"stage": "dev", "attempt": 1, "execution_status": "timeout",
         "score": 999.0, "error_evidence": {"stderr": "evaluation timed out"}},
        {"stage": "dev", "attempt": 2, "execution_status": "model_or_evaluator_error",
         "score": 1000.0, "error_evidence": {"stderr": "model request failed"}},
    ]
    for name in ("timeout-candidate", "model-failure-candidate"):
        _write_candidate(
            workspace, name,
            {"smoke": None, "dev": None, "holdout": None},
            failed_records,
        )

    report = bvr.build_structured_report()

    assert report["decision"]["status"] == "inconclusive"
    assert report["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert report["decision"]["best_candidate_id"] is None
    assert report["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    assert report["quality_ranking"]["eligible_candidate_ids"] == []
    assert len(report["quality_ranking"]["excluded_candidate_ids"]) == 2


# ---------------------------------------------------------------------------
# Wedge 案例：HEAD 不一致阻擋結論
# ---------------------------------------------------------------------------


def test_head_mismatch_blocks_conclusion(tmp_path, monkeypatch):
    """HEAD 與報告宣稱 commit 不符時，拒絕最佳結論。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    actual = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"
    claimed = "11ab7c5e654ede346e90fdca62393c890e5e6395"

    _write_candidate(
        workspace, "good-candidate",
        {"smoke": 92.0, "dev": 91.0, "holdout": 90.0}, _success_records(),
    )
    _write_candidate(
        workspace, "compare-candidate",
        {"smoke": 91.0, "dev": 90.0, "holdout": 89.0}, _success_records(),
    )

    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: _git_snapshot(actual))
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: claimed)
    report = bvr.build_structured_report()

    assert report["delivery_consistency"]["valid"] is False
    assert report["delivery_consistency"]["status"] == "unproven"
    assert report["decision"]["status"] == "inconclusive"
    assert report["decision"]["best_candidate_id"] is None
    assert report["quality_ranking"]["best_status"] == "unproven"


# ---------------------------------------------------------------------------
# 結論交付表面結構完整性
# ---------------------------------------------------------------------------


def test_conclusion_delivery_surface_includes_all_expected_keys(tmp_path, monkeypatch):
    """交付表面包含所有必要的結構化欄位。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    commit = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"

    _write_candidate(
        workspace, "surface-candidate",
        {"smoke": 92.0, "dev": 91.0, "holdout": 90.0}, _success_records(),
    )
    _write_candidate(
        workspace, "surface-compare",
        {"smoke": 91.0, "dev": 90.0, "holdout": 89.0}, _success_records(),
    )

    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: _git_snapshot(commit))
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: commit)
    report = bvr.build_structured_report()

    expected_keys = [
        "decision", "evidence_integrity", "delivery_consistency",
        "winner", "quality", "quality_ranking", "candidate_comparison",
        "reproduction", "execution_log", "execution_identity",
        "rerun_settings", "environment", "commands",
    ]
    for key in expected_keys:
        assert key in report, f"缺少必要欄位: {key}"

    assert isinstance(report["decision"], dict)
    assert isinstance(report["delivery_consistency"], dict)
    assert isinstance(report["quality_ranking"], dict)
    assert isinstance(report["candidate_comparison"], list)
    assert isinstance(report["reproduction"], dict)
    assert isinstance(report["execution_identity"], dict)
    assert isinstance(report["execution_identity"]["deliverable_allowed"], bool)
