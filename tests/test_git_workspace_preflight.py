# -*- coding: utf-8 -*-
"""Git 工作區預檢：資料夾、worktree 指標與跨平台阻塞契約。"""
import json
import os
import subprocess

import pytest

import scripts.git_reproducibility as git_reproducibility
from scripts.git_reproducibility import (
    collect_git_preflight,
    create_research_workspace,
    parse_git_metadata,
    persist_git_preflight,
    ResearchWorkspaceError,
)
import scripts.best_version_report as best_version_report


def _git(workspace, *args, check=True):
    result = subprocess.run(
        ["git", *args], cwd=workspace, capture_output=True, text=True, check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _repository(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "branch", "-M", "main")
    _git(tmp_path, "config", "user.name", "Preflight Test")
    _git(tmp_path, "config", "user.email", "preflight@example.test")
    (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "--quiet", "-m", "test: establish git preflight fixture")
    return tmp_path


def test_parse_git_directory_and_head(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

    result = parse_git_metadata(tmp_path)

    assert result["git_metadata_kind"] == "directory"
    assert result["head_readable"] is True
    assert result["blocked"] is False


def test_parse_worktree_git_file_resolves_relative_gitdir(tmp_path):
    (tmp_path / ".git").write_text("gitdir: metadata\n", encoding="utf-8")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    (metadata / "HEAD").write_text("abc\n", encoding="utf-8")

    result = parse_git_metadata(tmp_path)

    assert result["git_metadata_kind"] == "worktree_file"
    assert result["git_dir"].endswith("metadata")
    assert result["blocked"] is False


def test_parse_windows_worktree_path_blocks_on_linux(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").write_text(
        "gitdir: D:/work/.git/worktrees/example\n", encoding="utf-8"
    )

    result = parse_git_metadata(".", platform_name="Linux")

    assert result["blocked"] is True
    assert "windows_gitdir_path_unresolvable" in result["blockers"]
    assert "git worktree repair" in result["repair_commands"]


def test_parse_non_git_and_unreadable_head_are_blocked(tmp_path):
    non_git = parse_git_metadata(tmp_path)
    assert "not_git_repository" in non_git["blockers"]

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("", encoding="utf-8")
    unreadable = parse_git_metadata(tmp_path)
    assert "head_unreadable" in unreadable["blockers"]


def test_controlled_linux_workspace_states_gate_ranking_and_best_claim(
    tmp_path, monkeypatch
):
    """Linux 下的失效工作區不得比較／交付；有效 worktree 保留完整身分。"""
    head = "a" * 40
    windows_path = tmp_path / "windows-gitdir"
    valid_worktree = tmp_path / "valid-worktree"
    non_git = tmp_path / "non-git"
    for workspace in (windows_path, valid_worktree, non_git):
        workspace.mkdir()

    (windows_path / ".git").write_text(
        "gitdir: D:/work/.git/worktrees/example\n", encoding="utf-8"
    )
    metadata = valid_worktree / "metadata"
    metadata.mkdir()
    (valid_worktree / ".git").write_text(
        "gitdir: metadata\n", encoding="utf-8"
    )
    (metadata / "HEAD").write_text(f"{head}\n", encoding="utf-8")

    cases = (
        (windows_path, True),
        (valid_worktree, False),
        (non_git, True),
    )
    for workspace, blocked in cases:
        with monkeypatch.context() as patch:
            patch.chdir(workspace)
            parsed = parse_git_metadata(".", platform_name="Linux")

            def fake_parse(_cwd=None, platform_name=None, parsed=parsed):
                assert platform_name == "Linux"
                return parsed

            def fake_detail(args, cwd):
                if args == ["rev-parse", "--show-toplevel"]:
                    return {
                        "ok": True,
                        "stdout": f"/linux/research/{workspace.name}\n",
                        "stderr": "",
                        "returncode": 0,
                        "timed_out": False,
                    }
                if args == ["rev-parse", "--verify", "HEAD"]:
                    return {
                        "ok": not blocked,
                        "stdout": f"{head}\n" if not blocked else "",
                        "stderr": "" if not blocked else "not a git repository",
                        "returncode": 0 if not blocked else 128,
                        "timed_out": False,
                    }
                if args in (
                    ["status", "--porcelain=v1", "--untracked-files=all"],
                    ["ls-files", "-u"],
                ):
                    return {
                        "ok": not blocked,
                        "stdout": "",
                        "stderr": "" if not blocked else "not a git repository",
                        "returncode": 0 if not blocked else 128,
                        "timed_out": False,
                    }
                raise AssertionError(f"unexpected git command: {args}")

            def fake_git(args, cwd, timeout=git_reproducibility.DEFAULT_GIT_TIMEOUT):
                return f"{head}\n" if args == ["rev-parse", "HEAD"] and not blocked else ""

            patch.setattr(git_reproducibility, "parse_git_metadata", fake_parse)
            patch.setattr(git_reproducibility, "_run_git_detail", fake_detail)
            patch.setattr(git_reproducibility, "_run_git", fake_git)
            preflight = collect_git_preflight(
                cwd=workspace, platform_name="Linux", now=lambda: "2026-08-04T00:00:00Z"
            )

        assert preflight["blocked"] is blocked
        assert preflight["comparison_allowed"] is (not blocked)
        assert preflight["deliverable_allowed"] is (not blocked)
        assert preflight["global_best_allowed"] is (not blocked)

        if blocked:
            assert preflight["status"] == "blocked"
            assert preflight["head_readable"] is False
            continue

        assert preflight["status"] == "passed"
        assert preflight["head_commit"] == head
        assert preflight["head_file"] == head
        assert preflight["head_readable"] is True
        assert preflight["workspace"] == str(valid_worktree.resolve())
        assert preflight["repository_root"] == "/linux/research/valid-worktree"
        assert preflight["git_metadata_kind"] == "worktree_file"
        assert preflight["git_dir"] == str(metadata.resolve())


def test_persist_blocking_reason_and_repair_commands(tmp_path):
    state_path = tmp_path / "output" / "research_git_preflight.json"
    preflight = {
        "blocked": True,
        "blockers": ["not_git_repository"],
        "blocking_reason": "not_git_repository",
        "blocking_reasons": [{"code": "not_git_repository"}],
        "repair_commands": ["git init", "git status --short"],
    }

    persist_git_preflight(preflight, state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert state["status"] == "blocked"
    assert state["reason_code"] == "not_git_repository"
    assert state["repair_commands"] == ["git init", "git status --short"]


def test_blocked_preflight_prevents_best_version_delivery(tmp_path, monkeypatch):
    output = tmp_path / "output"
    output.mkdir()
    (output / "research_git_preflight.json").write_text(
        json.dumps({
            "status": "blocked",
            "blocked": True,
            "reason_code": "head_unreadable",
            "blocking_reason": "head_unreadable",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(best_version_report, "ROOT", str(tmp_path))

    report = best_version_report.build_structured_report()

    assert report["decision"]["status"] == "inconclusive"
    assert any("Git 預檢阻塞" in error for error in report["evidence_integrity"]["errors"])


def test_worktree_preflight_blocks_dirty_lock_and_operation_residue(tmp_path):
    """每種 Git 阻塞都要留下可定位路徑與安全重跑命令。"""
    cases = (
        ("dirty", "dirty_worktree", "dirty.txt"),
        ("index_lock", "git_index_lock_present", "index.lock"),
        ("merge", "git_merge_in_progress", "MERGE_HEAD"),
        ("rebase", "git_rebase_in_progress", "rebase-merge"),
    )
    for name, expected_blocker, expected_path in cases:
        workspace = _repository(tmp_path / name)
        git_dir = workspace / ".git"
        if name == "dirty":
            (workspace / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        elif name == "index_lock":
            (git_dir / "index.lock").write_text("stale lock\n", encoding="utf-8")
        elif name == "merge":
            (git_dir / "MERGE_HEAD").write_text("a" * 40 + "\n", encoding="utf-8")
        else:
            (git_dir / "rebase-merge").mkdir()

        preflight = collect_git_preflight(workspace)

        assert preflight["blocked"] is True
        assert expected_blocker in preflight["blockers"]
        assert preflight["comparison_allowed"] is False
        assert preflight["deliverable_allowed"] is False
        assert preflight["global_best_allowed"] is False
        assert any(path.endswith(expected_path) for path in preflight["affected_paths"])
        assert preflight["rerun_commands"] == ["python scripts/preflight.py --require-git"]

        state_path = workspace / "output" / "research_git_preflight.json"
        persist_git_preflight(preflight, state_path)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert expected_blocker in state["preflight"]["blockers"]
        assert state["affected_paths"] == preflight["affected_paths"]
        assert state["rerun_commands"] == preflight["rerun_commands"]


def test_worktree_preflight_blocks_unmerged_paths_and_locked_linked_worktree(tmp_path):
    workspace = _repository(tmp_path / "main")
    _git(workspace, "branch", "side")
    (workspace / "tracked.txt").write_text("main\n", encoding="utf-8")
    _git(workspace, "commit", "--all", "--quiet", "-m", "test: main change")
    _git(workspace, "checkout", "--quiet", "side")
    (workspace / "tracked.txt").write_text("side\n", encoding="utf-8")
    _git(workspace, "commit", "--all", "--quiet", "-m", "test: side change")
    _git(workspace, "checkout", "--quiet", "main")

    merge = _git(workspace, "merge", "side", check=False)
    assert merge.returncode != 0
    conflicted = collect_git_preflight(workspace)
    assert {"dirty_worktree", "git_unmerged_paths", "git_merge_in_progress"} <= set(conflicted["blockers"])
    assert conflicted["unmerged_paths"] == ["tracked.txt"]
    assert "tracked.txt" in conflicted["affected_paths"]
    _git(workspace, "merge", "--abort")

    linked = tmp_path / "linked-worktree"
    _git(workspace, "worktree", "add", "--detach", str(linked))
    _git(workspace, "worktree", "lock", str(linked))
    locked = collect_git_preflight(linked)
    assert "git_worktree_lock_present" in locked["blockers"]
    assert any(path.endswith("locked") for path in locked["affected_paths"])
    _git(workspace, "worktree", "unlock", str(linked))
    _git(workspace, "worktree", "remove", "--force", str(linked))


def test_research_workspace_uses_clean_identifiable_baseline(tmp_path):
    repository = _repository(tmp_path / "research-repo")
    workspace = create_research_workspace(
        repository=repository,
        workspace_root=repository / "output" / "research-worktrees",
        run_id="test-run",
    )

    assert workspace.metadata["status"] == "ready"
    assert workspace.metadata["baseline_commit"] == _git(repository, "rev-parse", "HEAD").stdout.strip()
    assert workspace.metadata["baseline_snapshot_hash"]
    assert collect_git_preflight(workspace.path)["passed"] is True
    with workspace.activate():
        assert os.getcwd() == str(workspace.path)
        with open(os.path.join(workspace.path, "candidate.txt"), "w", encoding="utf-8") as handle:
            handle.write("candidate\n")
    assert not (repository / "candidate.txt").exists()

    _git(repository, "worktree", "remove", "--force", str(workspace.path))


def test_research_workspace_failure_is_unproven_without_fallback(tmp_path):
    repository = _repository(tmp_path / "dirty-repo")
    (repository / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")

    with pytest.raises(ResearchWorkspaceError) as failure:
        create_research_workspace(repository=repository, run_id="blocked")

    assert failure.value.evidence["decision"] == {
        "status": "unproven",
        "code": "INCOMPLETE_EVIDENCE",
        "reason": "無法建立隔離研究工作區：來源 Git 預檢阻塞。",
    }
    assert not (repository / "output" / "research-worktrees" / "blocked").exists()
