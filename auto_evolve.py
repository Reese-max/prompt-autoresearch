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
        sys.exit(preflight.returncode)

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    for gen in range(1, generations + 1):
        gen_start = time.time()
        print(f"\n\n{C_PURPLE}{'='*60}{C_RESET}")
        print(f" 🚀 啟動演化世代 第 {gen} / {generations} 代")
        print(f"{C_PURPLE}{'='*60}{C_RESET}")

        total_attempts += 1

        try:
            success = run_opt_pass(**parallel_config)
            consecutive_errors = 0
            if success:
                successful_evolutions += 1
                print(f"\n{C_GREEN}✨ 第 {gen} 代演化成功！新冠軍誕生。{C_RESET}")
            else:
                print(f"\n{C_YELLOW}⚠️ 第 {gen} 代演化未取得突破，已安全回滾。{C_RESET}")
        except Exception as e:
            consecutive_errors += 1
            print(f"\n{C_RED}❌ 第 {gen} 代演化執行出錯: {str(e)}{C_RESET}")
            record_event("auto_evolve_error", {"generation": gen, "error": str(e), "consecutive": consecutive_errors})
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"{C_RED}連續 {consecutive_errors} 代出錯，停止演化。{C_RESET}")
                break

        gen_elapsed = time.time() - gen_start
        print(f"⏱️ 第 {gen} 代耗時: {gen_elapsed/60:.1f} 分鐘。")

        # 輸出目前冠軍提示詞分數 (從 results.tsv 讀取)
        try:
            meta = load_json("prompts/baseline.meta.json")
            if meta.get("dev_avg") is not None:
                holdout_avg = meta.get('holdout_avg')
                print(f"🏆 當前冠軍基線: dev={meta.get('dev_avg'):.2f}, holdout={holdout_avg:.2f if holdout_avg is not None else 'N/A'}, run={meta.get('dev_run')}")
            else:
                tsv_lines = load_file("results.tsv").strip().split("\n")
                if tsv_lines:
                    latest_record = tsv_lines[-1].split("\t")
                    print(f"🏆 最近紀錄: {latest_record[2]} (題庫: {latest_record[1]})")
        except Exception:
            pass

        # 世代之間短暫休息防 API 限制
        time.sleep(5)

    total_elapsed = time.time() - start_time
    print(f"\n\n{C_PURPLE}=================================================={C_RESET}")
    print(f" 🎉 完整自主演化程序執行完畢！")
    print(f"  - 總規劃世代: {generations} 代")
    print(f"  - 總嘗試次數: {total_attempts} 次")
    print(f"  - 成功晉升數: {successful_evolutions} 次")
    print(f"  - 總運行耗時: {total_elapsed/3600:.2f} 小時 ({total_elapsed/60:.1f} 分鐘)")
    print(f"{C_PURPLE}=================================================={C_RESET}")

if __name__ == "__main__":
    main()
