# -*- coding: utf-8 -*-
"""
lib/completion_gate.py — 任務完成資格閘門

定義並實作完成資格閘門：只有存在非空、可存取且可驗證的任務產出／結果證據時，
才能判定為已完成。runner 的 exit code、文字成功訊息或空摘要不得單獨構成完成依據。

用法：
    from lib.completion_gate import verify_completion_evidence, TaskResult
    is_complete, reasons = verify_completion_evidence(task_result)
"""
import hashlib
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
    workspace_root: str = ""


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


def _workspace_root(workspace_root=None):
    """取得證據驗證用的工作區根目錄。"""
    root = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.realpath(os.fspath(root))


def _artifact_path(info):
    """回傳 (是否提供路徑, 路徑)。"""
    if isinstance(info, (str, os.PathLike)):
        return True, os.fspath(info)
    if isinstance(info, dict) and "path" in info:
        try:
            return True, os.fspath(info.get("path"))
        except TypeError:
            return True, None
    return False, None


def _read_evidence_file(path, workspace_root):
    """讀取並驗證單一證據檔案，回傳 (紀錄, 錯誤)。"""
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path):
        return None, "evidence path is empty or invalid"

    root = _workspace_root(workspace_root)
    raw_path = os.fspath(path)
    candidate = os.path.realpath(
        raw_path if os.path.isabs(raw_path) else os.path.join(root, raw_path)
    )
    try:
        within_workspace = os.path.commonpath(
            [os.path.normcase(candidate), os.path.normcase(root)]
        ) == os.path.normcase(root)
    except ValueError:
        within_workspace = False
    if not within_workspace:
        return None, "evidence path is outside workspace"

    digest = hashlib.sha256()
    size = 0
    try:
        with open(candidate, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
    except (OSError, ValueError):
        return None, "evidence file is unreadable"
    if size == 0:
        return None, "evidence file is empty"

    return {
        "path": os.path.relpath(candidate, root).replace(os.sep, "/"),
        "size": size,
        "sha256": digest.hexdigest(),
        "verified": True,
    }, ""


def build_evidence_manifest(artifacts, workspace_root=None):
    """建立可機械驗證的 repo 內產出證據清單。"""
    if not isinstance(artifacts, dict) or not artifacts:
        return [], ["artifacts is empty"]

    manifest = []
    errors = []
    legacy_metadata = False
    for name, info in artifacts.items():
        has_path, path = _artifact_path(info)
        if not has_path:
            # 相容舊 runner；這類資料不能產生雜湊清單，只能作為舊閘門訊號。
            if isinstance(info, dict) and info.get("exists") is True and info.get("size", 0) > 0:
                legacy_metadata = True
                continue
            errors.append(f"artifact {name!r} has no verifiable path")
            continue
        entry, error = _read_evidence_file(path, workspace_root)
        if error:
            errors.append(f"artifact {name!r}: {error}")
        else:
            manifest.append(entry)

    if errors:
        return [], errors
    if manifest or legacy_metadata:
        return manifest, []
    return [], ["no valid non-empty artifacts found"]


def validate_evidence_manifest(manifest, workspace_root=None):
    """重新讀取 manifest 指向的檔案，確認大小、雜湊與工作區邊界仍一致。"""
    if not isinstance(manifest, list) or not manifest:
        return [], ["evidence_manifest is empty or invalid"]

    verified = []
    errors = []
    for index, entry in enumerate(manifest):
        if not isinstance(entry, dict):
            errors.append(f"evidence_manifest[{index}] is not an object")
            continue
        if entry.get("verified") is not True:
            errors.append(f"evidence_manifest[{index}] is not marked verified")
            continue
        current, error = _read_evidence_file(entry.get("path"), workspace_root)
        if error:
            errors.append(f"evidence_manifest[{index}]: {error}")
            continue
        if entry.get("size") != current["size"]:
            errors.append(
                f"evidence_manifest[{index}] size mismatch: "
                f"expected {entry.get('size')}, found {current['size']}"
            )
            continue
        if str(entry.get("sha256", "")).lower() != current["sha256"]:
            errors.append(f"evidence_manifest[{index}] sha256 mismatch")
            continue
        verified.append(current)

    if errors:
        return [], errors
    return verified, []


def _run_workspace_root(run_dir):
    """由 runs/<name> 或測試用單層目錄推導 manifest 工作區。"""
    absolute = os.path.abspath(os.fspath(run_dir))
    parent = os.path.dirname(absolute)
    if os.path.basename(parent).lower() == "runs":
        return os.path.dirname(parent)
    return parent


def verify_persisted_run_evidence(run_dir):
    """驗證已完成 run 的持久化證據清單與實際產出。"""
    if not run_dir or not os.path.isdir(run_dir):
        return {
            "status": "failed",
            "completion_status": "failed",
            "reason_code": "NO_VALID_OUTPUT",
            "rejection_reason": "run directory is missing or invalid",
            "rejection_reasons": ["run directory is missing or invalid"],
            "evidence_manifest": [],
            "evidence_errors": ["run directory is missing or invalid"],
        }

    root = _run_workspace_root(run_dir)
    summary_path = os.path.join(run_dir, "summary.json")
    try:
        with open(summary_path, "r", encoding="utf-8") as handle:
            summary = json.load(handle)
    except (OSError, ValueError, TypeError):
        return {
            "status": "failed",
            "completion_status": "failed",
            "reason_code": "MISSING_EVIDENCE_MANIFEST",
            "rejection_reason": "completed run has no readable summary evidence",
            "rejection_reasons": ["summary.json is missing or invalid"],
            "evidence_manifest": [],
            "evidence_errors": ["summary.json is missing or invalid"],
        }

    if summary.get("completion_status") in {"failed", "incomplete"}:
        reason = summary.get("rejection_reason") or "run is not completed"
        return {
            "status": "failed",
            "completion_status": summary.get("completion_status"),
            "reason_code": summary.get("reason_code") or "NON_COMPLETED_STATUS",
            "rejection_reason": reason,
            "rejection_reasons": summary.get("rejection_reasons") or [reason],
            "evidence_manifest": [],
            "evidence_errors": summary.get("evidence_errors") or [reason],
        }

    if summary.get("evidence_errors"):
        errors = list(summary["evidence_errors"])
        return {
            "status": "failed",
            "completion_status": "failed",
            "reason_code": "INVALID_EVIDENCE_MANIFEST",
            "rejection_reason": "persisted evidence errors are present",
            "rejection_reasons": errors,
            "evidence_manifest": [],
            "evidence_errors": errors,
        }

    manifest, errors = validate_evidence_manifest(summary.get("evidence_manifest"), root)
    if errors:
        return {
            "status": "failed",
            "completion_status": "failed",
            "reason_code": "INVALID_EVIDENCE_MANIFEST",
            "rejection_reason": "persisted evidence manifest failed revalidation",
            "rejection_reasons": errors,
            "evidence_manifest": [],
            "evidence_errors": errors,
        }

    _artifacts, results, _summary = load_run_evidence(run_dir)
    if not any(_has_meaningful_result(result) for result in results):
        reason = "run details contain no meaningful result evidence"
        return {
            "status": "failed",
            "completion_status": "failed",
            "reason_code": "NO_VALID_OUTPUT",
            "rejection_reason": reason,
            "rejection_reasons": [reason],
            "evidence_manifest": [],
            "evidence_errors": [reason],
        }

    return {
        "status": "completed",
        "completion_status": "completed",
        "reason_code": "",
        "rejection_reason": "",
        "rejection_reasons": [],
        "evidence_manifest": manifest,
        "evidence_errors": [],
    }


def persist_run_failure(run_dir, failure):
    """將 run 的驗證拒絕結果持久化，供後續入口排除。"""
    if not run_dir:
        return False
    path = os.path.join(run_dir, "summary.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            summary = json.load(handle)
        if not isinstance(summary, dict):
            return False
        summary.update({
            "completion_status": "failed",
            "status": "failed",
            "reason_code": failure.get("reason_code") or "INVALID_EVIDENCE_MANIFEST",
            "rejection_reason": failure.get("rejection_reason") or "evidence validation failed",
            "rejection_reasons": failure.get("rejection_reasons", []),
            "reject_reasons": failure.get("rejection_reasons", []),
            "missing_evidence_types": ["evidence_manifest"],
            "evidence_manifest": [],
            "evidence_errors": failure.get("evidence_errors") or failure.get("rejection_reasons", []),
        })
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2)
    except (OSError, ValueError, TypeError):
        return False
    return True


ACCEPTANCE_TARGET_RELATIVE = "tests/ed6a1a498025c1ec-artifact-success-verification.py"


def resolve_acceptance_target(workspace_root=None):
    """解析驗收目標路徑，回傳 (requested_path, resolved_path, error)。

    requested_path 為相對於 repo 根的固定目標路徑。
    resolved_path 為實際解析後的絕對路徑（若存在且可讀）。
    error 為空字串表示成功，否則為診斷原因。
    """
    root = _workspace_root(workspace_root)
    requested = ACCEPTANCE_TARGET_RELATIVE
    resolved = os.path.normpath(os.path.join(root, requested))
    if not os.path.isfile(resolved):
        return requested, resolved, "target file does not exist"
    try:
        with open(resolved, "rb") as fh:
            chunk = fh.read(1)
            if not chunk and os.path.getsize(resolved) == 0:
                return requested, resolved, "target file is empty"
    except OSError as exc:
        return requested, resolved, f"target file is unreadable: {exc}"
    return requested, resolved, ""


def verify_acceptance_target_precheck(workspace_root=None):
    """在啟動 pytest 前驗證驗收目標檔存在且可讀。

    回傳 dict：
    - passed: bool
    - requested_path: 相對路徑
    - resolved_path: 實際路徑
    - error: 錯誤診斷（passed=True 時為空）
    - reason_code: gate-configuration failure 時為 "GATE_CONFIGURATION_FAILURE"
    """
    requested, resolved, error = resolve_acceptance_target(workspace_root)
    if not error:
        return {
            "passed": True,
            "requested_path": requested,
            "resolved_path": resolved,
            "error": "",
            "reason_code": "",
        }
    return {
        "passed": False,
        "requested_path": requested,
        "resolved_path": resolved,
        "error": error,
        "reason_code": "GATE_CONFIGURATION_FAILURE",
    }


def verify_acceptance_target_content(workspace_root=None):
    """驗證驗收目標檔的內容是否符合預期（含有意義性的測試代碼）。

    回傳 dict：
    - passed: bool
    - requested_path: 相對路徑
    - resolved_path: 實際路徑
    - error: 錯誤診斷（passed=True 時為空）
    - reason_code: gate-configuration failure 時為 "GATE_CONFIGURATION_FAILURE"
    - content_summary: 內容摘要（通過時）
    """
    requested, resolved, error = resolve_acceptance_target(workspace_root)
    if error:
        return {
            "passed": False,
            "requested_path": requested,
            "resolved_path": resolved,
            "error": error,
            "reason_code": "GATE_CONFIGURATION_FAILURE",
            "content_summary": "",
        }

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        return {
            "passed": False,
            "requested_path": requested,
            "resolved_path": resolved,
            "error": f"content unreadable: {exc}",
            "reason_code": "GATE_CONFIGURATION_FAILURE",
            "content_summary": "",
        }

    has_test_class = "class " in content and ("Test" in content or "test_" in content)
    has_assert = "assert " in content
    has_def = "def " in content
    meaningful = has_test_class and has_assert and has_def

    if not meaningful:
        parts = []
        if not has_test_class:
            parts.append("no test class")
        if not has_assert:
            parts.append("no assertions")
        if not has_def:
            parts.append("no function definitions")
        error_msg = f"content does not meet expectations: {', '.join(parts)}"
        return {
            "passed": False,
            "requested_path": requested,
            "resolved_path": resolved,
            "error": error_msg,
            "reason_code": "GATE_CONFIGURATION_FAILURE",
            "content_summary": "",
        }

    return {
        "passed": True,
        "requested_path": requested,
        "resolved_path": resolved,
        "error": "",
        "reason_code": "",
        "content_summary": f"test_class={has_test_class}, assert={has_assert}, def={has_def}",
    }


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


def _check_artifacts_evidence(artifacts: dict, workspace_root=None) -> tuple:
    """檢查 artifacts 是否提供有效證據。回傳 (is_valid, reason)。"""
    if not isinstance(artifacts, dict) or not artifacts:
        return False, "artifacts is empty"
    manifest, errors = build_evidence_manifest(artifacts, workspace_root)
    if not errors and manifest:
        return True, ""
    if not errors and any(
        isinstance(info, dict)
        and info.get("exists") is True
        and info.get("size", 0) > 0
        and "path" not in info
        for info in artifacts.values()
    ):
        return True, ""
    return False, errors[0] if errors else "no valid non-empty artifacts found"


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
        workspace_root = task_result.workspace_root
    else:
        exit_code = task_result.get("exit_code", -1)
        stdout = task_result.get("stdout", "")
        artifacts = task_result.get("artifacts", {})
        results = task_result.get("results", [])
        summary = task_result.get("summary", {})
        workspace_root = task_result.get("workspace_root") or task_result.get("repo_root")

    evidence_manifest, evidence_errors = build_evidence_manifest(artifacts, workspace_root)
    checks = (
        ("artifacts", _check_artifacts_evidence(artifacts, workspace_root)),
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
        "evidence_manifest": evidence_manifest,
        "evidence_errors": evidence_errors,
    }


def acceptance_gate_disposition(task_result, workspace_root=None):
    """驗收閘門專用完成處置 — 結合 precheck、內容驗證與一般完成證據驗證。

    在啟動 pytest 前驗證目標檔存在且可讀；若目標不存在、解析到其他舊測試或
    檔案不可讀，將該次驗收標為 GATE_CONFIGURATION_FAILURE，持久化
    requested/resolved path 與具體診斷，禁止把 pytest exit=4 或零收集誤記為
    產品驗證失敗或成功。

    成功狀態僅在產物存在、可讀且內容符合預期的驗證全部通過後才設定。

    回傳 dict 與 completion_disposition 相同，額外包含 precheck 與 content_check 欄位。
    """
    if isinstance(task_result, dict):
        ws = workspace_root or task_result.get("workspace_root") or task_result.get("repo_root")
    else:
        ws = workspace_root or getattr(task_result, "workspace_root", None)

    precheck = verify_acceptance_target_precheck(ws)
    content_check = verify_acceptance_target_content(ws)
    disposition = completion_disposition(task_result)

    if not precheck["passed"]:
        disposition.update({
            "status": "failed",
            "reason_code": "GATE_CONFIGURATION_FAILURE",
            "rejection_reason": (
                f"acceptance target precheck failed: "
                f"requested={precheck['requested_path']!r}, "
                f"resolved={precheck['resolved_path']!r}, "
                f"error={precheck['error']!r}"
            ),
            "rejection_reasons": [
                f"gate-configuration failure: requested={precheck['requested_path']!r}, "
                f"resolved={precheck['resolved_path']!r}, error={precheck['error']!r}"
            ],
            "missing_evidence_types": ["acceptance_target"],
        })
    elif not content_check["passed"]:
        disposition.update({
            "status": "failed",
            "reason_code": "GATE_CONFIGURATION_FAILURE",
            "rejection_reason": (
                f"acceptance target content verification failed: "
                f"requested={content_check['requested_path']!r}, "
                f"resolved={content_check['resolved_path']!r}, "
                f"error={content_check['error']!r}"
            ),
            "rejection_reasons": [
                f"gate-configuration failure: content verification failed, "
                f"requested={content_check['requested_path']!r}, "
                f"resolved={content_check['resolved_path']!r}, error={content_check['error']!r}"
            ],
            "missing_evidence_types": ["acceptance_target_content"],
        })

    disposition["precheck"] = precheck
    disposition["content_check"] = content_check
    return disposition


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
            - workspace_root: 證據必須位於其中的工作區根目錄（可選）

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
        workspace_root = task_result.workspace_root
    else:
        exit_code = task_result.get("exit_code", -1)
        stdout = task_result.get("stdout", "")
        stderr = task_result.get("stderr", "")
        artifacts = task_result.get("artifacts", {})
        results = task_result.get("results", [])
        summary = task_result.get("summary", {})
        workspace_root = task_result.get("workspace_root") or task_result.get("repo_root")

    reasons = []

    # 閘門 1: exit code 必須為 0
    if exit_code != 0:
        reasons.append(f"exit_code={exit_code} != 0")
        return False, reasons

    if isinstance(artifacts, dict) and artifacts:
        _, artifact_errors = build_evidence_manifest(artifacts, workspace_root)
        if artifact_errors:
            reasons.append("invalid artifact evidence: " + "; ".join(artifact_errors))
            return False, reasons

    # 閘門 2: 至少有一個可驗證的產出／結果證據
    # exit_code=0 或 stdout 成功文字都不足以判定成功。
    evidence_sources = []
    evidence_reasons = []

    ok, reason = _check_artifacts_evidence(artifacts, workspace_root)
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
