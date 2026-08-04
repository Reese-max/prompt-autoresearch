# -*- coding: utf-8 -*-
"""研究結果交付：品質排名、執行可靠性與 Git 交付一致性的受控整合案例。"""
import hashlib
import json

import auto_evolve
import scripts.best_version_report as bvr


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
        "{\"event\": \"start\", \"timestamp\": \"2026-08-03 00:00:00\"}\n"
        "{\"event\": \"stop\", \"timestamp\": \"2026-08-03 00:01:00\"}\n",
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


def _failed_attempts():
    return [
        {
            "stage": "dev",
            "attempt": 1,
            "execution_status": "timeout",
            "score": 999.0,
            "error_evidence": {"stderr": "evaluation timed out"},
        },
        {
            "stage": "dev",
            "attempt": 2,
            "execution_status": "model_or_evaluator_error",
            "score": 1000.0,
            "error_evidence": {"stderr": "model request failed"},
        },
    ]


def _git_snapshot(
    head_commit,
    *,
    untracked=(),
    status_paths=(),
    diff_tracked="",
    diff_paths=(),
    porcelain="",
):
    """構造受控的 collect_git_snapshot() 輸出，模擬 Git 工作樹狀態。"""
    untracked = sorted(str(path).replace("\\", "/") for path in untracked)
    status_paths = sorted(str(path).replace("\\", "/") for path in status_paths)
    diff_paths = sorted(str(path).replace("\\", "/") for path in diff_paths)
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


def _good_delivery_sandbox(tmp_path, monkeypatch):
    """乾淨的兩候選沙箱：兩個候選都有可比較的成功量測。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    success_records = [{
        "stage": "dev",
        "attempt": 1,
        "execution_status": "quality_measurement_obtained",
        "quality_measurement": {"metric": "average_score", "score": 90.0},
    }]
    _write_candidate(
        workspace,
        "candidate-success",
        {"smoke": 92.0, "dev": 91.0, "holdout": 90.0},
        success_records,
    )
    _write_candidate(
        workspace,
        "candidate-comparison",
        {"smoke": 91.0, "dev": 90.0, "holdout": 89.0},
        success_records,
    )
    return workspace


def test_research_result_delivery_ranks_success_and_preserves_failed_attempt_evidence(
    tmp_path, monkeypatch
):
    """失敗 attempt 的假分數不得污染成功品質排名，但可靠性證據不可遺失。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    failed_attempts = _failed_attempts()
    success_records = failed_attempts + [{
        "stage": "dev",
        "attempt": 3,
        "execution_status": "quality_measurement_obtained",
        "quality_measurement": {"metric": "average_score", "score": 91.0},
    }]

    winner, ranking_report = auto_evolve._rank_candidate_evaluations([
        _ranking_card("candidate-success", 91.0, success_records),
        _ranking_card("candidate-comparison", 90.0, [{
            "stage": "dev",
            "attempt": 1,
            "execution_status": "quality_measurement_obtained",
            "quality_measurement": {"metric": "average_score", "score": 90.0},
        }]),
    ])

    assert winner["candidate_path"] == "candidate-success"
    assert winner["score"] == 91.0
    success_report = next(
        row for row in ranking_report if row["candidate_path"] == "candidate-success"
    )
    assert success_report["execution_reliability"] == {
        "attempt_count": 3,
        "completed_attempt_count": 1,
        "failed_attempt_count": 2,
        "timeout_attempt_count": 1,
        "failed_attempts": failed_attempts,
    }

    _write_candidate(
        workspace,
        "candidate-success",
        {"smoke": 92.0, "dev": 91.0, "holdout": 90.0},
        success_records,
    )
    _write_candidate(
        workspace,
        "candidate-comparison",
        {"smoke": 91.0, "dev": 90.0, "holdout": 89.0},
        [{
            "stage": "dev",
            "attempt": 1,
            "execution_status": "quality_measurement_obtained",
            "quality_measurement": {"metric": "average_score", "score": 90.0},
        }],
    )

    report = bvr.build_structured_report()
    rows = {row["path"]: row for row in report["candidate_comparison"]}
    delivered = rows["prompts/candidates/candidate-success.md"]
    assert report["decision"]["status"] == "valid"
    assert delivered["scores"]["dev"]["score"] == 91.0
    assert delivered["scores"]["dev"]["score"] not in {999.0, 1000.0}
    assert delivered["quality_eligible"] is True
    assert delivered["execution_reliability"]["attempt_count"] == 3
    assert delivered["execution_reliability"]["failed_attempt_count"] == 2
    assert delivered["execution_reliability"]["timeout_attempt_count"] == 1
    assert delivered["execution_reliability"]["failed_attempts"] == failed_attempts
    assert delivered["execution_records"] == success_records
    assert delivered["candidate_id"] in report["quality_ranking"]["eligible_candidate_ids"]


