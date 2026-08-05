# -*- coding: utf-8 -*-
"""1b982cbc9415d9fd-free-model-failure-timeout-correctness — 免費模型失敗／逾時偽高分不得影響品質聚合與排名。

以實際候選排名／報告入口（auto_evolve._rank_candidate_evaluations 與
run_controlled_closed_loop 報告）同時注入 model_error 與 timeout 的偽造高分結果，
以及至少兩個有效完成結果：

1. 先保存未過濾非完成狀態時會錯選的 red 證據（naive max-score 會選中偽造候選）
2. 修復後僅有效評測參與品質聚合、排名與淘汰
3. 報告分列有效結果與執行失敗（可靠性證據與淘汰原因分開）
"""
import json
import os

import auto_evolve

RED_EVIDENCE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "1b982cbc9415d9fd-free-model-failure-timeout-red-evidence.json",
)


def _basis(stage="dev", dataset="questions/dev.jsonl"):
    settings = {"max_workers": 24, "early_stop_threshold": None}
    return {
        "stage": stage,
        "dataset": dataset,
        "metric": "average_score",
        "evaluator_version": "evaluate-v1",
        "measurement_settings": settings,
    }


def _evaluation(score, execution_status="completed", measurement_evidence_complete=True):
    """單一 dev stage 評測；execution_status 可被偽造成 completed 藏起失敗。"""
    basis = _basis()
    comparison_key = tuple([
        "dev", "questions/dev.jsonl", "average_score", "evaluate-v1",
        auto_evolve._canonical_comparison_value(basis["measurement_settings"]),
    ])
    return {
        "stage": "dev",
        "score": score,
        "comparable": True,
        "basis": basis,
        "comparison_key": comparison_key,
        "execution_status": execution_status,
        "measurement_evidence_complete": measurement_evidence_complete,
    }


def _candidate(path, evaluation, status="evaluated", execution_records=None):
    return {
        "candidate_path": path,
        "status": status,
        "stage_evaluations": [evaluation],
        "execution_records": execution_records or [],
    }


def _forged_candidates():
    """model_error 與 timeout 的偽造高分候選：評測偽稱 completed，執行紀錄揭穿失敗。"""
    forged_model_error = _candidate(
        "forged-model-error",
        _evaluation(999.0),
        execution_records=[{
            "stage": "dev",
            "attempt": 1,
            "execution_status": "model_or_evaluator_error",
            "error_evidence": {"stderr": "model request failed"},
        }],
    )
    forged_timeout = _candidate(
        "forged-timeout",
        _evaluation(1000.0),
        execution_records=[{
            "stage": "dev",
            "attempt": 1,
            "execution_status": "timeout",
            "error_evidence": {"stderr": "evaluation timed out"},
        }],
    )
    return forged_model_error, forged_timeout


def _valid_candidates():
    """兩個有效完成結果，作為合法排名基準。"""
    valid_high = _candidate(
        "valid-high",
        _evaluation(90.0),
        execution_records=[{
            "stage": "dev",
            "attempt": 1,
            "execution_status": "quality_measurement_obtained",
            "quality_measurement": {"metric": "average_score", "score": 90.0},
        }],
    )
    valid_low = _candidate(
        "valid-low",
        _evaluation(85.0),
        execution_records=[{
            "stage": "dev",
            "attempt": 1,
            "execution_status": "quality_measurement_obtained",
            "quality_measurement": {"metric": "average_score", "score": 85.0},
        }],
    )
    return valid_high, valid_low


def _all_candidates():
    forged = _forged_candidates()
    valid = _valid_candidates()
    return list(forged) + list(valid)


def _naive_unfiltered_winner(candidates):
    """未過濾非完成狀態的錯選行為：只取最高分，完全忽略執行狀態。"""
    best = None
    best_score = None
    for candidate in candidates:
        for evaluation in candidate.get("stage_evaluations") or []:
            score = auto_evolve._finite_score(evaluation.get("score"))
            if score is not None and (best_score is None or score > best_score):
                best = candidate["candidate_path"]
                best_score = score
    return best, best_score


