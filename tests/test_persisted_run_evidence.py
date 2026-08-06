# -*- coding: utf-8 -*-
"""
tests/test_persisted_run_evidence.py — 產物驗證通過宣告成功與失敗拒絕回報原因。

覆蓋需求：
- verify_persisted_run_evidence 在產物存在、可讀且驗證通過時宣告成功
- verify_persisted_run_evidence 在產物缺失、不可讀或驗證失敗時拒絕成功並回報原因
- persist_run_failure 正確持久化拒絕原因到 summary.json
- load_run_evidence 正確讀取與解析評估證據
- validate_evidence_manifest 重新驗證 manifest 內容一致性
"""
import hashlib
import json
import os

import pytest

from lib import completion_gate


# ---------------------------------------------------------------------------
# Helpers — 建立受控 run 目錄
# ---------------------------------------------------------------------------

def _make_run_dir(tmp_path, run_name="test_run", details=None, summary_extra=None):
    """建立包含 summary.json 與 details.jsonl 的 run 目錄。"""
    run_dir = tmp_path / run_name
    run_dir.mkdir(parents=True)

    if details is None:
        details = [{"id": 1, "answer": "some answer", "total_score": 80.0}]

    details_path = run_dir / "details.jsonl"
    with open(details_path, "w", encoding="utf-8") as f:
        for rec in details:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary_data = {
        "timestamp": "2026-08-06 00:00:00",
        "prompt_file": "prompt.md",
        "prompt_hash": "a" * 64,
        "question_file": "questions.jsonl",
        "total_questions": 1,
        "average_score": 80.0,
        "type_averages": {},
        "failure_counts": {},
        "word_count_pass_rate": 100.0,
        "risk_perfect_rate": 100.0,
        "elapsed_seconds": 0.1,
        "char_count": 10,
    }
    if summary_extra:
        summary_data.update(summary_extra)

    # Build evidence manifest with the actual files
    manifest_entries = []
    for fname in ["summary.json", "details.jsonl"]:
        fpath = run_dir / fname
        entry = completion_gate._read_evidence_file(str(fpath), str(tmp_path))
        if entry[0]:
            manifest_entries.append(entry[0])
    summary_data["evidence_manifest"] = manifest_entries

    summary_path = run_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    return str(run_dir)


# ---------------------------------------------------------------------------
# verify_persisted_run_evidence — 產物驗證通過宣告成功
# ---------------------------------------------------------------------------

class TestPersistedRunEvidenceSuccess:
    """產物存在、可讀且驗證通過時，verify_persisted_run_evidence 宣告成功。"""

    def test_valid_run_returns_completed(self, tmp_path):
        """正常 run 目錄 → status=completed, reason_code=''。"""
        run_dir = _make_run_dir(tmp_path)
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        assert result["status"] == "completed"
        assert result["completion_status"] == "completed"
        assert result["reason_code"] == ""
        assert result["rejection_reason"] == ""
        assert result["rejection_reasons"] == []
        assert result["evidence_manifest"] != []
        assert result["evidence_errors"] == []

    def test_valid_run_has_verified_manifest(self, tmp_path):
        """正常 run → evidence_manifest 全部 verified=True。"""
        run_dir = _make_run_dir(tmp_path)
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        for entry in result["evidence_manifest"]:
            assert entry["verified"] is True
            assert entry["size"] > 0
            assert entry["sha256"] != ""

    def test_valid_run_manifest_matches_files(self, tmp_path):
        """正常 run → evidence_manifest 指向實際存在的檔案。"""
        run_dir = _make_run_dir(tmp_path)
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        for entry in result["evidence_manifest"]:
            full_path = os.path.join(tmp_path, entry["path"])
            assert os.path.isfile(full_path), f"manifest points to missing file: {entry['path']}"


# ---------------------------------------------------------------------------
# verify_persisted_run_evidence — 產物缺失拒絕成功並回報原因
# ---------------------------------------------------------------------------

