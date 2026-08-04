# -*- coding: utf-8 -*-
"""
route_loop.py — route 子集合搜尋與閉環控制器。

用途：
  python route_loop.py --loops 1 --evolve-rounds 0 --parallel 24
  python route_loop.py --loops 5 --evolve-rounds 1 --parallel 24

流程：
  1. 掃描 prompts/champions/*.md。
  2. 枚舉 champion 子集合，產生候選 route。
  3. 對每個 route 跑 routed dev / holdout。
  4. 必須 dev 與 holdout 都通過 compare_runs pragmatic，才啟用 route。
  5. 若沒有通過，且 evolve-rounds > 0，跑一輪題型演化後重試。
"""
import argparse
import itertools
import json
import os
import shutil
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from route_evolve import (  # noqa: E402
    BASELINE_PROMPT,
    PYTHON_BIN,
    ROUTE_PATH,
    TYPE_SLUGS,
    append_jsonl,
    compare_run,
    evaluate_routed,
    read_json,
    write_json,
)

C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET = "\033[0m"

ROUTE_CANDIDATE_DIR = "prompts/routes/candidates"
ACTIVE_ROUTE_PATH = "prompts/routes/active_type_champions.json"
DECISION_PATH = "prompts/routes/route_loop.decision.json"
LOG_PATH = "route_loop_log.jsonl"


def write_route(path, by_type, name):
    route = {
        "name": name,
        "default_prompt": BASELINE_PROMPT,
        "by_type": by_type,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(route, f, ensure_ascii=False, indent=2)
    return route


def available_champions():
    champions = {}
    for type_name, slug in TYPE_SLUGS.items():
        path = os.path.join("prompts/champions", f"{slug}.md")
        if os.path.exists(path):
            champions[type_name] = path.replace("\\", "/")
    return champions


def route_subsets(champions):
    items = sorted(champions.items())
    yield "baseline_only", {}
    for size in range(1, len(items) + 1):
        for combo in itertools.combinations(items, size):
            slugs = [TYPE_SLUGS[type_name] for type_name, _ in combo]
            name = "route_" + "__".join(slugs)
            yield name, dict(combo)


def avg_from_summary(summary):
    return float(summary.get("average_score", 0.0))


def score_route(route_path, parallel, baseline_meta):
    _, dev_run, dev_summary = evaluate_routed(route_path, "questions/dev.jsonl", parallel)
    _, holdout_run, holdout_summary = evaluate_routed(route_path, "questions/holdout.jsonl", parallel)
    dev_accept, dev_diff, dev_comparison = compare_run(
        dev_run,
        baseline_meta.get("dev_run", "runs/20260524_041843"),
        mode="pragmatic",
    )
    holdout_accept, holdout_diff, holdout_comparison = compare_run(
        holdout_run,
        baseline_meta.get("holdout_run", "runs/20260524_162523"),
        mode="pragmatic",
    )
    comparisons = (dev_comparison, holdout_comparison)
    invalid = next(
        (comparison for comparison in comparisons
         if comparison.get("completion_status") in {"failed", "incomplete"}),
        None,
    )
    if invalid:
        return {
            "route_path": route_path,
            "dev_run": dev_run,
            "holdout_run": holdout_run,
            "dev_avg": avg_from_summary(dev_summary),
            "holdout_avg": avg_from_summary(holdout_summary),
            "dev_accept": False,
            "holdout_accept": False,
            "accepted": False,
            "valid": False,
            "dev_diff": None,
            "holdout_diff": None,
            "holdout_risk_rate": None,
            "completion_status": "failed",
            "reason_code": invalid.get("reason_code") or "NON_COMPLETED_STATUS",
            "rejection_reason": invalid.get("rejection_reason") or "route evidence is not completed",
            "rejection_reasons": invalid.get("rejection_reasons", []),
            "evidence_errors": invalid.get("evidence_errors", []),
        }
    return {
        "route_path": route_path,
        "dev_run": dev_run,
        "holdout_run": holdout_run,
        "dev_avg": avg_from_summary(dev_summary),
        "holdout_avg": avg_from_summary(holdout_summary),
        "dev_accept": dev_accept,
        "holdout_accept": holdout_accept,
        "accepted": bool(dev_accept and holdout_accept),
        "valid": True,
        "completion_status": "completed",
        "dev_diff": dev_diff,
        "holdout_diff": holdout_diff,
        "dev_risk_rate": dev_comparison.get("risk_rate"),
        "holdout_risk_rate": holdout_comparison.get("risk_rate"),
        "dev_type_diffs": dev_comparison.get("type_diffs", {}),
        "holdout_type_diffs": holdout_comparison.get("type_diffs", {}),
        "failure_new_holdout": holdout_comparison.get("failure_new", {}),
        "failure_base_holdout": holdout_comparison.get("failure_base", {}),
    }


def rank_key(result):
    accepted_bonus = 1 if result.get("accepted") else 0
    return (
        accepted_bonus,
        result.get("holdout_diff", -999),
        result.get("dev_diff", -999),
        result.get("holdout_risk_rate") or 0,
        result.get("holdout_avg", 0),
    )


def search_routes(parallel):
    champions = available_champions()
    if not champions:
        print(f"{C_YELLOW}沒有任何題型 champion，只能評估 baseline route。{C_RESET}")

    baseline_meta = read_json("prompts/baseline.meta.json", {})
    stamp = time.strftime("%Y%m%d_%H%M%S")
    results = []
    rejected_results = []
    print(f"{C_PURPLE}開始 route 子集合搜尋：{len(champions)} 個 champion。{C_RESET}")

    for name, by_type in route_subsets(champions):
        route_path = os.path.join(ROUTE_CANDIDATE_DIR, f"{stamp}_{name}.json")
        write_route(route_path, by_type, name)
        print(f"\n{C_CYAN}=== 評估 route: {name} ==={C_RESET}")
        result = score_route(route_path, parallel, baseline_meta)
        result["name"] = name
        result["by_type"] = by_type
        if not result.get("valid", True):
            rejected_results.append(result)
        else:
            results.append(result)
        append_jsonl(LOG_PATH, {
            "event": "route_candidate",
            "name": name,
            "route_path": route_path,
            "accepted": result["accepted"],
            "dev_diff": result["dev_diff"],
            "holdout_diff": result["holdout_diff"],
            "holdout_risk_rate": result.get("holdout_risk_rate"),
            "completion_status": result.get("completion_status", "completed"),
            "reason_code": result.get("reason_code", ""),
            "rejection_reason": result.get("rejection_reason", ""),
        })

    results.sort(key=rank_key, reverse=True)
    best = results[0] if results else {}
    accepted = [row for row in results if row.get("accepted")]
    decision = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "decision": "ACCEPT_ROUTE" if accepted else "REJECT_ALL_ROUTES",
        "best": best,
        "accepted_count": len(accepted),
        "candidate_count": len(results),
        "rejected_count": len(rejected_results),
        "rejected_results": rejected_results,
        "top_results": results[:10],
    }
    write_json(DECISION_PATH, decision)

    if accepted:
        winner = accepted[0]
        shutil.copy2(winner["route_path"], ACTIVE_ROUTE_PATH)
        shutil.copy2(winner["route_path"], ROUTE_PATH)
        print(f"{C_GREEN}Route 已啟用：{winner['name']} -> {ACTIVE_ROUTE_PATH}{C_RESET}")
    else:
        best_diff = best.get("holdout_diff")
        diff_text = f"{best_diff:+.2f}" if isinstance(best_diff, (int, float)) else "N/A"
        print(f"{C_RED}沒有 route 通過 dev + holdout。最佳候選：{best.get('name', 'N/A')} holdout_diff={diff_text}{C_RESET}")

    return decision


