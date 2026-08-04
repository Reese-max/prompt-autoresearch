# -*- coding: utf-8 -*-
"""96250b18b42ebb36-eval-timeout-evidence-isolation — 評測逾時候選隔離受控回歸測試。

注入一個不可返回的候選評測與後續可成功候選，斷言：
1. 評測 deadline 到期後卡死工作可取消
2. 迴圈在總期限內繼續評測後續候選
3. 逾時候選明確標記為 timeout／incomplete
"""
import json
import hashlib
import time

import scripts.best_version_report as best_version_report
from scripts.research_validation_executor import (
    StagedValidationExecutor,
    StageTimeout,
    WedgeDetected,
)


def _block_until_deadline(context):
    """模擬一個在 deadline 到期前持續檢查的候選評測（最終逾時）。"""
    context.heartbeat("開始卡死評測")
    while True:
        context.check_deadline()
        time.sleep(0.05)


def _successful_candidate(context):
    """模擬一個正常完成的候選評測。"""
    evidence = {
        "score": 85,
        "status": "completed",
        "reproducible": True,
        "evaluation_id": "good-candidate-evaluation-001",
        "input_sha256": hashlib.sha256(b"good-candidate-input").hexdigest(),
        "output_sha256": hashlib.sha256(b"good-candidate-output").hexdigest(),
    }
    context.heartbeat("候選評測開始")
    context.completed_candidate("good-candidate", evidence)
    context.heartbeat("候選評測完成", {"candidate": "good-candidate"})
    return {"candidate": "good-candidate", "score": 85, "evidence": evidence}


def _timeout_with_forged_high_score(context):
    """留下看似高分但不完整的輸出後逾時。"""
    context.heartbeat(
        "逾時候選只留下部分證據",
        {
            "candidate": "timed-out-candidate",
            "score": 1000,
            "status": "partial",
            "evidence": {"complete": False, "reproducible": False},
        },
    )
    while True:
        context.check_deadline()
        time.sleep(0.05)


def _successful_evidence_validation(context):
    return {"validated": True}


def _successful_ranking(context):
    return {"winner": "good-candidate"}


def _successful_report_delivery(context):
    return {"report": "persisted"}


def test_timeout_candidate_isolated_and_loop_continues(tmp_path):
    """逾時候選被隔離，迴圈繼續評測後續候選。"""
    state_path = tmp_path / "validation.json"
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={
            "candidate_evaluation": 0.3,
            "evidence_validation": 0.5,
            "ranking": 0.5,
            "report_delivery": 0.5,
        },
    )

    state = executor.run({
        "candidate_evaluation": _block_until_deadline,
        "evidence_validation": _successful_evidence_validation,
        "ranking": _successful_ranking,
        "report_delivery": _successful_report_delivery,
    })

    assert state["status"] in {"timed_out", "wedge"}
    assert state["stages"]["candidate_evaluation"]["status"] == "timeout"
    assert state["stages"]["candidate_evaluation"]["error"] is not None
    assert "StageTimeout" in state["stages"]["candidate_evaluation"]["error"]


def test_timed_out_candidate_marked_timeout_in_state(tmp_path):
    """逾時候選在狀態中明確標記為 timeout。"""
    state_path = tmp_path / "validation.json"
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={
            "candidate_evaluation": 0.3,
            "evidence_validation": 0.5,
            "ranking": 0.5,
            "report_delivery": 0.5,
        },
    )

    state = executor.run({
        "candidate_evaluation": _block_until_deadline,
        "evidence_validation": _successful_evidence_validation,
        "ranking": _successful_ranking,
        "report_delivery": _successful_report_delivery,
    })

    assert state["stages"]["candidate_evaluation"]["status"] == "timeout"
    assert state["timed_out_stage"] == "candidate_evaluation"
    assert "candidate_evaluation" in state["timed_out_stages"]
    assert state["status"] in {"timed_out", "wedge"}


def test_timeout_allows_cancellation_of_stuck_work(tmp_path):
    """逾時機制可取消卡死的候選評測工作。"""
    state_path = tmp_path / "validation.json"
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={
            "candidate_evaluation": 0.2,
            "evidence_validation": 0.3,
            "ranking": 0.3,
            "report_delivery": 0.3,
        },
    )

    start = time.monotonic()
    state = executor.run({
        "candidate_evaluation": _block_until_deadline,
        "evidence_validation": _successful_evidence_validation,
        "ranking": _successful_ranking,
        "report_delivery": _successful_report_delivery,
    })

    elapsed = time.monotonic() - start
    total_deadline = sum([0.2, 0.3, 0.3, 0.3])
    assert elapsed < total_deadline + 2.0
    assert state["stages"]["candidate_evaluation"]["status"] == "timeout"
    assert state["stages"]["candidate_evaluation"]["ended_at"] is not None


