# -*- coding: utf-8 -*-
"""
回填既有 prompts/candidates/*.md 的 scorecard。

只讀候選與旁邊的 .meta.md / .meta.json，建立缺少的
*.scorecard.json；預設不覆蓋已存在 scorecard。

用法：
  python scripts/backfill_candidate_scorecards.py
  python scripts/backfill_candidate_scorecards.py --force
"""
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = ROOT / "prompts" / "candidates"


def sha256_text(text):
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}


def parse_meta_md(path):
    meta = {}
    text = read_text(path)
    for line in text.splitlines():
        match = re.match(r"^\s*-\s*([A-Za-z0-9_]+):\s*(.*)\s*$", line)
        if match:
            meta[match.group(1)] = match.group(2).strip()
    return meta


def is_candidate_prompt(path):
    if path.suffix.lower() != ".md":
        return False
    name = path.name
    return (
        not name.endswith(".meta.md")
        and not name.endswith(".scorecard.md")
        and path.name.startswith(("candidate_", "compare_", "analyze_", "explain_", "legal_", "practical_"))
    )


def build_scorecard(path):
    text = read_text(path)
    rel = path.relative_to(ROOT).as_posix()
    meta_md = parse_meta_md(path.with_suffix("").with_suffix(".meta.md"))
    # 上面對 candidate_x.md 會變 candidate_x.meta.md；若 pathlib 雙 suffix 不適用，回退字串。
    meta_md_path = Path(str(path).replace(".md", ".meta.md"))
    if meta_md_path.exists():
        meta_md = parse_meta_md(meta_md_path)
    meta_json_path = Path(str(path).replace(".md", ".meta.json"))
    meta_json = load_json(meta_json_path)

    return {
        "candidate_path": rel,
        "candidate_hash": sha256_text(text),
        "candidate_length": len(text),
        "status": "backfilled_existing",
        "backfilled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "direction": meta_md.get("direction") or meta_json.get("direction") or "",
        "target_failures": meta_md.get("target_failures", ""),
        "hypothesis": meta_md.get("hypothesis") or meta_json.get("hypothesis") or "",
        "temperature": meta_md.get("temperature", ""),
        "candidate_index": meta_md.get("candidate_index", ""),
        "source_meta": {
            "meta_md": meta_md_path.relative_to(ROOT).as_posix() if meta_md_path.exists() else "",
            "meta_json": meta_json_path.relative_to(ROOT).as_posix() if meta_json_path.exists() else "",
        },
        "note": "Backfilled from existing candidate files; historical gatekeeper/smoke/dev results may be unavailable.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="覆蓋既有 scorecard")
    args = parser.parse_args()

    created = 0
    skipped = 0
    candidates = []
    if CANDIDATE_DIR.exists():
        candidates = [path for path in CANDIDATE_DIR.rglob("*.md") if is_candidate_prompt(path)]

    for path in sorted(candidates):
        scorecard_path = Path(str(path).replace(".md", ".scorecard.json"))
        if scorecard_path.exists() and not args.force:
            skipped += 1
            continue
        scorecard_path.write_text(
            json.dumps(build_scorecard(path), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        created += 1

    print(f"candidates={len(candidates)} created={created} skipped={skipped}")


if __name__ == "__main__":
    main()
