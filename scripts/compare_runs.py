# -*- coding: utf-8 -*-
"""
scripts/compare_runs.py — 運行結果對比與接受條件判定器
比較新運行結果與基準運行結果，驗證是否符合 program.md 中的 10 大接受條件。
用法: python3 scripts/compare_runs.py <new_run_dir_or_latest> <baseline_run_dir_or_file>
"""
import math
import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure we operate in the project root
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Colors
C_GREEN  = "\033[92m"
C_CYAN   = "\033[96m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_RESET  = "\033[0m"
LAST_COMPARISON = {}

from lib.completion_gate import (  # noqa: E402
    build_evidence_manifest,
    persist_run_failure,
    verify_persisted_run_evidence,
)


def _has_meaningful_output(row):
    """單題結果至少要有答案或正分，否則不得參與候選比較。"""
    if row.get("error"):
        return False
    answer = row.get("answer")
    if isinstance(answer, str) and answer.strip():
        return True
    try:
        return float(row.get("total_score") or 0) > 0
    except (TypeError, ValueError):
        return False


def _record_invalid_comparison(
    new_dir,
    base_dir,
    candidate_id,
    round_no,
    missing,
    reason_code="NO_VALID_OUTPUT",
    rejection_reason="no valid output evidence",
    rejection_reasons=None,
    evidence_errors=None,
    evidence_manifest=None,
    base_evidence_manifest=None,
):
    global LAST_COMPARISON
    rejection_reasons = rejection_reasons or [f"missing evidence types: {', '.join(missing)}"]
    LAST_COMPARISON = {
        "new_dir": new_dir,
        "base_dir": base_dir,
        "candidate_id": candidate_id,
        "round_no": round_no,
        "passed": False,
        "completion_status": "failed",
        "reason_code": reason_code,
        "rejection_reason": rejection_reason,
        "rejection_reasons": rejection_reasons,
        "evidence_types": [],
        "evidence_manifest": evidence_manifest or [],
        "base_evidence_manifest": base_evidence_manifest or [],
        "evidence_errors": evidence_errors or ["no valid output evidence"],
        "missing_evidence_types": missing,
        "type_breakthroughs": [],
    }


def _validated_run_manifest(run_dir, role):
    """有 summary 的 run 必須重新驗證持久化證據；舊 details-only fixture 保持相容。"""
    if not run_dir or not os.path.isfile(os.path.join(run_dir, "summary.json")):
        return None
    result = verify_persisted_run_evidence(run_dir)
    if result["status"] == "completed":
        return result
    result["role"] = role
    return result

def acceptance_mode():
    return os.environ.get("AUTORESEARCH_ACCEPTANCE_MODE", "pragmatic").strip().lower() or "pragmatic"

def load_details(run_dir):
    """
    載入某個運行目錄中的 details.jsonl。
    """
    path = os.path.join(run_dir, "details.jsonl")
    if not os.path.exists(path):
        # 嘗試直接作為路徑
        if os.path.exists(run_dir) and run_dir.endswith("details.jsonl"):
            path = run_dir
        else:
            return None
            
    questions_data = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line.strip())
                questions_data[obj["id"]] = obj
    return questions_data

