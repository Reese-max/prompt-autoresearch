# -*- coding: utf-8 -*-
"""
端對端自動化測試：建立可讀產物並以斷言驗證，僅在驗證通過後標示成功。

覆蓋核心模組：
- lib/version.py：版本追蹤與雜湊計算
- lib/io.py：檔案讀寫與雜湊一致性
- lib/immutable_store.py：不可變版本儲存與雜湊追溯
- lib/completion_gate.py：完成資格閘門與證據驗證
- scripts/analyze_runs.py：run 分析與彙整
- api/feedback.py：回饋資料分析
"""
import hashlib
import json
import os

import pytest

from lib import completion_gate, immutable_store, io, version


# ---------------------------------------------------------------------------
# 輔助：可讀產物驗證器
# ---------------------------------------------------------------------------

class ArtifactVerifier:
    """建立並驗證可讀產物，只有所有檢查通過才標示成功。"""

    def __init__(self, tmp_path, artifact_name="report"):
        self.base_dir = tmp_path
        self.artifact_path = tmp_path / f"{artifact_name}.json"
        self.verification_path = tmp_path / f"{artifact_name}_verification.json"
        self.checks = []

    def create(self, payload):
        io.write_json(str(self.artifact_path), payload)
        return self

    def verify_exists(self):
        exists = self.artifact_path.exists()
        self.checks.append({"check": "exists", "passed": exists})
        return self

    def verify_readable(self):
        try:
            content = self.artifact_path.read_text(encoding="utf-8")
            readable = len(content.strip()) > 0
        except Exception:
            readable = False
        self.checks.append({"check": "readable", "passed": readable})
        return self

    def verify_json_parseable(self):
        try:
            data = json.loads(self.artifact_path.read_text(encoding="utf-8"))
            parseable = isinstance(data, dict) and len(data) > 0
        except Exception:
            parseable = False
        self.checks.append({"check": "json_parseable", "passed": parseable})
        return self

    def verify_content_matches(self, expected_keys):
        try:
            data = json.loads(self.artifact_path.read_text(encoding="utf-8"))
            all_present = all(k in data for k in expected_keys)
        except Exception:
            all_present = False
        self.checks.append({"check": "content_matches", "passed": all_present,
                            "expected_keys": expected_keys})
        return self

    def verify_sha256_integrity(self):
        try:
            raw = self.artifact_path.read_bytes()
            actual_hash = hashlib.sha256(raw).hexdigest()
            self.checks.append({"check": "sha256_integrity", "passed": True,
                                "hash": actual_hash})
        except Exception:
            self.checks.append({"check": "sha256_integrity", "passed": False})
        return self

    def finalize(self):
        """產出驗證報告，回傳 (all_passed, report)。"""
        all_passed = all(c["passed"] for c in self.checks)
        report = {
            "artifact": str(self.artifact_path.name),
            "all_passed": all_passed,
            "checks": self.checks,
        }
        io.write_json(str(self.verification_path), report)
        return all_passed, report


# ---------------------------------------------------------------------------
# 1. lib/version.py — 版本追蹤模組
# ---------------------------------------------------------------------------

class TestVersionTracking:
    """版本追蹤模組的端對端驗證。"""

    def test_get_program_version_returns_nonempty_string(self):
        ver = version.get_program_version()
        assert isinstance(ver, str)
        assert len(ver) > 0

    def test_get_program_version_full_matches_short_prefix(self):
        short = version.get_program_version()
        full = version.get_program_version_full()
        if full != "unknown":
            assert full.startswith(short) or short == full[:12]

    def test_compute_input_settings_hash_deterministic(self):
        h1 = version.compute_input_settings_hash()
        h2 = version.compute_input_settings_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_compute_input_settings_hash_changes_with_cli_args(self):
        h1 = version.compute_input_settings_hash(cli_args={"a": 1})
        h2 = version.compute_input_settings_hash(cli_args={"a": 2})
        assert h1 != h2

    def test_get_baseline_info_returns_dict_with_expected_keys(self, tmp_path):
        info = version.get_baseline_info(
            baseline_md_path=str(tmp_path / "missing.md"),
            baseline_meta_path=str(tmp_path / "missing.meta.json"),
        )
        assert isinstance(info, dict)
        assert "baseline_version" in info
        assert "baseline_hash" in info
        assert info["baseline_version"] == "unknown"
        assert info["baseline_hash"] == ""

    def test_version_tracking_artifact(self, tmp_path):
        """建立版本追蹤可讀產物，驗證通過才標示成功。"""
        verifier = ArtifactVerifier(tmp_path, "version_tracking")
        payload = {
            "program_version": version.get_program_version(),
            "program_version_full": version.get_program_version_full(),
            "input_hash": version.compute_input_settings_hash(),
            "baseline_info": version.get_baseline_info(
                baseline_md_path=str(tmp_path / "no.md"),
                baseline_meta_path=str(tmp_path / "no.json"),
            ),
        }
        verifier.create(payload)
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches(["program_version", "input_hash", "baseline_info"])
            .verify_sha256_integrity()
            .finalize()
        )
        assert passed, f"版本追蹤產物驗證失敗：{json.dumps(report, ensure_ascii=False)}"


