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
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps

DEFAULT_GIT_TIMEOUT = 5  # seconds
GIT_PREFLIGHT_STATE_PATH = "output/research_git_preflight.json"
RESEARCH_WORKTREE_ROOT = "output/research-worktrees"


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


class ResearchWorkspaceError(RuntimeError):
    """研究隔離工作區無法建立時，攜帶可持久化的阻塞證據。"""

    def __init__(self, message, evidence=None):
        super().__init__(message)
        self.evidence = evidence if isinstance(evidence, dict) else {}


class ResearchWorkspace:
    """以目前 HEAD 建立一個不可混入既有工作樹的研究工作區。"""

    def __init__(self, repository=None, workspace_root=None, run_id=None,
                 timeout=DEFAULT_GIT_TIMEOUT):
        self.repository = os.path.abspath(os.fspath(repository or os.getcwd()))
        self.workspace_root = os.path.abspath(
            os.fspath(workspace_root or os.path.join(self.repository, RESEARCH_WORKTREE_ROOT))
        )
        self.run_id = re.sub(r"[^A-Za-z0-9_.-]", "-", str(run_id or uuid_hex()))
        self.path = os.path.join(self.workspace_root, self.run_id)
        self.timeout = timeout
        self.metadata = {}

    def _blocked(self, reason, *, preflight=None, command=None, result=None):
        preflight = preflight if isinstance(preflight, dict) else {}
        commands = ["python scripts/preflight.py --require-git"]
        if command:
            commands.append(command)
        if isinstance(preflight.get("repair_commands"), list):
            commands.extend(preflight["repair_commands"])
        self.metadata = {
            "schema_version": 1,
            "status": "blocked",
            "blocked": True,
            "required": True,
            "workspace_id": self.run_id,
            "repository": self.repository,
            "workspace": self.path,
            "baseline_commit": preflight.get("head_commit", ""),
            "baseline_snapshot_hash": "",
            "preflight": preflight,
            "command": result or {},
            "decision": {
                "status": "unproven",
                "code": "INCOMPLETE_EVIDENCE",
                "reason": str(reason),
            },
            "rerun_commands": list(dict.fromkeys(str(item) for item in commands if item)),
        }
        raise ResearchWorkspaceError(str(reason), self.metadata)

    def create(self):
        source_preflight = collect_git_preflight(self.repository)
        if source_preflight.get("blocked"):
            return self._blocked(
                "無法建立隔離研究工作區：來源 Git 預檢阻塞。",
                preflight=source_preflight,
            )
        baseline_commit = str(source_preflight.get("head_commit") or "").strip()
        if not baseline_commit:
            return self._blocked(
                "無法建立隔離研究工作區：來源 HEAD 不可解析。",
                preflight=source_preflight,
            )
        if os.path.exists(self.path):
            return self._blocked(
                f"無法建立隔離研究工作區：目標已存在：{self.path}",
                preflight=source_preflight,
            )
        try:
            os.makedirs(self.workspace_root, exist_ok=True)
        except OSError as exc:
            return self._blocked(
                f"無法建立隔離研究工作區父目錄：{exc}",
                preflight=source_preflight,
            )

        result = _run_git_detail(
            ["worktree", "add", "--detach", "--quiet", self.path, baseline_commit],
            self.repository,
            timeout=self.timeout,
        )
        if not result["ok"]:
            return self._blocked(
                "無法建立隔離研究工作區：git worktree add 失敗。",
                preflight=source_preflight,
                command="git worktree add --detach <workspace-path> <baseline-commit>",
                result=result,
            )

        workspace_preflight = collect_git_preflight(self.path)
        snapshot = collect_git_snapshot(cwd=self.path)
        if (
            workspace_preflight.get("blocked")
            or snapshot.get("head_commit") != baseline_commit
            or snapshot.get("changed_paths")
        ):
            _run_git_detail(
                ["worktree", "remove", "--force", self.path],
                self.repository,
                timeout=self.timeout,
            )
            return self._blocked(
                "無法建立可辨識的隔離基線：新 worktree 預檢或快照不一致。",
                preflight=workspace_preflight,
                command="git worktree remove --force <workspace-path>",
            )

        self.metadata = {
            "schema_version": 1,
            "status": "ready",
            "blocked": False,
            "workspace_id": self.run_id,
            "repository": self.repository,
            "workspace": self.path,
            "baseline_commit": baseline_commit,
            "baseline_snapshot_hash": snapshot["snapshot_hash"],
            "baseline_snapshot": snapshot,
            "source_preflight": source_preflight,
            "workspace_preflight": workspace_preflight,
            "decision": {"status": "proven", "code": "READY"},
            "rerun_commands": [],
        }
        return self

    @contextmanager
    def activate(self):
        if self.metadata.get("status") != "ready":
            raise ResearchWorkspaceError(
                "研究工作區尚未通過隔離預檢。", self.metadata,
            )
        previous = os.getcwd()
        os.chdir(self.path)
        try:
            yield self
        finally:
            os.chdir(previous)


