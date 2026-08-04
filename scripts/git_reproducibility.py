# -*- coding: utf-8 -*-
"""Git 可重現性快照：在研究執行開始與報告組裝時擷取並持久化。

擷取項目：
  - HEAD commit
  - git status --porcelain（已追蹤差異）
  - git diff（已追蹤差異內容）
  - git ls-files --others --exclude-standard（未追蹤檔清單）
  - 快照雜湊、取得時間、所屬工作區

所有 Git 命令皆設定逾時，避免卡住整體報告組裝。
"""
import hashlib
import json
import ntpath
import os
import platform
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone

DEFAULT_GIT_TIMEOUT = 5  # seconds
GIT_PREFLIGHT_STATE_PATH = "output/research_git_preflight.json"


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _run_git(args, cwd, timeout=DEFAULT_GIT_TIMEOUT):
    """執行 git 命令，逾時或失敗時回傳空字串。"""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if r.returncode == 0:
            return r.stdout
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass
    return ""


def _run_git_detail(args, cwd, timeout=DEFAULT_GIT_TIMEOUT):
    """保留 Git 預檢所需的成功、錯誤與逾時狀態。"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "returncode": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "returncode": None,
            "timed_out": True,
        }
    except (OSError, ValueError) as exc:
        return {
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
            "returncode": None,
            "timed_out": False,
        }


def _is_windows_path(value):
    value = str(value or "").strip()
    return bool(re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("\\\\", "//")))


def _is_windows_platform(platform_name=None):
    value = str(platform_name or platform.system()).lower()
    return value in {"windows", "win32", "cygwin", "msys"}


def _normalise_commands(commands):
    return list(dict.fromkeys(str(command) for command in commands if command))


def _finish_git_metadata(result, repairs):
    result["repair_commands"] = _normalise_commands(repairs)
    result["git_metadata_resolved"] = not result["blockers"]
    result["blocked"] = bool(result["blockers"])
    return result


def parse_git_metadata(cwd=None, platform_name=None):
    """解析 `.git` 資料夾或 worktree `.git` 指標檔，不依賴 Git CLI。"""
    raw_cwd = os.fspath(cwd or os.getcwd())
    windows = _is_windows_platform(platform_name)
    result = {
        "workspace": os.path.abspath(raw_cwd),
        "git_metadata_path": os.path.join(raw_cwd, ".git"),
        "git_metadata_kind": "",
        "gitdir_value": "",
        "git_dir": "",
        "head_path": "",
        "head": "",
        "head_readable": False,
        "blockers": [],
        "blocking_reasons": [],
        "repair_commands": [],
    }
    blockers = result["blockers"]
    reasons = result["blocking_reasons"]
    repairs = result["repair_commands"]

    def block(code, detail, commands):
        if code not in blockers:
            blockers.append(code)
            reasons.append({
                "code": code,
                "detail": detail,
                "repair_commands": _normalise_commands(commands),
            })
        repairs.extend(commands)

    if _is_windows_path(raw_cwd) and not windows:
        block(
            "windows_workspace_path_unresolvable",
            f"Linux/macOS 無法解析 Windows 工作區路徑：{raw_cwd}",
            ["git rev-parse --show-toplevel"],
        )
        return _finish_git_metadata(result, repairs)

    metadata_path = result["git_metadata_path"]
    try:
        is_dir = os.path.isdir(metadata_path)
        is_file = os.path.isfile(metadata_path)
    except OSError as exc:
        block("git_metadata_unreadable", f"無法檢查 .git：{exc}", ["git status --short"])
        return _finish_git_metadata(result, repairs)

    if is_dir:
        result["git_metadata_kind"] = "directory"
        git_dir = metadata_path
    elif is_file:
        result["git_metadata_kind"] = "worktree_file"
        try:
            with open(metadata_path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except (OSError, UnicodeError) as exc:
            block(
                "git_metadata_unreadable",
                f"無法讀取 worktree .git 檔：{exc}",
                ["git worktree repair", "git status --short"],
            )
            return _finish_git_metadata(result, repairs)
        match = re.search(
            r"^\s*gitdir:\s*(.+?)\s*$", content,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if not match:
            block(
                "git_metadata_invalid",
                "worktree .git 檔缺少 gitdir 指標。",
                ["git worktree repair", "git status --short"],
            )
            return _finish_git_metadata(result, repairs)
        gitdir_value = match.group(1).strip()
        result["gitdir_value"] = gitdir_value
        if _is_windows_path(gitdir_value) and not windows:
            block(
                "windows_gitdir_path_unresolvable",
                f"Linux/macOS 無法解析 worktree 的 Windows gitdir：{gitdir_value}",
                ["git worktree repair", "git rev-parse HEAD"],
            )
            return _finish_git_metadata(result, repairs)
        if _is_windows_path(gitdir_value):
            git_dir = ntpath.normpath(gitdir_value)
        else:
            git_dir = os.path.abspath(os.path.join(os.path.dirname(metadata_path), gitdir_value))
    else:
        block(
            "not_git_repository",
            f"工作區沒有 .git 資料夾或 worktree .git 檔：{metadata_path}",
            ["git init", "git add -A", 'git commit -m "chore: establish research baseline"'],
        )
        return _finish_git_metadata(result, repairs)

    result["git_dir"] = (
        git_dir
        if is_file and _is_windows_path(gitdir_value)
        else os.path.abspath(git_dir)
    )
    try:
        if not os.path.isdir(git_dir):
            block(
                "git_metadata_target_missing",
                f"Git metadata 目錄不存在：{git_dir}",
                ["git worktree repair", "git status --short"],
            )
            return _finish_git_metadata(result, repairs)
        lock_path = os.path.join(git_dir, "index.lock")
        if os.path.exists(lock_path):
            block(
                "git_index_lock_present",
                f"Git index.lock 存在：{lock_path}",
                ["git status --short", "git worktree repair"],
            )
        head_path = os.path.join(git_dir, "HEAD")
        result["head_path"] = head_path
        with open(head_path, "r", encoding="utf-8") as handle:
            head = handle.read().strip()
        if not head:
            block(
                "head_unreadable",
                f"HEAD 為空或不可讀：{head_path}",
                ["git status --short", "git rev-parse --verify HEAD"],
            )
        else:
            result["head"] = head
            result["head_readable"] = True
    except (OSError, UnicodeError) as exc:
        block(
            "head_unreadable",
            f"無法讀取 HEAD：{exc}",
            ["git status --short", "git rev-parse --verify HEAD"],
        )
    return _finish_git_metadata(result, repairs)


parse_git_workspace = parse_git_metadata


def collect_git_snapshot(cwd=None, now=None):
    """擷取 Git 可重現性快照。

    Args:
        cwd: repo 根目錄路徑；None 則使用目前工作目錄。
        now: 時間戳產生器（可替換用於測試）。

    Returns:
        dict: 含 head_commit, status_porcelain, diff_tracked,
              untracked_files, snapshot_hash, captured_at, workspace。
    """
    cwd = cwd or os.getcwd()
    now_fn = now or _utc_now
    captured_at = now_fn()

    head_commit = _run_git(["rev-parse", "HEAD"], cwd).strip()
    status_porcelain = _run_git(
        ["status", "--porcelain=v1", "--untracked-files=all"], cwd,
    )
    diff_tracked = _run_git(["diff", "HEAD"], cwd)
    diff_paths = sorted(
        line.strip()
        for line in _run_git(["diff", "HEAD", "--name-only"], cwd).splitlines()
        if line.strip()
    )
    untracked_raw = _run_git(
        ["ls-files", "--others", "--exclude-standard"], cwd,
    )
    untracked_files = sorted(
        line for line in untracked_raw.splitlines() if line.strip()
    )

    snapshot_payload = {
        "head_commit": head_commit,
        "status_porcelain": status_porcelain,
        "diff_tracked": diff_tracked,
        "diff_paths": diff_paths,
        "untracked_files": untracked_files,
    }
    snapshot_hash = hashlib.sha256(
        json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "head_commit": head_commit,
        "status_porcelain": status_porcelain,
        "diff_tracked": diff_tracked,
        "diff_paths": diff_paths,
        "untracked_files": untracked_files,
        "status_paths": _status_paths(status_porcelain),
        "changed_paths": sorted(set(diff_paths + untracked_files)),
        "snapshot_hash": snapshot_hash,
        "captured_at": captured_at,
        "workspace": os.path.abspath(cwd),
    }


def collect_git_preflight(cwd=None, now=None, platform_name=None):
    """執行跨平台 Git 工作區預檢並回傳可持久化的阻塞證據。"""
    cwd = os.path.abspath(os.fspath(cwd or os.getcwd()))
    metadata = parse_git_metadata(cwd, platform_name=platform_name)
    blockers = list(metadata["blockers"])
    reasons = list(metadata["blocking_reasons"])
    repairs = list(metadata["repair_commands"])

    root_result = _run_git_detail(["rev-parse", "--show-toplevel"], cwd)
    head_result = _run_git_detail(["rev-parse", "--verify", "HEAD"], cwd)

    def block(code, detail, commands):
        if code not in blockers:
            blockers.append(code)
            reasons.append({
                "code": code,
                "detail": detail,
                "repair_commands": _normalise_commands(commands),
            })
        repairs.extend(commands)

    repository_root = root_result["stdout"].strip() if root_result["ok"] else ""
    if not root_result["ok"]:
        error = root_result["stderr"].strip() or "git rev-parse --show-toplevel 失敗"
        if "not a git repository" in error.lower() and "not_git_repository" not in blockers:
            block("not_git_repository", error, ["git init", "git status --short"])
        else:
            block("git_command_failed", error, ["git status --short", "git rev-parse --show-toplevel"])
    elif _is_windows_path(repository_root) and not _is_windows_platform(platform_name):
        block(
            "windows_repository_path_unresolvable",
            f"目前平台無法解析 Git 回報的 Windows repository root：{repository_root}",
            ["git rev-parse --show-toplevel", "git status --short"],
        )
    if not head_result["ok"] or not head_result["stdout"].strip():
        error = head_result["stderr"].strip() or "git rev-parse --verify HEAD 失敗"
        block("head_unreadable", error, ["git status --short", "git rev-parse --verify HEAD"])

    snapshot = collect_git_snapshot(cwd=cwd, now=now)
    payload = dict(snapshot)
    git_errors = [
        result["stderr"].strip()
        for result in (root_result, head_result)
        if result["stderr"].strip()
    ]
    payload.update({
        "repository_root": repository_root,
        "git_metadata_path": metadata["git_metadata_path"],
        "git_metadata_kind": metadata["git_metadata_kind"],
        "gitdir_value": metadata["gitdir_value"],
        "git_dir": metadata["git_dir"],
        "head_path": metadata["head_path"],
        "head_file": metadata["head"],
        "head_readable": bool(
            metadata["head_readable"] and head_result["ok"] and head_result["stdout"].strip()
        ),
        "git_metadata_status": "resolved" if not blockers else "unresolved",
        "git_metadata_errors": git_errors,
        "git_metadata_resolved": not blockers,
        "blocked": bool(blockers),
        "passed": not blockers,
        "status": "blocked" if blockers else "passed",
        "comparison_allowed": not blockers,
        "deliverable_allowed": not blockers,
        "global_best_allowed": not blockers,
        "blockers": blockers,
        "blocking_reasons": reasons,
        "blocking_reason": "; ".join(blockers),
        "blocked_reason": "; ".join(blockers),
        "reason_code": blockers[0] if blockers else "",
        "repair_commands": _normalise_commands(repairs),
        "repair": {
            "required": bool(blockers),
            "status": "required" if blockers else "not_required",
            "commands": _normalise_commands(repairs),
        },
        "git_command_details": {
            "show_toplevel": root_result,
            "verify_head": head_result,
        },
        "preflight_captured_at": snapshot["captured_at"],
    })
    return payload


def persist_git_preflight(preflight, state_path=GIT_PREFLIGHT_STATE_PATH):
    """原子保存預檢結果；阻塞狀態可供後續報告明確拒絕交付。"""
    state_path = os.fspath(state_path)
    parent = os.path.dirname(os.path.abspath(state_path)) or "."
    os.makedirs(parent, exist_ok=True)
    blocked = bool((preflight or {}).get("blocked"))
    payload = {
        "schema_version": 1,
        "status": "blocked" if blocked else "passed",
        "passed": not blocked,
        "blocked": blocked,
        "comparison_allowed": not blocked,
        "deliverable_allowed": not blocked,
        "global_best_allowed": not blocked,
        "reason_code": ((preflight or {}).get("blockers") or [""])[0],
        "blocking_reason": (preflight or {}).get("blocking_reason", ""),
        "blocking_reasons": (preflight or {}).get("blocking_reasons", []),
        "repair_commands": (preflight or {}).get("repair_commands", []),
        "preflight": preflight or {},
        "persisted_at": _utc_now(),
    }
    fd, temp_path = tempfile.mkstemp(
        prefix=".research-git-preflight-", suffix=".tmp", dir=parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, state_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return state_path


def _status_paths(status_porcelain):
    """從 porcelain v1 狀態擷取受影響的 repo 相對路徑。"""
    paths = []
    for line in (status_porcelain or "").splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        path = path.strip().strip('"').replace("\\", "/")
        if path:
            paths.append(path)
    return sorted(set(paths))


def classify_git_provenance(path, snapshot):
    """判定單一檔案的 Git 歸屬狀態。

    Args:
        path: repo 相對路徑（正斜線）。
        snapshot: collect_git_snapshot() 產出的快照字典。

    Returns:
        str: "committed"  |  "diff_tracked"  |  "untracked_worktree"

    - committed: 檔案已提交且自 HEAD 以來無變更。
    - diff_tracked: 檔案已追蹤但工作樹中有未提交變更（modified / staged）。
    - untracked_worktree: 檔案不在 Git 追蹤範圍內（untracked）。
    """
    if not isinstance(snapshot, dict):
        return "untracked_worktree"
    norm = str(path).replace("\\", "/")
    untracked = snapshot.get("untracked_files") or []
    if norm in untracked:
        return "untracked_worktree"
    status_paths = snapshot.get("status_paths") or []
    if norm in status_paths:
        return "diff_tracked"
    diff_paths = snapshot.get("diff_paths") or []
    if norm in diff_paths:
        return "diff_tracked"
    head = snapshot.get("head_commit", "")
    if head:
        return "committed"
    return "untracked_worktree"
