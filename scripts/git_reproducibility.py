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
import os
import subprocess
import time
from datetime import datetime, timezone

DEFAULT_GIT_TIMEOUT = 5  # seconds


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