class TestPersistedRunEvidenceMissing:
    """產物缺失時，verify_persisted_run_evidence 拒絕成功並回報原因。"""

    def test_missing_run_dir_returns_failed(self, tmp_path):
        """run 目錄不存在 → status=failed, reason_code=NO_VALID_OUTPUT。"""
        result = completion_gate.verify_persisted_run_evidence(str(tmp_path / "nonexistent"))
        assert result["status"] == "failed"
        assert result["completion_status"] == "failed"
        assert result["reason_code"] == "NO_VALID_OUTPUT"
        assert "missing or invalid" in result["rejection_reason"]
        assert len(result["rejection_reasons"]) > 0

    def test_none_run_dir_returns_failed(self):
        """run_dir=None → status=failed。"""
        result = completion_gate.verify_persisted_run_evidence(None)
        assert result["status"] == "failed"
        assert result["reason_code"] == "NO_VALID_OUTPUT"

    def test_empty_string_run_dir_returns_failed(self):
        """run_dir='' → status=failed。"""
        result = completion_gate.verify_persisted_run_evidence("")
        assert result["status"] == "failed"
        assert result["reason_code"] == "NO_VALID_OUTPUT"

    def test_run_dir_without_summary_returns_failed(self, tmp_path):
        """run 目錄存在但缺少 summary.json → status=failed, MISSING_EVIDENCE_MANIFEST。"""
        run_dir = tmp_path / "incomplete_run"
        run_dir.mkdir()
        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "MISSING_EVIDENCE_MANIFEST"
        assert "summary" in result["rejection_reason"]

    def test_run_dir_with_corrupted_summary_returns_failed(self, tmp_path):
        """summary.json 內容損壞（非 JSON）→ status=failed, MISSING_EVIDENCE_MANIFEST。"""
        run_dir = tmp_path / "corrupted_run"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text("not valid json {{{")
        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "MISSING_EVIDENCE_MANIFEST"


# ---------------------------------------------------------------------------
# verify_persisted_run_evidence — 產物不可讀拒絕成功並回報原因
# ---------------------------------------------------------------------------

class TestPersistedRunEvidenceUnreadable:
    """產物不可讀時，verify_persisted_run_evidence 拒絕成功並回報原因。"""

    def test_empty_summary_returns_failed(self, tmp_path):
        """summary.json 為空檔 → status=failed, MISSING_EVIDENCE_MANIFEST。"""
        run_dir = tmp_path / "empty_summary_run"
        run_dir.mkdir()
        (run_dir / "summary.json").write_bytes(b"")
        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "MISSING_EVIDENCE_MANIFEST"

    def test_summary_without_manifest_returns_failed(self, tmp_path):
        """summary.json 無 evidence_manifest 欄位 → status=failed。"""
        run_dir = tmp_path / "no_manifest_run"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"average_score": 80.0}), encoding="utf-8"
        )
        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] in {"MISSING_EVIDENCE_MANIFEST", "INVALID_EVIDENCE_MANIFEST"}

    def test_summary_with_empty_manifest_returns_failed(self, tmp_path):
        """summary.json 的 evidence_manifest 為空列表 → INVALID_EVIDENCE_MANIFEST。"""
        run_dir = tmp_path / "empty_manifest_run"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"average_score": 80.0, "evidence_manifest": []}),
            encoding="utf-8",
        )
        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"


# ---------------------------------------------------------------------------
# verify_persisted_run_evidence — 驗證失敗拒絕成功並回報原因
# ---------------------------------------------------------------------------

