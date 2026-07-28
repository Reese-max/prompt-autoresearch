# -*- coding: utf-8 -*-
"""
產生 Prompt AutoResearch 實驗治理報告。

這支腳本只讀取既有 runs、decision 與 baseline metadata，不會修改題庫、
rubric、評分器或提示詞。用途是把歷史實驗整理成下一輪 loop 的決策依據。

用法：
  python scripts/experiment_report.py
  python scripts/experiment_report.py --out output/experiment_report.md
"""
import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNS_DIR = os.path.join(ROOT, "runs")
BASELINE_META = os.path.join(ROOT, "prompts", "baseline.meta.json")

STRICT_WORD_RATE = {
    "smoke": 70.0,
    "dev": 85.0,
    "holdout": 85.0,
    "final": 85.0,
}


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def dataset_name(question_file):
    name = os.path.basename(question_file or "").lower()
    for key in ("smoke", "dev", "holdout", "final"):
        if key in name:
            return key
    return "unknown"


def parse_decision(text):
    data = {}
    for line in text.splitlines():
        match = re.match(r"^\s*-\s*([A-Za-z0-9_]+):\s*(.*)\s*$", line)
        if match:
            data[match.group(1)] = match.group(2).strip()
    return data


def validate_summary(summary, run_name):
    """驗證 summary.json 結構合法性，拋出 ValueError 若結構非法。"""
    if not isinstance(summary, dict):
        raise ValueError(f"Run {run_name}: summary.json 必須是 dict，實際類型 {type(summary).__name__}")
    
    # 檢查必要欄位是否存在（允許值為 None，由後續轉換處理）
    required_fields = ["average_score"]
    for field in required_fields:
        if field not in summary:
            raise ValueError(f"Run {run_name}: 缺少必要欄位 '{field}'")
    
    # 檢查 average_score 是否為數值且非負值（若不為 None）
    score = summary.get("average_score")
    if score is not None:
        try:
            score_value = float(score)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Run {run_name}: average_score 必須是數值，實際值 {score!r}") from e
        
        if score_value < 0:
            raise ValueError(f"Run {run_name}: average_score 必須非負值，實際值 {score_value}")


def list_runs():
    rows = []
    if not os.path.isdir(RUNS_DIR):
        return rows
    for name in sorted(os.listdir(RUNS_DIR)):
        run_dir = os.path.join(RUNS_DIR, name)
        if name == "latest" or not os.path.isdir(run_dir):
            continue
        summary = load_json(os.path.join(run_dir, "summary.json"))
        if not summary:
            continue
        validate_summary(summary, name)
        decision_text = read_text(os.path.join(run_dir, "decision.md"))
        decision = parse_decision(decision_text)
        question_file = summary.get("question_file", "")
        rows.append(
            {
                "name": name,
                "run_dir": os.path.relpath(run_dir, ROOT),
                "dataset": dataset_name(question_file),
                "question_file": question_file,
                "prompt_file": summary.get("prompt_file", ""),
                "prompt_hash": summary.get("prompt_hash", ""),
                "score": float(summary.get("average_score") or 0.0),
                "risk": float(summary.get("risk_perfect_rate") or 0.0),
                "word_rate": float(summary.get("word_count_pass_rate") or 0.0),
                "char_count": int(summary.get("char_count") or 0),
                "elapsed": float(summary.get("elapsed_seconds") or 0.0),
                "api_calls": int(summary.get("estimated_api_calls") or 0),
                "errors": int(summary.get("error_count") or 0),
                "types": summary.get("type_averages") or {},
                "failures": summary.get("failure_counts") or {},
                "decision": decision,
            }
        )
    return rows


def gate_notes(row):
    notes = []
    threshold = STRICT_WORD_RATE.get(row["dataset"])
    if threshold is not None and row["word_rate"] < threshold:
        notes.append(f"字數合格率 {row['word_rate']:.1f}% < {threshold:.0f}%")
    if row["risk"] < 100.0:
        notes.append(f"風險滿分率 {row['risk']:.1f}% < 100%")
    if row["errors"] > 0:
        notes.append(f"評估錯誤 {row['errors']} 筆")
    return notes


def format_table(headers, rows):
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def best_worst_type(types):
    if not types:
        return "-", "-"
    best_name, best_score = max(types.items(), key=lambda item: float(item[1]))
    worst_name, worst_score = min(types.items(), key=lambda item: float(item[1]))
    return f"{best_name} {float(best_score):.2f}", f"{worst_name} {float(worst_score):.2f}"


def top_rows(rows, dataset, limit):
    filtered = [row for row in rows if row["dataset"] == dataset]
    return sorted(filtered, key=lambda row: row["score"], reverse=True)[:limit]


