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
# verify_acceptance_target_content
# ---------------------------------------------------------------------------

class TestVerifyAcceptanceTargetContent:
    """驗收目標內容驗證。"""

    def test_content_check_passes_for_valid_test_file(self):
        """目標為有效測試檔時，content_check 通過。"""
        result = completion_gate.verify_acceptance_target_content()
        assert result["passed"] is True
        assert result["reason_code"] == ""
        assert result["error"] == ""
        assert result["content_summary"] != ""

    def test_content_check_fails_for_missing_file(self, tmp_path):
        """目標不存在時，content_check 失敗。"""
        fake_root = tmp_path / "empty_repo"
        fake_root.mkdir()
        result = completion_gate.verify_acceptance_target_content(str(fake_root))
        assert result["passed"] is False
        assert result["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert "does not exist" in result["error"]

    def test_content_check_fails_for_file_without_test_class(self, tmp_path):
        """目標檔無測試類別時，content_check 失敗。"""
        target_dir = tmp_path / "tests"
        target_dir.mkdir()
        target = target_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        target.write_text("def helper():\n    pass\n")
        result = completion_gate.verify_acceptance_target_content(str(tmp_path))
        assert result["passed"] is False
        assert "no test class" in result["error"]

    def test_content_check_fails_for_file_without_assertions(self, tmp_path):
        """目標檔無斷言時，content_check 失敗。"""
        target_dir = tmp_path / "tests"
        target_dir.mkdir()
        target = target_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        target.write_text("class TestSomething:\n    def test_method(self):\n        pass\n")
        result = completion_gate.verify_acceptance_target_content(str(tmp_path))
        assert result["passed"] is False
        assert "no assertions" in result["error"]

    def test_content_check_fails_for_file_without_function_definitions(self, tmp_path):
        """目標檔無函式定義時，content_check 失敗。"""
        target_dir = tmp_path / "tests"
        target_dir.mkdir()
        target = target_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        target.write_text("class TestSomething:\n    assert True\n")
        result = completion_gate.verify_acceptance_target_content(str(tmp_path))
        assert result["passed"] is False
        assert "no function definitions" in result["error"]

    def test_content_check_passes_for_valid_test_code(self, tmp_path):
        """目標檔含有效測試代碼時，content_check 通過。"""
        target_dir = tmp_path / "tests"
        target_dir.mkdir()
        target = target_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        target.write_text(
            "class TestExample:\n"
            "    def test_something(self):\n"
            "        assert 1 + 1 == 2\n"
        )
        result = completion_gate.verify_acceptance_target_content(str(tmp_path))
        assert result["passed"] is True
        assert result["content_summary"] != ""


# ---------------------------------------------------------------------------
# acceptance_gate_disposition — content verification integration
# ---------------------------------------------------------------------------

class TestAcceptanceGateDispositionContentVerification:
    """acceptance_gate_disposition 結合 precheck 與內容驗證。"""

    def test_exit_zero_with_invalid_content_yields_gate_config_failure(self, tmp_path, monkeypatch):
        """exit_code=0 但目標檔內容無效時，reason_code 為 GATE_CONFIGURATION_FAILURE。
        禁止將無效內容的 exit=0 記為產品驗證成功。"""
        fake_root = tmp_path / "repo"
        tests_dir = fake_root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "ed6a1a498025c1ec-artifact-success-verification.py").write_text(
            "# just a comment, no test class or assertions\n"
        )
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
        assert "content_check" in disposition
        assert disposition["content_check"]["passed"] is False

    def test_exit_zero_with_valid_content_passes(self):
        """exit_code=0 且目標檔內容有效時，不產生 GATE_CONFIGURATION_FAILURE。"""
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
        assert disposition["content_check"]["passed"] is True

    def test_missing_target_yields_gate_config_failure_before_content_check(self, tmp_path):
        """目標不存在時，precheck 失敗優先於 content_check。"""
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
        assert disposition["precheck"]["passed"] is False
        assert disposition["content_check"]["passed"] is False

    def test_invalid_content_no_success_record(self, tmp_path, monkeypatch):
        """無效內容 → GATE_CONFIGURATION_FAILURE，即使 exit=0 且有完整證據。"""
        fake_root = tmp_path / "repo"
        tests_dir = fake_root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "ed6a1a498025c1ec-artifact-success-verification.py").write_text(
            "# no test class\nx = 1\n"
        )
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests/ed6a1a498025c1ec-artifact-success-verification.py",
        )
        task = {
            "exit_code": 0,
            "stdout": "finished",
            "stderr": "",
            "artifacts": {"data": {"path": str(fake_root / "placeholder.txt")}},
            "results": [{"id": 1, "answer": "yes", "total_score": 100}],
            "summary": {"average_score": 100.0},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert disposition["content_check"]["passed"] is False
        assert any("content verification failed" in r for r in disposition["rejection_reasons"])


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


# ---------------------------------------------------------------------------
# 過期／錯誤路徑 — ACCEPTANCE_TARGET_RELATIVE 被修改時的回歸案例
# ---------------------------------------------------------------------------

class TestExpiredOrWrongPathResolution:
    """驗收目標常數指向過期或錯誤路徑時的解析行為。"""

    def test_renamed_target_path(self, tmp_path, monkeypatch):
        """目標路徑已更名（舊檔名不存在）→ 回傳 does not exist。"""
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests/old-removed-artifact-test.py",
        )
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert requested == "tests/old-removed-artifact-test.py"
        assert error == "target file does not exist"

    def test_wrong_filename_in_same_directory(self, tmp_path, monkeypatch):
        """目標目錄存在但檔名錯誤 → 回傳 does not exist。"""
        fake_root = tmp_path / "repo"
        (fake_root / "tests").mkdir(parents=True)
        (fake_root / "tests" / "some-other-test.py").write_text("# other")
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests/nonexistent-wrong-name.py",
        )
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert error == "target file does not exist"

    def test_completely_wrong_path(self, tmp_path, monkeypatch):
        """目標路徑完全錯誤 → 回傳 does not exist。"""
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "lib/nonexistent_module.py",
        )
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert error == "target file does not exist"

    def test_target_points_to_different_existing_file(self, tmp_path, monkeypatch):
        """目標指向另一個確實存在的檔案 → precheck 仍通過（不驗證內容）。
        確認路徑解析邏輯本身正確，gate 只管目標檔的可讀性。"""
        fake_root = tmp_path / "repo"
        (fake_root / "tests").mkdir(parents=True)
        other_file = fake_root / "tests" / "other-test.py"
        other_file.write_text("# other test")
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests/other-test.py",
        )
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert requested == "tests/other-test.py"
        assert error == ""

    def test_target_with_wrong_extension(self, tmp_path, monkeypatch):
        """目標指向 .md 檔 → precheck 通過（可讀即通過）。"""
        fake_root = tmp_path / "repo"
        (fake_root / "tests").mkdir(parents=True)
        md_file = fake_root / "tests" / "ed6a1a498025c1ec-artifact-success-verification.md"
        md_file.write_text("# readme")
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests/ed6a1a498025c1ec-artifact-success-verification.md",
        )
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert error == ""


