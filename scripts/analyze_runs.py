# -*- coding: utf-8 -*-
"""
scripts/analyze_runs.py — 彙整近期 run 的失敗碼、題型均分與局部突破。
"""
import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def list_run_dirs():
    if not os.path.exists("runs"):
        return []
    return [
        os.path.join("runs", name)
        for name in sorted(os.listdir("runs"))
        if name != "latest" and os.path.isdir(os.path.join("runs", name))
    ]


def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def read_details(run_dir):
    path = os.path.join(run_dir, "details.jsonl")
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def normalize(path):
    return path.replace("\\", "/")


def summarize_run(run_dir):
    summary = load_json(os.path.join(run_dir, "summary.json"))
    rows = read_details(run_dir)
    if not rows:
        return None

    failure_counts = {}
    type_scores = {}
    type_counts = {}
    for row in rows:
        qtype = row.get("type", "unknown")
        type_scores[qtype] = type_scores.get(qtype, 0) + row.get("total_score", 0)
        type_counts[qtype] = type_counts.get(qtype, 0) + 1
        for code in row.get("failures", []):
            if code:
                failure_counts[code] = failure_counts.get(code, 0) + 1

    type_averages = {qtype: type_scores[qtype] / type_counts[qtype] for qtype in type_scores}
    avg = sum(row.get("total_score", 0) for row in rows) / len(rows)
    return {
        "run_dir": run_dir,
        "question_file": normalize(summary.get("question_file", rows[0].get("question_file", ""))),
        "prompt_hash": summary.get("prompt_hash", rows[0].get("prompt_hash", "")),
        "average_score": summary.get("average_score", avg),
        "failure_counts": summary.get("failure_counts", failure_counts),
        "type_averages": summary.get("type_averages", type_averages),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-file", default="questions/dev.jsonl")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    runs = []
    for run_dir in reversed(list_run_dirs()):
        summary = summarize_run(run_dir)
        if not summary or summary["question_file"] != normalize(args.question_file):
            continue
        runs.append(summary)
        if len(runs) >= args.limit:
            break

    total_failures = {}
    type_scores = {}
    type_counts = {}
    for run in runs:
        for code, count in run["failure_counts"].items():
            total_failures[code] = total_failures.get(code, 0) + count
        for qtype, score in run["type_averages"].items():
            type_scores[qtype] = type_scores.get(qtype, 0) + score
            type_counts[qtype] = type_counts.get(qtype, 0) + 1

    payload = {
        "question_file": normalize(args.question_file),
        "runs": runs,
        "failure_trend": dict(sorted(total_failures.items(), key=lambda item: item[1], reverse=True)),
        "type_average_trend": {
            qtype: type_scores[qtype] / type_counts[qtype]
            for qtype in sorted(type_scores)
        },
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("============================================================")
    print("  Prompt AutoResearch Run Trend")
    print("============================================================")
    print(f"題庫: {payload['question_file']}")
    print(f"納入 runs: {', '.join(run['run_dir'] for run in runs) or '無'}")
    print("\n[失敗碼趨勢]")
    for code, count in payload["failure_trend"].items():
        print(f"  - {code}: {count}")
    print("\n[題型平均趨勢]")
    for qtype, score in payload["type_average_trend"].items():
        print(f"  - {qtype}: {score:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
