# -*- coding: utf-8 -*-
"""
scripts/preflight.py — Prompt AutoResearch 執行前健康檢查。
檢查金鑰、題庫數量、baseline hash、baseline metadata 與併緒設定。
"""
import argparse
import hashlib
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
from scripts.git_reproducibility import collect_git_preflight, persist_git_preflight

C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_RESET = "\033[0m"

EXPECTED_COUNTS = {
    "questions/smoke.jsonl": 6,
    "questions/dev.jsonl": 48,
    "questions/holdout.jsonl": 18,
    "questions/final.jsonl": 12,
}


def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_jsonl(path):
    if not os.path.exists(path):
        return None
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                json.loads(line)
                count += 1
    return count


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_run_path(path):
    return bool(path and os.path.exists(os.path.join(path, "summary.md")) and os.path.exists(os.path.join(path, "details.jsonl")))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-git",
        action="store_true",
        help="研究執行入口使用：Git 工作區預檢失敗時硬阻塞。",
    )
    parser.add_argument("--smoke-parallel", type=int, default=int(os.environ.get("AUTORESEARCH_SMOKE_PARALLEL", "6")))
    parser.add_argument("--dev-parallel", type=int, default=int(os.environ.get("AUTORESEARCH_DEV_PARALLEL", "24")))
    parser.add_argument("--holdout-parallel", type=int, default=int(os.environ.get("AUTORESEARCH_HOLDOUT_PARALLEL", "24")))
    args = parser.parse_args(argv)

    checks = []
    git_preflight = collect_git_preflight(cwd=os.getcwd())

    def add(name, passed, detail, severity="error"):
        checks.append({"name": name, "passed": bool(passed), "detail": detail, "severity": severity})

    git_state_path = ""
    if args.require_git or git_preflight.get("blocked"):
        try:
            git_state_path = persist_git_preflight(git_preflight)
        except OSError as exc:
            add("Git preflight state", False, f"預檢阻塞狀態無法持久化：{exc}")
    if args.require_git:
        add(
            "Git workspace",
            git_preflight.get("passed", False),
            git_preflight.get("blocking_reason") or "Git metadata、repository root 與 HEAD 可解析",
        )

    add("MINIMAX_API_KEY", bool(os.environ.get("MINIMAX_API_KEY")), "環境變數已設定" if os.environ.get("MINIMAX_API_KEY") else "缺少 MINIMAX_API_KEY")
    add("Python version", sys.version_info >= (3, 10), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    for path, expected in EXPECTED_COUNTS.items():
        try:
            actual = count_jsonl(path)
            add(path, actual == expected, f"題數 {actual} / 預期 {expected}")
        except Exception as exc:
            add(path, False, f"題庫解析失敗：{exc}")

    baseline = read_text("prompts/baseline.md").strip()
    current = read_text("prompts/current.md").strip()
    add("prompts/baseline.md", bool(baseline), f"字數 {len(baseline)}")
    add("prompts/current.md", bool(current), f"字數 {len(current)}")

    baseline_hash = sha256_text(baseline) if baseline else ""
    meta = load_json("prompts/baseline.meta.json")
    add(
        "baseline.meta hash",
        bool(meta) and meta.get("prompt_hash") == baseline_hash,
        f"meta={str(meta.get('prompt_hash', ''))[:12]} baseline={baseline_hash[:12]}",
    )
    add("baseline dev run", check_run_path(meta.get("dev_run")), str(meta.get("dev_run")))
    add("baseline smoke run", check_run_path(meta.get("smoke_run")), str(meta.get("smoke_run")), severity="warn")
    add("baseline holdout run", check_run_path(meta.get("holdout_run")), str(meta.get("holdout_run")), severity="warn")
    add("runs/latest", os.path.exists("runs/latest/summary.md"), "runs/latest/summary.md")
    add(
        "parallel settings",
        args.smoke_parallel >= 1 and args.dev_parallel >= 1 and args.holdout_parallel >= 1,
        f"smoke={args.smoke_parallel}, dev={args.dev_parallel}, holdout={args.holdout_parallel}",
    )

    errors = [c for c in checks if not c["passed"] and c["severity"] == "error"]
    warnings = [c for c in checks if not c["passed"] and c["severity"] == "warn"]
    passed = not errors

    payload = {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "git_preflight": git_preflight,
        "git_preflight_state_path": git_state_path,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("============================================================")
        print("  Prompt AutoResearch Preflight")
        print("============================================================")
        for check in checks:
            if check["passed"]:
                color = C_GREEN
                mark = "OK"
            elif check["severity"] == "warn":
                color = C_YELLOW
                mark = "WARN"
            else:
                color = C_RED
                mark = "FAIL"
            print(f"  {color}[{mark}]{C_RESET} {check['name']}: {check['detail']}")
        print("============================================================")
        print(f"  結果: {C_GREEN + 'PASS' + C_RESET if passed else C_RED + 'FAIL' + C_RESET}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
