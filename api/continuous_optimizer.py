# -*- coding: utf-8 -*-
"""
api/continuous_optimizer.py — 持續優化迴圈

整合 Voice Actress (Shenlun) 的回的回饋資料，驅動提示詞持續優化。

流程：
1. 定期讀取 feedback.jsonl
2. 分析弱點區域
3. 生成優化建議
4. 觸發演化優化
"""
import json
import os
import sys
import time
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.io import load_json, read_jsonl, append_jsonl
from lib.config import get
from lib.completion_gate import completion_disposition, verify_completion_evidence
from api.feedback import get_feedback_summary, get_weak_areas, generate_optimization_hints

# --- 常數 ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIMIZATION_LOG = os.path.join(PROJECT_ROOT, "optimization_log.jsonl")
PYTHON_BIN = sys.executable or "python"


def check_feedback_threshold(min_feedback=10):
    """檢查是否有足夠的回饋資料。"""
    feedback_path = os.path.join(PROJECT_ROOT, "feedback.jsonl")
    if not os.path.exists(feedback_path):
        return False, 0

    feedback = read_jsonl(feedback_path)
    return len(feedback) >= min_feedback, len(feedback)


def analyze_and_suggest():
    """分析回饋資料並生成優化建議。"""
    summary = get_feedback_summary()
    hints = generate_optimization_hints()

    result = {
        "timestamp": datetime.now().isoformat(),
        "total_feedback": summary.get("total_feedback", 0),
        "baseline_score": summary.get("baseline_score"),
        "hints": hints,
        "weak_areas": summary.get("weak_areas", {}),
    }

    # 記錄分析結果
    append_jsonl(OPTIMIZATION_LOG, {
        "event": "analysis",
        **result,
    })

    return result


def run_optimization_round(direction=None, parallel=6):
    """執行一輪優化。

    回傳 True 僅當子程序 exit_code=0 且完成資格閘門驗證通過
    （存在非空、可存取且可驗證的任務產出證據）。
    """
    cmd = [PYTHON_BIN, "run_opt.py"]
    if direction:
        cmd.extend(["--force-direction", direction])
    cmd.extend([
        "--smoke-parallel", str(parallel),
        "--dev-parallel", str(parallel),
        "--holdout-parallel", str(parallel),
    ])

    print(f"[ContinuousOptimizer] 執行優化: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 小時逾時
        )

        stdout_text = result.stdout[-1000:] if result.stdout else ""
        stderr_text = result.stderr[-500:] if result.stderr else ""

        # 完成資格閘門：exit_code=0 不足以判定成功，
        # 還必須有非空且可驗證的產出證據
        gate_result, gate_reasons = verify_completion_evidence({
            "exit_code": result.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "artifacts": {},
            "results": [],
            "summary": {},
        })
        disposition = completion_disposition({
            "exit_code": result.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "artifacts": {},
            "results": [],
            "summary": {},
        })
        success = result.returncode == 0 and gate_result

        append_jsonl(OPTIMIZATION_LOG, {
            "event": "optimization",
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "direction": direction,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "returncode": result.returncode,
            "gate_passed": gate_result,
            "gate_reasons": gate_reasons,
            "completion_status": disposition["status"],
            "reason_code": disposition["reason_code"],
            "rejection_reason": disposition["rejection_reason"],
            "missing_evidence_types": disposition["missing_evidence_types"],
        })

        return success
    except Exception as e:
        append_jsonl(OPTIMIZATION_LOG, {
            "event": "optimization_error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
        })
        return False


def run_continuous_loop(max_rounds=10, min_feedback=10, parallel=6):
    """持續優化迴圈。"""
    print(f"{'='*60}")
    print(f"  持續優化迴圈")
    print(f"  最大輪數: {max_rounds}")
    print(f"  最少回饋數: {min_feedback}")
    print(f"  併緒數: {parallel}")
    print(f"{'='*60}")

    for round_num in range(1, max_rounds + 1):
        print(f"\n--- 第 {round_num} 輪 ---")

        # 檢查回饋數量
        has_enough, count = check_feedback_threshold(min_feedback)
        if not has_enough:
            print(f"回饋數量不足 ({count}/{min_feedback})，等待中...")
            time.sleep(60)
            continue

        # 分析回饋
        analysis = analyze_and_suggest()
        print(f"回饋數量: {analysis['total_feedback']}")
        print(f"優化建議: {len(analysis['hints'])}")

        if not analysis['hints']:
            print("無優化建議，跳過本輪")
            continue

        # 取第一個建議作為優化方向
        hint = analysis['hints'][0]
        direction = hint.get('target', '')
        print(f"優化方向: {direction} ({hint.get('hint', '')})")

        # 執行優化
        success = run_optimization_round(direction, parallel)
        if success:
            print("優化成功！")
        else:
            print("優化失敗或未通過接受條件")

        # 短暫休息
        time.sleep(5)

    print(f"\n{'='*60}")
    print(f"  持續優化迴圈結束")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="持續優化迴圈")
    parser.add_argument("--max-rounds", type=int, default=10, help="最大輪數")
    parser.add_argument("--min-feedback", type=int, default=10, help="最少回饋數")
    parser.add_argument("--parallel", type=int, default=6, help="併緒數")
    parser.add_argument("--analyze-only", action="store_true", help="僅分析，不執行優化")

    args = parser.parse_args()

    if args.analyze_only:
        analysis = analyze_and_suggest()
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
    else:
        run_continuous_loop(args.max_rounds, args.min_feedback, args.parallel)
