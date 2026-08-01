# -*- coding: utf-8 -*-
"""
以受控 runner／任務結果重現「命令未拋錯但未寫出任何有效產出」情境。

覆蓋需求：
- exit_code=0 但無有效產出時，完成判定應拒絕標記完成（gate 阻擋）
- 具有效產出與可驗證證據時，完成判定可標記完成（gate 通過）
- 任務未提供可驗證結果時，完成判定應回報失敗（gate 阻擋）

測試焦點：
1. continuous_optimizer.run_optimization_round — 透過 completion_gate 驗證產出
2. evaluate 單題結果 — error_count=0 但 answer 為空串
3. completion_gate.verify_completion_evidence — 閘門邏輯驗證
"""
import json
import os
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Helpers — 受控任務結果
# ---------------------------------------------------------------------------

def _empty_task_result():
    """模擬命令執行完畢（exit_code=0）但未寫出任何有效產出。"""
    return {
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "artifacts": {},
        "results": [],
        "summary": {},
    }


def _valid_task_result():
    """模擬命令執行完畢且產出有效可驗證結果。"""
    return {
        "exit_code": 0,
        "stdout": "E2E 評量完成",
        "stderr": "",
        "artifacts": {"summary.json": {"exists": True, "size": 1024}},
        "results": [{"id": 1, "answer": "答案正文", "total_score": 79}],
        "summary": {"average_score": 79.0, "error_count": 0},
    }


def _stdout_only_result():
    """模擬只有 stdout 但無 artifacts/results/summary 的結果（子程序場景）。"""
    return {
        "exit_code": 0,
        "stdout": "優化完成，新基線分數 82.5",
        "stderr": "",
        "artifacts": {},
        "results": [],
        "summary": {},
    }


# ---------------------------------------------------------------------------
# Tests — 完成資格閘門邏輯驗證
# ---------------------------------------------------------------------------

