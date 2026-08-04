# -*- coding: utf-8 -*-
"""tests/test_git_reproducibility.py — Git 可重現性快照單元測試。"""
import json
import os
import subprocess
import sys

import pytest

from scripts.git_reproducibility import collect_git_snapshot, classify_git_provenance
import scripts.best_version_report as bvr


# ---------- helpers ----------

def _init_git_repo(path):
    """在 tmp_path 內初始化一個 bare git repo。"""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path), capture_output=True, check=True,
    )
    return path


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """把所有路徑指到 tmp_path，隔離真實 repo。"""
    champions = tmp_path / "prompts" / "champions"
    champions.mkdir(parents=True)
    candidates = tmp_path / "prompts" / "candidates"
    candidates.mkdir(parents=True)
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(bvr, "ROOT", str(tmp_path))
    monkeypatch.setattr(bvr, "BASELINE_META_PATH", str(tmp_path / "prompts" / "baseline.meta.json"))
    monkeypatch.setattr(bvr, "CHAMPIONS_DIR", str(champions))
    monkeypatch.setattr(bvr, "CANDIDATES_DIR", str(candidates))
    monkeypatch.setattr(bvr, "EVOLUTION_LOG_PATH", str(tmp_path / "evolution_log.jsonl"))
    monkeypatch.setattr(bvr, "CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(bvr, "RUNS_DIR", str(runs))
    return tmp_path


def write_baseline_meta(tmp_path, **overrides):
    meta = {
        "prompt_hash": "abc123def456",
        "dev_avg": 88.5,
        "holdout_avg": 87.0,
        "dev_run": "runs/dev_run_001",
        "holdout_run": "runs/holdout_run_001",
        "smoke_avg": 90.0,
    }
    meta.update(overrides)
    path = tmp_path / "prompts" / "baseline.meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def write_config(tmp_path, content="thresholds:\n  dev_min_improvement: 2.0\n"):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")


def write_evolution_log(tmp_path, rows):
    path = tmp_path / "evolution_log.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------- collect_git_snapshot 單元測試 ----------

def test_collect_git_snapshot_returns_all_required_fields(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True, check=True)

    fixed_time = "2026-08-03T12:00:00Z"
    snapshot = collect_git_snapshot(cwd=str(repo), now=lambda: fixed_time)

    assert "head_commit" in snapshot
    assert "status_porcelain" in snapshot
    assert "diff_tracked" in snapshot
    assert "untracked_files" in snapshot
    assert "snapshot_hash" in snapshot
    assert "captured_at" in snapshot
    assert "workspace" in snapshot

    assert len(snapshot["head_commit"]) == 40  # full SHA-1
    assert snapshot["captured_at"] == fixed_time
    assert os.path.abspath(str(repo)) == snapshot["workspace"]


def test_collect_git_snapshot_hash_is_deterministic(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "a.txt").write_text("content", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True, check=True)

    fixed_time = "2026-08-03T12:00:00Z"
    s1 = collect_git_snapshot(cwd=str(repo), now=lambda: fixed_time)
    s2 = collect_git_snapshot(cwd=str(repo), now=lambda: fixed_time)

    assert s1["snapshot_hash"] == s2["snapshot_hash"]
    assert len(s1["snapshot_hash"]) == 64  # SHA-256 hex


def test_collect_git_snapshot_captures_untracked_files(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "tracked.txt").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True, check=True)
    (repo / "untracked.txt").write_text("untracked", encoding="utf-8")

    snapshot = collect_git_snapshot(cwd=str(repo))

    assert "untracked.txt" in snapshot["untracked_files"]
    assert "tracked.txt" not in snapshot["untracked_files"]


def test_collect_git_snapshot_captures_status_porcelain(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "file.txt").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True, check=True)
    (repo / "file.txt").write_text("v2", encoding="utf-8")

    snapshot = collect_git_snapshot(cwd=str(repo))

    assert "M" in snapshot["status_porcelain"]
    assert "file.txt" in snapshot["status_porcelain"]