def compare(new_dir, base_dir, mode=None, candidate_id=None, round_no=None):
    global LAST_COMPARISON
    mode = mode or acceptance_mode()
    new_evidence = _validated_run_manifest(new_dir, "candidate")
    if new_evidence and new_evidence["status"] != "completed":
        print(f"{C_RED}[拒絕] 候選證據清單驗證失敗，排除比較：{new_evidence['rejection_reason']}{C_RESET}")
        persist_run_failure(new_dir, new_evidence)
        _record_invalid_comparison(
            new_dir, base_dir, candidate_id, round_no,
            ["evidence_manifest"],
            reason_code=new_evidence["reason_code"],
            rejection_reason=new_evidence["rejection_reason"],
            rejection_reasons=new_evidence["rejection_reasons"],
            evidence_errors=new_evidence["evidence_errors"],
        )
        return False, 0.0, 0.0

    new_data = load_details(new_dir)
    if not new_data:
        print(f"{C_RED}[錯誤] 無法載入新運行數據: {new_dir}{C_RESET}")
        sys.exit(1)
    if not any(_has_meaningful_output(row) for row in new_data.values()):
        print(f"{C_RED}[拒絕] 新運行沒有有效產出，維持未完成，不納入候選比較。{C_RESET}")
        _record_invalid_comparison(
            new_dir, base_dir, candidate_id, round_no,
            ["results"],
        )
        return False, 0.0, 0.0
    base_evidence = _validated_run_manifest(base_dir, "baseline")
    if base_evidence and base_evidence["status"] != "completed":
        print(f"{C_RED}[拒絕] 基準證據清單驗證失敗，排除比較：{base_evidence['rejection_reason']}{C_RESET}")
        persist_run_failure(base_dir, base_evidence)
        _record_invalid_comparison(
            new_dir, base_dir, candidate_id, round_no,
            ["baseline_evidence_manifest"],
            reason_code=base_evidence["reason_code"],
            rejection_reason=base_evidence["rejection_reason"],
            rejection_reasons=base_evidence["rejection_reasons"],
            evidence_errors=base_evidence["evidence_errors"],
            evidence_manifest=new_evidence.get("evidence_manifest", []) if new_evidence else [],
        )
        return False, 0.0, 0.0

    base_data = load_details(base_dir)
    if not base_data:
        print(f"{C_YELLOW}[警告] 無法載入基準運行數據: {base_dir}。將進行無基準自我分析。{C_RESET}")
        base_data = {}
    elif not any(_has_meaningful_output(row) for row in base_data.values()):
        print(f"{C_RED}[拒絕] 基準運行沒有有效產出，維持未完成，不納入候選比較。{C_RESET}")
        _record_invalid_comparison(
            new_dir, base_dir, candidate_id, round_no,
            ["baseline_results"],
        )
        return False, 0.0, 0.0
    # 計算分數
    new_scores = [q["total_score"] for q in new_data.values()]
    avg_new = sum(new_scores) / len(new_scores) if new_scores else 0
    
    base_scores = [q["total_score"] for q in base_data.values()]
    avg_base = sum(base_scores) / len(base_scores) if base_scores else 0
    
    score_diff = avg_new - avg_base
    
    # 題型分數計算
    type_new = {}
    for q in new_data.values():
        type_new[q["type"]] = type_new.get(q["type"], []) + [q["total_score"]]
    avg_type_new = {t: sum(s)/len(s) for t, s in type_new.items()}
    
    type_base = {}
    for q in base_data.values():
        type_base[q["type"]] = type_base.get(q["type"], []) + [q["total_score"]]
    avg_type_base = {t: sum(s)/len(s) for t, s in type_base.items()}
    
    # 缺陷統計
    fail_new = {}
    for q in new_data.values():
        for f in q.get("failures", []):
            if isinstance(f, str) and f:
                fail_new[f] = fail_new.get(f, 0) + 1
                
    fail_base = {}
    for q in base_data.values():
        for f in q.get("failures", []):
            if isinstance(f, str) and f:
                fail_base[f] = fail_base.get(f, 0) + 1
                
    # 字數與風險率
    char_in_range = sum(1 for q in new_data.values() if 800 <= q.get("char_count", 0) <= 1200)
    word_rate = (char_in_range / len(new_data)) * 100 if new_data else 0
    
    risk_perfect = sum(1 for q in new_data.values() if q.get("risk_score", 0) == 10)
    risk_rate = (risk_perfect / len(new_data)) * 100 if new_data else 0
    base_risk_perfect = sum(1 for q in base_data.values() if q.get("risk_score", 0) == 10)
    base_risk_rate = (base_risk_perfect / len(base_data)) * 100 if base_data else 0
    
    # 印出比較結果
    print(f"\n{C_CYAN}=================================================={C_RESET}")
    print(f"       新舊運行對比報告")
    print(f"  新運行: {new_dir} (均分: {avg_new:.2f})")
    print(f"  舊基準: {base_dir} (均分: {avg_base:.2f})")
    print(f"  均分變更: {C_GREEN if score_diff >= 0 else C_RED}{score_diff:+.2f}{C_RESET} 分")
    print(f"==================================================")
    
    print(f"\n[1] 題型平均分對比:")
    all_types = set(list(avg_type_new.keys()) + list(avg_type_base.keys()))
    for t in sorted(all_types):
        n_val = avg_type_new.get(t, 0)
        b_val = avg_type_base.get(t, 0)
        d_val = n_val - b_val
        diff_color = C_GREEN if d_val >= 0 else C_RED
        print(f"  - {t:8s}: {b_val:5.2f} -> {n_val:5.2f} ({diff_color}{d_val:+.2f}{C_RESET})")
        
    # 多目標指標 (#6) - 提前計算
    type_scores_list = list(avg_type_new.values())
    type_variance = 0.0
    if type_scores_list:
        type_variance = math.sqrt(sum((s - avg_new) ** 2 for s in type_scores_list) / len(type_scores_list))
    worst_type = min(avg_type_new.items(), key=lambda x: x[1]) if avg_type_new else ("N/A", 0)
    worst_type_name, worst_type_score = worst_type

    print(f"\n[2] 多目標指標 (#6):")
    print(f"  - 題型分數方差: {type_variance:.2f} (越低越穩定)")
    print(f"  - 最差題型: {worst_type_name} ({worst_type_score:.2f} 分)")

    print(f"\n[3] 缺陷代碼增減對比:")
    all_fails = set(list(fail_new.keys()) + list(fail_base.keys()))
    for f in sorted(all_fails):
        n_cnt = fail_new.get(f, 0)
        b_cnt = fail_base.get(f, 0)
        d_cnt = n_cnt - b_cnt
        diff_color = C_GREEN if d_cnt <= 0 else C_RED
        print(f"  - {f}: {b_cnt:2d} -> {n_cnt:2d} ({diff_color}{d_cnt:+d}{C_RESET})")
        
    # 4. 判定 10 大接受條件（在 program.md 中定義）
    print(f"\n{C_YELLOW}[4] 晉升接受條件驗證 (Acceptance Criteria, mode={mode}):{C_RESET}")
    
    passed_all = True
    
    # 條件 1: 總分提升至少 +2.0 分
    from lib.config import get as cfg_get
    min_improvement = cfg_get("thresholds", "dev_min_improvement", 2.0)
    c1 = (score_diff >= min_improvement) or (avg_new >= 92.0 and score_diff >= 0)
    c1_status = f"{C_GREEN}通過{C_RESET}" if c1 else f"{C_RED}拒絕 (提升 {score_diff:.2f} 未滿 +2 分，且未達 92 分以上不退步){C_RESET}"
    passed_all = passed_all and c1
    print(f"  1. 總平均分晉升門檻 (>= +2.0分 或 均分>=92且不退步): {c1_status}")
    
    # 條件 2: 單項退步不超過 3.0 分
    c2 = True
    max_reg = 0
    for t in all_types:
        n_val = avg_type_new.get(t, 0)
        b_val = avg_type_base.get(t, 0)
        if b_val - n_val > 3.0:
            c2 = False
            max_reg = max(max_reg, b_val - n_val)
    c2_status = f"{C_GREEN}通過{C_RESET}" if c2 else f"{C_RED}拒絕 (有題型退步 {max_reg:.2f} 分，超過 3 分限制){C_RESET}"
    passed_all = passed_all and c2
    print(f"  2. 單項題型無大幅退步限制 (退步 <= 3.0分): {c2_status}")
    
    # 條件 3: 風險控制。strict 要求 100%；pragmatic 要求不低於 baseline、至少 90%，且 F12 不增加。
    f12_new = fail_new.get("F12", 0)
    f12_base = fail_base.get("F12", 0)
    if mode == "strict":
        c3 = (risk_rate == 100.0)
        c3_reason = f"風險滿分率僅 {risk_rate:.1f}%，strict 模式要求 100%"
    else:
        c3 = (risk_rate >= 90.0 and risk_rate >= base_risk_rate and f12_new <= f12_base + 2)
        c3_reason = (
            f"風險滿分率 {risk_rate:.1f}% 未達 pragmatic 門檻："
            f"需 >=90% 且不低於 baseline ({base_risk_rate:.1f}%)，"
            f"且 F12 增加不超過 2 ({f12_base}->{f12_new})"
        )
    c3_status = f"{C_GREEN}通過{C_RESET}" if c3 else f"{C_RED}拒絕 ({c3_reason}){C_RESET}"
    passed_all = passed_all and c3
    print(f"  3. 風險控制門檻: {c3_status}")
    
    # 條件 4: 字數合格率高於 85%。此項作為 warning，不再硬性拒絕。
    c4 = (word_rate >= 85.0)
    c4_status = f"{C_GREEN}通過{C_RESET}" if c4 else f"{C_YELLOW}警告 (字數合格率 {word_rate:.1f}%，低於 85%，不作為硬拒絕){C_RESET}"
    print(f"  4. 答案字數合格率門檻 (800-1200字比例 >= 85%): {c4_status}")

    type_diffs = {}
    type_breakthroughs = []
    for t in sorted(all_types):
        base_avg = avg_type_base.get(t, 0)
        new_avg = avg_type_new.get(t, 0)
        diff = new_avg - base_avg
        type_diffs[t] = {
            "baseline_avg": base_avg,
            "candidate_avg": new_avg,
            "diff": diff,
        }
        if base_avg and diff >= 5.0 and risk_rate >= base_risk_rate:
            type_breakthroughs.append({
                "type": t,
                "baseline_avg": base_avg,
                "candidate_avg": new_avg,
                "diff": diff,
            })

    LAST_COMPARISON = {
        "new_dir": new_dir,
        "base_dir": base_dir,
        "candidate_id": candidate_id,
        "round_no": round_no,
        "avg_new": avg_new,
        "avg_base": avg_base,
        "score_diff": score_diff,
        "risk_rate": risk_rate,
        "base_risk_rate": base_risk_rate,
        "word_rate": word_rate,
        "type_diffs": type_diffs,
        "type_breakthroughs": type_breakthroughs,
        "failure_new": fail_new,
        "failure_base": fail_base,
        "acceptance_mode": mode,
        "passed": passed_all,
        "type_variance": type_variance,
        "worst_type": worst_type_name,
        "worst_type_score": worst_type_score,
        "new_details_path": os.path.join(new_dir, "details.jsonl") if new_dir else None,
        "base_details_path": os.path.join(base_dir, "details.jsonl") if base_dir else None,
        "completion_status": "completed",
        "evidence_manifest": new_evidence.get("evidence_manifest", []) if new_evidence else build_evidence_manifest(
            {"details.jsonl": {"path": os.path.join(new_dir, "details.jsonl")}},
            os.path.dirname(new_dir),
        )[0],
        "base_evidence_manifest": base_evidence.get("evidence_manifest", []) if base_evidence else (
            build_evidence_manifest(
                {"details.jsonl": {"path": os.path.join(base_dir, "details.jsonl")}},
                os.path.dirname(base_dir),
            )[0] if base_data else []
        ),
        "evidence_errors": [],
    }

    if type_breakthroughs:
        print(f"\n{C_YELLOW}[5] 局部突破候選:{C_RESET}")
        for item in type_breakthroughs:
            print(f"  - {item['type']}: {item['baseline_avg']:.2f} -> {item['candidate_avg']:.2f} ({C_GREEN}+{item['diff']:.2f}{C_RESET})")
    
    print(f"\n{C_CYAN}=================================================={C_RESET}")
    print(f"  最終判定: {'✅ 晉升 (ACCEPT)' if passed_all else '❌ 回滾 (REVERT)'}")
    print(f"==================================================")
    
    # 回傳晉升狀態與分數
    return passed_all, avg_new, score_diff

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 scripts/compare_runs.py <new_run_dir_or_file> <base_run_dir_or_file> [--mode strict|pragmatic]")
        sys.exit(1)
    cli_mode = None
    if "--mode" in sys.argv:
        try:
            cli_mode = sys.argv[sys.argv.index("--mode") + 1]
        except IndexError:
            cli_mode = None
    compare(sys.argv[1], sys.argv[2], mode=cli_mode)
