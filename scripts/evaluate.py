# -*- coding: utf-8 -*-
"""
scripts/evaluate.py — 三層閉環評量引擎 (LLM-as-Judge)
這是一個高度並行化、真實呼叫 MiniMax API 的國考申論題評估腳本。
"""
import os
import sys
import json
import re
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

# 確保專案根目錄在 sys.path 中，讓 lib 模組可被匯入
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from lib.api import call_minimax
from lib.io import sha256_text, load_file, normalize_path
from lib.completion_gate import completion_disposition

# Colors for terminal output
C_GREEN  = "\033[92m"
C_CYAN   = "\033[96m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET  = "\033[0m"

CACHE_DIR  = os.path.join(".cache", "eval")


# ---------------------------------------------------------------------------
# 連續內插計分函式 — 取代 count 門檻型階梯計分
#
# 每個函式皆有明確上下界（lo, hi），並在 breakpoints 之間做線性內插，
# 使 count 每增加一個單位均產生正比例且可觀察的分數增量。
# 保留既有 rubric 權重語義：general=70, type_specific=20, risk=10。
# ---------------------------------------------------------------------------

def _lerp(x, x0, x1, y0, y1):
    """在 (x0,y0)-(x1,y1) 之間做線性內插。"""
    if x1 == x0:
        return y1
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def _count_interpolate(count, breakpoints, lo, hi):
    """
    通用 count→score 連續內插。

    breakpoints: sorted list of (count_threshold, score_value)，至少含 (0, lo) 與 (max_count, hi)。
    count: 觀測到的數量（整數或浮點）。
    lo, hi: 輸出分數的下界與上界。

    回傳 lo ≤ result ≤ hi。
    """
    count = max(0, count)
    # 超過最大 breakpoint → 回傳 hi
    if count >= breakpoints[-1][0]:
        return hi
    # 低於最小 breakpoint → 回傳 lo
    if count <= breakpoints[0][0]:
        return lo
    # 找到 count 落在哪兩個 breakpoint 之間
    for i in range(len(breakpoints) - 1):
        c0, s0 = breakpoints[i]
        c1, s1 = breakpoints[i + 1]
        if c0 <= count < c1:
            return _lerp(count, c0, c1, s0, s1)
    return hi


# ---- 基礎申論維度（滿分 70 分，六個子維度） ----

def score_topic_relevance(count):
    """
    題意命中（滿分 15 分）。
    count: 正確回應的子問 / 關鍵詞數量。
    breakpoints: 0→0, 1→4, 2→8, 3→11, 4→13, 5→15。
    """
    bps = [(0, 0), (1, 4), (2, 8), (3, 11), (4, 13), (5, 15)]
    return _count_interpolate(count, bps, 0, 15)


def score_structure(count):
    """
    架構清楚（滿分 10 分）。
    count: 可辨識的邏輯段落層次數。
    breakpoints: 0→0, 1→2, 2→4, 3→6, 4→8, 5→10。
    """
    bps = [(0, 0), (1, 2), (2, 4), (3, 6), (4, 8), (5, 10)]
    return _count_interpolate(count, bps, 0, 10)


def score_scoring_points_visible(count):
    """
    採分點外露（滿分 15 分）。
    count: 以標題或粗體明確外露的採分點數。
    breakpoints: 0→0, 1→3, 2→6, 3→9, 4→12, 5→15。
    """
    bps = [(0, 0), (1, 3), (2, 6), (3, 9), (4, 12), (5, 15)]
    return _count_interpolate(count, bps, 0, 15)


def score_content_concreteness(count):
    """
    內容具體（滿分 15 分）。
    count: 具體佐證數（法條、學說、案例、統計數據等）。
    breakpoints: 0→0, 1→3, 2→6, 3→9, 4→12, 5→15。
    """
    bps = [(0, 0), (1, 3), (2, 6), (3, 9), (4, 12), (5, 15)]
    return _count_interpolate(count, bps, 0, 15)


def score_exam_tone(count):
    """
    考場語氣（滿分 10 分）。
    count: 符合考場語氣的段落數（反向指標：違規次數越多分越低）。
    breakpoints: 0→0, 1→2, 2→4, 3→6, 4→8, 5→10。
    """
    bps = [(0, 0), (1, 2), (2, 4), (3, 6), (4, 8), (5, 10)]
    return _count_interpolate(count, bps, 0, 10)


def score_conclusion(count):
    """
    結論回扣（滿分 5 分）。
    count: 結論中回扣題目關鍵詞的數量。
    breakpoints: 0→0, 1→2, 2→3, 3→4, 4→5。
    """
    bps = [(0, 0), (1, 2), (2, 3), (3, 4), (4, 5)]
    return _count_interpolate(count, bps, 0, 5)


def score_general(counts):
    """
    基礎申論分（滿分 70 分）。
    counts: dict，keys 為上述六個維度的 count 名稱，values 為整數。
    """
    return (
        score_topic_relevance(counts.get("topic_relevance", 0))
        + score_structure(counts.get("structure", 0))
        + score_scoring_points_visible(counts.get("scoring_points_visible", 0))
        + score_content_concreteness(counts.get("content_concreteness", 0))
        + score_exam_tone(counts.get("exam_tone", 0))
        + score_conclusion(counts.get("conclusion", 0))
    )


# ---- 題型專項維度（滿分 20 分） ----

def score_type_specific(count, max_count=5, max_score=20):
    """
    題型專項分（滿分 20 分）。
    count: 符合特定題型要求的項目數。
    等距內插：0→0, max_count→max_score。
    """
    bps = [(0, 0), (max_count, max_score)]
    return _count_interpolate(count, bps, 0, max_score)


# ---- 風險控制維度（滿分 10 分，扣分制） ----

def score_risk(violation_count, max_score=10):
    """
    風險控制分（滿分 10 分，扣分制）。
    violation_count: 違規項目的數量。
    每個違規按比例扣分，直至 0。
    """
    if violation_count <= 0:
        return max_score
    # 每個違規扣 2.5 分（4 個違規扣完 10 分）
    penalty_per_violation = max_score / 4.0
    return max(0, max_score - violation_count * penalty_per_violation)


# ---- 總分加總 ----

def score_total(general, type_specific, risk):
    """三層分數加總，範圍 0–100。"""
    return general + type_specific + risk


def interpolate_within_tier(raw_score, lo, hi):
    """
    將整數 raw_score 連續內插到 [lo, hi] 區間內。

    取代原本的離散階梯（例如 general 0-6=低分, 7-12=中等, 13-15=滿分），
    改為：score = lo + (hi - lo) * (raw_score - tier_lo) / (tier_hi - tier_lo)
    使每增加 1 分均產生正比例且可觀察的增量。

    raw_score: LLM judge 回傳的整數原始分數
    lo, hi: 該維度的滿分下界與上界（例如 0, 15）
    """
    raw_score = max(lo, min(hi, raw_score))
    return lo + (hi - lo) * (raw_score - lo) / (hi - lo)


def interpolate_general_score(raw_score):
    """基礎申論分連續內插（滿分 70 分）。"""
    return interpolate_within_tier(raw_score, 0, 70)


def interpolate_type_score(raw_score):
    """題型專項分連續內插（滿分 20 分）。"""
    return interpolate_within_tier(raw_score, 0, 20)


def interpolate_risk_score(raw_score):
    """風險控制分連續內插（滿分 10 分）。"""
    return interpolate_within_tier(raw_score, 0, 10)


# ---------------------------------------------------------------------------
# 結束連續內插計分函式
# ---------------------------------------------------------------------------


def cache_path(prompt_hash, question_file, question_id):
    qfile_hash = sha256_text(normalize_path(question_file))[:16]
    return os.path.join(CACHE_DIR, prompt_hash[:16], qfile_hash, f"{question_id}.json")

def load_cached_result(prompt_hash, question_file, question_id):
    path = cache_path(prompt_hash, question_file, question_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["cached"] = True
        return data
    except Exception:
        return None

def save_cached_result(prompt_hash, question_file, question_id, result):
    path = cache_path(prompt_hash, question_file, question_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = dict(result)
    payload.pop("cached", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def parse_judge_json(judge_output):
    json_match = re.search(r"```json\s*(.*?)\s*```", judge_output, re.DOTALL)
    if json_match:
        judge_json_str = json_match.group(1)
    else:
        judge_json_str = judge_output.strip()

    if not judge_json_str.startswith("{"):
        start_idx = judge_json_str.find("{")
        end_idx = judge_json_str.rfind("}")
        if start_idx != -1 and end_idx != -1:
            judge_json_str = judge_json_str[start_idx:end_idx + 1]

    return json.loads(judge_json_str, strict=False)

def evaluate_single_question(question_obj, system_prompt, general_rubric, type_rubric, risk_rubric, failure_taxonomy, prompt_hash, question_file):
    """
    對單一題目進行真實作答與閱卷評分。
    """
    q_id = question_obj["id"]
    q_type = question_obj["type"]
    q_text = question_obj["question"]
    q_key_points = question_obj.get("key_points", [])

    cached = load_cached_result(prompt_hash, question_file, q_id)
    if cached:
        return cached
    
    # 1. 產生答案
    answer_system = system_prompt
    answer_user = f"請回答以下臺灣國家考試申論題：\n\n題目：\n{q_text}\n\n答題指引：\n請作為國考高分考生，直接輸出答案正文。必須結構嚴密、段落清晰，且字數控制在 800-1200 字左右。"
    
    try:
        answer = call_minimax(answer_system, answer_user, temperature=0.3)
    except Exception as e:
        return {
            "id": q_id, "type": q_type, "error": f"Answer Generation Failed: {str(e)}",
            "question": q_text, "prompt_hash": prompt_hash, "question_file": normalize_path(question_file),
            "general_score": 0, "type_specific_score": 0, "risk_score": 0, "total_score": 0, "failures": ["F01"]
        }
        
    # 2. 呼叫 Judge 進行評分
    judge_system = """你是一位極其嚴格、公正、具有多年閱卷經驗的臺灣國家考試（高考/特考三等）申論題閱卷官。
請根據提供的評分規準與答案，為這位考生的答卷進行深度評審與量化打分。

【評分標準說明】
總分 100 分，由三部分組成：
1. 基礎申論分 (滿分 70 分)：評估題意命中、架構清楚、採分點外露、內容具體、考場語氣、結論回扣。
2. 題型專項分 (滿分 20 分)：評估是否符合本題型的特定要求。
3. 風險控制分 (滿分 10 分)：預設 10 分，若出現幻覺編造、反問、前導廢話、散文議論等，依規定扣分。

【缺陷代碼系統 (Failure Taxonomy)】
一旦扣分，必須標記對應的缺陷代碼（F01-F14）：
- F01: 偏題 | F02: 架構錯誤 | F03: 採分點不外露 | F04: 內容抽象 | F05: 比較題無比較基準 | F06: 評析題缺乏正反平衡 | F07: 法理題誤寫成案例 | F08: 案例題缺乏涵攝 | F09: 前言空泛 | F10: 結論無回扣 | F11: 字數失控 | F12: 出現編造風險 | F13: 非考場語氣 | F14: 骨架不利記憶

【輸出格式要求】
為了讓系統自動解析，你必須「只」輸出一個 JSON 代碼塊（以 ```json 開頭，``` 結尾），其中包含以下欄位：
```json
{
  "general_score": 55,
  "general_reason": "說明在 general.md 各維度的得分與扣分原因...",
  "type_specific_score": 15,
  "type_specific_reason": "說明符合 type_specific.md 特定題型要求的得分與扣分原因...",
  "risk_score": 10,
  "risk_reason": "說明符合 risk_rules.md 的扣分詳情（無扣分則寫無）...",
  "total_score": 80,
  "failures": ["F03", "F04"],
  "critique": "針對本次扣分給予具體的修復方向..."
}
```
絕對不要輸出任何 markdown 格式的中文引言、解釋或廢話。只輸出這個 json。
"""

    judge_user = f"""【評分依據文件】
1. 基礎申論評分表 (general.md)：
{general_rubric}

2. 題型專項評分表 (type_specific.md)：
{type_rubric}

3. 風險控制評分表 (risk_rules.md)：
{risk_rubric}

4. 缺陷分類系統 (failure_taxonomy.md)：
{failure_taxonomy}

---

【待評分題目】
題型：{q_type}
題目：{q_text}
評分採分點提示：{", ".join(q_key_points)}

---

【待評分答案】
{answer}
"""

    try:
        judge_output = ""
        last_parse_error = None
        eval_res = None
        for judge_attempt in range(2):
            judge_user_retry = judge_user
            if judge_attempt > 0:
                judge_user_retry += (
                    "\n\n【重試要求】上一輪評分 JSON 解析失敗。"
                    "本輪只能輸出可由 json.loads 直接解析的合法 JSON 物件；"
                    "字串內不得包含未跳脫換行、tab 或控制字元。"
                )
            judge_output = call_minimax(judge_system, judge_user_retry, temperature=0.1)
            try:
                eval_res = parse_judge_json(judge_output)
                break
            except Exception as parse_error:
                last_parse_error = parse_error
        if eval_res is None:
            raise last_parse_error or ValueError("judge json parse failed")
        
        # 補齊欄位以防漏失
        eval_res["id"] = q_id
        eval_res["type"] = q_type
        eval_res["question"] = q_text
        eval_res["answer"] = answer
        eval_res["char_count"] = len(answer)
        eval_res["prompt_hash"] = prompt_hash
        eval_res["question_file"] = normalize_path(question_file)
        
        # 連續內插：將整數原始分數映射到連續區間，保留上下界並消除階梯
        raw_general = int(eval_res.get("general_score", 0))
        raw_type = int(eval_res.get("type_specific_score", 0))
        raw_risk = int(eval_res.get("risk_score", 0))
        eval_res["general_score"] = round(interpolate_general_score(raw_general), 2)
        eval_res["type_specific_score"] = round(interpolate_type_score(raw_type), 2)
        eval_res["risk_score"] = round(interpolate_risk_score(raw_risk), 2)
        eval_res["total_score"] = round(eval_res["general_score"] + eval_res["type_specific_score"] + eval_res["risk_score"], 2)
        
        save_cached_result(prompt_hash, question_file, q_id, eval_res)
        return eval_res
        
    except Exception as e:
        return {
            "id": q_id, "type": q_type, "question": q_text, "answer": answer, "char_count": len(answer),
            "prompt_hash": prompt_hash, "question_file": normalize_path(question_file),
            "error": f"Judging Failed: {str(e)}", "raw_judge_output": locals().get("judge_output", ""),
            "general_score": 0, "type_specific_score": 0, "risk_score": 0, "total_score": 0,
            "failures": ["F01"], "critique": f"評分器解析異常: {str(e)}"
        }

def run_evaluation(prompt_file, question_file, max_workers=6, early_stop_threshold=None):
    """
    運行完整題庫評估。
    early_stop_threshold: 若提供（baseline 平均分），跑完 1/3 題時若平均分低於此值 3 分以上則中止。
    """
    # 載入所有依據檔案
    system_prompt = load_file(prompt_file)
    prompt_hash = sha256_text(system_prompt)
    general_rubric = load_file("rubrics/general.md")
    type_rubric = load_file("rubrics/type_specific.md")
    risk_rubric = load_file("rubrics/risk_rules.md")
    failure_taxonomy = load_file("rubrics/failure_taxonomy.md")

    if not system_prompt:
        print(f"{C_RED}[錯誤] 找不到提示詞檔案: {prompt_file}{C_RESET}")
        sys.exit(1)

    # 載入題庫
    questions = []
    if not os.path.exists(question_file):
        print(f"{C_RED}[錯誤] 找不到題庫檔案: {question_file}{C_RESET}")
        sys.exit(1)

    with open(question_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line.strip()))

    total_q = len(questions)
    print(f"\n{C_PURPLE}開始評估題庫: {question_file} (共 {total_q} 題，並行執行緒: {max_workers}, prompt_hash={prompt_hash[:12]}){C_RESET}")

    results = []
    start_time = time.time()
    early_stop_at = total_q // 3 if early_stop_threshold else total_q  # 1/3 處檢查
    early_stopped = False

    # 使用 ThreadPoolExecutor 進行多執行緒並行呼叫
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_q = {
            executor.submit(
                evaluate_single_question, q, system_prompt, general_rubric, type_rubric, risk_rubric, failure_taxonomy, prompt_hash, question_file
            ): q for q in questions
        }

        completed_count = 0
        for future in as_completed(future_to_q):
            q_obj = future_to_q[future]
            completed_count += 1
            try:
                res = future.result()
                results.append(res)
                # 即時在終端列印進度與單題得分
                err_flag = f" [ERROR: {res['error']}]" if "error" in res else ""
                fails_str = ", ".join(res.get("failures", []))
                cache_flag = " [CACHE]" if res.get("cached") else ""
                print(f" [{completed_count}/{total_q}] 題號: {res['id']} ({res['type']}) -> 總分: {res['total_score']} (基礎: {res['general_score']}, 專項: {res['type_specific_score']}, 風險: {res['risk_score']}) | 缺陷: {fails_str or '無'}{err_flag}{cache_flag}")
            except Exception as e:
                print(f" [{completed_count}/{total_q}] 題號: {q_obj['id']} -> 執行異常: {str(e)}")
                results.append({
                    "id": q_obj["id"], "type": q_obj["type"], "question": q_obj["question"],
                    "general_score": 0, "type_specific_score": 0, "risk_score": 0, "total_score": 0,
                    "failures": ["F01"], "error": str(e)
                })

            # Early termination check (#10)
            if early_stop_threshold and completed_count >= early_stop_at and not early_stopped:
                interim_avg = sum(r.get("total_score", 0) for r in results) / len(results)
                if interim_avg < early_stop_threshold - 3.0:
                    print(f"\n{C_YELLOW}[Early Stop] 前 {completed_count} 題平均分 {interim_avg:.2f} 低於 baseline {early_stop_threshold:.2f} 超過 3 分，中止評估。{C_RESET}")
                    early_stopped = True
                    # Cancel remaining futures
                    for f in future_to_q:
                        f.cancel()
                    break

    elapsed = time.time() - start_time
    print(f"\n{C_GREEN}評估完成！耗時: {elapsed:.2f} 秒 (約 {elapsed/60:.1f} 分鐘)。{C_RESET}")
    
    # 3. 計算統計數據
    summary_stats = calculate_statistics(results, elapsed, prompt_file, question_file, prompt_hash)
    return summary_stats, results

def calculate_statistics(results, elapsed_seconds, prompt_file, question_file, prompt_hash):
    """
    計算評估總結指標。
    """
    total_q = len(results)
    if total_q == 0:
        return {}
        
    total_score = sum(r.get("total_score", 0) for r in results)
    avg_score = total_score / total_q
    
    # 按題型計算平均分
    type_scores = {}
    type_counts = {}
    for r in results:
        t = r["type"]
        type_scores[t] = type_scores.get(t, 0) + r.get("total_score", 0)
        type_counts[t] = type_counts.get(t, 0) + 1
        
    type_averages = {}
    for t in type_scores:
        type_averages[t] = type_scores[t] / type_counts[t]
        
    # 統計缺陷頻率
    failure_counts = {}
    for r in results:
        for f in r.get("failures", []):
            if f:
                failure_counts[f] = failure_counts.get(f, 0) + 1
                
    # 統計字數合格率 (800-1200字)
    in_range_count = sum(1 for r in results if 800 <= r.get("char_count", 0) <= 1200)
    word_count_pass_rate = (in_range_count / total_q) * 100 if total_q > 0 else 0
    
    # 統計風險滿分率 (10分比例)
    risk_perfect_count = sum(1 for r in results if r.get("risk_score", 0) == 10)
    risk_perfect_rate = (risk_perfect_count / total_q) * 100 if total_q > 0 else 0
    cache_hit_count = sum(1 for r in results if r.get("cached"))
    error_count = sum(1 for r in results if r.get("error"))
    estimated_api_calls = (total_q - cache_hit_count) * 2
    
    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prompt_file": prompt_file,
        "question_file": normalize_path(question_file),
        "prompt_hash": prompt_hash,
        "elapsed_seconds": elapsed_seconds,
        "total_questions": total_q,
        "average_score": avg_score,
        "type_averages": type_averages,
        "failure_counts": failure_counts,
        "word_count_pass_rate": word_count_pass_rate,
        "risk_perfect_rate": risk_perfect_rate,
        "char_count": len(load_file(prompt_file)),
        "cache_hit_count": cache_hit_count,
        "error_count": error_count,
        "estimated_api_calls": estimated_api_calls,
    }
    completion = completion_disposition({
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "artifacts": {},
        "results": results,
        "summary": {"average_score": avg_score},
    })
    summary.update({
        "completion_status": completion["status"],
        "reason_code": completion["reason_code"],
        "rejection_reason": completion["rejection_reason"],
        "missing_evidence_types": completion["missing_evidence_types"],
    })
    
    return summary

def save_run_results(summary, results):
    """
    將運行結果持久化儲存到 runs/ 中。
    """
    # 建立以時間戳命名的運行目錄
    timestamp_slug = time.strftime("%Y%m%d_%H%M%S")
    run_dir = f"runs/{timestamp_slug}"
    suffix = 2
    while os.path.exists(run_dir):
        run_dir = f"runs/{timestamp_slug}_{suffix:02d}"
        suffix += 1
    os.makedirs(run_dir, exist_ok=True)
    
    # 寫入 details.jsonl
    details_path = f"{run_dir}/details.jsonl"
    with open(details_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    # 建立 markdown 報告
    summary_md = f"""# Prompt AutoResearch v3 — 測試運行報告
- **評估時間**: {summary["timestamp"]}
- **提示詞檔案**: {summary["prompt_file"]} (字數: {summary["char_count"]})
- **Prompt Hash**: `{summary["prompt_hash"]}`
- **測試題庫**: {summary["question_file"]} (共 {summary["total_questions"]} 題)
- **總平均分數**: {summary["average_score"]:.2f} / 100
- **字數合格率 (800-1200字)**: {summary["word_count_pass_rate"]:.1f}%
- **風險扣分控制率 (得10分滿分比例)**: {summary["risk_perfect_rate"]:.1f}%
- **總測試耗時**: {summary["elapsed_seconds"]:.1f} 秒

---

## 1. 題型分項成績

| 題型 | 測試題數 | 平均分數 |
|------|----------|----------|
"""
    for t, avg in summary["type_averages"].items():
        summary_md += f"| {t} | {summary['total_questions']//6} | {avg:.2f} |\n"
        
    summary_md += """
---

## 2. 缺陷代碼統計 (Failure Taxonomy)

| 缺陷代碼 | 出現次數 | 缺陷定義描述 |
|----------|----------|--------------|
"""
    failure_defs = {
        "F01": "偏題", "F02": "架構錯誤", "F03": "採分點不外露", "F04": "內容抽象",
        "F05": "比較題無比較基準", "F06": "評析題缺乏正反平衡", "F07": "法理題誤寫成案例",
        "F08": "案例題缺乏涵攝", "F09": "前言空泛", "F10": "結論無回扣",
        "F11": "字數失控", "F12": "出現編造風險", "F13": "非考場語氣", "F14": "骨架不利記憶"
    }
    
    # 排序缺陷，次數多的在前面
    sorted_failures = sorted(summary["failure_counts"].items(), key=lambda x: x[1], reverse=True)
    for f_code, count in sorted_failures:
        desc = failure_defs.get(f_code, "未知缺陷")
        summary_md += f"| **{f_code}** | {count} | {desc} |\n"
        
    if not sorted_failures:
        summary_md += "| - | 0 | 無任何缺陷！完美表現。 |\n"
        
    summary_md += """
---

## 3. 單題詳細成績表

| 題號 | 題型 | 總分 | 基礎分 | 專項分 | 風險分 | 主要缺陷代碼 |
|------|------|------|--------|--------|--------|--------------|
"""
    for r in sorted(results, key=lambda x: x["id"]):
        fails_str = ", ".join(r.get("failures", [])) or "無"
        summary_md += f"| {r['id']} | {r['type']} | **{r['total_score']}** | {r.get('general_score', 0)} | {r.get('type_specific_score', 0)} | {r.get('risk_score', 0)} | {fails_str} |\n"
        
    # 寫入 summary.md
    with open(f"{run_dir}/summary.md", "w", encoding="utf-8") as f:
        f.write(summary_md)

    with open(f"{run_dir}/summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    # 同步複製一份至 runs/latest/ 供下一代引擎與前端 app 讀取
    latest_dir = "runs/latest"
    os.makedirs(latest_dir, exist_ok=True)
    shutil.copy(details_path, f"{latest_dir}/details.jsonl")
    shutil.copy(f"{run_dir}/summary.md", f"{latest_dir}/summary.md")
    shutil.copy(f"{run_dir}/summary.json", f"{latest_dir}/summary.json")
    
    # 寫入/追加到結果記錄表 results.tsv (格式：時間 \t 題庫 \t 平均分 \t 提示詞長度)
    tsv_line = f"{summary['timestamp']}\t{summary['question_file']}\t{summary['average_score']:.2f}\t{summary['char_count']}\n"
    with open("results.tsv", "a", encoding="utf-8") as f:
        f.write(tsv_line)
        
    print(f"\n{C_GREEN}[保存] 運行報告已成功儲存至 {run_dir}/ 及 runs/latest/{C_RESET}")
    return run_dir

def main():
    if len(sys.argv) < 3:
        print("用法: python3 scripts/evaluate.py <prompt_file> <question_file> [--parallel <workers>] [--early-stop <baseline_score>]")
        print("範例: python3 scripts/evaluate.py prompts/current.md questions/smoke.jsonl --parallel 6")
        sys.exit(1)

    prompt_file = sys.argv[1]
    question_file = sys.argv[2]

    # 預設 6 個並行 worker，以防 rate limit 超限，但又能快速完成
    workers = 6
    if "--parallel" in sys.argv:
        try:
            idx = sys.argv.index("--parallel")
            workers = int(sys.argv[idx + 1])
        except Exception:
            pass

    early_stop_threshold = None
    if "--early-stop" in sys.argv:
        try:
            idx = sys.argv.index("--early-stop")
            early_stop_threshold = float(sys.argv[idx + 1])
        except Exception:
            pass

    summary, results = run_evaluation(prompt_file, question_file, max_workers=workers, early_stop_threshold=early_stop_threshold)
    save_run_results(summary, results)

    # 輸出簡潔結果給主控制台
    print(f"\n{C_CYAN}====== 評估結果摘要 ======{C_RESET}")
    print(f"  總平均分: {summary['average_score']:.2f}")
    print(f"  字數合格率: {summary['word_count_pass_rate']:.1f}%")
    print(f"  風險控制滿分率: {summary['risk_perfect_rate']:.1f}%")
    print(f"{C_CYAN}=========================={C_RESET}")

if __name__ == "__main__":
    main()
