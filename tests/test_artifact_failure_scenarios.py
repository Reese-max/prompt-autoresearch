# -*- coding: utf-8 -*-
"""
tests/test_artifact_failure_scenarios.py — 產物缺失、不可讀及內容驗證失敗的負向測試。

覆蓋需求：
- 產物缺失（missing artifacts）→ 任務標示失敗，回報具體原因
- 產物不可讀（unreadable artifacts）→ 任務標示失敗，回報具體原因
- 內容驗證失敗（content verification failure）→ 任務標示失敗，回報具體原因
"""
import hashlib
import json
import os

import pytest

from lib.completion_gate import (
    TaskResult,
    build_evidence_manifest,
    completion_disposition,
    verify_completion_evidence,
)


# ---------------------------------------------------------------------------
# 產物缺失（Missing Artifacts）
# ---------------------------------------------------------------------------

class TestMissingArtifacts:
    """產物缺失時，任務標示失敗並回報具體原因。"""

    def test_empty_artifacts_dict_fails(self, tmp_path):
        """artifacts 為空 dict → 失敗，回報 artifacts is empty。"""
        task = TaskResult(
            exit_code=0,
            artifacts={},
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("artifacts is empty" in r for r in reasons)

    def test_empty_artifacts_dict_disposition_failed(self, tmp_path):
        """artifacts 為空 dict → completion_disposition 回傳 failed。"""
        task = {
            "exit_code": 0,
            "artifacts": {},
            "results": [],
            "summary": {},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert disp["reason_code"] == "NO_VALID_EVIDENCE"
        assert "artifacts" in disp["missing_evidence_types"]

    def test_artifact_without_path_fails(self, tmp_path):
        """artifacts 含無路徑且無 legacy metadata 條目 → 失敗。"""
        task = TaskResult(
            exit_code=0,
            artifacts={"report": {"exists": False}},
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False

    def test_artifact_pointing_to_nonexistent_file_fails(self, tmp_path):
        """artifacts 指向不存在的檔案 → 失敗，回報檔案缺失。"""
        task = TaskResult(
            exit_code=0,
            artifacts={"report": {"path": str(tmp_path / "nonexistent.json")}},
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("unreadable" in r or "empty" in r or "missing" in r for r in reasons)

    def test_artifact_nonexistent_file_disposition_failed(self, tmp_path):
        """artifacts 指向不存在的檔案 → completion_disposition 回傳 failed。"""
        task = {
            "exit_code": 0,
            "artifacts": {"report": {"path": str(tmp_path / "missing.json")}},
            "results": [],
            "summary": {},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert disp["reason_code"] == "NO_VALID_EVIDENCE"

    def test_multiple_artifacts_all_missing_fails(self, tmp_path):
        """多個 artifacts 全部指向不存在的檔案 → 失敗。"""
        task = TaskResult(
            exit_code=0,
            artifacts={
                "details": {"path": str(tmp_path / "details.jsonl")},
                "summary": {"path": str(tmp_path / "summary.json")},
            },
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False

    def test_artifact_none_path_fails(self, tmp_path):
        """artifacts 路徑為 None → 失敗，回報路徑無效。"""
        manifest, errors = build_evidence_manifest(
            {"report": {"path": None}},
            workspace_root=str(tmp_path),
        )
        assert manifest == []
        assert any("empty or invalid" in e for e in errors)

    def test_artifacts_with_only_legacy_metadata_passes(self, tmp_path):
        """artifacts 含 legacy metadata（exists=True, size>0, 無 path）→ 通過。"""
        task = TaskResult(
            exit_code=0,
            artifacts={"report": {"exists": True, "size": 100}},
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is True
        assert reasons == []

    def test_artifacts_legacy_metadata_zero_size_fails(self, tmp_path):
        """artifacts 含 legacy metadata 但 size=0 → 失敗。"""
        task = TaskResult(
            exit_code=0,
            artifacts={"report": {"exists": True, "size": 0}},
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False


# ---------------------------------------------------------------------------
# 產物不可讀（Unreadable Artifacts）
# ---------------------------------------------------------------------------

class TestUnreadableArtifacts:
    """產物不可讀時，任務標示失敗並回報具體原因。"""

    def test_empty_file_fails(self, tmp_path):
        """產物檔案為空（0 bytes）→ 失敗，回報 evidence file is empty。"""
        artifact = tmp_path / "empty.json"
        artifact.write_bytes(b"")
        task = TaskResult(
            exit_code=0,
            artifacts={"report": {"path": str(artifact)}},
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("empty" in r for r in reasons)

    def test_empty_file_disposition_failed(self, tmp_path):
        """產物檔案為空 → completion_disposition 回傳 failed。"""
        artifact = tmp_path / "empty.json"
        artifact.write_bytes(b"")
        task = {
            "exit_code": 0,
            "artifacts": {"report": {"path": str(artifact)}},
            "results": [],
            "summary": {},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert any("empty" in e for e in disp["evidence_errors"])

    def test_permission_denied_file_fails(self, tmp_path, monkeypatch):
        """產物檔案因權限問題無法讀取 → 失敗，回報 unreadable。"""
        artifact = tmp_path / "secret.json"
        artifact.write_text('{"data": 1}', encoding="utf-8")

        real_open = open

        def mock_open(path, *args, **kwargs):
            if "secret.json" in str(path):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        task = TaskResult(
            exit_code=0,
            artifacts={"report": {"path": str(artifact)}},
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("unreadable" in r for r in reasons)

    def test_permission_denied_file_disposition_failed(self, tmp_path, monkeypatch):
        """產物檔案因權限問題無法讀取 → completion_disposition 回傳 failed。"""
        artifact = tmp_path / "secret.json"
        artifact.write_text('{"data": 1}', encoding="utf-8")

        real_open = open

        def mock_open(path, *args, **kwargs):
            if "secret.json" in str(path):
                raise OSError("permission denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        task = {
            "exit_code": 0,
            "artifacts": {"report": {"path": str(artifact)}},
            "results": [],
            "summary": {},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert any("unreadable" in e for e in disp["evidence_errors"])

    def test_file_outside_workspace_fails(self, tmp_path):
        """產物檔案位於 workspace 外部 → 失敗，回報 outside workspace。"""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        artifact = outside / "data.json"
        artifact.write_text('{"data": 1}', encoding="utf-8")

        manifest, errors = build_evidence_manifest(
            {"report": {"path": str(artifact)}},
            workspace_root=str(workspace),
        )
        assert manifest == []
        assert any("outside workspace" in e for e in errors)

    def test_multiple_artifacts_one_unreadable_fails(self, tmp_path, monkeypatch):
        """多個產物中有一個不可讀 → 整體失敗。"""
        good = tmp_path / "good.json"
        good.write_text('{"ok": true}', encoding="utf-8")
        bad = tmp_path / "bad.json"
        bad.write_text('{"secret": true}', encoding="utf-8")

        real_open = open

        def mock_open(path, *args, **kwargs):
            if "bad.json" in str(path):
                raise OSError("access denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        task = TaskResult(
            exit_code=0,
            artifacts={
                "good": {"path": str(good)},
                "bad": {"path": str(bad)},
            },
            results=[],
            summary={},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("unreadable" in r for r in reasons)

    def test_symlink_to_deleted_target_fails(self, tmp_path):
        """symlink 指向已被刪除的目標 → 失敗。"""
        real_file = tmp_path / "real.json"
        real_file.write_text('{"data": 1}', encoding="utf-8")
        link = tmp_path / "link.json"
        try:
            os.symlink(str(real_file), str(link))
        except OSError:
            pytest.skip("symlink not supported")
        real_file.unlink()

        manifest, errors = build_evidence_manifest(
            {"report": {"path": str(link)}},
            workspace_root=str(tmp_path),
        )
        assert manifest == []
        assert any("unreadable" in e or "empty" in e for e in errors)


# ---------------------------------------------------------------------------
# 內容驗證失敗（Content Verification Failure）
# ---------------------------------------------------------------------------

class TestContentVerificationFailure:
    """內容驗證失敗時，任務標示失敗並回報具體原因。"""

    def test_sha256_mismatch_fails(self, tmp_path):
        """產物檔案雜湊與 manifest 不符 → 失敗，回報 sha256 mismatch。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        file_path = run_dir / "details.jsonl"
        file_path.write_text('{"id": 1}\n', encoding="utf-8")

        real_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        bad_hash = "0" * 64

        manifest_entry = {
            "path": "run/details.jsonl",
            "size": file_path.stat().st_size,
            "sha256": bad_hash,
            "verified": True,
        }
        verified, errors = build_evidence_manifest(
            {"report": {"path": str(file_path)}},
            workspace_root=str(tmp_path),
        )
        # build_evidence_manifest 重新計算雜湊，所以不會有 mismatch
        # 但 validate_evidence_manifest 可以偵測
        from lib.completion_gate import validate_evidence_manifest
        result, val_errors = validate_evidence_manifest(
            [manifest_entry], str(tmp_path)
        )
        assert result == []
        assert any("sha256 mismatch" in e for e in val_errors)

    def test_sha256_mismatch_verify_persisted_run_fails(self, tmp_path):
        """verify_persisted_run_evidence 偵測到 sha256 mismatch → 失敗。"""
        run_dir = tmp_path / "tampered_run"
        run_dir.mkdir()

        details_path = run_dir / "details.jsonl"
        details_path.write_text("{\"id\": 1}\n", encoding="utf-8")
        real_hash = hashlib.sha256(details_path.read_bytes()).hexdigest()
        bad_hash = "0" * 64

        manifest_entry = {
            "path": "tampered_run/details.jsonl",
            "size": details_path.stat().st_size,
            "sha256": bad_hash,
            "verified": True,
        }
        summary_data = {
            "average_score": 80.0,
            "evidence_manifest": [manifest_entry],
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary_data), encoding="utf-8"
        )

        from lib.completion_gate import verify_persisted_run_evidence
        result = verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"
        assert any("sha256 mismatch" in r for r in result["rejection_reasons"])

    def test_size_mismatch_fails(self, tmp_path):
        """產物檔案大小與 manifest 不符 → 失敗，回報 size mismatch。"""
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        file_path = run_dir / "details.jsonl"
        file_path.write_text('{"id": 1}\n', encoding="utf-8")
        real_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()

        manifest_entry = {
            "path": "run/details.jsonl",
            "size": file_path.stat().st_size + 999,
            "sha256": real_hash,
            "verified": True,
        }

        from lib.completion_gate import validate_evidence_manifest
        result, errors = validate_evidence_manifest(
            [manifest_entry], str(tmp_path)
        )
        assert result == []
        assert any("size mismatch" in e for e in errors)

    def test_size_mismatch_verify_persisted_run_fails(self, tmp_path):
        """verify_persisted_run_evidence 偵測到 size mismatch → 失敗。"""
        run_dir = tmp_path / "sizediff_run"
        run_dir.mkdir()

        details_path = run_dir / "details.jsonl"
        details_path.write_text('{"id": 1}\n', encoding="utf-8")
        real_hash = hashlib.sha256(details_path.read_bytes()).hexdigest()

        manifest_entry = {
            "path": "sizediff_run/details.jsonl",
            "size": details_path.stat().st_size + 999,
            "sha256": real_hash,
            "verified": True,
        }
        summary_data = {
            "average_score": 80.0,
            "evidence_manifest": [manifest_entry],
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary_data), encoding="utf-8"
        )

        from lib.completion_gate import verify_persisted_run_evidence
        result = verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"
        assert any("size mismatch" in r for r in result["rejection_reasons"])

    def test_no_meaningful_result_evidence_fails(self, tmp_path):
        """details.jsonl 全部為空或 errored 結果 → 失敗，回報無有效輸出。"""
        run_dir = tmp_path / "empty_results_run"
        run_dir.mkdir()

        details_path = run_dir / "details.jsonl"
        details_path.write_text(
            '{"id": 1, "error": "timeout", "total_score": 0}\n',
            encoding="utf-8",
        )

        entry = build_evidence_manifest(
            {"details": {"path": str(details_path)}},
            workspace_root=str(tmp_path),
        )
        manifest_entries = entry[0] if entry[0] else []

        summary_data = {
            "average_score": 0.0,
            "evidence_manifest": manifest_entries,
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary_data), encoding="utf-8"
        )

        from lib.completion_gate import verify_persisted_run_evidence
        result = verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "NO_VALID_OUTPUT"
        assert "no meaningful result" in result["rejection_reason"]

    def test_manifest_points_to_deleted_file_fails(self, tmp_path):
        """evidence_manifest 指向已刪除的檔案 → 失敗。"""
        run_dir = tmp_path / "deleted_run"
        run_dir.mkdir()

        temp_file = run_dir / "ephemeral.jsonl"
        temp_file.write_text('{"id": 1}\n', encoding="utf-8")
        real_hash = hashlib.sha256(temp_file.read_bytes()).hexdigest()
        file_size = temp_file.stat().st_size
        temp_file.unlink()

        manifest_entry = {
            "path": "deleted_run/ephemeral.jsonl",
            "size": file_size,
            "sha256": real_hash,
            "verified": True,
        }
        summary_data = {
            "average_score": 80.0,
            "evidence_manifest": [manifest_entry],
        }
        summary_path = run_dir / "summary.json"
        summary_path.write_text(
            json.dumps(summary_data), encoding="utf-8"
        )

        from lib.completion_gate import verify_persisted_run_evidence
        result = verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"

    def test_unverified_manifest_entry_fails(self, tmp_path):
        """manifest 項目 verified=False → 失敗，回報 not marked verified。"""
        entry = {
            "path": "some/file.json",
            "size": 10,
            "sha256": "abc",
            "verified": False,
        }
        from lib.completion_gate import validate_evidence_manifest
        result, errors = validate_evidence_manifest([entry], str(tmp_path))
        assert result == []
        assert any("not marked verified" in e for e in errors)

    def test_non_dict_manifest_entry_fails(self):
        """manifest 含非 dict 項目 → 失敗，回報 not an object。"""
        from lib.completion_gate import validate_evidence_manifest
        result, errors = validate_evidence_manifest(["not a dict"])
        assert result == []
        assert any("not an object" in e for e in errors)

    def test_empty_manifest_fails(self):
        """空 manifest → 失敗，回報 empty or invalid。"""
        from lib.completion_gate import validate_evidence_manifest
        result, errors = validate_evidence_manifest([])
        assert result == []
        assert any("empty" in e for e in errors)


# ---------------------------------------------------------------------------
# 端對端：三種失敗情境透過 completion_disposition 回報
# ---------------------------------------------------------------------------

class TestEndToEndArtifactFailureDisposition:
    """端對端驗證：三種產物失敗情境透過 completion_disposition 正確回報。"""

    def test_missing_artifact_yields_failed_disposition(self, tmp_path):
        """缺失產物 → completion_disposition 回傳 status=failed 且含具體原因。"""
        task = {
            "exit_code": 0,
            "artifacts": {},
            "results": [],
            "summary": {},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert disp["reason_code"] == "NO_VALID_EVIDENCE"
        assert "artifacts" in disp["missing_evidence_types"]
        assert len(disp["rejection_reasons"]) > 0

    def test_unreadable_artifact_yields_failed_disposition(self, tmp_path, monkeypatch):
        """不可讀產物 → completion_disposition 回傳 status=failed 且含具體原因。"""
        artifact = tmp_path / "locked.json"
        artifact.write_text('{"data": 1}', encoding="utf-8")

        real_open = open

        def mock_open(path, *args, **kwargs):
            if "locked.json" in str(path):
                raise OSError("access denied")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", mock_open)
        task = {
            "exit_code": 0,
            "artifacts": {"report": {"path": str(artifact)}},
            "results": [],
            "summary": {},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert any("unreadable" in e for e in disp["evidence_errors"])

    def test_content_verification_failure_yields_failed_disposition(self, tmp_path):
        """內容驗證失敗（results 全部無效）→ completion_disposition 回傳 failed。"""
        task = {
            "exit_code": 0,
            "artifacts": {},
            "results": [{"id": 1, "error": "timeout", "total_score": 0}],
            "summary": {"average_score": 0},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert disp["reason_code"] == "NO_VALID_EVIDENCE"
        assert "results" in disp["missing_evidence_types"]

    def test_exit_nonzero_with_valid_artifacts_still_fails(self, tmp_path):
        """exit_code!=0 即使有有效產物 → 仍失敗（exit code 閘門優先）。"""
        artifact = tmp_path / "report.json"
        artifact.write_text('{"data": 1}', encoding="utf-8")
        task = {
            "exit_code": 1,
            "artifacts": {"report": {"path": str(artifact)}},
            "results": [{"id": 1, "answer": "ok", "total_score": 80}],
            "summary": {"average_score": 80.0},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert disp["reason_code"] == "NONZERO_EXIT_CODE"

    def test_all_evidence_sources_missing_yields_comprehensive_reasons(self, tmp_path):
        """所有證據來源皆缺失 → 回報所有缺失的證據來源。"""
        task = {
            "exit_code": 0,
            "artifacts": {},
            "results": [],
            "summary": {},
            "workspace_root": str(tmp_path),
        }
        disp = completion_disposition(task)
        assert disp["status"] == "failed"
        assert "artifacts" in disp["missing_evidence_types"]
        assert "results" in disp["missing_evidence_types"]
        assert "summary" in disp["missing_evidence_types"]
        assert disp["evidence_types"] == []
