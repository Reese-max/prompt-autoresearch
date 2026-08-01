# -*- coding: utf-8 -*-
"""
lib/completion_gate.py — 任務完成資格閘門

定義並實作完成資格閘門：只有存在非空、可存取且可驗證的任務產出／結果證據時，
才能判定為已完成。runner 的 exit code、文字成功訊息或空摘要不得單獨構成完成依據。

用法：
    from lib.completion_gate import verify_completion_evidence, TaskResult
    is_complete, reasons = verify_completion_evidence(task_result)
"""
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskResult:
    """任務執行結果的標準化容器。"""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    artifacts: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _is_non_empty_string(value: Any) -> bool:
    """檢查值是否為非空白字串。"""
    return isinstance(value, str) and bool(value.strip())


def _is_accessible_file(path: str) -> bool:
    """檢查路徑是否為可存取的非空檔案。"""
    if not path or not os.path.isfile(path):
        return False
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def _has_meaningful_result(result: dict) -> bool:
    """檢查單一結果是否含有意義性內容（answer 或 total_score > 0）。"""
    if result.get("error"):
        return False
    has_answer = _is_non_empty_string(result.get("answer", ""))
    has_score = (result.get("total_score") or 0) > 0
    return has_answer or has_score


def _check_artifacts_evidence(artifacts: dict) -> tuple:
    """檢查 artifacts 是否提供有效證據。回傳 (is_valid, reason)。"""
    if not artifacts:
        return False, "artifacts is empty"
    for _name, info in artifacts.items():
        if isinstance(info, dict) and info.get("exists") and info.get("size", 0) > 0:
            return True, ""
    return False, "no valid non-empty artifacts found"


def _check_results_evidence(results: list) -> tuple:
    """檢查 results 是否提供有效證據。回傳 (is_valid, reason)。"""
    if not results:
        return False, "results is empty"
    meaningful_count = sum(1 for r in results if _has_meaningful_result(r))
    if meaningful_count == 0:
        return False, "results contain no meaningful content (all empty or errored)"
    return True, ""


def _check_summary_evidence(summary: dict) -> tuple:
    """檢查 summary 是否提供有效證據。回傳 (is_valid, reason)。"""
    if not summary:
        return False, "summary is empty"
    avg_score = summary.get("average_score")
    if avg_score is None or (isinstance(avg_score, (int, float)) and avg_score <= 0):
        return False, "summary has no valid average_score"
    return True, ""


def _check_stdout_evidence(stdout: str) -> tuple:
    """檢查 stdout 是否提供有效證據（非空白且非純成功訊息）。回傳 (is_valid, reason)。"""
    if not _is_non_empty_string(stdout):
        return False, "stdout is empty or whitespace-only"
    return True, ""


def completion_disposition(task_result):
    """回傳可持久化的完成處置，供 runner／候選流程使用。"""
    is_complete, reasons = verify_completion_evidence(task_result)
    if isinstance(task_result, TaskResult):
        exit_code = task_result.exit_code
        stdout = task_result.stdout
        artifacts = task_result.artifacts
        results = task_result.results
        summary = task_result.summary
    else:
        exit_code = task_result.get("exit_code", -1)
        stdout = task_result.get("stdout", "")
        artifacts = task_result.get("artifacts", {})
        results = task_result.get("results", [])
        summary = task_result.get("summary", {})

    checks = (
        ("stdout", _check_stdout_evidence(stdout)),
        ("artifacts", _check_artifacts_evidence(artifacts)),
        ("results", _check_results_evidence(results)),
        ("summary", _check_summary_evidence(summary)),
    )
    evidence_types = [name for name, (ok, _reason) in checks if ok]
    missing_evidence_types = [name for name, (ok, _reason) in checks if not ok]

    if is_complete:
        reason_code = ""
        rejection_reason = ""
        status = "completed"
        missing_evidence_types = []
    elif exit_code != 0:
        reason_code = "NONZERO_EXIT_CODE"
        rejection_reason = reasons[0] if reasons else f"exit_code={exit_code} != 0"
        status = "failed"
        missing_evidence_types = []
    else:
        reason_code = "NO_VALID_EVIDENCE"
        rejection_reason = "no valid evidence source found"
        status = "failed"

    return {
        "status": status,
        "reason_code": reason_code,
        "rejection_reason": rejection_reason,
        "rejection_reasons": reasons,
        "evidence_types": evidence_types,
        "missing_evidence_types": missing_evidence_types,
    }


def verify_completion_evidence(task_result):
    """驗證任務結果是否包含有效的完成證據。

    任務只有在存在非空、可存取且可驗證的產出／結果證據時才能判定為完成。
    runner 的 exit code、文字成功訊息或空摘要不得單獨構成完成依據。

    完成資格閘門規則：
    1. exit_code 必須為 0
    2. 至少有一個額外證據來源通過驗證：
       - stdout 有非空白內容
       - artifacts 含有可存取的非空檔案
       - results 含有至少一筆有意義的結果
       - summary 含有有效的 average_score

    參數：
        task_result: dict 或 TaskResult，包含以下欄位：
            - exit_code: 子程序退出碼（0=成功）
            - stdout: 標準輸出文字
            - stderr: 標準錯誤文字
            - artifacts: 產出檔案資訊 {name: {exists: bool, size: int}}
            - results: 評估結果列表
            - summary: 摘要統計

    回傳：
        tuple: (is_complete: bool, reasons: list[str])
        - is_complete: 是否通過完成資格閘門
        - reasons: 未通過的原因列表（通過時為空列表）
    """
    if isinstance(task_result, TaskResult):
        exit_code = task_result.exit_code
        stdout = task_result.stdout
        stderr = task_result.stderr
        artifacts = task_result.artifacts
        results = task_result.results
        summary = task_result.summary
    else:
        exit_code = task_result.get("exit_code", -1)
        stdout = task_result.get("stdout", "")
        stderr = task_result.get("stderr", "")
        artifacts = task_result.get("artifacts", {})
        results = task_result.get("results", [])
        summary = task_result.get("summary", {})

    reasons = []

    # 閘門 1: exit code 必須為 0
    if exit_code != 0:
        reasons.append(f"exit_code={exit_code} != 0")
        return False, reasons

    # 閘門 2: 至少有一個額外證據來源
    # exit_code=0 不足以判定成功，還必須有非空且可驗證的產出證據
    evidence_sources = []
    evidence_reasons = []

    ok, reason = _check_stdout_evidence(stdout)
    if ok:
        evidence_sources.append("stdout")
    else:
        evidence_reasons.append(reason)

    ok, reason = _check_artifacts_evidence(artifacts)
    if ok:
        evidence_sources.append("artifacts")
    else:
        evidence_reasons.append(reason)

    ok, reason = _check_results_evidence(results)
    if ok:
        evidence_sources.append("results")
    else:
        evidence_reasons.append(reason)

    ok, reason = _check_summary_evidence(summary)
    if ok:
        evidence_sources.append("summary")
    else:
        evidence_reasons.append(reason)

    if not evidence_sources:
        reasons.append("no valid evidence source found (exit_code alone is insufficient)")
        reasons.extend(evidence_reasons)

    return len(reasons) == 0, reasons
