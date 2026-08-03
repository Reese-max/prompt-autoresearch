# -*- coding: utf-8 -*-
"""分階段研究驗證執行器的最小可觀察行為測試。"""
import json

from scripts.research_validation_executor import StagedValidationExecutor
import scripts.best_version_report as best_version_report


def test_timeout_persists_heartbeat_and_keeps_following_stage_outputs(tmp_path):
    state_path = tmp_path / "validation.json"

    def candidate(context):
        context.checkpoint({"candidate": "partial"}, "候選評測已有部分輸出")
        raise TimeoutError("candidate deadline")

    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={stage: 1 for stage in (
            "candidate_evaluation", "evidence_validation", "ranking", "report_delivery",
        )},
    )
    state = executor.run({
        "candidate_evaluation": candidate,
        "evidence_validation": lambda context: {"evidence": "ok"},
        "ranking": lambda context: {"winner": "candidate-1"},
        "report_delivery": lambda context: {"report": "persisted"},
    })

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert state == persisted
    assert state["status"] == "timed_out"
    assert state["timed_out_stage"] == "candidate_evaluation"
    assert state["stages"]["candidate_evaluation"]["status"] == "timeout"
    assert state["stages"]["candidate_evaluation"]["last_available_output"] == {
        "candidate": "partial",
    }
    assert state["stages"]["evidence_validation"]["status"] == "completed"
    assert state["stages"]["ranking"]["status"] == "completed"
    assert state["stages"]["report_delivery"]["status"] == "completed"
    for stage in state["stages"].values():
        assert stage["started_at"]
        assert stage["ended_at"]
        assert stage["deadline"]
        assert len(stage["heartbeats"]) >= 2


def test_best_version_report_surfaces_validation_checkpoint(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    (output / "research_validation_state.json").write_text(
        json.dumps({
            "status": "timed_out",
            "timed_out_stage": "candidate_evaluation",
            "stages": {
                "candidate_evaluation": {
                    "status": "timeout",
                    "started_at": "2026-08-03T00:00:00Z",
                    "ended_at": "2026-08-03T00:01:00Z",
                    "deadline": "2026-08-03T00:00:30Z",
                    "heartbeats": [{}, {}],
                    "last_available_output": {"candidate": "partial"},
                },
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(best_version_report, "ROOT", str(tmp_path))

    state = best_version_report.load_validation_state()
    section = "\n".join(best_version_report.build_validation_execution_section(state))

    assert state["timed_out_stage"] == "candidate_evaluation"
    assert "candidate_evaluation" in section
    assert "2026-08-03T00:00:30Z" in section
    assert "最後輸出" in section
