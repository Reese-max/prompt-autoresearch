# -*- coding: utf-8 -*-
"""
驗收目標解析與 gate-configuration failure 驗證。

覆蓋需求：
- resolve_acceptance_target 正確解析到 tests/ed6a1a498025c1ec-artifact-success-verification.py
- verify_acceptance_target_precheck 在目標存在且可讀時通過
- 目標不存在時回傳 GATE_CONFIGURATION_FAILURE
- 目標不可讀時回傳 GATE_CONFIGURATION_FAILURE
- acceptance_gate_disposition 在 GATE_CONFIGURATION_FAILURE 時不將 exit=0 或零收集記為成功
- run_evaluate 在 precheck 失敗時提前回傳 GATE_CONFIGURATION_FAILURE
"""
import os
import subprocess

import pytest

from lib import completion_gate


# ---------------------------------------------------------------------------
# resolve_acceptance_target
# ---------------------------------------------------------------------------

class TestResolveAcceptanceTarget:
    """驗收目標路徑解析。"""

    def test_resolves_to_expected_relative_path(self):
        """requested_path 為固定相對路徑。"""
        requested, resolved, error = completion_gate.resolve_acceptance_target()
        assert requested == "tests/ed6a1a498025c1ec-artifact-success-verification.py"
        assert error == ""

    def test_resolved_path_exists_in_repo(self):
        """resolved_path 指向 repo 中實際存在的檔案。"""
        _, resolved, error = completion_gate.resolve_acceptance_target()
        assert os.path.isfile(resolved), f"expected file to exist: {resolved}"
        assert error == ""

    def test_resolved_path_is_within_workspace(self, tmp_path):
        """resolved_path 不超出 workspace_root。"""
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(tmp_path))
        if error == "":
            assert os.path.commonpath(
                [os.path.normcase(resolved), os.path.normcase(str(tmp_path))]
            ) == os.path.normcase(str(tmp_path))

    def test_nonexistent_target_returns_error(self, tmp_path):
        """目標不存在時回傳診斷。"""
        fake_root = tmp_path / "no_such_repo"
        fake_root.mkdir()
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert requested == "tests/ed6a1a498025c1ec-artifact-success-verification.py"
        assert error == "target file does not exist"

    def test_empty_file_returns_error(self, tmp_path):
        """目標為空檔時回傳診斷。"""
        target_dir = tmp_path / "tests"
        target_dir.mkdir()
        target = target_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        target.write_bytes(b"")
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(tmp_path))
        assert error == "target file is empty"

    def test_unreadable_file_returns_error(self, tmp_path, monkeypatch):
        """目標不可讀時回傳診斷。"""
        target_dir = tmp_path / "tests"
        target_dir.mkdir()
        target = target_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        target.write_bytes(b"# test")

        real_open = open

        def mock_open(path, *args, **kwargs):
            if "ed6a1a498025c1ec" in str(path):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(tmp_path))
        assert "unreadable" in error


# ---------------------------------------------------------------------------
# verify_acceptance_target_precheck
# ---------------------------------------------------------------------------

