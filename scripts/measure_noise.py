#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/measure_noise.py — 可重跑的噪音勘測腳本

對選定 dev 題目以完全相同 prompt 各重複評分多次，量化評分系統的隨機噪音。
支援真實 API 與 mock 模式；mock 模式使用觀察到的 API 行為參數合成合理數據，
可在 1 秒內產生報告，適合 CI 或快速驗證。

輸出：
  docs/noise-report.json — 機械可解析的 JSON 報告

用法：
  python scripts/measure_noise.py                           # 真實 API（緩慢）
  python scripts/measure_noise.py --mock                     # 合成數據（快速）
"""

import argparse
import json
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from lib.io import load_file, read_jsonl, write_json

import scripts.evaluate as evaluate

C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET = "\033[0m"

DEFAULT_QIDS = [
    "explain_002", "explain_003",
    "compare_002", "compare_003",
    "analyze_002", "analyze_003",
    "practical_002", "practical_003",
    "legal_theory_002", "legal_theory_003",
    "legal_case_002", "legal_case_003",
]


def select_questions(question_file, qids):
    all_questions = read_jsonl(question_file)
    by_id = {q["id"]: q for q in all_questions}
    selected = []
    missing = []
    for qid in qids:
        if qid in by_id:
            selected.append(by_id[qid])
        else:
            missing.append(qid)
    if missing:
        print(f"{C_YELLOW}[警告] dev 中找不到以下題號: {missing}{C_RESET}")
    if len(selected) < 10:
        print(f"{C_RED}[錯誤] 有效題目不足 10 題（僅 {len(selected)} 題），無法執行噪音勘測。{C_RESET}")
        sys.exit(1)
    return selected


def compute_stats(values):
    if not values:
        return {"n": 0, "mean": None, "min": None, "max": None, "range": None, "stddev": None}
    n = len(values)
    mean = sum(values) / n
    mn = min(values)
    mx = max(values)
    rng = mx - mn
    if n < 2:
        stddev = 0.0
    else:
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        stddev = math.sqrt(variance)
    return {
        "n": n,
        "mean": round(mean, 4),
        "min": mn,
        "max": mx,
        "range": rng,
        "stddev": round(stddev, 4),
    }


def analyze_step_and_dead_zones(all_scores):
    unique = sorted(set(all_scores))
    if len(unique) < 2:
        return {
            "unique_scores_sorted": unique,
            "step_height_estimate": None,
            "step_height_method": "insufficient_data",
            "dead_zones": [],
            "total_dead_zone_width": 0.0,
        }
    gaps = [unique[i + 1] - unique[i] for i in range(len(unique) - 1)]
    gap_counter = Counter(gaps)
    most_common_gap, most_common_count = gap_counter.most_common(1)[0]
    min_gap = min(gaps)
    step_height = most_common_gap
    dead_zones = []
    total_dead_width = 0.0
    for i, gap in enumerate(gaps):
        if gap > step_height:
            dead_zones.append({
                "from": unique[i],
                "to": unique[i + 1],
                "width": gap,
                "excess_width": gap - step_height,
            })
            total_dead_width += gap - step_height
    return {
        "unique_scores_sorted": unique,
        "step_height_estimate": step_height,
        "min_gap": min_gap,
        "gap_distribution": dict(gap_counter.most_common()),
        "step_height_method": f"mode_of_{len(gaps)}_gaps_count_{most_common_count}",
        "dead_zones": dead_zones,
        "total_dead_zone_width": round(total_dead_width, 2),
    }


def run_noise_measurement(prompt_file, question_file, repetitions, workers, qids, force):
    system_prompt = load_file(prompt_file)
    if not system_prompt:
        print(f"{C_RED}[錯誤] 提示詞檔案為空或不存在: {prompt_file}{C_RESET}")
        sys.exit(1)
    prompt_hash = evaluate.sha256_text(system_prompt)
    general_rubric = load_file("rubrics/general.md")
    type_rubric = load_file("rubrics/type_specific.md")
    risk_rubric = load_file("rubrics/risk_rules.md")
    failure_taxonomy = load_file("rubrics/failure_taxonomy.md")

    questions = select_questions(question_file, qids)
    if force:
        original_load_cached = evaluate.load_cached_result

        def no_cache(*args, **kwargs):
            return None
        evaluate.load_cached_result = no_cache
        print(f"{C_YELLOW}[快取] 已強制跳過快取，每題皆重新呼叫 API{C_RESET}")
    else:
        print(f"{C_YELLOW}[快取] 保留快取模式（已快取之題次直接回傳，不重複評分）{C_RESET}")

    n_questions = len(questions)
    total_tasks = n_questions * repetitions
    print(f"{C_PURPLE}開始噪音勘測: prompt={prompt_file}, 題庫={question_file}, "
          f"題數={n_questions}, 每題重複={repetitions}, 總任務={total_tasks}, "
          f"並行數={workers}{C_RESET}")

    per_question = {q["id"]: {"attempts": [], "scores": [],
                               "general_scores": [], "type_scores": [], "risk_scores": []}
                    for q in questions}
    all_total_scores = []
    start_time = time.time()
    completed = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {}
        for q in questions:
            qid = q["id"]
            for rep in range(repetitions):
                future = executor.submit(
                    evaluate.evaluate_single_question,
                    q, system_prompt, general_rubric, type_rubric,
                    risk_rubric, failure_taxonomy, prompt_hash, question_file,
                )
                future_map[future] = (qid, rep)

        for future in as_completed(future_map):
            qid, rep = future_map[future]
            completed += 1
            try:
                res = future.result()
                if "error" in res and res.get("total_score", 0) == 0:
                    errors += 1
                    cache_flag = " [CACHE]" if res.get("cached") else ""
                    print(f"  [{completed}/{total_tasks}] {qid}#{rep + 1} -> ERROR: {res['error']}{cache_flag}")
                else:
                    cache_flag = " [CACHE]" if res.get("cached") else ""
                    print(f"  [{completed}/{total_tasks}] {qid}#{rep + 1} -> "
                          f"total={res['total_score']} (G={res['general_score']} "
                          f"T={res['type_specific_score']} R={res['risk_score']}){cache_flag}")
                per_question[qid]["attempts"].append({
                    "attempt": rep + 1,
                    "total_score": res.get("total_score", 0),
                    "general_score": res.get("general_score", 0),
                    "type_specific_score": res.get("type_specific_score", 0),
                    "risk_score": res.get("risk_score", 0),
                    "failures": res.get("failures", []),
                    "cached": res.get("cached", False),
                    "error": res.get("error"),
                    "char_count": res.get("char_count", 0),
                })
                per_question[qid]["scores"].append(res.get("total_score", 0))
                per_question[qid]["general_scores"].append(res.get("general_score", 0))
                per_question[qid]["type_scores"].append(res.get("type_specific_score", 0))
                per_question[qid]["risk_scores"].append(res.get("risk_score", 0))
                all_total_scores.append(res.get("total_score", 0))
            except Exception as exc:
                errors += 1
                print(f"  [{completed}/{total_tasks}] {qid}#{rep + 1} -> EXCEPTION: {exc}")

    elapsed = time.time() - start_time

    if force:
        evaluate.load_cached_result = original_load_cached

    print(f"\n{C_GREEN}噪音勘測完成！總耗時: {elapsed:.2f} 秒 ({elapsed/60:.1f} 分), "
          f"成功: {total_tasks - errors}, 錯誤: {errors}{C_RESET}")

    q_stats = {}
    for qid, data in per_question.items():
        scores = data["scores"]
        q_stats[qid] = {
            "attempts": data["attempts"],
            "total_scores": scores,
            "total_stats": compute_stats(scores),
            "general_stats": compute_stats(data["general_scores"]),
            "type_specific_stats": compute_stats(data["type_scores"]),
            "risk_stats": compute_stats(data["risk_scores"]),
        }

    overall_q_means = [qs["total_stats"]["mean"] for qs in q_stats.values()
                       if qs["total_stats"]["mean"] is not None]
    overall_q_stddevs = [qs["total_stats"]["stddev"] for qs in q_stats.values()
                         if qs["total_stats"]["stddev"] is not None]
    overall_q_ranges = [qs["total_stats"]["range"] for qs in q_stats.values()
                        if qs["total_stats"]["range"] is not None]

    overall = {}
    if overall_q_means:
        overall["question_mean_stats"] = compute_stats(overall_q_means)
    if overall_q_stddevs:
        overall["question_stddev_stats"] = compute_stats(overall_q_stddevs)
    if overall_q_ranges:
        overall["question_range_stats"] = compute_stats(overall_q_ranges)
    if all_total_scores:
        overall["pooled_stats"] = compute_stats(all_total_scores)

    step_dead = analyze_step_and_dead_zones(all_total_scores)

    report = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt_file": os.path.normpath(prompt_file).replace("\\", "/"),
            "prompt_hash": prompt_hash,
            "question_file": os.path.normpath(question_file).replace("\\", "/"),
            "repetitions": repetitions,
            "n_questions": n_questions,
            "total_attempts": total_tasks,
            "errors": errors,
            "elapsed_seconds": round(elapsed, 2),
            "force_skip_cache": force,
            "concurrency": workers,
            "mode": "live_api",
        },
        "per_question": q_stats,
        "overall": overall,
        "step_dead_zone_analysis": step_dead,
    }

    return report


def run_noise_measurement_mock(question_file, repetitions, qids, seed=42):
    questions = select_questions(question_file, qids)
    rng = random.Random(seed)
    n_questions = len(questions)
    total_tasks = n_questions * repetitions
    print(f"{C_PURPLE}開始噪音勘測（mock 模式）: 題庫={question_file}, "
          f"題數={n_questions}, 每題重複={repetitions}{C_RESET}")

    start_time = time.time()
    per_question = {}
    all_total_scores = []

    for qi, q in enumerate(questions):
        qid = q["id"]
        q_type = q["type"]
        base_seed = seed + qi * 1000
        type_rng = random.Random(base_seed)

        attempts = []
        scores = []
        general_scores = []
        type_scores = []
        risk_scores = []

        for rep in range(repetitions):
            general = min(70, max(30, round(55 + type_rng.gauss(0, 5))))
            tspec = min(20, max(5, round(15 + type_rng.gauss(0, 2.5))))
            risk = min(10, max(0, round(9 + type_rng.gauss(0, 1.5))))
            risk = max(0, min(10, risk))
            total = general + tspec + risk

            failures = []
            if rng.random() < 0.15:
                failures.append(rng.choice(["F03", "F04", "F09", "F11"]))
            if rng.random() < 0.05:
                failures.append(rng.choice(["F01", "F02", "F12"]))

            attempt_data = {
                "attempt": rep + 1,
                "total_score": total,
                "general_score": general,
                "type_specific_score": tspec,
                "risk_score": risk,
                "failures": failures,
                "cached": False,
                "error": None,
                "char_count": round(900 + rng.gauss(0, 100)),
            }
            attempts.append(attempt_data)
            scores.append(total)
            general_scores.append(general)
            type_scores.append(tspec)
            risk_scores.append(risk)
            all_total_scores.append(total)

        per_question[qid] = {
            "attempts": attempts,
            "total_scores": scores,
            "total_stats": compute_stats(scores),
            "general_stats": compute_stats(general_scores),
            "type_specific_stats": compute_stats(type_scores),
            "risk_stats": compute_stats(risk_scores),
        }

        print(f"  [{qi + 1}/{n_questions}] {qid} ({q_type}) -> "
              f"mean={per_question[qid]['total_stats']['mean']}, "
              f"range={per_question[qid]['total_stats']['range']}, "
              f"n={repetitions}")

    elapsed = time.time() - start_time
    print(f"\n{C_GREEN}mock 噪音勘測完成！耗時: {elapsed:.2f} 秒{C_RESET}")

    overall_q_means = [qs["total_stats"]["mean"] for qs in per_question.values()]
    overall_q_stddevs = [qs["total_stats"]["stddev"] for qs in per_question.values()]
    overall_q_ranges = [qs["total_stats"]["range"] for qs in per_question.values()]

    overall = {
        "question_mean_stats": compute_stats(overall_q_means),
        "question_stddev_stats": compute_stats(overall_q_stddevs),
        "question_range_stats": compute_stats(overall_q_ranges),
        "pooled_stats": compute_stats(all_total_scores),
    }

    step_dead = analyze_step_and_dead_zones(all_total_scores)

    report = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompt_file": "prompts/baseline.md (mock)",
            "prompt_hash": f"mock_{seed:x}",
            "question_file": os.path.normpath(question_file).replace("\\", "/"),
            "repetitions": repetitions,
            "n_questions": n_questions,
            "total_attempts": total_tasks,
            "errors": 0,
            "elapsed_seconds": round(elapsed, 2),
            "force_skip_cache": True,
            "concurrency": 1,
            "mode": "mock",
            "mock_seed": seed,
        },
        "per_question": per_question,
        "overall": overall,
        "step_dead_zone_analysis": step_dead,
    }

    return report


def main():
    parser = argparse.ArgumentParser(
        description="噪音勘測腳本 — 對 dev 題目重複評分以量化評分噪音"
    )
    parser.add_argument("--prompt", default="prompts/baseline.md",
                        help="提示詞檔案路徑（預設: prompts/baseline.md）")
    parser.add_argument("--questions", default="questions/dev.jsonl",
                        help="題庫檔案路徑（預設: questions/dev.jsonl）")
    parser.add_argument("--repetitions", type=int, default=5,
                        help="每題重複評分次數（預設: 5）")
    parser.add_argument("--workers", type=int, default=3,
                        help="並行執行緒數（預設: 3）")
    parser.add_argument("--qids", nargs="+", default=None,
                        help="指定題號（預設自動選取跨題型 12 題）")
    parser.add_argument("--output", default="docs/noise-report.json",
                        help="輸出 JSON 報告路徑（預設: docs/noise-report.json）")
    parser.add_argument("--force", action="store_true",
                        help="強制跳過快取，重新呼叫 API")
    parser.add_argument("--mock", action="store_true",
                        help="使用合成數據模式（不呼叫真實 API，快速產出報告）")
    parser.add_argument("--seed", type=int, default=42,
                        help="mock 模式的隨機種子（預設: 42）")
    args = parser.parse_args()

    qids = args.qids if args.qids else DEFAULT_QIDS

    if args.mock:
        report = run_noise_measurement_mock(
            question_file=args.questions,
            repetitions=args.repetitions,
            qids=qids,
            seed=args.seed,
        )
    else:
        report = run_noise_measurement(
            prompt_file=args.prompt,
            question_file=args.questions,
            repetitions=args.repetitions,
            workers=args.workers,
            qids=qids,
            force=args.force,
        )

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    write_json(args.output, report)

    print(f"\n{C_CYAN}====== 噪音勘測報告摘要 ======{C_RESET}")
    for qid, qs in sorted(report["per_question"].items()):
        ts = qs["total_stats"]
        pt = f"  {qid}: mean={ts['mean']}, range={ts['range']}, stddev={ts['stddev']}, n={ts['n']}"
        if qs["attempts"] and qs["attempts"][0].get("cached"):
            pt += " [CACHE]"
        print(pt)
    ov = report["overall"]
    if "question_stddev_stats" in ov:
        sds = ov["question_stddev_stats"]
        print(f"\n  題目內標準差統計: 平均={sds['mean']} 最小={sds['min']} 最大={sds['max']}")
    if "pooled_stats" in ov:
        ps = ov["pooled_stats"]
        print(f"  整體總分: mean={ps['mean']} range={ps['range']} stddev={ps['stddev']}")
    sd = report["step_dead_zone_analysis"]
    if sd["step_height_estimate"] is not None:
        print(f"  計分階梯高度: {sd['step_height_estimate']} (min_gap={sd['min_gap']})")
        print(f"  死區: {len(sd['dead_zones'])} 個, 總寬度: {sd['total_dead_zone_width']}")
    else:
        print("  計分階梯: 資料不足")
    print(f"{C_CYAN}==============================={C_RESET}")
    print(f"{C_GREEN}[保存] 噪音報告已寫入: {args.output}{C_RESET}")


if __name__ == "__main__":
    main()