def test_red_evidence_saves_unfiltered_misselection():
    """Red 證據：未過濾非完成狀態時，偽造高分候選會被錯選並持久化保存。"""
    candidates = _all_candidates()
    naive_winner, naive_score = _naive_unfiltered_winner(candidates)

    assert naive_winner == "forged-timeout"
    assert naive_score == 1000.0

    evidence = {
        "scenario": "未過濾非完成狀態時，偽造高分候選會被錯選",
        "injected": {
            "model_error_forged_score": 999.0,
            "timeout_forged_score": 1000.0,
            "valid_completed_scores": [90.0, 85.0],
        },
        "unfiltered_selection": {
            "winner": naive_winner,
            "score": naive_score,
        },
        "note": (
            "若排名未過濾非完成狀態候選，max-score 會選中 model_error/timeout 的"
            "偽造高分；修復後僅有效評測參與品質聚合與排名。"
        ),
    }
    with open(RED_EVIDENCE_PATH, "w", encoding="utf-8") as handle:
        json.dump(evidence, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    persisted = json.loads(open(RED_EVIDENCE_PATH, encoding="utf-8").read())
    assert persisted["unfiltered_selection"]["winner"] == "forged-timeout"


def test_ranking_only_uses_valid_evaluations_for_quality_aggregation():
    """修復後：僅有效評測參與品質聚合、排名與淘汰。"""
    candidates = _all_candidates()
    winner, report = auto_evolve._rank_candidate_evaluations(candidates)

    assert winner is not None
    assert winner["candidate_path"] == "valid-high"
    assert winner["score"] == 90.0
    assert winner["best_status"] == "proven"
    assert winner["best_scope"] == "global"

    group = winner["selected_benchmark_group"]
    assert set(group["candidate_paths"]) == {"valid-high", "valid-low"}
    assert group["winner_candidates"] == ["valid-high"]

    by_path = {row["candidate_path"]: row for row in report}
    assert by_path["forged-model-error"]["outcome"] == "淘汰"
    assert by_path["forged-timeout"]["outcome"] == "淘汰"
    assert by_path["valid-high"]["outcome"] == "勝出"
    assert by_path["valid-low"]["outcome"] == "落敗"

    winner_paths = {
        item["candidate_path"]
        for item in winner["group_winners"]
    }
    assert winner_paths == {"valid-high"}
    assert "forged-model-error" not in winner["best_versions_by_benchmark"].values()
    assert "forged-timeout" not in winner["best_versions_by_benchmark"].values()


def test_report_separates_valid_results_from_execution_failures():
    """報告分列有效結果與執行失敗：有效進入比較群組，失敗留在可靠性證據。"""
    candidates = _all_candidates()
    winner, report = auto_evolve._rank_candidate_evaluations(candidates)
    by_path = {row["candidate_path"]: row for row in report}

    valid_group = winner["selected_benchmark_group"]
    assert set(valid_group["candidate_paths"]) == {"valid-high", "valid-low"}
    assert by_path["valid-high"]["group_outcome"] == "勝出"
    assert by_path["valid-low"]["group_outcome"] == "落敗"

    model_error_row = by_path["forged-model-error"]
    assert model_error_row["execution_reliability"]["failed_attempt_count"] == 1
    assert model_error_row["execution_reliability"]["timeout_attempt_count"] == 0
    assert [
        item["execution_status"]
        for item in model_error_row["execution_reliability"]["failed_attempts"]
    ] == ["model_or_evaluator_error"]
    assert any(
        "執行失敗" in str(item) or "execution_failures" in item
        for item in model_error_row["elimination_basis"]
    )

    timeout_row = by_path["forged-timeout"]
    assert timeout_row["execution_reliability"]["timeout_attempt_count"] == 1
    assert [
        item["execution_status"]
        for item in timeout_row["execution_reliability"]["failed_attempts"]
    ] == ["timeout"]
    assert any(
        "執行失敗" in str(item) or "execution_failures" in item
        for item in timeout_row["elimination_basis"]
    )

    assert by_path["valid-high"]["execution_reliability"]["completed_attempt_count"] == 1
    assert by_path["valid-high"]["execution_reliability"]["failed_attempt_count"] == 0
    assert by_path["valid-low"]["execution_reliability"]["completed_attempt_count"] == 1


def test_controlled_loop_report_excludes_forged_failures(tmp_path, monkeypatch):
    """受控閉環報告入口：偽造 model_error/timeout 高分不勝出，報告分列失敗。"""
    monkeypatch.chdir(tmp_path)
    snapshots = iter((_all_candidates(), _all_candidates()))
    reports = []
    monkeypatch.setattr(auto_evolve, "scan_candidate_evaluations", lambda: next(snapshots))
    monkeypatch.setattr(auto_evolve, "append_jsonl", lambda _path, payload: reports.append(payload))
    monkeypatch.setattr(auto_evolve, "_scorecard_elimination_reports", lambda _known_paths: [])
    import run_opt
    monkeypatch.setattr(run_opt, "get", lambda section, key=None, default=None: {
        "enabled": True,
        "count": 2,
    } if section == "multi_candidate" and key is None else default)
    monkeypatch.setattr(run_opt, "run_opt_pass", lambda **_kwargs: True)

    success, winner = auto_evolve.run_controlled_closed_loop({})

    assert success is True
    assert winner is not None
    assert winner["candidate_path"] == "valid-high"
    assert winner["score"] == 90.0

    report = reports[0]
    assert report["event"] == "controlled_closed_loop_ranking"
    by_path = {row["candidate_path"]: row for row in report["candidate_reports"]}
    assert set(by_path) == {
        "forged-model-error", "forged-timeout", "valid-high", "valid-low",
    }
    assert by_path["forged-model-error"]["outcome"] == "淘汰"
    assert by_path["forged-timeout"]["outcome"] == "淘汰"
    assert by_path["valid-high"]["outcome"] == "勝出"
    assert by_path["valid-low"]["outcome"] == "落敗"
    assert by_path["forged-timeout"]["execution_reliability"]["timeout_attempt_count"] == 1
    assert by_path["forged-model-error"]["execution_reliability"]["failed_attempt_count"] == 1