class TestVerifyAcceptanceTargetPrecheck:
    """驗收目標 precheck 驗證。"""

    def test_precheck_passes_when_target_exists(self):
        """目標存在且可讀時 precheck 通過。"""
        result = completion_gate.verify_acceptance_target_precheck()
        assert result["passed"] is True
        assert result["reason_code"] == ""
        assert result["error"] == ""
        assert result["requested_path"] == "tests/ed6a1a498025c1ec-artifact-success-verification.py"

    def test_precheck_fails_when_target_missing(self, tmp_path):
        """目標不存在時 precheck 失敗。"""
        fake_root = tmp_path / "empty_repo"
        fake_root.mkdir()
        result = completion_gate.verify_acceptance_target_precheck(str(fake_root))
        assert result["passed"] is False
        assert result["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert "does not exist" in result["error"]
        assert result["requested_path"] == "tests/ed6a1a498025c1ec-artifact-success-verification.py"

    def test_precheck_fails_when_target_unreadable(self, tmp_path, monkeypatch):
        """目標不可讀時 precheck 失敗。"""
        target_dir = tmp_path / "tests"
        target_dir.mkdir()
        target = target_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        target.write_bytes(b"# test")

        real_open = open

        def mock_open(path, *args, **kwargs):
            if "ed6a1a498025c1ec" in str(path):
                raise OSError("access denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        result = completion_gate.verify_acceptance_target_precheck(str(tmp_path))
        assert result["passed"] is False
        assert result["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert "unreadable" in result["error"]


# ---------------------------------------------------------------------------
# acceptance_gate_disposition
# ---------------------------------------------------------------------------

class TestAcceptanceGateDisposition:
    """acceptance_gate_disposition 結合 precheck 與完成證據驗證。"""

    def test_exit_zero_with_missing_target_yields_gate_config_failure(self, tmp_path):
        """exit_code=0 但目標不存在時，reason_code 為 GATE_CONFIGURATION_FAILURE。
        禁止將 exit=0 記為產品驗證成功。"""
        fake_root = tmp_path / "empty_repo"
        fake_root.mkdir()
        task = {
            "exit_code": 0,
            "stdout": "test output",
            "stderr": "",
            "artifacts": {},
            "results": [{"id": 1, "answer": "some answer", "total_score": 80}],
            "summary": {"average_score": 80.0},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert "precheck" in disposition
        assert disposition["precheck"]["passed"] is False

    def test_exit_zero_with_valid_target_passes(self):
        """exit_code=0 且目標存在時，不產生 GATE_CONFIGURATION_FAILURE。"""
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {"report": {"exists": True, "size": 100}},
            "results": [{"id": 1, "answer": "answer", "total_score": 80}],
            "summary": {"average_score": 80.0},
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["reason_code"] != "GATE_CONFIGURATION_FAILURE"
        assert disposition["precheck"]["passed"] is True

    def test_zero_collection_with_missing_target_yields_gate_config_failure(self, tmp_path):
        """零收集（exit=0, 無 artifacts/results/summary）且目標不存在時，
        應標記 GATE_CONFIGURATION_FAILURE 而非 NO_VALID_EVIDENCE。"""
        fake_root = tmp_path / "empty_repo"
        fake_root.mkdir()
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [],
            "summary": {},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"

    def test_exit_4_with_missing_target_yields_gate_config_failure(self, tmp_path):
        """exit=4 且目標不存在時，GATE_CONFIGURATION_FAILURE 優先於
        NONZERO_EXIT_CODE，禁止將 exit=4 誤記為產品驗證失敗。"""
        fake_root = tmp_path / "empty_repo"
        fake_root.mkdir()
        task = {
            "exit_code": 4,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [],
            "summary": {},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert any("gate-configuration failure" in r for r in disposition["rejection_reasons"])


# ---------------------------------------------------------------------------
# run_evaluate precheck integration
# ---------------------------------------------------------------------------

class TestRunEvaluatePrecheck:
    """run_evaluate 在 precheck 失敗時提前回傳。"""

    def test_run_evaluate_returns_gate_config_failure_when_target_missing(self, tmp_path, monkeypatch):
        """run_evaluate 在目標不存在時回傳 GATE_CONFIGURATION_FAILURE，
        不實際執行 pytest。"""
        from run_opt import run_evaluate

        fake_root = tmp_path / "empty_repo"
        fake_root.mkdir()
        monkeypatch.setattr(completion_gate, "_workspace_root", lambda _wr=None: str(fake_root))

        result, run_dir, summary = run_evaluate(
            "prompts/test.md", "questions/smoke.jsonl", parallel=1,
        )
        assert run_dir is None
        assert summary == {}
        assert hasattr(result, "precheck_disposition")
        assert result.precheck_disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert result.returncode == 4