def evolve_once(parallel, rounds):
    if rounds <= 0:
        return
    cmd = [
        PYTHON_BIN,
        "route_evolve.py",
        "--all",
        "--rounds",
        str(rounds),
        "--parallel",
        str(parallel),
        "--skip-route-eval",
    ]
    print(f"\n{C_PURPLE}=== 產生下一批題型 champion 候選 ==={C_RESET}")
    print(f"{C_CYAN}$ {' '.join(cmd)}{C_RESET}")
    subprocess.run(cmd, check=False)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loops", type=int, default=1, help="route 搜尋閉環輪數")
    parser.add_argument("--evolve-rounds", type=int, default=0, help="每輪 route 搜尋失敗後，各題型演化幾輪")
    parser.add_argument("--parallel", type=int, default=24)
    parser.add_argument("--stop-on-accept", action="store_true", default=True)
    return parser.parse_args()


def main():
    args = parse_args()
    preflight = subprocess.run([
        sys.executable or "python", "scripts/preflight.py", "--require-git",
    ])
    if preflight.returncode != 0:
        print(f"{C_RED}❌ Git／研究預檢未通過，未開始候選比較。{C_RESET}")
        return preflight.returncode

    final_decision = {}
    for loop_no in range(1, args.loops + 1):
        print(f"\n{C_PURPLE}######## ROUTE LOOP {loop_no}/{args.loops} ########{C_RESET}")
        final_decision = search_routes(args.parallel)
        if final_decision.get("decision") == "ACCEPT_ROUTE" and args.stop_on_accept:
            break
        if loop_no < args.loops:
            evolve_once(args.parallel, args.evolve_rounds)
    return 0 if final_decision else 1


if __name__ == "__main__":
    sys.exit(main())