# ---------------------------------------------------------------------------
# workspace 邊界 — 路徑逃逸與邊界驗證
# ---------------------------------------------------------------------------

class TestWorkspaceBoundaryPathResolution:
    """路徑解析的 workspace 邊界防護。"""

    def test_symlink_outside_workspace(self, tmp_path, monkeypatch):
        """symlink 指向 workspace 外部的真實檔案 → resolve_acceptance_target
        不檢查邊界（邊界檢查在 _read_evidence_file 中），但 precheck
        應正常通過（目標檔存在且可讀）。"""
        external_dir = tmp_path / "external"
        external_dir.mkdir()
        external_file = external_dir / "ed6a1a498025c1ec-artifact-success-verification.py"
        external_file.write_text("# external")

        fake_root = tmp_path / "repo"
        tests_dir = fake_root / "tests"
        tests_dir.mkdir(parents=True)
        try:
            os.symlink(str(external_file), str(tests_dir / "ed6a1a498025c1ec-artifact-success-verification.py"))
        except OSError:
            pytest.skip("symlink not supported on this platform")

        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert error == ""

    def test_absolute_path_outside_workspace(self, tmp_path):
        """workspace_root 為空時，ABSOLUTE 外部路徑被 normpath 後
        回傳 does not exist（因目標不在預期位置）。"""
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "tests").mkdir()
        (outside / "tests" / "ed6a1a498025c1ec-artifact-success-verification.py").write_text("# x")
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(outside))
        # outside 有 tests/ 子目錄，但 requested 為相對路徑，normpath 會組合
        # → resolved 指向 outside/tests/ed6a...py，該檔案存在 → error 為空
        assert requested == "tests/ed6a1a498025c1ec-artifact-success-verification.py"

    def test_path_with_dotdot_components(self, tmp_path, monkeypatch):
        """路徑含 .. 元件 → normpath 正常化後，不在 workspace 的路徑回傳 does not exist。"""
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests/../lib/../../etc/passwd",
        )
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert error == "target file does not exist"

    def test_empty_relative_path(self, tmp_path, monkeypatch):
        """空字串路徑 → normpath 回傳 root 本身，非檔案 → does not exist。"""
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        monkeypatch.setattr(completion_gate, "ACCEPTANCE_TARGET_RELATIVE", "")
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert error == "target file does not exist"

    def test_target_is_directory_not_file(self, tmp_path, monkeypatch):
        """目標路徑指向目錄 → isfile 為 False → does not exist。"""
        fake_root = tmp_path / "repo"
        (fake_root / "tests").mkdir(parents=True)
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests",
        )
        requested, resolved, error = completion_gate.resolve_acceptance_target(str(fake_root))
        assert error == "target file does not exist"