def collect_decisions(rows):
    by_direction = defaultdict(Counter)
    totals = Counter()
    for row in rows:
        decision = row["decision"]
        if not decision:
            continue
        direction = decision.get("direction") or "未標記"
        verdict = decision.get("decision") or "UNKNOWN"
        by_direction[direction][verdict] += 1
        totals[verdict] += 1
    return totals, by_direction


def collect_failure_trends(rows):
    failures = Counter()
    type_scores = defaultdict(list)
    for row in rows:
        if row["dataset"] != "dev":
            continue
        failures.update(row["failures"])
        for type_name, score in row["types"].items():
            type_scores[type_name].append(float(score))
    weak_types = []
    for type_name, scores in type_scores.items():
        weak_types.append((sum(scores) / len(scores), type_name, len(scores)))
    return failures, sorted(weak_types)


def build_report(rows, limit):
    baseline_meta = load_json(BASELINE_META)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Prompt AutoResearch 實驗治理報告",
        "",
        f"- 產生時間：{now}",
        f"- 掃描 runs：{len(rows)}",
        f"- baseline prompt hash：`{baseline_meta.get('prompt_hash', '-')}`",
        f"- baseline dev：`{baseline_meta.get('dev_run', '-')}` / {baseline_meta.get('dev_avg', '-')}",
        f"- baseline holdout：`{baseline_meta.get('holdout_run', '-')}` / {baseline_meta.get('holdout_avg', '-')}",
        "",
    ]

    lines.extend(["## 1. 資料集最佳 runs", ""])
    for dataset in ("smoke", "dev", "holdout"):
        table_rows = []
        for row in top_rows(rows, dataset, limit):
            best, worst = best_worst_type(row["types"])
            notes = "；".join(gate_notes(row)) or "通過治理檢查"
            table_rows.append(
                [
                    row["run_dir"],
                    f"{row['score']:.2f}",
                    f"{row['word_rate']:.1f}%",
                    f"{row['risk']:.1f}%",
                    best,
                    worst,
                    notes,
                ]
            )
        lines.append(f"### {dataset}")
        lines.append("")
        if table_rows:
            lines.append(
                format_table(
                    ["run", "分數", "字數合格", "風險滿分", "最佳題型", "最弱題型", "治理註記"],
                    table_rows,
                )
            )
        else:
            lines.append("_無資料_")
        lines.append("")

    totals, by_direction = collect_decisions(rows)
    lines.extend(["## 2. Decision 統計", ""])
    if totals:
        lines.append("- 總計：" + "，".join(f"{key}={value}" for key, value in sorted(totals.items())))
        lines.append("")
        decision_rows = []
        for direction, counts in sorted(by_direction.items()):
            decision_rows.append(
                [
                    direction,
                    counts.get("ACCEPT", 0),
                    counts.get("REVERT", 0),
                    counts.get("REJECT", 0),
                    sum(counts.values()),
                ]
            )
        lines.append(format_table(["方向", "ACCEPT", "REVERT", "REJECT", "總數"], decision_rows))
    else:
        lines.append("_尚無 decision.md 可統計_")
    lines.append("")

    failures, weak_types = collect_failure_trends(rows)
    lines.extend(["## 3. Dev 卡點", ""])
    if failures:
        top_failures = ", ".join(f"{code}:{count}" for code, count in failures.most_common(8))
        lines.append(f"- 常見 F-code：{top_failures}")
    else:
        lines.append("- 常見 F-code：無")
    if weak_types:
        weak_text = ", ".join(f"{name}:{avg:.2f}（n={count}）" for avg, name, count in weak_types[:6])
        lines.append(f"- 平均最弱題型：{weak_text}")
    lines.append("")

    hard_gate_rows = []
    for row in rows:
        notes = gate_notes(row)
        if notes:
            hard_gate_rows.append([row["run_dir"], row["dataset"], f"{row['score']:.2f}", "；".join(notes)])
    lines.extend(["## 4. 建議提前擋下的 runs", ""])
    if hard_gate_rows:
        lines.append(format_table(["run", "資料集", "分數", "提前淘汰理由"], hard_gate_rows[-limit:]))
    else:
        lines.append("_沒有明顯治理門檻違規_")
    lines.append("")

    lines.extend(
        [
            "## 5. 下一輪 loop 建議",
            "",
            "1. 先把 smoke 的字數合格率設成硬門檻：低於 70% 不進 dev。",
            "2. dev / holdout 字數合格率低於 85% 一律不 promote。",
            "3. 對高分但未通過全域門檻的候選，只能存成 type champion，不可直接升 baseline。",
            "4. 下一輪優先攻最常見 F-code 與平均最弱題型，避免只追總分。",
        ]
    )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="每段最多列出幾筆")
    parser.add_argument("--out", help="可選：寫出 markdown 報告路徑")
    args = parser.parse_args()

    rows = list_runs()
    report = build_report(rows, args.limit)
    print(report)
    if args.out:
        out_path = os.path.abspath(os.path.join(ROOT, args.out))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)


if __name__ == "__main__":
    main()
