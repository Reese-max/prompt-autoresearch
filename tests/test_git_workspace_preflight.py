# -*- coding: utf-8 -*-
"""Git 工作區預檢：資料夾、worktree 指標與跨平台阻塞契約。"""
import json

from scripts.git_reproducibility import parse_git_metadata, persist_git_preflight
import scripts.best_version_report as best_version_report


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