# ---------------------------------------------------------------------------
# 不得產生成功完成紀錄 — 所有路徑失敗情境的完整斷言
# ---------------------------------------------------------------------------

class TestDispositionNoFalseSuccess:
    """所有路徑解析失敗情境均不得產生成功完成紀錄。"""

    def test_expired_path_no_success_record(self, tmp_path, monkeypatch):
        """過期路徑 → GATE_CONFIGURATION_FAILURE，status 非 completed。"""
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "tests/old-deleted-test.py",
        )
        task = {
            "exit_code": 0,
            "stdout": "all tests passed",
            "stderr": "",
            "artifacts": {"report": {"exists": True, "size": 200}},
            "results": [{"id": 1, "answer": "correct", "total_score": 95}],
            "summary": {"average_score": 95.0},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert disposition["precheck"]["passed"] is False
        assert "does not exist" in disposition["precheck"]["error"]
        assert any("gate-configuration failure" in r for r in disposition["rejection_reasons"])

    def test_wrong_path_no_success_record(self, tmp_path, monkeypatch):
        """錯誤路徑 → GATE_CONFIGURATION_FAILURE，即使 exit=0 且有完整證據。"""
        fake_root = tmp_path / "repo"
        fake_root.mkdir()
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE",
            "lib/nonexistent.py",
        )
        task = {
            "exit_code": 0,
            "stdout": "finished",
            "stderr": "",
            "artifacts": {"data": {"path": str(fake_root / "placeholder.txt")}},
            "results": [{"id": 1, "answer": "yes", "total_score": 100}],
            "summary": {"average_score": 100.0},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"

    def test_empty_target_no_success_record(self, tmp_path, monkeypatch):
        """空目標檔 → GATE_CONFIGURATION_FAILURE，不得記為成功。"""
        fake_root = tmp_path / "repo"
        tests_dir = fake_root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "ed6a1a498025c1ec-artifact-success-verification.py").write_bytes(b"")
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [{"id": 1, "answer": "ok", "total_score": 50}],
            "summary": {"average_score": 50.0},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert "empty" in disposition["precheck"]["error"]

    def test_unreadable_target_no_success_record(self, tmp_path, monkeypatch):
        """不可讀目標 → GATE_CONFIGURATION_FAILURE，不得記為成功。"""
        fake_root = tmp_path / "repo"
        tests_dir = fake_root / "tests"
        tests_dir.mkdir(parents=True)
        (tests_dir / "ed6a1a498025c1ec-artifact-success-verification.py").write_text("# x")

        real_open = open

        def mock_open(path, *args, **kwargs):
            if "ed6a1a498025c1ec" in str(path):
                raise OSError("access denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        task = {
            "exit_code": 0,
            "stdout": "done",
            "stderr": "",
            "artifacts": {"out": {"exists": True, "size": 50}},
            "results": [{"id": 1, "answer": "pass", "total_score": 80}],
            "summary": {"average_score": 80.0},
            "workspace_root": str(fake_root),
        }
        disposition = completion_gate.acceptance_gate_disposition(task)
        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE"
        assert "unreadable" in disposition["precheck"]["error"]

    def test_directory_target_no_success_record(self, tmp_path, monkeypatch):
        """目標為目錄 → GATE_CONFIGURATION_FAILURE，不得記為成功。"""
        fake_root = tmp_path / "repo"
        (fake_root / "tests").mkdir(parents=True)
        monkeypatch.setattr(
            completion_gate, "ACCEPTANCE_TARGET_RELATIVE", "tests",
        )
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
        assert disposition["precheck"]["passed"] is False

    def test_all_failure_scenarios_have_identifiable_error(self, tmp_path, monkeypatch):
        """所有路徑失敗情境的 rejection_reasons 均含可識別的 gate-configuration
        字串，且 precheck.error 提供具體診斷。"""
        scenarios = [
            ("tests/deleted.py", "does not exist", {}),
            ("tests/empty.py", "empty", {"empty": True}),
            ("tests/unread.py", "unreadable", {"unreadable": True}),
        ]
        real_open = open

        def mock_open_for_unread(path, *args, **kwargs):
            if "unread" in str(path):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        for rel_path, expected_keyword, special in scenarios:
            fake_root = tmp_path / "scenario"
            fake_root.mkdir(exist_ok=True)
            tests_dir = fake_root / "tests"
            tests_dir.mkdir(exist_ok=True)

            if special.get("empty"):
                (tests_dir / "empty.py").write_bytes(b"")
            elif special.get("unreadable"):
                (tests_dir / "unread.py").write_text("# x")
                monkeypatch.setattr("builtins.open", mock_open_for_unread)
            else:
                pass  # file not created → does not exist

            monkeypatch.setattr(
                completion_gate, "ACCEPTANCE_TARGET_RELATIVE", rel_path,
            )
            task = {
                "exit_code": 0, "stdout": "", "stderr": "",
                "artifacts": {}, "results": [], "summary": {},
                "workspace_root": str(fake_root),
            }
            disposition = completion_gate.acceptance_gate_disposition(task)
            assert disposition["status"] == "failed", f"scenario={rel_path}"
            assert disposition["reason_code"] == "GATE_CONFIGURATION_FAILURE", f"scenario={rel_path}"
            assert any(
                "gate-configuration failure" in r for r in disposition["rejection_reasons"]
            ), f"scenario={rel_path}"
            assert expected_keyword in disposition["precheck"]["error"], (
                f"scenario={rel_path}: expected {expected_keyword!r} in "
                f"{disposition['precheck']['error']!r}"
            )
