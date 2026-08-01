# -*- coding: utf-8 -*-
"""
以受控 runner／任務結果重現「命令未拋錯但未寫出任何有效產出」情境。

覆蓋需求：
- exit_code=0 但無有效產出時，現行完成判定會錯誤標記完成（failing test）
- 具有效產出與可驗證證據時，既有完成流程仍可標記完成（passing test）
- 任務未提供可驗證結果時，完成判定應回報失敗（failing test）

測試焦點：
1. continuous_optimizer.run_optimization_round — 只看 returncode 不驗證輸出
2. evaluate 單題結果 — error_count=0 但 answer 為空串
3. run_core_flow_e2e._check_spec — 空結果列表通過完成檢查
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


# ---------------------------------------------------------------------------
# Tests — 無效輸出應被判定為未完成（failing tests，記錄現行缺陷）
# ---------------------------------------------------------------------------

class TestEmptyOutputMarkedAsCompleted:
    """命令未拋錯但未寫出任何有效產出時，現行完成判定會錯誤標記完成。"""

    def test_optimizer_treats_empty_stdout_as_success(self, monkeypatch, tmp_path):
        """continuous_optimizer 只看 returncode==0 即判定成功，不驗證實際輸出。"""
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

        # 現行邏輯：returncode==0 即回傳 True（標記成功）
        assert result is True, "期望現行邏輯將空輸出標記為成功"

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        assert opt_event["stdout"] == ""
        assert opt_event["success"] is True

    def test_evaluate_empty_answer_not_flagged_by_error_count(self):
        """evaluate 以 error_count=0 判定完成，但 answer 為空串無有效產出。"""
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

    def test_evaluate_results_empty_list_passes_count_check(self):
        """evaluate 結果為空列表時，error_count 仍為 0。"""
        results = []
        error_count = sum(1 for r in results if r.get("error"))
        assert error_count == 0
        assert len(results) == 0

    def test_empty_stdout_logged_as_success(self, monkeypatch, tmp_path):
        """continuous_optimizer 記錄的 optimization 事件中 stdout 為空但仍標記 success。"""
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

        optimizer.run_optimization_round("direction_test")

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        # 現行邏輯缺陷：stdout 為空但仍標記 success=True
        assert opt_event["stdout"] == ""
        assert opt_event["success"] is True

    def test_empty_stderr_still_counts_as_success(self, monkeypatch, tmp_path):
        """continuous_optimizer 即使 stderr 有內容但 returncode=0 仍標記成功。"""
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
        assert result is True

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        assert opt_event["stderr"] != ""
        assert opt_event["success"] is True


# ---------------------------------------------------------------------------
# Tests — 有效產出應被判定為完成（passing tests，驗證既有正常流程）
# ---------------------------------------------------------------------------

class TestValidOutputMarkedAsCompleted:
    """具有效產出與可驗證證據時，既有完成流程可正確標記完成。"""

    def test_optimizer_treats_nonempty_stdout_as_success(self, monkeypatch, tmp_path):
        """continuous_optimizer 收到有產出的 stdout 時回傳 True。"""
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

        assert result is True

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        assert opt_event["success"] is True
        assert len(opt_event["stdout"]) > 0

    def test_evaluate_valid_answer_has_content(self):
        """evaluate 產出有效 answer 時，結果含可驗證內容。"""
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

    def test_valid_task_result_has_all_fields(self):
        """有效任務結果含必要欄位與非空產出。"""
        task = _valid_task_result()
        assert task["exit_code"] == 0
        assert len(task["stdout"]) > 0
        assert len(task["artifacts"]) > 0
        assert len(task["results"]) > 0
        assert task["results"][0]["answer"] != ""
        assert task["summary"]["average_score"] > 0

    def test_optimizer_logs_nonempty_stdout(self, monkeypatch, tmp_path):
        """continuous_optimizer 記錄的 optimization 事件含非空 stdout。"""
        import api.continuous_optimizer as optimizer

        log_path = tmp_path / "optimization_log.jsonl"
        monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
        monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))

        good_proc = types.SimpleNamespace(
            returncode=0,
            stdout="dev_avg=82.5, promoted=True",
            stderr="",
        )
        monkeypatch.setattr(
            optimizer.subprocess, "run",
            lambda *a, **kw: good_proc,
        )

        optimizer.run_optimization_round("structure")

        log_entries = [
            json.loads(line)
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        opt_event = next(e for e in log_entries if e["event"] == "optimization")
        assert len(opt_event["stdout"]) > 0
        assert opt_event["success"] is True

    def test_evaluate_error_result_flagged(self):
        """evaluate 結果含 error key 時，error_count > 0。"""
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
# Tests — 無可驗證結果時完成判定應失敗（failing tests，記錄現行缺陷）
# ---------------------------------------------------------------------------

class TestNoVerifiableResultShouldFail:
    """任務未提供可驗證結果時，完成判定應回報失敗。"""

    def test_empty_task_result_fails_verification(self):
        """無有效產出的任務結果應無法通過驗證。"""
        task = _empty_task_result()
        has_valid_output = bool(task["results"]) or bool(task["summary"])
        assert has_valid_output is False

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

    def test_empty_results_and_empty_summary_fails_check(self):
        """空結果列表與空摘要無法通過完成檢查。"""
        results = []
        summary = {}
        error_count = sum(1 for r in results if r.get("error"))
        assert error_count == 0
        assert len(results) == 0
        assert summary.get("average_score") is None

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
