import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# -*- coding: utf-8 -*-
"""
auto_evolve.py — Prompt AutoResearch v3 多代自主演化引擎
在多個世代中循環執行單次演化優化（run_opt.py），實作自我疊代、定向進化。
用法: python3 auto_evolve.py [世代數，預設 10]
"""
import os
import sys
import time
import subprocess
import json
import platform

from lib.io import load_json
from lib.metrics import record_event

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# Ensure we operate in the project root
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Colors
C_GREEN  = "\033[92m"
C_CYAN   = "\033[96m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET  = "\033[0m"

LOG_PATH = "evolution_log.jsonl"
BASELINE_META_PATH = "prompts/baseline.meta.json"

# no_improve 控制流參數（可被測試覆寫）
NO_IMPROVE_LIMIT = 10
RETRY_AFTER_NO_IMPROVE = 3


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


def baseline_dev_score():
    meta = load_json(BASELINE_META_PATH, {})
    try:
        return float(meta.get("dev_avg") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def scan_candidate_evaluations():
    """評測既有候選：掃描 prompts/candidates/*.scorecard.json 收錄已評測候選證據。

    只收錄已有 smoke/dev 分數的候選，作為「比較並淘汰」階段的既有基礎，
    避免以預設 baseline 或空白資料跳過既有候選的評測。
    """
    results = []
    cand_dir = "prompts/candidates"
    if not os.path.isdir(cand_dir):
        return results
    for name in sorted(os.listdir(cand_dir)):
        if not name.endswith(".scorecard.json"):
            continue
        card = load_json(os.path.join(cand_dir, name))
        if not card:
            continue
        smoke = card.get("smoke") or {}
        dev = card.get("dev") or {}
        score = dev.get("score")
        if score is None:
            score = smoke.get("score")
        if score is None:
            continue
        results.append({
            "candidate_path": card.get("candidate_path") or "",
            "smoke_score": smoke.get("score"),
            "dev_score": dev.get("score"),
            "score": float(score),
            "status": card.get("status", ""),
            "selected": bool(card.get("selected")),
        })
    return results


def run_controlled_closed_loop(parallel_config):
    """受控執行路徑：串接「評測既有候選 → 依結果產生迭代候選 → 比較並淘汰 → 回傳全域最高品質候選」。

    1. 評測既有候選：scan_candidate_evaluations() 收錄既有候選評估證據。
    2. 依結果產生迭代候選：run_opt.run_opt_pass 依歷史結果產生多候選並評估。
    3. 比較並淘汰：run_opt_pass 以 smoke/dev/holdout 比較並淘汰較差候選。
    4. 回傳全域最高品質候選：回傳 (success, best_candidate)。

    multi_candidate 停用或 count<2 時直接 raise，避免單一候選捷徑跳過「比較並淘汰」階段。
    """
    import run_opt

    existing = scan_candidate_evaluations()
    prior_best = max(existing, key=lambda c: c.get("score", 0.0)) if existing else None

    get_fn = getattr(run_opt, "get", None)
    multi_cfg = {}
    if get_fn is not None:
        try:
            multi_cfg = get_fn("multi_candidate") or {}
        except Exception:
            multi_cfg = {}
    use_multi = bool(multi_cfg.get("enabled", True))
    count = int(multi_cfg.get("count") or 0) if multi_cfg else 3
    if not use_multi or count < 2:
        raise ValueError(
            f"[受控閉環] multi_candidate 未啟用或 count<2 (enabled={use_multi}, count={count})，"
            "單一候選捷徑會跳過「比較並淘汰」階段，請修正 config 後再跑。"
        )

    existing_info = (
        f"，最高 {prior_best['score']:.2f} ({prior_best['candidate_path']})"
        if prior_best
        else "（無）"
    )
    print(f"{C_CYAN}[受控閉環] 既有已評測候選 {len(existing)} 個{existing_info}"
          f"，本輪多候選 count={count}，產生迭代候選...{C_RESET}")

    success = run_opt.run_opt_pass(**parallel_config)

    after = scan_candidate_evaluations()
    merged = {c["candidate_path"]: c for c in existing + after if c.get("candidate_path")}
    best_candidate = max(merged.values(), key=lambda c: c.get("score", 0.0)) if merged else None
    if best_candidate:
        print(f"{C_CYAN}[受控閉環] 全域最高品質候選: {best_candidate['candidate_path']} "
              f"(score={best_candidate['score']:.2f}, status={best_candidate['status']}){C_RESET}")
    return success, best_candidate

def parse_args(argv):
    generations = 10
    rest = list(argv)
    if rest:
        try:
            generations = int(rest[0])
            rest = rest[1:]
        except ValueError:
            pass
    return generations, rest

def main():
    generations, parallel_args = parse_args(sys.argv[1:])

    print(f"{C_PURPLE}=================================================={C_RESET}")
    print(f"    Prompt AutoResearch v3 — 多代自主演化引擎")
    print(f"    規劃演化世代數: {generations} 代")
    print(f"{C_PURPLE}=================================================={C_RESET}")

    start_time = time.time()
    successful_evolutions = 0
    total_attempts = 0

    from run_opt import run_opt_pass, load_file, load_json
    from run_opt import parse_parallel_args

    parallel_config = parse_parallel_args(parallel_args)
    preflight_cmd = [
        sys.executable or "python",
        "scripts/preflight.py",
        "--smoke-parallel",
        str(parallel_config["smoke_parallel"]),
        "--dev-parallel",
        str(parallel_config["dev_parallel"]),
        "--holdout-parallel",
        str(parallel_config["holdout_parallel"]),
    ]
    preflight = subprocess.run(preflight_cmd)
    if preflight.returncode != 0:
        print(f"{C_RED}❌ Preflight 未通過，已停止演化。{C_RESET}")
        return preflight.returncode

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    # no_improve 控制流參數
    no_improve_count = 0
    retry_count = 0
    retry_mode = False
    best_score = baseline_dev_score()
    best_candidate = None

    append_jsonl(
        LOG_PATH,
        {
            "event": "start",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "generations": generations,
            "baseline_dev_score": best_score,
        },
    )

    for gen in range(1, generations + 1):
        gen_start = time.time()
        print(f"\n\n{C_PURPLE}{'='*60}{C_RESET}")
        print(f" 🚀 啟動演化世代 第 {gen} / {generations} 代")
        print(f"{C_PURPLE}{'='*60}{C_RESET}")

        total_attempts += 1
        before_baseline = baseline_dev_score()

        success = False
        best_candidate = None
        try:
            success, best_candidate = run_controlled_closed_loop(parallel_config)
            consecutive_errors = 0
            after_baseline = baseline_dev_score()
            promoted = after_baseline > before_baseline

            if promoted:
                successful_evolutions += 1
                best_score = after_baseline
                no_improve_count = 0
                print(f"\n{C_GREEN}✨ 第 {gen} 代演化成功！新冠軍誕生。{C_RESET}")
            else:
                no_improve_count += 1
                print(f"\n{C_YELLOW}⚠️ 第 {gen} 代演化未取得突破，已安全回滾。{C_RESET}")
        except Exception as e:
            consecutive_errors += 1
            print(f"\n{C_RED}❌ 第 {gen} 代演化執行出錯: {str(e)}{C_RESET}")
            record_event("auto_evolve_error", {"generation": gen, "error": str(e), "consecutive": consecutive_errors})
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"{C_RED}連續 {consecutive_errors} 代出錯，停止演化。{C_RESET}")
                append_jsonl(
                    LOG_PATH,
                    {
                        "event": "stop",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "reason": f"連續 {consecutive_errors} 代出錯",
                        "generation": gen,
                        "successful_evolutions": successful_evolutions,
                        "best_score": best_score,
                        "elapsed_seconds": time.time() - start_time,
                    },
                )
                return 1
            # 出錯時也視為未晉升
            no_improve_count += 1
            promoted = False
            after_baseline = before_baseline

        gen_elapsed = time.time() - gen_start
        print(f"⏱️ 第 {gen} 代耗時: {gen_elapsed/60:.1f} 分鐘。")

        # 輸出目前冠軍提示詞分數 (從 results.tsv 讀取)
        try:
            meta = load_json("prompts/baseline.meta.json")
            if meta.get("dev_avg") is not None:
                holdout_avg = meta.get('holdout_avg')
                holdout_display = f"{holdout_avg:.2f}" if holdout_avg is not None else "N/A"
                print(f"🏆 當前冠軍基線: dev={meta.get('dev_avg'):.2f}, holdout={holdout_display}, run={meta.get('dev_run')}")
            else:
                tsv_lines = load_file("results.tsv").strip().split("\n")
                if tsv_lines:
                    latest_record = tsv_lines[-1].split("\t")
                    print(f"🏆 最近紀錄: {latest_record[2]} (題庫: {latest_record[1]})")
        except Exception:
            pass

        # 記錄世代完成事件
        append_jsonl(
            LOG_PATH,
            {
                "event": "generation_complete",
                "generation": gen,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "success": bool(success),
                "promoted": promoted,
                "before_baseline_dev": before_baseline,
                "after_baseline_dev": after_baseline,
                "best_score": best_score,
                "no_improve_count": no_improve_count,
                "best_candidate": best_candidate,
                "elapsed_seconds": gen_elapsed,
            },
        )

        # no_improve 控制流檢查
        stop_reason = ""
        if no_improve_count >= NO_IMPROVE_LIMIT:
            if not retry_mode and RETRY_AFTER_NO_IMPROVE > 0:
                # 進入重試模式
                retry_mode = True
                retry_count = 0
                print(f"{C_YELLOW}🔄 連續 {no_improve_count} 代未晉升，進入重試模式（最多 {RETRY_AFTER_NO_IMPROVE} 次）{C_RESET}")
                no_improve_count = 0  # 重置計數以允許重試
                append_jsonl(
                    LOG_PATH,
                    {
                        "event": "retry_mode_entered",
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "generation": gen,
                        "reason": f"連續 {no_improve_count} 代未晉升",
                        "max_retries": RETRY_AFTER_NO_IMPROVE,
                    },
                )
            elif retry_mode:
                retry_count += 1
                if retry_count >= RETRY_AFTER_NO_IMPROVE:
                    stop_reason = f"連續 {no_improve_count} 代未晉升，重試 {retry_count} 次仍無改善"
                else:
                    # 繼續重試
                    print(f"{C_YELLOW}🔄 重試 {retry_count}/{RETRY_AFTER_NO_IMPROVE} 仍無改善，調整變異方向{C_RESET}")
                    no_improve_count = 0
                    append_jsonl(
                        LOG_PATH,
                        {
                            "event": "retry_adjust",
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "generation": gen,
                            "retry_count": retry_count,
                        },
                    )
            else:
                stop_reason = f"連續 {no_improve_count} 代未晉升"

        if stop_reason:
            print(f"{C_YELLOW}⏹️ 停止條件觸發：{stop_reason}{C_RESET}")

            # 若為重試耗盡，寫入結構化結論與證據
            if retry_mode and retry_count >= RETRY_AFTER_NO_IMPROVE:
                convergence_report = {
                    "event": "converged_to_baseline",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "generation": gen,
                    "reason": stop_reason,
                    "successful_evolutions": successful_evolutions,
                    "best_score": best_score,
                    "baseline_dev_score": baseline_dev_score(),
                    "no_improve_count": no_improve_count,
                    "retry_count": retry_count,
                    "best_candidate": best_candidate,
                    "elapsed_seconds": time.time() - start_time,
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
                    "generation": gen,
                    "successful_evolutions": successful_evolutions,
                    "best_score": best_score,
                    "best_candidate": best_candidate,
                    "elapsed_seconds": time.time() - start_time,
                    "retry_mode": retry_mode,
                    "retry_count": retry_count,
                },
            )
            return 0

        # 世代之間短暫休息防 API 限制
        time.sleep(5)

    total_elapsed = time.time() - start_time
    print(f"\n\n{C_PURPLE}=================================================={C_RESET}")
    print(f" 🎉 完整自主演化程序執行完畢！")
    print(f"  - 總規劃世代: {generations} 代")
    print(f"  - 總嘗試次數: {total_attempts} 次")
    print(f"  - 成功晉升數: {successful_evolutions} 次")
    if best_candidate:
        print(f"  - 全域最高品質候選: {best_candidate['candidate_path']} "
              f"(score={best_candidate['score']:.2f}, status={best_candidate['status']})")
    print(f"  - 總運行耗時: {total_elapsed/3600:.2f} 小時 ({total_elapsed/60:.1f} 分鐘)")
    print(f"{C_PURPLE}=================================================={C_RESET}")
    
    return 0

if __name__ == "__main__":
    main()