# ---------------------------------------------------------------------------
# 2. lib/io.py — 檔案讀寫一致性
# ---------------------------------------------------------------------------

class TestIOArtifactConsistency:
    """檔案讀寫模組的產物一致性驗證。"""

    def test_write_json_roundtrip_with_unicode(self, tmp_path):
        path = tmp_path / "unicode.json"
        payload = {"中文鍵": "中文值", "nested": {"key": [1, 2, 3]}}
        io.write_json(str(path), payload)
        loaded = io.load_json(str(path))
        assert loaded == payload

        verifier = ArtifactVerifier(tmp_path, "io_unicode")
        verifier.create(loaded)
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .finalize()
        )
        assert passed, f"IO unicode 產物驗證失敗：{report}"

    def test_append_jsonl_and_read_jsonl_consistency(self, tmp_path):
        path = tmp_path / "events.jsonl"
        events = [
            {"event": "start", "ts": "2026-01-01T00:00:00"},
            {"event": "round", "ts": "2026-01-01T00:01:00", "score": 85.0},
            {"event": "stop", "ts": "2026-01-01T00:02:00"},
        ]
        for e in events:
            io.append_jsonl(str(path), e)

        rows = io.read_jsonl(str(path))
        assert len(rows) == 3
        assert rows[1]["score"] == 85.0

        verifier = ArtifactVerifier(tmp_path, "jsonl_consistency")
        verifier.create({"events": rows, "count": len(rows)})
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches(["events", "count"])
            .finalize()
        )
        assert passed, f"JSONL 一致性產物驗證失敗：{report}"


# ---------------------------------------------------------------------------
# 3. lib/immutable_store.py — 不可變版本儲存
# ---------------------------------------------------------------------------

class TestImmutableStoreArtifacts:
    """不可變版本儲存的端對端驗證。"""

    def test_store_version_and_readback(self, tmp_path):
        store_dir = tmp_path / "versions"
        store_dir.mkdir()
        payload = {"prompt": "test prompt", "score": 90.5}

        result = immutable_store.store_version(payload, str(store_dir), namespace="test")
        assert result["stored"] is True
        assert result["rejected"] is False

        loaded = immutable_store.load_version(str(store_dir), result["version_id"])
        assert loaded == payload

        verifier = ArtifactVerifier(tmp_path, "immutable_store")
        verifier.create({
            "store_result": result,
            "loaded_payload": loaded,
            "versions": immutable_store.list_versions(str(store_dir)),
        })
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches(["store_result", "loaded_payload", "versions"])
            .verify_sha256_integrity()
            .finalize()
        )
        assert passed, f"不可變儲存產物驗證失敗：{report}"

    def test_store_version_rejects_duplicate(self, tmp_path):
        store_dir = tmp_path / "dup_store"
        store_dir.mkdir()
        payload = {"data": "same"}

        r1 = immutable_store.store_version(payload, str(store_dir), namespace="dup")
        r2 = immutable_store.store_version(payload, str(store_dir), namespace="dup")

        assert r1["stored"] is True
        assert r2["stored"] is False
        assert r2["rejected"] is True
        assert r2["reason"] == "version_already_exists"

    def test_content_hash_deterministic(self):
        payload = {"a": 1, "b": [2, 3]}
        h1 = immutable_store.content_hash(payload)
        h2 = immutable_store.content_hash(payload)
        assert h1 == h2
        assert len(h1) == 64

    def test_content_hash_changes_with_different_payload(self):
        h1 = immutable_store.content_hash({"a": 1})
        h2 = immutable_store.content_hash({"a": 2})
        assert h1 != h2

    def test_append_row_and_readback(self, tmp_path):
        rows_path = tmp_path / "rows.jsonl"
        row = {"candidate": "v1", "score": 88.0}
        result = immutable_store.append_row(str(rows_path), row)
        assert result["appended"] is True

        rows = immutable_store.read_rows(str(rows_path))
        assert len(rows) == 1
        assert rows[0]["row"] == row

    def test_append_row_rejects_duplicate(self, tmp_path):
        rows_path = tmp_path / "dup_rows.jsonl"
        row = {"x": 1}
        r1 = immutable_store.append_row(str(rows_path), row)
        r2 = immutable_store.append_row(str(rows_path), row)
        assert r1["appended"] is True
        assert r2["appended"] is False
        assert r2["rejected"] is True


