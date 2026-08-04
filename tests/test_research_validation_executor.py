# -*- coding: utf-8 -*-
"""分階段研究驗證執行器的最小可觀察行為測試。"""
import json
import os
import subprocess

from scripts.research_validation_executor import StagedValidationExecutor
import scripts.best_version_report as best_version_report


def _git(workspace, *args):
    result = subprocess.run(
        ["git", *args], cwd=workspace, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


def _repository(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "--quiet")
    _git(path, "config", "user.name", "Validation Test")
    _git(path, "config", "user.email", "validation@example.test")
    (path / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "--quiet", "-m", "test: establish validation fixture")
    return path


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


def test_timeout_isolates_candidate_and_keeps_recovery_contract(tmp_path):
    state_path = tmp_path / "validation.json"

    def candidate(context):
        context.completed_candidate("done", {"score": 91})
        context.isolate_candidate(
            "slow", "candidate timeout", ["python", "scripts/evaluate.py", "slow.md"]
        )
        raise TimeoutError("candidate deadline")

    state = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={stage: 1 for stage in (
            "candidate_evaluation", "evidence_validation", "ranking", "report_delivery",
        )},
    ).run({"candidate_evaluation": candidate})

    assert state["status"] == "timed_out"
    assert state["global_best_allowed"] is False
    assert state["completed_candidates"][0]["immutable"] is True
    assert state["completed_candidates"][0]["candidate_id"] == "done"
    assert state["isolated_candidates"] == [{
        "candidate_id": "slow",
        "stage": "candidate_evaluation",
        "attempt": 1,
        "status": "isolated",
        "reason": "candidate timeout",
    }]
    assert state["rerun_commands"][0]["argv"] == [
        "python", "scripts/evaluate.py", "slow.md",
    ]
    assert state["remaining_work"][0]["candidate_id"] == "slow"


def test_retry_archives_original_attempt_without_overwrite(tmp_path):
    state_path = tmp_path / "validation.json"
    executor = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={stage: 1 for stage in (
            "candidate_evaluation", "evidence_validation", "ranking", "report_delivery",
        )},
    )
    first = executor.run({
        "candidate_evaluation": lambda context: (_ for _ in ()).throw(TimeoutError("first")),
    })
    second = executor.run({
        "candidate_evaluation": lambda context: {"completed_candidates": [{
            "candidate_id": "done", "evidence": {"score": 95},
        }]},
    })

    archive = tmp_path / f"validation.json.attempt-{first['run_id']}.json"
    archived = json.loads(archive.read_text(encoding="utf-8"))
    assert second["attempt_number"] == 2
    assert second["attempt_history"][0]["run_id"] == first["run_id"]
    assert archived["run_id"] == first["run_id"]
    assert archived["stages"]["candidate_evaluation"]["status"] == "timeout"
    assert second["completed_candidates"][0]["evidence"] == {"score": 95}


def test_isolated_executor_runs_all_callbacks_in_one_baseline_worktree(tmp_path):
    repository = _repository(tmp_path / "repo")
    state_path = repository / "output" / "validation.json"
    observed = []

    def candidate(context):
        observed.append((context.stage, os.getcwd(), context.research_workspace["workspace_id"]))
        with open("candidate.txt", "w", encoding="utf-8") as handle:
            handle.write("generated\n")
        context.completed_candidate("candidate-1", {"score": 91})
        return {"research_workspace": context.research_workspace}

    state = StagedValidationExecutor(
        state_path=str(state_path),
        deadlines={stage: 1 for stage in (
            "candidate_evaluation", "evidence_validation", "ranking", "report_delivery",
        )},
        isolate_workspace=True,
        repository_root=str(repository),
        workspace_root=str(repository / "output" / "research-worktrees"),
    ).run({"candidate_evaluation": candidate})

    workspace = state["research_workspace"]
    assert workspace["status"] == "ready", workspace
    assert state["status"] == "completed", state
    assert len(observed) == 1
    assert all(row[1] == workspace["workspace"] for row in observed)
    assert state["completed_candidates"][0]["workspace_id"] == workspace["workspace_id"]
    assert state["completed_candidates"][0]["baseline_commit"] == workspace["baseline_commit"]
    assert os.path.exists(os.path.join(workspace["workspace"], "candidate.txt"))
    assert not (repository / "candidate.txt").exists()

    _git(repository, "worktree", "remove", "--force", workspace["workspace"])
