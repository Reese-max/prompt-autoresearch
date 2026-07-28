# -*- coding: utf-8 -*-
"""
infinite_evolve.py — Prompt AutoResearch 長跑演化控制器。

這不是無條件死循環，而是可長時間執行、具備硬停止條件的自動演化流程。

範例：
  python infinite_evolve.py --max-rounds 100 --parallel 24
  python infinite_evolve.py --max-rounds 100 --parallel 24 --budget-usd 50 --estimated-cost-per-call 0.002
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET = "\033[0m"

LOG_PATH = "evolution_log.jsonl"
ROUTE_PATH = "prompts/routes/baseline_legal_case.json"
BASELINE_META_PATH = "prompts/baseline.meta.json"


def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def append_jsonl(path, payload):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def list_run_dirs():
    if not os.path.exists("runs"):
        return []
    return [
        os.path.join("runs", name)
        for name in sorted(os.listdir("runs"))
        if name != "latest" and os.path.isdir(os.path.join("runs", name))
    ]


def run_summary(run_dir):
    return load_json(os.path.join(run_dir, "summary.json"), {})


def baseline_dev_score():
    meta = load_json(BASELINE_META_PATH, {})
    try:
        return float(meta.get("dev_avg") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def latest_dev_run_since(previous_runs):
    previous = set(previous_runs)
    candidates = []
    for run_dir in list_run_dirs():
        if run_dir in previous:
            continue
        summary = run_summary(run_dir)
        if summary.get("question_file") == "questions/dev.jsonl":
            candidates.append(run_dir)
    return candidates[-1] if candidates else ""


def latest_run_since(previous_runs):
    previous = set(previous_runs)
    candidates = [run_dir for run_dir in list_run_dirs() if run_dir not in previous]
    return candidates[-1] if candidates else ""


def collect_new_runs(previous_runs):
    previous = set(previous_runs)
    rows = []
    for run_dir in list_run_dirs():
        if run_dir in previous:
            continue
        summary = run_summary(run_dir)
        if summary:
            rows.append({"run_dir": run_dir, "summary": summary})
    return rows


def sum_estimated_calls(run_rows):
    return sum(int(row["summary"].get("estimated_api_calls") or 0) for row in run_rows)


def dominant_failure(summary):
    failures = summary.get("failure_counts") or {}
    if not failures:
        return ""
    return max(failures.items(), key=lambda item: item[1])[0]


def run_cmd(cmd, timeout=None):
    print(f"{C_CYAN}$ {' '.join(cmd)}{C_RESET}")
    return subprocess.run(cmd, timeout=timeout)


def route_accepts(route_run_dir, baseline_run="runs/20260524_041843"):
    import scripts.compare_runs as compare_runs

    accepted, _, diff = compare_runs.compare(route_run_dir, baseline_run)
    comparison = dict(compare_runs.LAST_COMPARISON)
    return accepted, diff, comparison


def maybe_run_route(args, round_no, previous_runs):
    if not args.route_every or round_no % args.route_every != 0:
        return None
    if not os.path.exists(ROUTE_PATH):
        print(f"{C_YELLOW}⚠️ 找不到 route 檔案，略過路由評估：{ROUTE_PATH}{C_RESET}")
        return None

    print(f"\n{C_PURPLE}[Route] 第 {round_no} 輪觸發題型路由 dev 評估。{C_RESET}")
    before = list_run_dirs()
    res = run_cmd(
        [
            sys.executable,
            "scripts/evaluate_routed.py",
            ROUTE_PATH,
            "questions/dev.jsonl",
            "--parallel",
            str(args.dev_parallel),
        ],
        timeout=args.route_timeout_seconds,
    )
    route_run = latest_dev_run_since(before)
    payload = {
        "stage": "route",
        "round": round_no,
        "returncode": res.returncode,
        "run_dir": route_run,
    }
    if route_run and res.returncode == 0:
        summary = run_summary(route_run)
        payload["summary"] = {
            "average_score": summary.get("average_score"),
            "risk_perfect_rate": summary.get("risk_perfect_rate"),
            "estimated_api_calls": summary.get("estimated_api_calls"),
        }
        try:
            accepted, diff, comparison = route_accepts(route_run)
            payload["accepted_by_compare"] = accepted
            payload["score_diff"] = diff
            payload["comparison"] = {
                "risk_rate": comparison.get("risk_rate"),
                "type_breakthroughs": comparison.get("type_breakthroughs", []),
            }
        except Exception as exc:
            payload["compare_error"] = str(exc)
    append_jsonl(LOG_PATH, payload)
    return payload


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rounds", type=int, default=100)
    parser.add_argument("--parallel", type=int, default=24, help="同時套用 smoke/dev/holdout 的併緒。")
    parser.add_argument("--smoke-parallel", type=int)
    parser.add_argument("--dev-parallel", type=int)
    parser.add_argument("--holdout-parallel", type=int)
    parser.add_argument("--no-improve-limit", type=int, default=10)
    parser.add_argument("--same-failure-limit", type=int, default=5)
    parser.add_argument("--rotate-after", type=int, default=2, help="同一主要失敗碼連續 N 輪後，下輪暫時避開該碼；0 表示停用。")
    parser.add_argument("--force-direction", default="", help="強制指定 D01-D10 或完整方向名稱。")
    parser.add_argument("--budget-usd", type=float, default=0.0)
    parser.add_argument("--estimated-cost-per-call", type=float, default=0.0)
    parser.add_argument("--route-every", type=int, default=3, help="每 N 輪跑一次 route dev；0 表示停用。")
    parser.add_argument("--sleep-seconds", type=int, default=5)
    parser.add_argument("--round-timeout-seconds", type=int, default=3600)
    parser.add_argument("--route-timeout-seconds", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retry-after-no-improve", type=int, default=3, help="達到 no_improve_limit 後的重試次數；0 表示停用。")
    args = parser.parse_args(argv)
    args.smoke_parallel = args.smoke_parallel or args.parallel
    args.dev_parallel = args.dev_parallel or args.parallel
    args.holdout_parallel = args.holdout_parallel or args.parallel
    return args


def main(argv=None):
    args = parse_args(argv)

    print(f"{C_PURPLE}============================================================{C_RESET}")
    print("  Prompt AutoResearch — 長跑自動演化")
    print(f"  max_rounds={args.max_rounds}, smoke={args.smoke_parallel}, dev={args.dev_parallel}, holdout={args.holdout_parallel}")
    print(f"  no_improve_limit={args.no_improve_limit}, same_failure_limit={args.same_failure_limit}, route_every={args.route_every}")
    print(f"  retry_after_no_improve={args.retry_after_no_improve}")
    if args.budget_usd:
        print(f"  budget_usd={args.budget_usd}, estimated_cost_per_call={args.estimated_cost_per_call}")
    print(f"{C_PURPLE}============================================================{C_RESET}")

    preflight = run_cmd(
        [
            sys.executable,
            "scripts/preflight.py",
            "--smoke-parallel",
            str(args.smoke_parallel),
            "--dev-parallel",
            str(args.dev_parallel),
            "--holdout-parallel",
            str(args.holdout_parallel),
        ],
        timeout=120,
    )
    if preflight.returncode != 0:
        print(f"{C_RED}❌ Preflight 未通過，停止。{C_RESET}")
        return preflight.returncode

    if args.dry_run:
        print(f"{C_GREEN}✅ dry-run 完成：只檢查設定，不執行演化。{C_RESET}")
        return 0

    started = time.time()
    best_score = baseline_dev_score()
    no_improve_count = 0
    same_failure_count = 0
    last_dominant_failure = ""
    avoid_failures_next = []
    estimated_calls_total = 0
    estimated_cost_total = 0.0
    successful_promotions = 0
    retry_count = 0
    retry_mode = False

    append_jsonl(
        LOG_PATH,
        {
            "event": "start",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "args": vars(args),
            "baseline_dev_score": best_score,
        },
    )

    from run_opt import run_opt_pass

    for round_no in range(1, args.max_rounds + 1):
        print(f"\n{C_PURPLE}{'=' * 64}{C_RESET}")
        print(f"  Round {round_no} / {args.max_rounds}")
        print(f"{C_PURPLE}{'=' * 64}{C_RESET}")

        before_runs = list_run_dirs()
        before_baseline = baseline_dev_score()
        round_started = time.time()
        error = ""

        try:
            round_avoid_failures = list(avoid_failures_next)
            avoid_failures_next = []
            if round_avoid_failures:
                print(f"{C_YELLOW}本輪方向避開：{', '.join(round_avoid_failures)}{C_RESET}")
            success = run_opt_pass(
                smoke_parallel=args.smoke_parallel,
                dev_parallel=args.dev_parallel,
                holdout_parallel=args.holdout_parallel,
                force_direction=args.force_direction,
                avoid_failures=round_avoid_failures,
            )
        except Exception as exc:
            success = False
            error = str(exc)
            print(f"{C_RED}❌ round 執行例外：{error}{C_RESET}")

        new_runs = collect_new_runs(before_runs)
        dev_run = latest_dev_run_since(before_runs)
        latest_run = latest_run_since(before_runs)
        dev_summary = run_summary(dev_run) if dev_run else {}
        latest_summary = run_summary(latest_run) if latest_run else {}
        after_baseline = baseline_dev_score()
        promoted = after_baseline > before_baseline
        if promoted:
            successful_promotions += 1
            best_score = after_baseline
            no_improve_count = 0
        else:
            no_improve_count += 1

        round_calls = sum_estimated_calls(new_runs)
        estimated_calls_total += round_calls
        if args.estimated_cost_per_call:
            estimated_cost_total += round_calls * args.estimated_cost_per_call

        failure_code = dominant_failure(dev_summary or latest_summary)
        if failure_code and failure_code == last_dominant_failure:
            same_failure_count += 1
        elif failure_code:
            same_failure_count = 1
            last_dominant_failure = failure_code
        if args.rotate_after and failure_code and same_failure_count >= args.rotate_after:
            avoid_failures_next = [failure_code]

        route_payload = maybe_run_route(args, round_no, before_runs)
        if route_payload:
            route_calls = int((route_payload.get("summary") or {}).get("estimated_api_calls") or 0)
            estimated_calls_total += route_calls
            if args.estimated_cost_per_call:
                estimated_cost_total += route_calls * args.estimated_cost_per_call

        elapsed = time.time() - round_started
        payload = {
            "event": "round_complete",
            "round": round_no,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": bool(success),
            "promoted": promoted,
            "error": error,
            "dev_run": dev_run,
            "latest_run": latest_run,
            "before_baseline_dev": before_baseline,
            "after_baseline_dev": after_baseline,
            "best_score": best_score,
            "no_improve_count": no_improve_count,
            "dominant_failure": failure_code,
            "same_failure_count": same_failure_count,
            "avoid_failures_next": avoid_failures_next,
            "round_estimated_api_calls": round_calls,
            "estimated_api_calls_total": estimated_calls_total,
            "estimated_cost_total": estimated_cost_total,
            "elapsed_seconds": elapsed,
        }
        append_jsonl(LOG_PATH, payload)

        print(f"{C_CYAN}Round {round_no} 完成：promoted={promoted}, best_dev={best_score:.2f}, no_improve={no_improve_count}{C_RESET}")
        if failure_code:
            print(f"{C_CYAN}主要失敗碼：{failure_code}，連續次數 {same_failure_count}{C_RESET}")
        if avoid_failures_next:
            print(f"{C_YELLOW}下輪將暫時避開：{', '.join(avoid_failures_next)}{C_RESET}")
        print(f"{C_CYAN}估計 API calls：本輪 {round_calls}，累計 {estimated_calls_total}{C_RESET}")
        if args.estimated_cost_per_call:
            print(f"{C_CYAN}估計成本：${estimated_cost_total:.4f}{C_RESET}")

        stop_reason = ""
        if args.no_improve_limit and no_improve_count >= args.no_improve_limit:
            if not retry_mode and args.retry_after_no_improve > 0:
                # 進入重試模式
                retry_mode = True
                retry_count = 0
                print(f"{C_YELLOW}🔄 連續 {no_improve_count} 輪未晉升，進入重試模式（最多 {args.retry_after_no_improve} 次）{C_RESET}")
                # 調整變異策略：強制避開當前主要失敗碼
                if failure_code:
                    avoid_failures_next = [failure_code]
                    print(f"{C_YELLOW}重試策略：下輪將避開主要失敗碼 {failure_code}{C_RESET}")
                else:
                    # 若無明確失敗碼，隨機選擇一個方向嘗試
                    args.force_direction = ""
                no_improve_count = 0  # 重置計數以允許重試
                append_jsonl(
                    LOG_PATH,
                    {
                        "event": "retry_mode_entered",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "round": round_no,
                        "reason": f"連續 {no_improve_count} 輪未晉升",
                        "dominant_failure": failure_code,
                        "max_retries": args.retry_after_no_improve,
                    },
                )
            elif retry_mode:
                retry_count += 1
                if retry_count >= args.retry_after_no_improve:
                    stop_reason = f"連續 {no_improve_count} 輪未晉升，重試 {retry_count} 次仍無改善"
                else:
                    # 繼續重試，調整策略
                    print(f"{C_YELLOW}🔄 重試 {retry_count}/{args.retry_after_no_improve} 仍無改善，調整變異方向{C_RESET}")
                    if failure_code:
                        avoid_failures_next = [failure_code]
                    no_improve_count = 0
                    append_jsonl(
                        LOG_PATH,
                        {
                            "event": "retry_adjust",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "round": round_no,
                            "retry_count": retry_count,
                            "dominant_failure": failure_code,
                        },
                    )
            else:
                stop_reason = f"連續 {no_improve_count} 輪未晉升"
        elif args.same_failure_limit and same_failure_count >= args.same_failure_limit:
            stop_reason = f"主要失敗碼 {failure_code} 連續 {same_failure_count} 輪未解"
        elif args.budget_usd and args.estimated_cost_per_call and estimated_cost_total >= args.budget_usd:
            stop_reason = f"估計成本 ${estimated_cost_total:.4f} 已達預算 ${args.budget_usd:.2f}"

        if stop_reason:
            print(f"{C_YELLOW}⏹️ 停止條件觸發：{stop_reason}{C_RESET}")
            
            # 若為重試耗盡，寫入結構化結論與證據
            if retry_mode and retry_count >= args.retry_after_no_improve:
                convergence_report = {
                    "event": "converged_to_baseline",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "round": round_no,
                    "reason": stop_reason,
                    "successful_promotions": successful_promotions,
                    "best_score": best_score,
                    "baseline_dev_score": baseline_dev_score(),
                    "no_improve_count": no_improve_count,
                    "retry_count": retry_count,
                    "dominant_failure": failure_code,
                    "same_failure_count": same_failure_count,
                    "estimated_api_calls_total": estimated_calls_total,
                    "estimated_cost_total": estimated_cost_total,
                    "elapsed_seconds": time.time() - started,
                    "conclusion": "已收斂於 baseline，重試仍無改善",
                    # 環境資訊用於同-seed 比對
                    "environment": {
                        "python": sys.version,
                        "executable": sys.executable,
                        "platform": platform.platform(),
                        "arch": platform.machine(),
                        "hashseed": os.environ.get("PYTHONHASHSEED", "not set"),
                    },
                }
                
                # 收集同-seed 比對證據
                if dev_run:
                    convergence_report["latest_dev_run"] = dev_run
                    convergence_report["latest_dev_summary"] = dev_summary
                if latest_run:
                    convergence_report["latest_run"] = latest_run
                    convergence_report["latest_summary"] = latest_summary
                
                # 寫入結構化結論檔案
                conclusion_path = f"docs/convergence_report_{time.strftime('%Y%m%d_%H%M%S')}.json"
                os.makedirs("docs", exist_ok=True)
                with open(conclusion_path, "w", encoding="utf-8") as f:
                    json.dump(convergence_report, f, ensure_ascii=False, indent=2)
                print(f"{C_CYAN}收斂報告已寫入：{conclusion_path}{C_RESET}")
                
                append_jsonl(LOG_PATH, convergence_report)
            
            append_jsonl(
                LOG_PATH,
                {
                    "event": "stop",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "reason": stop_reason,
                    "round": round_no,
                    "successful_promotions": successful_promotions,
                    "best_score": best_score,
                    "estimated_api_calls_total": estimated_calls_total,
                    "estimated_cost_total": estimated_cost_total,
                    "elapsed_seconds": time.time() - started,
                    "retry_mode": retry_mode,
                    "retry_count": retry_count,
                },
            )
            break

        if args.sleep_seconds:
            time.sleep(args.sleep_seconds)

    print(f"\n{C_PURPLE}============================================================{C_RESET}")
    print("  長跑演化結束")
    print(f"  成功晉升數: {successful_promotions}")
    print(f"  最佳 dev: {best_score:.2f}")
    print(f"  估計 API calls: {estimated_calls_total}")
    if args.estimated_cost_per_call:
        print(f"  估計成本: ${estimated_cost_total:.4f}")
    print(f"  log: {LOG_PATH}")
    print(f"{C_PURPLE}============================================================{C_RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
