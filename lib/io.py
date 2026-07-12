# -*- coding: utf-8 -*-
"""
lib/io.py — 統一 I/O 工具函數。

合併各檔案中重複的 load_file / write_file / sha256_text / load_json / write_json 等。
"""
import hashlib
import json
import os


def load_file(path, default=""):
    """讀取文字檔，回傳 strip 後的內容。不存在時回傳 default。"""
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read().strip()


def write_file(path, content):
    """寫入文字檔，自動建立目錄。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def sha256_text(text):
    """計算文字的 SHA-256 hash。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path, default=None):
    """讀取 JSON 檔。不存在或解析失敗時回傳 default（預設 {}）。"""
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, payload):
    """寫入 JSON 檔，自動建立目錄。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def read_jsonl(path, limit=None):
    """讀取 JSONL 檔，回傳 list of dict。"""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                if limit and len(rows) >= limit:
                    break
    return rows


def append_jsonl(path, payload):
    """追加一筆 JSON 到 JSONL 檔。"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_path(path):
    """統一路徑分隔符為 /。"""
    return path.replace("\\", "/")


def ensure_dir(path):
    """確保目錄存在。"""
    os.makedirs(path, exist_ok=True)