def test_research_result_delivery_rejects_best_without_comparable_success_measurement(
    tmp_path, monkeypatch
):
    """只有逾時／模型失敗證據時，報告不得產生最佳版本結論。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    failed_attempts = _failed_attempts()
    for name in ("timeout-candidate", "model-failure-candidate"):
        _write_candidate(
            workspace,
            name,
            {"smoke": None, "dev": None, "holdout": None},
            failed_attempts,
        )

    report = bvr.build_structured_report()
    rows = {row["path"]: row for row in report["candidate_comparison"]}

    assert report["decision"]["status"] == "inconclusive"
    assert report["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert report["decision"]["best_candidate_id"] is None
    assert report["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    assert report["quality_ranking"]["eligible_candidate_ids"] == []
    assert len(report["quality_ranking"]["excluded_candidate_ids"]) == 2
    assert all(row["quality_eligible"] is False for row in rows.values())
    assert all(row["execution_reliability"]["failed_attempt_count"] == 2 for row in rows.values())
    assert all(row["execution_reliability"]["timeout_attempt_count"] == 1 for row in rows.values())
    assert all(row["execution_records"] == failed_attempts for row in rows.values())
    assert any("關鍵量測欄位" in error for error in report["evidence_integrity"]["errors"])


def test_research_result_delivery_clean_consistent_commit_produces_best(
    tmp_path, monkeypatch
):
    """乾淨且報告 commit 與 HEAD 一致時，報告可產出最佳版本結論。"""
    workspace = _good_delivery_sandbox(tmp_path, monkeypatch)
    commit = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"
    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: _git_snapshot(commit))
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: commit)

    report = bvr.build_structured_report()

    consistency = report["delivery_consistency"]
    assert consistency["valid"] is True
    assert consistency["status"] == "proven"
    assert consistency["code"] == "VALID"
    assert consistency["actual_head"] == commit
    assert any(item["value"] == commit for item in consistency["claimed_commits"])
    assert consistency["inconsistencies"] == []
    assert consistency["undeclared_changes"] == []
    assert report["decision"]["status"] == "valid"
    assert report["decision"]["code"] == "VALID"
    assert report["decision"]["best_candidate_id"] == report["reproduction"]["settings"][
        "winner_input"
    ]["prompt_hash"]
    assert report["reproduction"]["settings"]["version"]["commit"] == commit
    assert report["quality_ranking"]["best_status"] == "proven"
    assert report["quality_ranking"]["best_scope"] == "global"
    assert len(report["quality_ranking"]["eligible_candidate_ids"]) == 2


def test_research_result_delivery_head_mismatch_rejects_best(tmp_path, monkeypatch):
    """HEAD 與報告宣稱 commit 不符時，拒絕最佳結論並給出結構化缺失與補救命令。"""
    workspace = _good_delivery_sandbox(tmp_path, monkeypatch)
    actual = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"
    claimed = "11ab7c5e654ede346e90fdca62393c890e5e6395"
    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: _git_snapshot(actual))
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: claimed)

    report = bvr.build_structured_report()

    consistency = report["delivery_consistency"]
    assert consistency["valid"] is False
    assert consistency["status"] == "unproven"
    assert consistency["code"] == "INCOMPLETE_EVIDENCE"
    assert any("HEAD" in item for item in consistency["inconsistencies"])
    assert report["decision"]["status"] == "inconclusive"
    assert report["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert report["decision"]["best_candidate_id"] is None
    assert report["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    assert report["quality_ranking"]["best_status"] == "unproven"
    assert report["quality_ranking"]["best_scope"] == "none"
    assert len(report["quality_ranking"]["eligible_candidate_ids"]) == 2
    commands = [item["command"] for item in consistency["rerun_commands"]]
    assert any("git rev-parse HEAD" in command for command in commands)
    assert any("git status --short" in command for command in commands)
    assert any(
        "best_version_report.py" in command and "--validate-schema" in command
        for command in commands
    )


def test_research_result_delivery_untracked_candidate_evidence_blocks_best(
    tmp_path, monkeypatch
):
    """未追蹤候選／證據檔混入工作樹時，拒絕最佳結論並指示提交補救。"""
    workspace = _good_delivery_sandbox(tmp_path, monkeypatch)
    stray = workspace / "prompts" / "candidates" / "stray-draft.md"
    stray.write_text("draft candidate not yet committed\n", encoding="utf-8")
    stray_rel = "prompts/candidates/stray-draft.md"
    commit = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"
    snapshot = _git_snapshot(
        commit,
        untracked=[stray_rel],
        status_paths=[stray_rel],
        porcelain="?? prompts/candidates/stray-draft.md",
    )
    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: snapshot)
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: commit)

    report = bvr.build_structured_report()

    consistency = report["delivery_consistency"]
    assert consistency["valid"] is False
    assert consistency["status"] == "unproven"
    assert consistency["code"] == "INCOMPLETE_EVIDENCE"
    assert stray_rel in consistency["undeclared_changes"]
    assert any(stray_rel in item for item in consistency["inconsistencies"])
    provenance = {item["path"]: item["provenance"] for item in consistency["git_provenance"]}
    assert provenance.get(stray_rel) == "untracked_worktree"
    assert report["decision"]["status"] == "inconclusive"
    assert report["decision"]["best_candidate_id"] is None
    assert report["quality_ranking"]["best_status"] == "unproven"
    assert report["quality_ranking"]["best_scope"] == "none"
    commands = [item["command"] for item in consistency["rerun_commands"]]
    assert any("git add -A" in command for command in commands)
    assert any("git commit" in command for command in commands)
    assert any("best_version_report.py" in command for command in commands)


def test_research_result_delivery_post_report_worktree_change_blocks_best(
    tmp_path, monkeypatch
):
    """報告後工作樹追蹤檔變更與候選記錄 diff 不符時，拒絕最佳結論。"""
    workspace = _sandbox(tmp_path, monkeypatch)
    recorded_diff = "diff as recorded at delivery time (clean commit)"
    commit = "e79fea82b93be15f32b39fc76c1fe7d6450a05b3"
    _write_candidate(
        workspace,
        "candidate-success",
        {"smoke": 92.0, "dev": 91.0, "holdout": 90.0},
        [{
            "stage": "dev",
            "attempt": 1,
            "execution_status": "quality_measurement_obtained",
            "quality_measurement": {"metric": "average_score", "score": 91.0},
        }],
        extra={"candidate_commit": commit, "git_diff": recorded_diff},
    )
    snapshot = _git_snapshot(
        commit,
        diff_tracked="diff after report: tracked baseline file modified",
        status_paths=["prompts/baseline.md"],
        diff_paths=["prompts/baseline.md"],
        porcelain=" M prompts/baseline.md",
    )
    monkeypatch.setattr(bvr, "collect_git_snapshot", lambda cwd=None: snapshot)
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: commit)

    report = bvr.build_structured_report()

    consistency = report["delivery_consistency"]
    assert consistency["valid"] is False
    assert consistency["status"] == "unproven"
    assert consistency["code"] == "INCOMPLETE_EVIDENCE"
    assert any("git_diff" in item for item in consistency["inconsistencies"])
    assert consistency["candidate_checks"][0]["valid"] is False
    assert any("git_diff" in error for error in consistency["candidate_checks"][0]["errors"])
    assert report["decision"]["status"] == "inconclusive"
    assert report["decision"]["best_candidate_id"] is None
    assert report["quality_ranking"]["best_status"] == "unproven"
    assert report["quality_ranking"]["best_scope"] == "none"
    assert any(
        "best_version_report.py" in item["command"]
        for item in consistency["rerun_commands"]
    )