# ---------------------------------------------------------------------------
# 4. lib/completion_gate.py — 完成資格閘門
# ---------------------------------------------------------------------------

class TestCompletionGateArtifacts:
    """完成資格閘門的端對端產物驗證。"""

    def test_verify_completion_evidence_with_valid_evidence(self, tmp_path):
        artifact = tmp_path / "output.json"
        artifact.write_text(json.dumps({"result": "ok"}), encoding="utf-8")

        task = completion_gate.TaskResult(
            exit_code=0,
            stdout="done",
            stderr="",
            artifacts={"output.json": {"path": str(artifact)}},
            results=[{"id": 1, "answer": "correct", "total_score": 90}],
            summary={"average_score": 90.0},
            workspace_root=str(tmp_path),
        )
        is_complete, reasons = completion_gate.verify_completion_evidence(task)
        assert is_complete is True
        assert reasons == []

    def test_verify_completion_evidence_rejects_empty_evidence(self):
        task = completion_gate.TaskResult(
            exit_code=0,
            stdout="",
            stderr="",
            artifacts={},
            results=[],
            summary={},
        )
        is_complete, reasons = completion_gate.verify_completion_evidence(task)
        assert is_complete is False
        assert any("no valid evidence" in r for r in reasons)

    def test_verify_completion_evidence_rejects_nonzero_exit(self):
        task = completion_gate.TaskResult(exit_code=1, stdout="error")
        is_complete, reasons = completion_gate.verify_completion_evidence(task)
        assert is_complete is False
        assert any("exit_code=1" in r for r in reasons)

    def test_completion_gate_artifact(self, tmp_path):
        """完成資格閘門端對端驗證，產出可讀報告。"""
        artifact = tmp_path / "gate_result.json"
        payload = {
            "scenario": "valid_evidence",
            "exit_code": 0,
            "has_artifact": True,
            "has_results": True,
            "has_summary": True,
        }
        io.write_json(str(artifact), payload)

        verifier = ArtifactVerifier(tmp_path, "completion_gate")
        verifier.create(payload)
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches(["scenario", "exit_code", "has_artifact"])
            .verify_sha256_integrity()
            .finalize()
        )
        assert passed, f"完成資格閘門產物驗證失敗：{report}"

    def test_persist_run_failure_writes_summary(self, tmp_path):
        run_dir = tmp_path / "failed_run"
        run_dir.mkdir()
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps({"status": "running"}), encoding="utf-8")

        failure = {
            "reason_code": "NO_VALID_OUTPUT",
            "rejection_reason": "no evidence",
            "rejection_reasons": ["no evidence"],
            "evidence_errors": ["no evidence"],
        }
        result = completion_gate.persist_run_failure(str(run_dir), failure)
        assert result is True

        updated = json.loads(summary_path.read_text(encoding="utf-8"))
        assert updated["completion_status"] == "failed"
        assert updated["reason_code"] == "NO_VALID_OUTPUT"

    def test_load_run_evidence_with_valid_files(self, tmp_path):
        run_dir = tmp_path / "valid_run"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(
            json.dumps({"average_score": 85.0}), encoding="utf-8"
        )
        (run_dir / "details.jsonl").write_text(
            json.dumps({"id": 1, "answer": "a", "total_score": 85}) + "\n",
            encoding="utf-8",
        )
        artifacts, results, summary = completion_gate.load_run_evidence(str(run_dir))
        assert "summary.json" in artifacts
        assert "details.jsonl" in artifacts
        assert len(results) == 1
        assert summary["average_score"] == 85.0