def uuid_hex():
    """延遲匯入 uuid，避免快照工具增加不必要的全域狀態。"""
    import uuid
    return uuid.uuid4().hex[:12]


def create_research_workspace(repository=None, workspace_root=None, run_id=None,
                              timeout=DEFAULT_GIT_TIMEOUT):
    """建立並驗證一個以目前 HEAD 為基線的研究 worktree。"""
    return ResearchWorkspace(
        repository=repository,
        workspace_root=workspace_root,
        run_id=run_id,
        timeout=timeout,
    ).create()


def persist_research_workspace(metadata, state_path="output/research_workspace.json"):
    """保存研究工作區身分，供同一 worktree 的報告與重跑使用。"""
    state_path = os.fspath(state_path)
    parent = os.path.dirname(os.path.abspath(state_path)) or "."
    os.makedirs(parent, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".research-workspace-", suffix=".tmp", dir=parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(metadata or {}, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, state_path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return state_path


def isolate_research_entrypoint(function):
    """在 CLI 明確啟用時，讓整個研究入口只在新 worktree 執行。"""
    @wraps(function)
    def wrapped(*args, **kwargs):
        if (
            os.environ.get("AUTORESEARCH_ISOLATE_WORKSPACE") != "1"
            or os.environ.get("AUTORESEARCH_WORKSPACE_ACTIVE") == "1"
        ):
            return function(*args, **kwargs)
        try:
            workspace = create_research_workspace()
        except ResearchWorkspaceError as exc:
            persist_research_workspace(exc.evidence)
            print("INCOMPLETE_EVIDENCE / unproven：研究隔離工作區建立失敗。")
            return 1
        except Exception as exc:
            evidence = {
                "status": "blocked",
                "blocked": True,
                "required": True,
                "decision": {
                    "status": "unproven",
                    "code": "INCOMPLETE_EVIDENCE",
                    "reason": f"{type(exc).__name__}: {exc}",
                },
                "rerun_commands": ["python scripts/preflight.py --require-git"],
            }
            persist_research_workspace(evidence)
            print("INCOMPLETE_EVIDENCE / unproven：研究隔離工作區建立失敗。")
            return 1
        previous = os.environ.get("AUTORESEARCH_WORKSPACE_ACTIVE")
        os.environ["AUTORESEARCH_WORKSPACE_ACTIVE"] = "1"
        try:
            with workspace.activate():
                persist_research_workspace(workspace.metadata)
                return function(*args, **kwargs)
        finally:
            if previous is None:
                os.environ.pop("AUTORESEARCH_WORKSPACE_ACTIVE", None)
            else:
                os.environ["AUTORESEARCH_WORKSPACE_ACTIVE"] = previous
    return wrapped


def _is_windows_path(value):
    value = str(value or "").strip()
    return bool(re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith(("\\\\", "//")))


def _is_windows_platform(platform_name=None):
    value = str(platform_name or platform.system()).lower()
    return value in {"windows", "win32", "cygwin", "msys"}


def _normalise_commands(commands):
    return list(dict.fromkeys(str(command) for command in commands if command))


def _rerun_commands():
    """回傳不改變 Git 狀態的研究重跑前檢查命令。"""
    return ["python scripts/preflight.py --require-git"]


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
        "affected_paths": [],
    }
    blockers = result["blockers"]
    reasons = result["blocking_reasons"]
    repairs = result["repair_commands"]

    def block(code, detail, commands, affected_paths=()):
        affected_paths = sorted({os.fspath(path) for path in affected_paths if path})
        if code not in blockers:
            blockers.append(code)
            reasons.append({
                "code": code,
                "detail": detail,
                "affected_paths": affected_paths,
                "repair_commands": _normalise_commands(commands),
            })
        result["affected_paths"].extend(affected_paths)
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
            block("git_index_lock_present", f"Git index.lock 存在：{lock_path}", [
                "git status --short",
                "git worktree list --porcelain",
                "git worktree repair",
            ], [lock_path])
        worktree_lock_path = os.path.join(git_dir, "locked")
        if os.path.exists(worktree_lock_path):
            block("git_worktree_lock_present", f"Git worktree lock 存在：{worktree_lock_path}", [
                "git worktree list --porcelain",
                "git worktree unlock <worktree-path>",
            ], [worktree_lock_path])
        merge_head_path = os.path.join(git_dir, "MERGE_HEAD")
        if os.path.exists(merge_head_path):
            block("git_merge_in_progress", f"偵測到未完成的 merge：{merge_head_path}", [
                "git status --short",
                "git merge --continue",
                "git merge --abort",
            ], [merge_head_path])
        rebase_paths = [
            path for path in (
                os.path.join(git_dir, "rebase-merge"),
                os.path.join(git_dir, "rebase-apply"),
                os.path.join(git_dir, "REBASE_HEAD"),
            ) if os.path.exists(path)
        ]
        if rebase_paths:
            block("git_rebase_in_progress", "偵測到未完成的 rebase。", [
                "git status --short",
                "git rebase --continue",
                "git rebase --abort",
            ], rebase_paths)
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
    result["affected_paths"] = sorted(set(result["affected_paths"]))
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
    affected_paths = list(metadata.get("affected_paths") or [])

    root_result = _run_git_detail(["rev-parse", "--show-toplevel"], cwd)
    head_result = _run_git_detail(["rev-parse", "--verify", "HEAD"], cwd)
    status_result = _run_git_detail(
        ["status", "--porcelain=v1", "--untracked-files=all"], cwd,
    )
    unmerged_result = _run_git_detail(["ls-files", "-u"], cwd)

    def block(code, detail, commands, paths=()):
        paths = sorted({str(path).replace("\\", "/") for path in paths if path})
        if code not in blockers:
            blockers.append(code)
            reasons.append({
                "code": code,
                "detail": detail,
                "affected_paths": paths,
                "repair_commands": _normalise_commands(commands),
            })
        affected_paths.extend(paths)
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
    status_porcelain = status_result["stdout"] if status_result["ok"] else snapshot["status_porcelain"]
    status_paths = _status_paths(status_porcelain)
    unmerged_paths = sorted({
        line.rsplit("\t", 1)[-1].strip().replace("\\", "/")
        for line in unmerged_result["stdout"].splitlines()
        if "\t" in line and line.rsplit("\t", 1)[-1].strip()
    })
    if status_porcelain.strip():
        block("dirty_worktree", "工作區含有未提交的 index 或 worktree 變更。", [
            "git status --short",
            "git diff --check",
            "git diff --cached --check",
        ], status_paths)
    if unmerged_paths:
        block("git_unmerged_paths", "index 含有未合併的衝突路徑。", [
            "git status --short",
            "git add -- <resolved-path>",
            "git merge --continue",
        ], unmerged_paths)
    if not status_result["ok"] and not any(code in blockers for code in (
        "git_index_lock_present", "git_worktree_lock_present",
    )):
        error = status_result["stderr"].strip() or "git status --porcelain 失敗"
        block("git_status_unavailable", error, ["git status --short"])
    if not unmerged_result["ok"] and not any(code in blockers for code in (
        "git_index_lock_present", "git_worktree_lock_present",
    )):
        error = unmerged_result["stderr"].strip() or "git ls-files -u 失敗"
        block("git_unmerged_check_failed", error, ["git status --short"])
    payload = dict(snapshot)
    git_errors = [
        result["stderr"].strip()
        for result in (root_result, head_result, status_result, unmerged_result)
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
        "affected_paths": sorted(set(affected_paths + status_paths + unmerged_paths)),
        "status_paths": status_paths,
        "unmerged_paths": unmerged_paths,
        "blocking_reason": "; ".join(blockers),
        "blocked_reason": "; ".join(blockers),
        "reason_code": blockers[0] if blockers else "",
        "repair_commands": _normalise_commands(repairs),
        "rerun_commands": _rerun_commands() if blockers else [],
        "repair": {
            "required": bool(blockers),
            "status": "required" if blockers else "not_required",
            "commands": _normalise_commands(repairs),
            "rerun_commands": _rerun_commands() if blockers else [],
        },
        "git_command_details": {
            "show_toplevel": root_result,
            "verify_head": head_result,
            "status_porcelain": status_result,
            "unmerged_paths": unmerged_result,
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
        "affected_paths": (preflight or {}).get("affected_paths", []),
        "status_paths": (preflight or {}).get("status_paths", []),
        "unmerged_paths": (preflight or {}).get("unmerged_paths", []),
        "repair_commands": (preflight or {}).get("repair_commands", []),
        "rerun_commands": (preflight or {}).get("rerun_commands", []),
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


def load_persisted_git_preflight(state_path=GIT_PREFLIGHT_STATE_PATH):
    """讀取預檢持久化資料，回傳研究入口採用的同一份預檢結果。"""
    try:
        with open(os.fspath(state_path), "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(state, dict):
        return {}
    preflight = state.get("preflight")
    return preflight if isinstance(preflight, dict) else state


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
