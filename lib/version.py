# -*- coding: utf-8 -*-
"""
lib/version.py — 程式版本追蹤。

提供当前程式版本識別（Git commit hash），
供旁路重評等追溯中繼資料使用。
"""
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git_commit_hash():
    """嘗試取得當前 Git HEAD commit hash。失敗時回傳 None。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_program_version():
    """回傳程式版本字串（Git commit short hash）。"""
    full = _git_commit_hash()
    if full:
        return full[:12]
    return "unknown"


def get_program_version_full():
    """回傳完整 Git commit hash。"""
    return _git_commit_hash() or "unknown"


def compute_input_settings_hash(config_path=None, cli_args=None):
    """計算輸入與設定雜湊。

    輸入包括：
      - config.json 內容（若存在）
      - CLI 參數（若提供）

    回傳 SHA-256 hex string。
    """
    parts = []
    cfg = Path(config_path) if config_path else ROOT / "config.json"
    if cfg.exists():
        try:
            parts.append(cfg.read_text(encoding="utf-8"))
        except Exception:
            pass
    if cli_args:
        parts.append(json.dumps(cli_args, sort_keys=True, ensure_ascii=False))
    combined = "\x00".join(parts) if parts else ""
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def get_baseline_info(baseline_md_path=None, baseline_meta_path=None):
    """讀取基線 prompt 版本資訊。

    回傳 dict：
      baseline_version: str  基線版本（来自 meta 的 updated_at 或 prompt_hash）
      baseline_hash: str     baseline.md 內容 SHA-256
    """
    md_path = Path(baseline_md_path) if baseline_md_path else ROOT / "prompts" / "baseline.md"
    meta_path = Path(baseline_meta_path) if baseline_meta_path else ROOT / "prompts" / "baseline.meta.json"

    baseline_hash = ""
    if md_path.exists():
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
            baseline_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        except Exception:
            pass

    baseline_version = "unknown"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            baseline_version = meta.get("prompt_hash", meta.get("updated_at", "unknown"))
        except Exception:
            pass

    return {
        "baseline_version": baseline_version,
        "baseline_hash": baseline_hash,
    }
