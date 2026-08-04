# -*- coding: utf-8 -*-
"""交付一致性閘門的最小正反案例。"""

import scripts.best_version_report as bvr


def _check(snapshot, *, rerun=None, cards=None, comparisons=None, evidence=None):
    return bvr.verify_delivery_consistency(
        snapshot,
        rerun or {},
        {},
        [],
        cards or [],
        [],
        [],
        evidence or [],
        [],
        comparisons or [],
    )


def test_head_mismatch_is_unproven_and_has_rerun_commands():
    result = _check(
        {"head_commit": "actual", "status_paths": [], "diff_tracked": ""},
        rerun={"version": {"commit": "recorded"}},
    )

    assert result["status"] == "unproven"
    assert result["code"] == "INCOMPLETE_EVIDENCE"
    assert any("HEAD" in item for item in result["inconsistencies"])
    assert any("best_version_report.py" in item["command"] for item in result["rerun_commands"])


def test_undeclared_worktree_change_blocks_best_claim():
    result = _check(
        {
            "head_commit": "actual",
            "status_paths": ["candidate.md", "unrelated.py"],
            "diff_tracked": "diff",
        },
        evidence=[{"path": "candidate.md"}],
        comparisons=[{"candidate_id": "candidate", "path": "candidate.md", "scorecard_path": "card.json"}],
    )

    assert result["valid"] is False
    assert result["undeclared_changes"] == ["unrelated.py"]
    assert any("unrelated.py" in item for item in result["inconsistencies"])


def test_candidate_recorded_diff_mismatch_is_unproven():
    result = _check(
        {"head_commit": "actual", "status_paths": [], "diff_tracked": "actual diff"},
        cards=[{"candidate_path": "candidate.md", "git_diff": "recorded diff"}],
        comparisons=[{"candidate_id": "candidate", "path": "candidate.md"}],
    )

    assert result["valid"] is False
    assert any("git_diff" in item for item in result["inconsistencies"])


def test_git_provenance_marks_committed_files():
    result = _check(
        {
            "head_commit": "abc123",
            "status_paths": [],
            "diff_tracked": "",
            "untracked_files": [],
            "diff_paths": [],
        },
        evidence=[{"path": "prompts/baseline.md"}],
        comparisons=[],
    )

    provenance_map = {item["path"]: item["provenance"] for item in result["git_provenance"]}
    assert provenance_map["prompts/baseline.md"] == "committed"


def test_git_provenance_marks_diff_tracked_files():
    result = _check(
        {
            "head_commit": "abc123",
            "status_paths": ["prompts/baseline.md"],
            "diff_tracked": "diff content",
            "untracked_files": [],
            "diff_paths": [],
        },
        evidence=[{"path": "prompts/baseline.md"}],
        comparisons=[],
    )

    provenance_map = {item["path"]: item["provenance"] for item in result["git_provenance"]}
    assert provenance_map["prompts/baseline.md"] == "diff_tracked"


def test_git_provenance_marks_undeclared_as_untracked():
    result = _check(
        {
            "head_commit": "abc123",
            "status_paths": ["untracked_draft.md"],
            "diff_tracked": "",
            "untracked_files": [],
            "diff_paths": [],
        },
        evidence=[],
        comparisons=[],
    )

    provenance_map = {item["path"]: item["provenance"] for item in result["git_provenance"]}
    assert provenance_map.get("untracked_draft.md") == "untracked_worktree"