def test_timeout_candidate_recorded_in_isolated_candidates(tmp_path):
    """逾時候選被記錄在隔離狀態中，global_best_allowed 為 False。"""
    state_path = tmp_path / "validation.json"
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={
            "candidate_evaluation": 0.3,
            "evidence_validation": 0.5,
            "ranking": 0.5,
            "report_delivery": 0.5,
        },
    )

    state = executor.run({
        "candidate_evaluation": _block_until_deadline,
        "evidence_validation": _successful_evidence_validation,
        "ranking": _successful_ranking,
        "report_delivery": _successful_report_delivery,
    })

    assert state["stages"]["candidate_evaluation"]["status"] == "timeout"
    assert state["global_best_allowed"] is False


def test_successful_candidate_continues_after_timeout(tmp_path):
    """逾時後迴圈仍可繼續評測後續候選（階段級逾時允許後續階段執行）。"""
    state_path = tmp_path / "validation.json"
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={
            "candidate_evaluation": 0.3,
            "evidence_validation": 0.5,
            "ranking": 0.5,
            "report_delivery": 0.5,
        },
    )

    def candidate_callback(context):
        context.heartbeat("開始卡死候選評測")
        while True:
            context.check_deadline()
            time.sleep(0.05)

    state = executor.run({
        "candidate_evaluation": candidate_callback,
        "evidence_validation": _successful_evidence_validation,
        "ranking": _successful_ranking,
        "report_delivery": _successful_report_delivery,
    })

    # 第一個階段逾時，後續階段仍應正常執行
    assert state["stages"]["candidate_evaluation"]["status"] == "timeout"
    assert state["stages"]["evidence_validation"]["status"] == "completed"
    assert state["stages"]["ranking"]["status"] == "completed"
    assert state["stages"]["report_delivery"]["status"] == "completed"


def test_overall_deadline_respects_total_budget(tmp_path):
    """整體 deadline 確保迴圈在總期限內繼續評測。"""
    state_path = tmp_path / "validation.json"
    round_deadline = 0.5
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={
            "candidate_evaluation": 0.3,
            "evidence_validation": 0.3,
            "ranking": 0.3,
            "report_delivery": 0.3,
        },
        round_deadline_seconds=round_deadline,
    )

    start = time.monotonic()
    state = executor.run({
        "candidate_evaluation": _block_until_deadline,
        "evidence_validation": _successful_evidence_validation,
        "ranking": _successful_ranking,
        "report_delivery": _successful_report_delivery,
    })

    elapsed = time.monotonic() - start
    assert elapsed < round_deadline + 2.0
    assert state["status"] in {"timed_out", "wedge"}


def test_timeout_evidence_cannot_win_or_pollute_final_report(tmp_path, monkeypatch):
    """逾時偽高分不得勝出，報告只引用後續成功且可重複的證據。"""
    state_path = tmp_path / "validation.json"
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={
            "candidate_evaluation": 0.2,
            "evidence_validation": 0.5,
            "ranking": 0.5,
            "report_delivery": 0.5,
        },
    )

    state = executor.run({
        "candidate_evaluation": _timeout_with_forged_high_score,
        "evidence_validation": _successful_candidate,
        "ranking": _successful_ranking,
        "report_delivery": _successful_report_delivery,
    })

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert state == persisted
    assert state["stages"]["candidate_evaluation"]["last_available_output"] == {
        "candidate": "timed-out-candidate",
        "score": 1000,
        "status": "partial",
        "evidence": {"complete": False, "reproducible": False},
    }
    assert state["stages"]["evidence_validation"]["status"] == "completed"

    completed = state["completed_candidates"]
    assert [item["candidate_id"] for item in completed] == ["good-candidate"]
    record = completed[0]
    assert record["status"] == "completed"
    assert record["immutable"] is True
    assert record["evidence"]["reproducible"] is True
    assert record["evidence"]["input_sha256"]
    assert record["evidence"]["output_sha256"]
    assert record["evidence_sha256"] == hashlib.sha256(
        json.dumps(
            record["evidence"], ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    monkeypatch.setattr(
        best_version_report,
        "load_validation_state",
        lambda: json.loads(state_path.read_text(encoding="utf-8")),
    )
    report = best_version_report.build_structured_report()

    assert report["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert report["decision"]["status"] == "inconclusive"
    assert report["decision"]["best_candidate_id"] is None
    assert report["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    assert report["quality_ranking"]["best_status"] == "unproven"
    assert report["quality_ranking"]["best_scope"] == "none"
    cited = report["quality_ranking"]["completed_candidates"]
    assert [item["candidate_id"] for item in cited] == ["good-candidate"]
    assert all(item["status"] == "completed" for item in cited)
    assert "timed-out-candidate" not in {
        item["candidate_id"] for item in cited
    }
