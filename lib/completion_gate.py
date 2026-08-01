# -*- coding: utf-8 -*-
"""
lib/completion_gate.py — 任務完成資格閘門

定義並實作完成資格閘門：只有存在非空、可存取且可驗證的任務產出／結果證據時，
才能判定為已完成。runner 的 exit code、文字成功訊息或空摘要不得單獨構成完成依據。

用法：
    from lib.completion_gate import verify_completion_evidence, TaskResult
    is_complete, reasons = verify_completion_evidence(task_result)
"""
import json
import math
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


def load_run_evidence(run_dir):
    """讀取已落盤且可解析的評估證據。"""
    if not run_dir or not os.path.isdir(run_dir):
        return {}, [], {}

    artifacts = {}
    results = []
    summary = {}

    summary_path = os.path.join(run_dir, "summary.json")
    try:
        with open(summary_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict) and loaded:
            artifacts["summary.json"] = {"path": summary_path}
            summary = loaded
    except (OSError, ValueError, TypeError):
        pass

    details_path = os.path.join(run_dir, "details.jsonl")
    try:
        with open(details_path, "r", encoding="utf-8") as handle:
            lines = [line.strip() for line in handle if line.strip()]
        loaded_results = [json.loads(line) for line in lines]
        if loaded_results and all(isinstance(item, dict) for item in loaded_results):
            artifacts["details.jsonl"] = {"path": details_path}
            results = loaded_results
    except (OSError, ValueError, TypeError):
        pass

    return artifacts, results, summary


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
    if not isinstance(result, dict):
        return False
    if result.get("error"):
        return False
    has_answer = _is_non_empty_string(result.get("answer", ""))
    try:
        score = float(result.get("total_score") or 0)
        has_score = math.isfinite(score) and score > 0
    except (TypeError, ValueError):
        has_score = False
    return has_answer or has_score


def _check_artifacts_evidence(artifacts: dict) -> tuple:
    """檢查 artifacts 是否提供有效證據。回傳 (is_valid, reason)。"""
    if not isinstance(artifacts, dict) or not artifacts:
        return False, "artifacts is empty"
    for _name, info in artifacts.items():
        if isinstance(info, (str, os.PathLike)) and _is_accessible_file(os.fspath(info)):
            return True, ""
        if isinstance(info, dict):
            path = info.get("path")
            if path:
                if _is_accessible_file(os.fspath(path)):
                    return True, ""
                continue
            # 相容既有 runner 的檔案探測結果；exists/size 必須由 runner 明確提供。
            if info.get("exists") is True and info.get("size", 0) > 0:
                return True, ""
    return False, "no valid non-empty artifacts found"


def _check_results_evidence(results: list) -> tuple:
    """檢查 results 是否提供有效證據。回傳 (is_valid, reason)。"""
    if not isinstance(results, list) or not results:
        return False, "results is empty"
    meaningful_count = sum(1 for r in results if _has_meaningful_result(r))
    if meaningful_count == 0:
        return False, "results contain no meaningful content (all empty or errored)"
    return True, ""


def _check_summary_evidence(summary: dict) -> tuple:
    """檢查 summary 是否提供有效證據。回傳 (is_valid, reason)。"""
    if not isinstance(summary, dict) or not summary:
        return False, "summary is empty"
    avg_score = summary.get("average_score")
    if isinstance(avg_score, bool):
        return False, "summary has no valid average_score"
    try:
        valid_score = math.isfinite(float(avg_score)) and float(avg_score) > 0
    except (TypeError, ValueError):
        valid_score = False
    if not valid_score:
        return False, "summary has no valid average_score"
    return True, ""


def _check_stdout_evidence(stdout: str) -> tuple:
    """stdout 僅供診斷；不可作為完成資格證據。"""
    if not _is_non_empty_string(stdout):
        return False, "stdout is empty or whitespace-only"
    return False, "stdout is not completion evidence"


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

    # 閘門 2: 至少有一個可驗證的產出／結果證據
    # exit_code=0 或 stdout 成功文字都不足以判定成功。
    evidence_sources = []
    evidence_reasons = []

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
