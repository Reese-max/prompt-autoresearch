# -*- coding: utf-8 -*-
"""
scripts/gatekeeper.py — 硬性規則防呆檢查器
檢查 prompt 是否違反硬性規則，不過就淘汰，不進入正式測試。
用法：python3 scripts/gatekeeper.py prompts/current.md
"""
import os
import sys
import re
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure we operate in the project root
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


# 語意等價詞表，用於第二層語意驗證 (#15)
SEMANTIC_EQUIVALENTS = {
    "R05_NO_EXPERT_ROLE": [
        ["專家", "閱卷委員", "評分委員", "寫作名師", "考官", "老師", "命題老師", "國考顧問", "考試專家"],
    ],
    "R03_NO_ANTI_QUESTION": [
        ["不得反問", "禁止反問", "不要反問", "不得提問", "不得摻雜.*提問", "禁止.*提問", "不得詢問", "禁止詢問"],
    ],
    "R04_NO_ANTI_FABRICATION": [
        ["不得編造", "嚴禁編造", "嚴禁捏造", "不要編造", "禁止編造", "杜絕捏造", "嚴禁憑空捏造", "不得.*捏造", "不可編造", "不可捏造"],
    ],
}


def _semantic_check(rule, prompt_text):
    """第二層語意驗證：檢查 prompt 是否包含語意等價詞。"""
    equivalents = SEMANTIC_EQUIVALENTS.get(rule)
    if not equivalents:
        return False  # 無等價詞表，無法語意驗證
    for group in equivalents:
        if any(re.search(keyword, prompt_text) for keyword in group):
            return True
    return False


def run_gatekeeper(prompt_text):
    """
    對提示詞進行硬性規則檢查。
    回傳 (passed: bool, violations: list[dict])
    每個 violation: {"rule": str, "severity": "warning"|"reject", "detail": str}
    """
    violations = []
    p_len = len(prompt_text)

    # --- Rule 1: 字數限制 ---
    if p_len > 700:
        violations.append({
            "rule": "R01_LENGTH_REJECT",
            "severity": "reject",
            "detail": f"提示詞字數 {p_len} 超過 700 字硬性上限。"
        })
    elif p_len > 550:
        violations.append({
            "rule": "R01_LENGTH_WARNING",
            "severity": "warning",
            "detail": f"提示詞字數 {p_len} 超過 550 字警告線。建議精簡。"
        })

    if p_len < 100:
        violations.append({
            "rule": "R01_LENGTH_TOO_SHORT",
            "severity": "reject",
            "detail": f"提示詞字數 {p_len} 低於 100 字，內容不足。"
        })

    # --- Rule 2: 要求輸出審題過程但未禁止 ---
    if re.search(r"(先分析題型|先判斷題目類型|先進行審題)", prompt_text):
        if not re.search(r"(不要輸出審題|不得輸出審題|不輸出分析過程|嚴禁輸出.*審題)", prompt_text):
            violations.append({
                "rule": "R02_ANALYSIS_LEAK",
                "severity": "reject",
                "detail": "包含「先分析題型」但未設定「不要輸出審題過程」，會導致答案前面出現廢話。"
            })

    # --- Rule 3: 反問防範 ---
    if not re.search(r"(不得反問|禁止反問|不要反問|不得提問|不得摻雜.*提問|禁止.*提問)", prompt_text):
        violations.append({
            "rule": "R03_NO_ANTI_QUESTION",
            "severity": "warning",
            "detail": "未設定反問禁止語句，模型可能在答案中反問使用者。"
        })

    # --- Rule 4: 編造防範 ---
    if not re.search(r"(不得編造|嚴禁編造|嚴禁捏造|不要編造|禁止編造|杜絕捏造|嚴禁憑空捏造|不得.*捏造)", prompt_text):
        violations.append({
            "rule": "R04_NO_ANTI_FABRICATION",
            "severity": "reject",
            "detail": "未設定法條/判決/年份/統計的防編造宣告。"
        })

    # --- Rule 5: 專家角色宣告 ---
    if not re.search(r"(專家|閱卷委員|寫作名師|考官|老師|評分委員)", prompt_text):
        violations.append({
            "rule": "R05_NO_EXPERT_ROLE",
            "severity": "reject",
            "detail": "缺乏國考專家角色設定宣告。"
        })

    # --- Rule 6: 比較基準要求 ---
    if not re.search(r"(比較基準|比較.*基準|橫向對比|對比.*基準|比對)", prompt_text):
        violations.append({
            "rule": "R06_NO_COMPARE_CRITERIA",
            "severity": "warning",
            "detail": "未提及比較題需建立比較基準。"
        })

    # --- Rule 7: 法律題分流 ---
    if not re.search(r"(法理|法律.*案例|三段論|涵攝|大前提)", prompt_text):
        violations.append({
            "rule": "R07_NO_LEGAL_DIFFERENTIATION",
            "severity": "warning",
            "detail": "未區分法律法理題與法律案例題的作答策略。"
        })

    # --- Rule 8: 直接輸出要求 ---
    if not re.search(r"(直接輸出|直接.*正文|不得摻雜.*說明|不得.*輸出.*前言)", prompt_text):
        violations.append({
            "rule": "R08_NO_DIRECT_OUTPUT",
            "severity": "warning",
            "detail": "未要求模型直接輸出答案正文（可能會輸出前導廢話）。"
        })

    # --- 第二層語意驗證 (#15)：對 reject 級違規做語意等價詞檢查 ---
    filtered_violations = []
    for v in violations:
        if v["severity"] == "reject" and _semantic_check(v["rule"], prompt_text):
            # 語意等價詞命中，降級為 warning
            v["detail"] += "（語意驗證通過：包含等價表達）"
            v["severity"] = "warning"
        filtered_violations.append(v)

    # --- 判定 ---
    has_reject = any(v["severity"] == "reject" for v in filtered_violations)
    passed = not has_reject

    return passed, filtered_violations


def main():
    if len(sys.argv) < 2:
        print("用法: python3 scripts/gatekeeper.py <prompt_file>")
        print("範例: python3 scripts/gatekeeper.py prompts/current.md")
        sys.exit(1)

    prompt_path = sys.argv[1]
    if not os.path.exists(prompt_path):
        print(f"[錯誤] 找不到檔案: {prompt_path}")
        sys.exit(1)

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    passed, violations = run_gatekeeper(prompt_text)

    print(f"{'='*60}")
    print(f"  Gatekeeper 硬性規則防呆檢查")
    print(f"  檔案: {prompt_path}")
    print(f"  字數: {len(prompt_text)}")
    print(f"{'='*60}")

    if not violations:
        print("\n  ✅ 全部通過！無任何違規。")
    else:
        for v in violations:
            icon = "❌" if v["severity"] == "reject" else "⚠️"
            print(f"\n  {icon} [{v['rule']}] {v['detail']}")

    print(f"\n{'='*60}")
    print(f"  結果: {'✅ 通過' if passed else '❌ 淘汰'}")
    print(f"{'='*60}")

    # 輸出 JSON 格式結果到 stdout（供其他腳本呼叫）
    if "--json" in sys.argv:
        result = {"passed": passed, "violations": violations, "char_count": len(prompt_text)}
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
