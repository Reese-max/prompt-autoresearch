# -*- coding: utf-8 -*-
"""
scripts/evaluate_routed.py — 依題型選擇不同 prompt 的評估入口。

用途：
  python scripts/evaluate_routed.py prompts/routes/baseline_legal_case.json questions/dev.jsonl --parallel 24
"""
import os
import sys
import json
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# 確保專案根目錄在 sys.path 中，讓 lib 模組可被匯入
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.join(_scripts_dir, "..")
sys.path.insert(0, _project_root)
sys.path.insert(0, _scripts_dir)
os.chdir(_project_root)

import evaluate

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_RED = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET = "\033[0m"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_questions(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def resolve_prompt(route, q_type):
    prompt_path = route.get("by_type", {}).get(q_type) or route.get("default_prompt")
    if not prompt_path:
        raise RuntimeError(f"找不到題型 {q_type} 的 prompt，且 route 未設定 default_prompt。")
    prompt_text = evaluate.load_file(prompt_path)
    if not prompt_text:
        raise RuntimeError(f"prompt 檔案不存在或空白：{prompt_path}")
    return prompt_path, prompt_text, evaluate.sha256_text(prompt_text)


def route_hash(route_path, route):
    payload = {
        "route_path": evaluate.normalize_path(route_path),
        "default_prompt": route.get("default_prompt", ""),
        "by_type": route.get("by_type", {}),
    }
    return evaluate.sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def calculate_route_usage(results):
    usage = {}
    for row in results:
        path = row.get("prompt_file", "")
        usage[path] = usage.get(path, 0) + 1
    return usage


def run_routed_evaluation(route_file, question_file, max_workers=24):
    route = load_json(route_file)
    questions = load_questions(question_file)
    if not questions:
        raise RuntimeError(f"題庫空白：{question_file}")

    general_rubric = evaluate.load_file("rubrics/general.md")
    type_rubric = evaluate.load_file("rubrics/type_specific.md")
    risk_rubric = evaluate.load_file("rubrics/risk_rules.md")
    failure_taxonomy = evaluate.load_file("rubrics/failure_taxonomy.md")

    composite_hash = route_hash(route_file, route)
    started = time.time()
    print(
        f"\n{C_PURPLE}開始路由評估: {question_file} "
        f"(共 {len(questions)} 題，並行執行緒: {max_workers}, route_hash={composite_hash[:12]}){C_RESET}"
    )

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for q in questions:
            prompt_path, prompt_text, prompt_hash = resolve_prompt(route, q["type"])
            future = executor.submit(
                evaluate.evaluate_single_question,
                q,
                prompt_text,
                general_rubric,
                type_rubric,
                risk_rubric,
                failure_taxonomy,
                prompt_hash,
                question_file,
            )
            future_map[future] = (q, prompt_path)

        for i, future in enumerate(as_completed(future_map), 1):
            q, prompt_path = future_map[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "id": q.get("id", ""),
                    "type": q.get("type", ""),
                    "question": q.get("question", ""),
                    "prompt_file": prompt_path,
                    "error": str(exc),
                    "general_score": 0,
                    "type_specific_score": 0,
                    "risk_score": 0,
                    "total_score": 0,
                    "failures": ["F01"],
                }
            row["prompt_file"] = prompt_path
            results.append(row)
            failures = ", ".join(row.get("failures", [])) or "無"
            cached = " cache" if row.get("cached") else ""
            print(
                f" [{i}/{len(questions)}] 題號: {row.get('id')} ({row.get('type')})"
                f" -> 總分: {row.get('total_score', 0)} | 缺陷: {failures} | prompt: {prompt_path}{cached}"
            )

    elapsed = time.time() - started
    summary = evaluate.calculate_statistics(results, elapsed, route_file, question_file, composite_hash)
    summary["route_file"] = evaluate.normalize_path(route_file)
    summary["route_name"] = route.get("name", "")
    summary["route"] = route
    summary["prompt_usage"] = calculate_route_usage(results)

    run_dir = evaluate.save_run_results(summary, results)
    with open(os.path.join(run_dir, "route.json"), "w", encoding="utf-8") as f:
        json.dump(route, f, ensure_ascii=False, indent=2)
    shutil.copy2(route_file, os.path.join(run_dir, "route_source.json"))

    print(f"\n{C_GREEN}路由評估完成！耗時: {elapsed:.2f} 秒。{C_RESET}")
    print(f"{C_GREEN}[保存] 運行報告已儲存至 {run_dir} 及 runs/latest/{C_RESET}")
    print(f"\n{C_CYAN}====== 評估結果摘要 ======{C_RESET}")
    print(f"  總平均分: {summary['average_score']:.2f}")
    print(f"  風險控制滿分率: {summary['risk_perfect_rate']:.1f}%")
    print(f"  Prompt 使用: {summary['prompt_usage']}")
    print(f"{C_CYAN}=========================={C_RESET}")
    return summary, results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python scripts/evaluate_routed.py <route.json> <question_file> [--parallel <workers>]")
        sys.exit(1)

    route_file = sys.argv[1]
    question_file = sys.argv[2]
    workers = 24
    if "--parallel" in sys.argv:
        try:
            workers = max(1, int(sys.argv[sys.argv.index("--parallel") + 1]))
        except (IndexError, ValueError):
            print(f"{C_RED}[錯誤] --parallel 後面必須接整數。{C_RESET}")
            sys.exit(1)

    run_routed_evaluation(route_file, question_file, workers)