class TestPersistedRunEvidenceVerificationFailed:
    """驗證失敗時，verify_persisted_run_evidence 拒絕成功並回報原因。"""

    def test_failed_completion_status_returns_failed(self, tmp_path):
        """summary.completion_status='failed' → status=failed, NON_COMPLETED_STATUS。"""
        run_dir = _make_run_dir(tmp_path, summary_extra={
            "completion_status": "failed",
            "rejection_reason": "evidence validation failed",
        })
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        assert result["status"] == "failed"
        assert result["completion_status"] == "failed"
        assert result["reason_code"] == "NON_COMPLETED_STATUS"
        assert result["rejection_reason"] != ""

    def test_incomplete_completion_status_returns_failed(self, tmp_path):
        """summary.completion_status='incomplete' → status=failed。"""
        run_dir = _make_run_dir(tmp_path, summary_extra={
            "completion_status": "incomplete",
        })
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        assert result["status"] == "failed"
        assert result["completion_status"] == "incomplete"

    def test_summary_with_evidence_errors_returns_failed(self, tmp_path):
        """summary.evidence_errors 非空 → INVALID_EVIDENCE_MANIFEST。"""
        run_dir = _make_run_dir(tmp_path, summary_extra={
            "evidence_errors": ["file missing", "hash mismatch"],
        })
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"
        assert any("file missing" in r for r in result["rejection_reasons"])

    def test_manifest_sha256_mismatch_returns_failed(self, tmp_path):
        """evidence_manifest 的 sha256 與實際檔案不符 → INVALID_EVIDENCE_MANIFEST。"""
        run_dir = tmp_path / "hash_mismatch_run"
        run_dir.mkdir()

        details_path = run_dir / "details.jsonl"
        details_path.write_text('{"id": 1, "answer": "ok", "total_score": 80}\n', encoding="utf-8")

        # Create summary with a deliberately wrong hash
        bad_hash = "0" * 64
        manifest_entry = {
            "path": "hash_mismatch_run/details.jsonl",
            "size": details_path.stat().st_size,
            "sha256": bad_hash,
            "verified": True,
        }
        summary_data = {
            "average_score": 80.0,
            "evidence_manifest": [manifest_entry],
        }
        summary_path = run_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False)

        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"
        assert any("sha256 mismatch" in r for r in result["rejection_reasons"])

    def test_manifest_size_mismatch_returns_failed(self, tmp_path):
        """evidence_manifest 的 size 與實際檔案不符 → INVALID_EVIDENCE_MANIFEST。"""
        run_dir = tmp_path / "size_mismatch_run"
        run_dir.mkdir()

        details_path = run_dir / "details.jsonl"
        details_path.write_text('{"id": 1}\n', encoding="utf-8")
        actual_size = details_path.stat().st_size

        real_hash = hashlib.sha256(details_path.read_bytes()).hexdigest()
        manifest_entry = {
            "path": "size_mismatch_run/details.jsonl",
            "size": actual_size + 999,  # wrong size
            "sha256": real_hash,
            "verified": True,
        }
        summary_data = {
            "average_score": 80.0,
            "evidence_manifest": [manifest_entry],
        }
        summary_path = run_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False)

        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"
        assert any("size mismatch" in r for r in result["rejection_reasons"])

    def test_manifest_points_to_deleted_file_returns_failed(self, tmp_path):
        """evidence_manifest 指向已刪除的檔案 → INVALID_EVIDENCE_MANIFEST。"""
        run_dir = tmp_path / "deleted_file_run"
        run_dir.mkdir()

        # Create file, compute hash, then delete it
        temp_file = run_dir / "ephemeral.jsonl"
        temp_file.write_text('{"id": 1}\n', encoding="utf-8")
        real_hash = hashlib.sha256(temp_file.read_bytes()).hexdigest()
        file_size = temp_file.stat().st_size
        temp_file.unlink()

        manifest_entry = {
            "path": "deleted_file_run/ephemeral.jsonl",
            "size": file_size,
            "sha256": real_hash,
            "verified": True,
        }
        summary_data = {
            "average_score": 80.0,
            "evidence_manifest": [manifest_entry],
        }
        summary_path = run_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False)

        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "INVALID_EVIDENCE_MANIFEST"

    def test_no_meaningful_results_returns_failed(self, tmp_path):
        """details.jsonl 全部為空或 errored → NO_VALID_OUTPUT。"""
        run_dir = tmp_path / "no_results_run"
        run_dir.mkdir()

        details_path = run_dir / "details.jsonl"
        details_path.write_text(
            '{"id": 1, "error": "timeout", "total_score": 0}\n',
            encoding="utf-8",
        )

        # Build valid manifest for the file
        entry = completion_gate._read_evidence_file(str(details_path), str(tmp_path))
        manifest_entries = [entry[0]] if entry[0] else []

        summary_data = {
            "average_score": 0.0,
            "evidence_manifest": manifest_entries,
        }
        summary_path = run_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False)

        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] == "NO_VALID_OUTPUT"
        assert "no meaningful result" in result["rejection_reason"]

    def test_empty_details_returns_failed(self, tmp_path):
        """details.jsonl 為空 → NO_VALID_OUTPUT（manifest 驗證先失敗，然後無有效結果）。"""
        run_dir = tmp_path / "empty_details_run"
        run_dir.mkdir()

        details_path = run_dir / "details.jsonl"
        details_path.write_text("dummy", encoding="utf-8")

        entry = completion_gate._read_evidence_file(str(details_path), str(tmp_path))
        manifest_entries = [entry[0]] if entry[0] else []

        summary_data = {
            "average_score": 80.0,
            "evidence_manifest": manifest_entries,
        }
        summary_path = run_dir / "summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, ensure_ascii=False)

        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"
        assert result["reason_code"] in {"NO_VALID_OUTPUT", "INVALID_EVIDENCE_MANIFEST"}