# ---------------------------------------------------------------------------
# 5. scripts/analyze_runs.py — run 分析
# ---------------------------------------------------------------------------

class TestAnalyzeRunsArtifacts:
    """run 分析模組的端對端產物驗證。"""

    def _make_run(self, tmp_path, name, question_file, scores, failures=None):
        run_dir = tmp_path / "runs" / name
        run_dir.mkdir(parents=True)
        details = []
        for i, score in enumerate(scores):
            row = {
                "id": i,
                "type": "legal",
                "question_file": question_file,
                "total_score": score,
                "answer": f"answer_{i}",
                "failures": failures or [],
            }
            details.append(row)
        details_path = run_dir / "details.jsonl"
        with open(str(details_path), "w", encoding="utf-8") as f:
            for row in details:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        summary = {
            "question_file": question_file,
            "average_score": sum(scores) / len(scores) if scores else 0,
        }
        (run_dir / "summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        return run_dir

    def test_summarize_run_returns_valid_structure(self, tmp_path):
        from scripts.analyze_runs import summarize_run
        run_dir = self._make_run(tmp_path, "run1", "questions/dev.jsonl", [80, 85, 90])
        result = summarize_run(str(run_dir))
        assert result is not None
        assert result["run_dir"] == str(run_dir)
        assert result["question_file"] == "questions/dev.jsonl"
        assert 80 <= result["average_score"] <= 90

    def test_summarize_run_returns_none_for_empty(self, tmp_path):
        from scripts.analyze_runs import summarize_run
        run_dir = tmp_path / "empty_run"
        run_dir.mkdir()
        result = summarize_run(str(run_dir))
        assert result is None

    def test_analyze_runs_artifact(self, tmp_path):
        from scripts.analyze_runs import summarize_run
        self._make_run(tmp_path, "run_a", "questions/dev.jsonl", [75, 80])
        self._make_run(tmp_path, "run_b", "questions/dev.jsonl", [82, 88])

        summaries = []
        for name in ["run_a", "run_b"]:
            run_dir = tmp_path / "runs" / name
            s = summarize_run(str(run_dir))
            if s:
                summaries.append(s)

        verifier = ArtifactVerifier(tmp_path, "analyze_runs")
        verifier.create({
            "run_count": len(summaries),
            "runs": summaries,
        })
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches(["run_count", "runs"])
            .finalize()
        )
        assert passed, f"run 分析產物驗證失敗：{report}"


# ---------------------------------------------------------------------------
# 6. api/feedback.py — 回饋分析
# ---------------------------------------------------------------------------

class TestFeedbackAnalysisArtifacts:
    """回饋分析模組的端對端產物驗證。"""

    def test_analyze_feedback_by_hash(self, tmp_path):
        from api.feedback import analyze_feedback_by_hash
        feedback_data = [
            {
                "prompt_hash": "abc123",
                "total_score": 85,
                "scores": {"issueHit": 18, "structure": 16},
                "question_type": "法規分析",
            },
            {
                "prompt_hash": "abc123",
                "total_score": 90,
                "scores": {"issueHit": 19, "structure": 17},
                "question_type": "法規分析",
            },
            {
                "prompt_hash": "def456",
                "total_score": 70,
                "scores": {"issueHit": 14, "structure": 13},
                "question_type": "案例分析",
            },
        ]
        result = analyze_feedback_by_hash(feedback_data)
        assert "abc123" in result
        assert result["abc123"]["count"] == 2
        assert result["abc123"]["avg_total"] == 87.5

        verifier = ArtifactVerifier(tmp_path, "feedback_analysis")
        verifier.create({
            "prompt_hashes": list(result.keys()),
            "analysis": result,
        })
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches(["prompt_hashes", "analysis"])
            .verify_sha256_integrity()
            .finalize()
        )
        assert passed, f"回饋分析產物驗證失敗：{report}"

    def test_analyze_feedback_empty_data(self):
        from api.feedback import analyze_feedback_by_hash
        result = analyze_feedback_by_hash([])
        assert result == {}

    def test_feedback_weak_areas(self, tmp_path, monkeypatch):
        from api import feedback
        monkeypatch.setattr(feedback, "FEEDBACK_PATH", str(tmp_path / "fb.jsonl"))
        monkeypatch.setattr(feedback, "BASELINE_META_PATH", str(tmp_path / "baseline.json"))

        fb_data = [
            {
                "prompt_hash": "hash1",
                "total_score": 60,
                "scores": {"issueHit": 10},
                "question_type": "爭點整理",
            },
        ]
        fb_path = tmp_path / "fb.jsonl"
        with open(str(fb_path), "w", encoding="utf-8") as f:
            for row in fb_data:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        weak = feedback.get_weak_areas()
        assert isinstance(weak, dict)
        assert "weak_dimensions" in weak
        assert "weak_types" in weak