class TestCompletionGate:
    """verify_completion_evidence 閘門邏輯驗證。"""

    def test_empty_task_result_blocked_by_gate(self):
        """無有效產出的任務結果應被閘門阻擋。"""
        from lib.completion_gate import verify_completion_evidence
        task = _empty_task_result()
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert len(reasons) > 0
        assert any("no valid evidence source" in r for r in reasons)

    def test_valid_task_result_passes_gate(self):
        """具有效產出的任務結果應通過閘門。"""
        from lib.completion_gate import verify_completion_evidence
        task = _valid_task_result()
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is True
        assert reasons == []

    def test_stdout_only_result_passes_gate(self):
        """只有 stdout 但無其他證據時，應通過閘門（stdout 作為證據）。"""
        from lib.completion_gate import verify_completion_evidence
        task = _stdout_only_result()
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is True
        assert reasons == []

    def test_nonzero_exit_code_blocked(self):
        """exit_code != 0 時，即使有 stdout 也應被阻擋。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 1,
            "stdout": "some output",
            "stderr": "error",
            "artifacts": {},
            "results": [],
            "summary": {},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("exit_code" in r for r in reasons)

    def test_empty_stdout_no_artifacts_no_results_no_summary_blocked(self):
        """所有證據來源皆為空時應被阻擋。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [],
            "summary": {},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("no valid evidence source" in r for r in reasons)

    def test_empty_stdout_with_valid_artifacts_passes(self):
        """stdout 為空但有有效 artifacts 時應通過閘門。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {"report.json": {"exists": True, "size": 512}},
            "results": [],
            "summary": {},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is True

    def test_empty_stdout_with_valid_results_passes(self):
        """stdout 為空但有有效 results 時應通過閘門。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [{"id": 1, "answer": "答案", "total_score": 80}],
            "summary": {},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is True

    def test_empty_stdout_with_valid_summary_passes(self):
        """stdout 為空但有有效 summary 時應通過閘門。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [],
            "summary": {"average_score": 75.0, "error_count": 0},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is True

    def test_results_all_errored_blocked(self):
        """results 全部為 error 時應被阻擋。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [{"id": 1, "error": "timeout", "total_score": 0}],
            "summary": {},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("no meaningful content" in r for r in reasons)

    def test_results_empty_answer_zero_score_blocked(self):
        """results 含空 answer 且 score=0 時應被阻擋。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [{"id": 1, "answer": "", "total_score": 0}],
            "summary": {},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False

    def test_summary_zero_average_score_blocked(self):
        """summary average_score=0 時應被阻擋。"""
        from lib.completion_gate import verify_completion_evidence
        task = {
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "artifacts": {},
            "results": [],
            "summary": {"average_score": 0, "error_count": 0},
        }
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert any("average_score" in r for r in reasons)


# ---------------------------------------------------------------------------
# Tests — continuous_optimizer 透過閘門阻擋空輸出
# ---------------------------------------------------------------------------

class TestOptimizerGateBlocksEmptyOutput:
    """continuous_optimizer 透過 completion_gate 阻擋空輸出。"""

    def test_optimizer_empty_stdout_returns_false(self, monkeypatch, tmp_path):
        """continuous_optimizer 收到空 stdout 時應回傳 False（閘門阻擋）。"""
        import api.continuous_optimizer as optimizer

        log_path = tmp_path / "optimization_log.jsonl"
        monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
        monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))

        empty_proc = types.SimpleNamespace(
            returncode=0, stdout="", stderr=""
        )
        monkeypatch.setattr(
            optimizer.subprocess, "run",
            lambda *a, **kw: empty_proc,
        )

        result = optimizer.run_optimization_round("structure")

        assert result is False, "空 stdout 應被閘門阻擋"

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        assert opt_event["success"] is False
        assert opt_event["gate_passed"] is False
        assert len(opt_event["gate_reasons"]) > 0

    def test_optimizer_nonempty_stdout_returns_true(self, monkeypatch, tmp_path):
        """continuous_optimizer 收到有內容的 stdout 時應回傳 True（閘門通過）。"""
        import api.continuous_optimizer as optimizer

        log_path = tmp_path / "optimization_log.jsonl"
        monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
        monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))

        good_proc = types.SimpleNamespace(
            returncode=0,
            stdout="優化完成，新基線分數 82.5",
            stderr="",
        )
        monkeypatch.setattr(
            optimizer.subprocess, "run",
            lambda *a, **kw: good_proc,
        )

        result = optimizer.run_optimization_round("structure")

        assert result is True, "有內容的 stdout 應通過閘門"

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        assert opt_event["success"] is True
        assert opt_event["gate_passed"] is True

    def test_optimizer_failure_returns_false(self, monkeypatch, tmp_path):
        """continuous_optimizer 在 returncode!=0 時回傳 False。"""
        import api.continuous_optimizer as optimizer

        log_path = tmp_path / "optimization_log.jsonl"
        monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
        monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))

        fail_proc = types.SimpleNamespace(
            returncode=1, stdout="", stderr="Error: pipeline failed"
        )
        monkeypatch.setattr(
            optimizer.subprocess, "run",
            lambda *a, **kw: fail_proc,
        )

        result = optimizer.run_optimization_round("structure")
        assert result is False

    def test_optimizer_exception_returns_false(self, monkeypatch, tmp_path):
        """continuous_optimizer 在例外時回傳 False。"""
        import api.continuous_optimizer as optimizer

        log_path = tmp_path / "optimization_log.jsonl"
        monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
        monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))

        def raise_error(*a, **kw):
            raise OSError("子程序無法啟動")

        monkeypatch.setattr(optimizer.subprocess, "run", raise_error)

        result = optimizer.run_optimization_round("structure")
        assert result is False

    def test_optimizer_stderr_with_empty_stdout_blocked(self, monkeypatch, tmp_path):
        """continuous_optimizer 即使有 stderr 但 stdout 為空時仍應被阻擋。"""
        import api.continuous_optimizer as optimizer

        log_path = tmp_path / "optimization_log.jsonl"
        monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
        monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))

        proc_with_stderr = types.SimpleNamespace(
            returncode=0, stdout="", stderr="Warning: no output generated"
        )
        monkeypatch.setattr(
            optimizer.subprocess, "run",
            lambda *a, **kw: proc_with_stderr,
        )

        result = optimizer.run_optimization_round("structure")
        assert result is False

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        assert opt_event["stderr"] != ""
        assert opt_event["success"] is False

    def test_optimizer_error_logged_without_success(self, monkeypatch, tmp_path):
        """continuous_optimizer 例外時記錄 optimization_error 事件，無 optimization 成功事件。"""
        import api.continuous_optimizer as optimizer

        log_path = tmp_path / "optimization_log.jsonl"
        monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
        monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))

        def raise_error(*a, **kw):
            raise OSError("子程序無法啟動")

        monkeypatch.setattr(optimizer.subprocess, "run", raise_error)

        optimizer.run_optimization_round("structure")

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(e["event"] == "optimization_error" for e in log_entries)
        assert not any(e["event"] == "optimization" for e in log_entries)


# ---------------------------------------------------------------------------
# Tests — evaluate 結果驗證（error_count 不應掩蓋空 answer）
# ---------------------------------------------------------------------------

class TestEvaluateEmptyAnswerDetection:
    """evaluate 以 error_count=0 判定完成，但 answer 為空串無有效產出。"""

    def test_empty_answer_not_flagged_by_error_count(self):
        """error_count=0 不代表有有效產出，需額外驗證 answer。"""
        result = {
            "id": 1,
            "type": "案例題",
            "question": "請說明行政處分之要件。",
            "answer": "",
            "char_count": 0,
            "prompt_hash": "abc123",
            "question_file": "questions/test.jsonl",
            "general_score": 0,
            "type_specific_score": 0,
            "risk_score": 0,
            "total_score": 0,
            "failures": [],
            "critique": "",
        }
        # 不含 "error" key → error_count=0
        assert "error" not in result
        error_count = sum(1 for r in [result] if r.get("error"))
        assert error_count == 0
        # 但實際上無有效答案產出
        assert result["answer"] == ""
        assert result["char_count"] == 0

    def test_empty_results_list_passes_count_check(self):
        """空結果列表時 error_count 仍為 0。"""
        results = []
        error_count = sum(1 for r in results if r.get("error"))
        assert error_count == 0
        assert len(results) == 0

    def test_valid_answer_has_content(self):
        """有效 answer 時，結果含可驗證內容。"""
        result = {
            "id": 1,
            "type": "案例題",
            "question": "請說明行政處分之要件。",
            "answer": "行政處分係指行政機關就公法上具體事件所為之決定"
                      "或其他公權力措施而對外直接發生法律效果之單方行政行為。",
            "char_count": 62,
            "prompt_hash": "abc123",
            "question_file": "questions/test.jsonl",
            "general_score": 55,
            "type_specific_score": 15,
            "risk_score": 9,
            "total_score": 79,
            "failures": ["F03"],
            "critique": "請加強採分點。",
        }
        assert "error" not in result
        error_count = sum(1 for r in [result] if r.get("error"))
        assert error_count == 0
        assert len(result["answer"]) > 0
        assert result["char_count"] > 0
        assert result["total_score"] > 0

    def test_error_result_flagged(self):
        """含 error key 時，error_count > 0。"""
        results = [
            {
                "id": 1,
                "error": "Answer Generation Failed: timeout",
                "total_score": 0,
            },
            {
                "id": 2,
                "answer": "有效答案",
                "total_score": 79,
            },
        ]
        error_count = sum(1 for r in results if r.get("error"))
        assert error_count == 1
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Tests — 無可驗證結果時完成判定應失敗
# ---------------------------------------------------------------------------

class TestNoVerifiableResultShouldFail:
    """任務未提供可驗證結果時，完成判定應回報失敗。"""

    def test_empty_task_result_fails_verification(self):
        """無有效產出的任務結果應無法通過閘門驗證。"""
        from lib.completion_gate import verify_completion_evidence
        task = _empty_task_result()
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert len(reasons) > 0

    def test_valid_task_result_passes_verification(self):
        """有效產出的任務結果應通過閘門驗證。"""
        from lib.completion_gate import verify_completion_evidence
        task = _valid_task_result()
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is True
        assert reasons == []

    def test_empty_results_and_empty_summary_fails_gate(self):
        """空結果列表與空摘要無法通過完成閘門。"""
        from lib.completion_gate import verify_completion_evidence
        task = _empty_task_result()
        is_complete, reasons = verify_completion_evidence(task)
        assert is_complete is False
        assert len(reasons) > 0


# ---------------------------------------------------------------------------
# Tests — completion_disposition 可持久化完成處置與『可存取』證據面向
# ---------------------------------------------------------------------------

class TestCompletionDisposition:
    """completion_disposition 產出可驗證的完成處置，供 runner／候選流程使用。"""

    def test_empty_task_disposition_failed_no_valid_evidence(self):
        """無有效產出時 disposition 為 failed + NO_VALID_EVIDENCE。"""
        from lib.completion_gate import completion_disposition
        disposition = completion_disposition(_empty_task_result())

        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "NO_VALID_EVIDENCE"
        assert disposition["rejection_reason"] == "no valid evidence source found"
        assert disposition["evidence_types"] == []
        assert set(disposition["missing_evidence_types"]) == {
            "stdout", "artifacts", "results", "summary",
        }
        assert len(disposition["rejection_reasons"]) > 0

    def test_valid_task_disposition_completed(self):
        """具有效產出與驗證證據時 disposition 為 completed。"""
        from lib.completion_gate import completion_disposition
        disposition = completion_disposition(_valid_task_result())

        assert disposition["status"] == "completed"
        assert disposition["reason_code"] == ""
        assert disposition["rejection_reasons"] == []
        assert set(disposition["evidence_types"]) == {
            "stdout", "artifacts", "results", "summary",
        }
        assert disposition["missing_evidence_types"] == []

    def test_stdout_only_disposition_completed(self):
        """只有帶實質內容的 stdout 時 disposition 為 completed，證據類型為 stdout。"""
        from lib.completion_gate import completion_disposition
        disposition = completion_disposition(_stdout_only_result())

        assert disposition["status"] == "completed"
        assert disposition["evidence_types"] == ["stdout"]
        assert disposition["missing_evidence_types"] == []

    def test_nonzero_exit_disposition_failed_nonzero_exit_code(self):
        """exit_code != 0 時 disposition 為 failed + NONZERO_EXIT_CODE。"""
        from lib.completion_gate import completion_disposition
        disposition = completion_disposition({
            "exit_code": 1,
            "stdout": "some output",
            "stderr": "error",
            "artifacts": {},
            "results": [],
            "summary": {},
        })

        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "NONZERO_EXIT_CODE"
        assert disposition["rejection_reason"] == "exit_code=1 != 0"

    def test_evaluation_completion_maps_no_valid_evidence_to_no_valid_output(self):
        """evaluation_completion 將無證據的空摘要映射為 NO_VALID_OUTPUT（既有候選流程）。"""
        from types import SimpleNamespace
        from run_opt import evaluation_completion

        disposition = evaluation_completion(SimpleNamespace(returncode=0), None, {})

        assert disposition["status"] == "failed"
        assert disposition["reason_code"] == "NO_VALID_OUTPUT"
        assert disposition["missing_evidence_types"]

    def test_artifact_accessibility_requires_non_empty_file(self, tmp_path):
        """『可存取』面向：產出檔案必須真實存在且非空才構成有效證據。"""
        from lib.completion_gate import _is_accessible_file

        real_file = tmp_path / "report.json"
        real_file.write_text("{}", encoding="utf-8")
        assert _is_accessible_file(str(real_file)) is True

        assert _is_accessible_file(str(tmp_path / "missing.json")) is False

        empty_file = tmp_path / "empty.json"
        empty_file.write_text("", encoding="utf-8")
        assert _is_accessible_file(str(empty_file)) is False