# ---------------------------------------------------------------------------
# persist_run_failure — 拒絕原因持久化
# ---------------------------------------------------------------------------

class TestPersistRunFailure:
    """persist_run_failure 正確持久化拒絕原因到 summary.json。"""

    def test_persists_failure_to_summary(self, tmp_path):
        """正常 run 目錄 → persist_run_failure 寫入 failed 狀態到 summary.json。"""
        run_dir = _make_run_dir(tmp_path)
        failure = {
            "reason_code": "INVALID_EVIDENCE_MANIFEST",
            "rejection_reason": "evidence manifest failed revalidation",
            "rejection_reasons": ["sha256 mismatch", "size mismatch"],
            "evidence_errors": ["sha256 mismatch"],
        }
        success = completion_gate.persist_run_failure(run_dir, failure)
        assert success is True

        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["completion_status"] == "failed"
        assert saved["status"] == "failed"
        assert saved["reason_code"] == "INVALID_EVIDENCE_MANIFEST"
        assert saved["rejection_reason"] == "evidence manifest failed revalidation"
        assert "sha256 mismatch" in saved["rejection_reasons"]
        assert saved["evidence_manifest"] == []

    def test_returns_false_for_empty_run_dir(self):
        """run_dir 為空 → 回傳 False。"""
        result = completion_gate.persist_run_failure("", {"reason_code": "TEST"})
        assert result is False

    def test_returns_false_for_none_run_dir(self):
        """run_dir=None → 回傳 False。"""
        result = completion_gate.persist_run_failure(None, {"reason_code": "TEST"})
        assert result is False

    def test_returns_false_for_missing_summary(self, tmp_path):
        """summary.json 不存在 → 回傳 False。"""
        run_dir = tmp_path / "no_summary"
        run_dir.mkdir()
        result = completion_gate.persist_run_failure(
            str(run_dir), {"reason_code": "TEST"}
        )
        assert result is False

    def test_returns_false_for_corrupted_summary(self, tmp_path):
        """summary.json 損壞 → 回傳 False。"""
        run_dir = tmp_path / "bad_summary"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text("not json {{{")
        result = completion_gate.persist_run_failure(
            str(run_dir), {"reason_code": "TEST"}
        )
        assert result is False

    def test_overwrites_existing_completed_status(self, tmp_path):
        """persist_run_failure 覆蓋原本的 completed 狀態。"""
        run_dir = _make_run_dir(tmp_path)
        failure = {"reason_code": "LATE_FAILURE", "rejection_reason": "post-completion error"}
        completion_gate.persist_run_failure(run_dir, failure)

        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["completion_status"] == "failed"
        assert saved["reason_code"] == "LATE_FAILURE"

    def test_persists_rejection_reasons_list(self, tmp_path):
        """persist_run_failure 正確儲存 rejection_reasons 列表。"""
        run_dir = _make_run_dir(tmp_path)
        reasons = ["reason A", "reason B", "reason C"]
        failure = {
            "reason_code": "MULTI_FAILURE",
            "rejection_reason": reasons[0],
            "rejection_reasons": reasons,
        }
        completion_gate.persist_run_failure(run_dir, failure)

        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["rejection_reasons"] == reasons
        assert saved["reject_reasons"] == reasons


# ---------------------------------------------------------------------------
# load_run_evidence — 證據讀取與解析
# ---------------------------------------------------------------------------