# ---------------------------------------------------------------------------
# 7. 端對端：多模組產物串接驗證
# ---------------------------------------------------------------------------

class TestEndToEndArtifactPipeline:
    """多模組串接的端對端產物驗證。"""

    def test_full_pipeline_produces_verified_artifact(self, tmp_path):
        """模擬完整流程：版本追蹤 → 資料寫入 → 驗證 → 產物輸出。"""
        # 1. 取得版本資訊
        prog_ver = version.get_program_version()
        input_hash = version.compute_input_settings_hash()

        # 2. 建立不可變版本
        store_dir = tmp_path / "store"
        store_dir.mkdir()
        baseline = {"prompt": "baseline prompt", "score": 82.0}
        store_result = immutable_store.store_version(baseline, str(store_dir))

        # 3. 寫入可讀產物
        artifact = {
            "pipeline": "e2e_verification",
            "version": prog_ver,
            "input_hash": input_hash,
            "baseline_stored": store_result["stored"],
            "baseline_version_id": store_result["version_id"],
            "baseline_content_hash": store_result["content_hash"],
        }
        io.write_json(str(tmp_path / "pipeline_output.json"), artifact)

        # 4. 驗證產物
        verifier = ArtifactVerifier(tmp_path, "pipeline_output")
        verifier.create(artifact)
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches([
                "pipeline", "version", "input_hash",
                "baseline_stored", "baseline_version_id",
            ])
            .verify_sha256_integrity()
            .finalize()
        )

        # 5. 驗證不可變版本仍可讀
        loaded = immutable_store.load_version(str(store_dir), store_result["version_id"])
        assert loaded == baseline

        # 6. 驗證版本追溯鏈
        assert store_result["content_hash"] == immutable_store.content_hash(baseline)

        assert passed, f"端對端管線產物驗證失敗：{json.dumps(report, ensure_ascii=False)}"

    def test_completion_gate_with_persisted_evidence(self, tmp_path):
        """模擬 run 完成後的證據持久化與驗證流程。"""
        # 1. 建立 run 目錄
        run_dir = tmp_path / "runs" / "e2e_run"
        run_dir.mkdir(parents=True)

        # 2. 寫入有效證據
        evidence_content = {"result": "pass", "score": 92.5}
        evidence_path = run_dir / "evidence.json"
        io.write_json(str(evidence_path), evidence_content)

        # 3. 建立 summary 與 details
        manifest_entry, _ = completion_gate._read_evidence_file(
            str(evidence_path), str(tmp_path)
        )
        summary = {
            "completion_status": "completed",
            "average_score": 92.5,
            "evidence_manifest": [manifest_entry] if manifest_entry else [],
            "evidence_errors": [],
        }
        io.write_json(str(run_dir / "summary.json"), summary)

        details_row = {"id": 1, "answer": "correct", "total_score": 92.5}
        with open(str(run_dir / "details.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(details_row) + "\n")

        # 4. 驗證持久化證據
        result = completion_gate.verify_persisted_run_evidence(str(run_dir))
        assert result["status"] == "completed"
        assert result["completion_status"] == "completed"
        assert len(result["evidence_manifest"]) > 0

        # 5. 建立並驗證可讀報告
        verifier = ArtifactVerifier(tmp_path, "e2e_gate")
        verifier.create({
            "run_dir": str(run_dir),
            "verification": result,
        })
        passed, report = (
            verifier
            .verify_exists()
            .verify_readable()
            .verify_json_parseable()
            .verify_content_matches(["run_dir", "verification"])
            .verify_sha256_integrity()
            .finalize()
        )
        assert passed, f"端對端閘門產物驗證失敗：{json.dumps(report, ensure_ascii=False)}"
