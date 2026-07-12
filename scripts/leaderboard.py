# -*- coding: utf-8 -*-
"""
列出最近 dev runs 排行，協助判斷下一輪應優化哪個方向。

用法：
  python scripts/leaderboard.py --limit 20
"""
import argparse
import json
import os

if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_runs():
    rows = []
    if not os.path.exists("runs"):
        return rows
    for name in sorted(os.listdir("runs")):
        run_dir = os.path.join("runs", name)
        if name == "latest" or not os.path.isdir(run_dir):
            continue
        summary = load_json(os.path.join(run_dir, "summary.json"))
        if summary.get("question_file") != "questions/dev.jsonl":
            continue
        rows.append(
            {
                "run_dir": run_dir,
                "score": float(summary.get("average_score") or 0.0),
                "risk": float(summary.get("risk_perfect_rate") or 0.0),
                "prompt_file": summary.get("prompt_file", ""),
                "prompt_hash": summary.get("prompt_hash", "")[:12],
                "types": summary.get("type_averages", {}),
                "failures": summary.get("failure_counts", {}),
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    rows = sorted(list_runs(), key=lambda row: row["score"], reverse=True)[: args.limit]
    print("rank\tscore\trisk\trun\tprompt\tbest_type\tworst_type\tfailures")
    for i, row in enumerate(rows, 1):
        types = row["types"]
        best_type = ""
        worst_type = ""
        if types:
            best_name, best_score = max(types.items(), key=lambda item: item[1])
            worst_name, worst_score = min(types.items(), key=lambda item: item[1])
            best_type = f"{best_name}:{best_score:.2f}"
            worst_type = f"{worst_name}:{worst_score:.2f}"
        failures = ",".join(f"{k}:{v}" for k, v in sorted(row["failures"].items(), key=lambda item: item[1], reverse=True)[:4])
        print(
            f"{i}\t{row['score']:.2f}\t{row['risk']:.1f}%\t{row['run_dir']}\t"
            f"{row['prompt_file']}#{row['prompt_hash']}\t{best_type}\t{worst_type}\t{failures}"
        )


if __name__ == "__main__":
    main()