class TestLoadRunEvidence:
    """load_run_evidence 正確讀取與解析評估證據。"""

    def test_valid_run_returns_artifacts_results_summary(self, tmp_path):
        """正常 run 目錄 → 回傳完整 artifacts/results/summary。"""
        run_dir = _make_run_dir(tmp_path)
        artifacts, results, summary = completion_gate.load_run_evidence(run_dir)
        assert "details.jsonl" in artifacts
        assert len(results) == 1
        assert results[0]["total_score"] == 80.0
        assert summary["average_score"] == 80.0

    def test_missing_run_dir_returns_empty(self, tmp_path):
        """run 目錄不存在 → 回傳空結構。"""
        artifacts, results, summary = completion_gate.load_run_evidence(
            str(tmp_path / "nonexistent")
        )
        assert artifacts == {}
        assert results == []
        assert summary == {}

    def test_none_run_dir_returns_empty(self):
        """run_dir=None → 回傳空結構。"""
        artifacts, results, summary = completion_gate.load_run_evidence(None)
        assert artifacts == {}
        assert results == []
        assert summary == {}

    def test_empty_string_run_dir_returns_empty(self):
        """run_dir='' → 回傳空結構。"""
        artifacts, results, summary = completion_gate.load_run_evidence("")
        assert artifacts == {}
        assert results == []

    def test_missing_summary_json_returns_empty_summary(self, tmp_path):
        """缺少 summary.json → summary 為空。"""
        run_dir = tmp_path / "no_summary"
        run_dir.mkdir()
        details_path = run_dir / "details.jsonl"
        details_path.write_text('{"id": 1, "answer": "ok", "total_score": 80}\n', encoding="utf-8")
        artifacts, results, summary = completion_gate.load_run_evidence(str(run_dir))
        assert "summary.json" not in artifacts
        assert summary == {}

    def test_missing_details_jsonl_returns_empty_results(self, tmp_path):
        """缺少 details.jsonl → results 為空。"""
        run_dir = tmp_path / "no_details"
        run_dir.mkdir()
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps({"average_score": 80.0}), encoding="utf-8")
        artifacts, results, summary = completion_gate.load_run_evidence(str(run_dir))
        assert "details.jsonl" not in artifacts
        assert results == []

    def test_corrupted_details_returns_empty_results(self, tmp_path):
        """details.jsonl 損壞 → results 為空。"""
        run_dir = tmp_path / "bad_details"
        run_dir.mkdir()
        (run_dir / "details.jsonl").write_text("not json\n{{{\n", encoding="utf-8")
        artifacts, results, summary = completion_gate.load_run_evidence(str(run_dir))
        assert results == []


# ---------------------------------------------------------------------------
# validate_evidence_manifest — manifest 重新驗證
# ---------------------------------------------------------------------------

class TestValidateEvidenceManifest:
    """validate_evidence_manifest 重新讀取並驗證 manifest 內容一致性。"""

    def test_valid_manifest_passes(self, tmp_path):
        """有效 manifest → 回傳 verified 列表，無 errors。"""
        file_path = tmp_path / "evidence.json"
        file_path.write_text('{"key": "value"}', encoding="utf-8")
        entry = completion_gate._read_evidence_file(str(file_path), str(tmp_path))
        assert entry[0] is not None

        verified, errors = completion_gate.validate_evidence_manifest(
            [entry[0]], str(tmp_path)
        )
        assert errors == []
        assert len(verified) == 1
        assert verified[0]["verified"] is True

    def test_empty_manifest_returns_errors(self):
        """空 manifest → 回傳 errors。"""
        verified, errors = completion_gate.validate_evidence_manifest([])
        assert errors != []
        assert "empty" in errors[0]

    def test_none_manifest_returns_errors(self):
        """manifest=None → 回傳 errors。"""
        verified, errors = completion_gate.validate_evidence_manifest(None)
        assert errors != []

    def test_manifest_with_non_dict_entry_returns_error(self):
        """manifest 含非 dict 項目 → 回傳 error。"""
        verified, errors = completion_gate.validate_evidence_manifest(["not a dict"])
        assert errors != []
        assert "not an object" in errors[0]

    def test_manifest_with_unverified_entry_returns_error(self):
        """manifest 含 verified=False 的項目 → 回傳 error。"""
        entry = {"path": "file.json", "size": 10, "sha256": "abc", "verified": False}
        verified, errors = completion_gate.validate_evidence_manifest([entry])
        assert errors != []
        assert "not marked verified" in errors[0]

    def test_manifest_with_wrong_sha256_returns_error(self, tmp_path):
        """manifest sha256 與實際不符 → 回傳 sha256 mismatch error。"""
        file_path = tmp_path / "evidence.json"
        file_path.write_text('{"data": 123}', encoding="utf-8")
        entry = completion_gate._read_evidence_file(str(file_path), str(tmp_path))
        assert entry[0] is not None

        tampered = dict(entry[0])
        tampered["sha256"] = "0" * 64

        verified, errors = completion_gate.validate_evidence_manifest(
            [tampered], str(tmp_path)
        )
        assert errors != []
        assert "sha256 mismatch" in errors[0]

    def test_manifest_with_wrong_size_returns_error(self, tmp_path):
        """manifest size 與實際不符 → 回傳 size mismatch error。"""
        file_path = tmp_path / "evidence.json"
        file_path.write_text('{"data": 123}', encoding="utf-8")
        entry = completion_gate._read_evidence_file(str(file_path), str(tmp_path))
        assert entry[0] is not None

        tampered = dict(entry[0])
        tampered["size"] = 999999

        verified, errors = completion_gate.validate_evidence_manifest(
            [tampered], str(tmp_path)
        )
        assert errors != []
        assert "size mismatch" in errors[0]