def test_collect_git_snapshot_graceful_failure_on_non_git_dir(tmp_path):
    non_git = tmp_path / "not_a_repo"
    non_git.mkdir()

    snapshot = collect_git_snapshot(cwd=str(non_git))

    assert snapshot["head_commit"] == ""
    assert snapshot["status_porcelain"] == ""
    assert snapshot["diff_tracked"] == ""
    assert snapshot["untracked_files"] == []
    assert len(snapshot["snapshot_hash"]) == 64
    assert snapshot["captured_at"]


def test_collect_git_snapshot_diff_tracked(tmp_path):
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "code.py").write_text("print('hello')\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True, check=True)
    (repo / "code.py").write_text("print('changed')\n", encoding="utf-8")

    snapshot = collect_git_snapshot(cwd=str(repo))

    assert "print('changed')" in snapshot["diff_tracked"]
    assert "print('hello')" in snapshot["diff_tracked"]


# ---------- 整合測試：best_version_report 包含快照 ----------

def test_build_structured_report_includes_git_snapshot(sandbox, monkeypatch):
    """build_structured_report() 的 reproduction 與 execution 皆包含 git_reproducibility_snapshot。"""
    write_baseline_meta(sandbox)
    write_config(sandbox)
    write_evolution_log(sandbox, [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {}},
        {"event": "stop", "timestamp": "2026-01-01 00:01:00"},
    ])

    data = bvr.build_structured_report()

    # reproduction section
    repro_snap = data["reproduction"].get("git_reproducibility_snapshot")
    assert repro_snap is not None
    assert "snapshot_hash" in repro_snap
    assert "captured_at" in repro_snap
    assert "workspace" in repro_snap
    assert "head_commit" in repro_snap

    # execution section
    exec_snap = data["execution"].get("git_reproducibility_snapshot")
    assert exec_snap is not None
    assert exec_snap["snapshot_hash"] == repro_snap["snapshot_hash"]


def test_build_report_includes_snapshot_hash_in_output(sandbox):
    """Markdown 報告應包含快照雜湊。"""
    write_baseline_meta(sandbox)
    write_config(sandbox)
    write_evolution_log(sandbox, [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {}},
        {"event": "stop", "timestamp": "2026-01-01 00:01:00"},
    ])

    data = bvr.build_structured_report()
    report = bvr.build_report(structured=data)
    snap_hash = data["reproduction"]["git_reproducibility_snapshot"]["snapshot_hash"]

    assert snap_hash in report


# ---------- classify_git_provenance 單元測試 ----------

def test_classify_committed_file():
    snapshot = {
        "head_commit": "abc123",
        "status_paths": [],
        "diff_paths": [],
        "untracked_files": [],
    }
    assert classify_git_provenance("prompts/baseline.md", snapshot) == "committed"


def test_classify_diff_tracked_via_status_paths():
    snapshot = {
        "head_commit": "abc123",
        "status_paths": ["prompts/baseline.md"],
        "diff_paths": [],
        "untracked_files": [],
    }
    assert classify_git_provenance("prompts/baseline.md", snapshot) == "diff_tracked"


def test_classify_diff_tracked_via_diff_paths():
    snapshot = {
        "head_commit": "abc123",
        "status_paths": [],
        "diff_paths": ["prompts/baseline.md"],
        "untracked_files": [],
    }
    assert classify_git_provenance("prompts/baseline.md", snapshot) == "diff_tracked"


def test_classify_untracked_file():
    snapshot = {
        "head_commit": "abc123",
        "status_paths": [],
        "diff_paths": [],
        "untracked_files": ["draft.md"],
    }
    assert classify_git_provenance("draft.md", snapshot) == "untracked_worktree"


def test_classify_untracked_when_no_head():
    snapshot = {
        "head_commit": "",
        "status_paths": [],
        "diff_paths": [],
        "untracked_files": [],
    }
    assert classify_git_provenance("any.txt", snapshot) == "untracked_worktree"


def test_classify_empty_snapshot():
    assert classify_git_provenance("any.txt", {}) == "untracked_worktree"


def test_classify_none_snapshot():
    assert classify_git_provenance("any.txt", None) == "untracked_worktree"
