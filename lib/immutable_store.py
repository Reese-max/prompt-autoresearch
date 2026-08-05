# -*- coding: utf-8 -*-
"""
lib/immutable_store.py — 不可變基準儲存機制

以內容雜湊（content hash）與唯一版本 ID 建立不可覆寫的評測結果／基準版本：

1. 旁路重評等寫入動作不得覆寫既有基準檔、資料列或版本。
2. 若目標版本已存在，一律拒絕操作（不覆寫、不更新）。
3. 新版本以內容雜湊派生的唯一版本 ID 建立，版本可機械追溯。

用法：
    from lib.immutable_store import store_version, append_row, load_version
    result = store_version(report, store_dir, namespace="bypass-reeval")
    if result["rejected"]:
        print("目標版本已存在，拒絕覆寫：", result["version_id"])
"""
import hashlib
import json
import os
from pathlib import Path


class VersionExistsError(FileExistsError):
    """目標版本已存在，拒絕寫入。"""


def canonical_json(payload):
    """產生穩定排序的 canonical JSON 字串（供內容雜湊計算）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload):
    """計算 payload 的內容雜湊（canonical JSON 的 SHA-256）。

    字串直接雜湊，其他型別以 canonical JSON 序列化後雜湊，
    保證相同內容必定產生相同雜湊。
    """
    raw = payload if isinstance(payload, str) else canonical_json(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def derive_version_id(content_hash_value, namespace="baseline"):
    """由內容雜湊派生唯一版本 ID。"""
    return f"{namespace}-{content_hash_value[:16]}"


def version_path(store_dir, version_id):
    """回傳版本檔路徑。"""
    return Path(store_dir) / f"{version_id}.json"


def version_exists(store_dir, version_id):
    """檢查版本是否已存在。"""
    return version_path(store_dir, version_id).exists()


def load_version(store_dir, version_id):
    """讀取既有版本內容；不存在時回傳 None。"""
    path = version_path(store_dir, version_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def list_versions(store_dir):
    """列出 store 內所有版本 ID（排序）。"""
    base = Path(store_dir)
    if not base.is_dir():
        return []
    return sorted(item.stem for item in base.glob("*.json"))


def _atomic_write_json(path, payload):
    """以暫存檔＋改名原子寫入，避免殘留半檔被當成有效版本。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def store_version(payload, store_dir, namespace="baseline", reject_existing=True):
    """以內容雜湊與唯一版本 ID 建立不可覆寫版本。

    目標版本（由內容雜湊派生）已存在時：
      - reject_existing=True（預設）→ 拒絕操作，不寫入任何內容。
      - reject_existing=False → 回傳已存在狀態，仍不覆寫既有檔案。

    回傳 dict：
      stored: bool     是否建立新版本
      rejected: bool   是否因版本已存在而拒絕
      version_id: str  唯一版本 ID
      content_hash: str 內容雜湊（完整 SHA-256）
      path: str        版本檔路徑
      reason: str      rejected 時的拒絕原因
    """
    ch = content_hash(payload)
    vid = derive_version_id(ch, namespace)
    target = version_path(store_dir, vid)
    if version_exists(store_dir, vid):
        return {
            "stored": False,
            "rejected": bool(reject_existing),
            "version_id": vid,
            "content_hash": ch,
            "path": str(target),
            "reason": "version_already_exists",
        }
    _atomic_write_json(target, payload)
    return {
        "stored": True,
        "rejected": False,
        "version_id": vid,
        "content_hash": ch,
        "path": str(target),
        "reason": "",
    }


def append_row(rows_path, row, reject_duplicate=True):
    """以 append-only 方式新增資料列；重複內容雜湊的資料列拒絕加入。

    回傳 dict：
      appended: bool    是否成功新增
      rejected: bool    是否因重複內容而拒絕
      content_hash: str 資料列內容雜湊
      reason: str       拒絕原因
    """
    rows_path = Path(rows_path)
    ch = content_hash(row)
    existing = read_rows(rows_path)
    if reject_duplicate and any(item.get("content_hash") == ch for item in existing):
        return {
            "appended": False,
            "rejected": True,
            "content_hash": ch,
            "reason": "row_already_exists",
        }
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"content_hash": ch, "row": row}
    with open(rows_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {
        "appended": True,
        "rejected": False,
        "content_hash": ch,
        "reason": "",
    }


def read_rows(rows_path):
    """讀取既有資料列清單（不存在或不可解析時回傳空清單）。"""
    rows_path = Path(rows_path)
    if not rows_path.exists():
        return []
    rows = []
    with open(rows_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                continue
    return rows