# ---------------------------------------------------------------------------
# 端對端：verify_persisted_run_evidence + persist_run_failure 完整流程
# ---------------------------------------------------------------------------

class TestEndToEndPersistedEvidence:
    """端對端驗證：從建立 run 到驗證成功或失敗再到持久化拒絕原因。"""

    def test_success_flow_validates_and_declares_completed(self, tmp_path):
        """完整成功流程：建立有效 run → 驗證通過 → status=completed。"""
        run_dir = _make_run_dir(tmp_path)
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        assert result["status"] == "completed"
        assert result["evidence_manifest"] != []

    def test_failure_flow_rejects_and_persists_reason(self, tmp_path):
        """完整失敗流程：建立無效 run → 驗證失敗 → 拒絕成功 → 持久化拒絕原因。"""
        run_dir = tmp_path / "failing_run"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(json.dumps({
            "average_score": 80.0,
            "evidence_manifest": [],
            "evidence_errors": ["initial error"],
        }), encoding="utf-8")
        (run_dir / "details.jsonl").write_text(
            '{"id": 1, "answer": "ok", "total_score": 80}\n', encoding="utf-8"
        )

        # First verify — should fail
        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "failed"

        # Persist the failure
        persisted = completion_gate.persist_run_failure(str(run_dir), result)
        assert persisted is True

        # Re-verify — should still show failed with persisted reason
        result2 = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result2["status"] == "failed"
        assert result2["reason_code"] in {"INVALID_EVIDENCE_MANIFEST", "NON_COMPLETED_STATUS"}

    def test_tampered_evidence_rejected_after_persist(self, tmp_path):
        """竄改產物後重新驗證：hash/size 不符 → 拒絕成功。"""
        run_dir = _make_run_dir(tmp_path)

        # Verify initially passes
        result = completion_gate.verify_persisted_run_evidence(run_dir)
        assert result["status"] == "completed"

        # Tamper with details.jsonl — keep same size to test sha256 detection
        details_path = os.path.join(run_dir, "details.jsonl")
        original_size = os.path.getsize(details_path)
        # Pad content to match original size
        tampered_content = '{"id": 1, "answer": "X", "total_score": 99}'
        padding = original_size - len(tampered_content.encode("utf-8"))
        if padding > 0:
            tampered_content = tampered_content + " " * padding
        with open(details_path, "w", encoding="utf-8") as f:
            f.write(tampered_content)

        # Re-verify — should fail due to hash mismatch
        result2 = completion_gate.verify_persisted_run_evidence(run_dir)
        assert result2["status"] == "failed"
        assert result2["reason_code"] == "INVALID_EVIDENCE_MANIFEST"
        assert any("sha256 mismatch" in r for r in result2["rejection_reasons"])
