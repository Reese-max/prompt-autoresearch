import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
# -*- coding: utf-8 -*-
"""
run_opt.py — Prompt AutoResearch v3 單次演化優化入口
實作完整的三層閉環流程：
1. 讀取最新運行報告 runs/latest/summary.md，讓 MiniMax 進行定向突變（選擇 D01-D10 中的一個方向）。
2. 硬性規則防呆（Gatekeeper）。
3. 快速小題庫篩選（Smoke Test）。
4. 全量開發測試（Dev Test）。
5. 接受條件對比與決策（晉升或回滾）。
"""
import os
import sys
import json
import re
import time
import shutil
import subprocess

from lib.api import call_minimax
from lib.config import get
from lib.io import (
    load_file, write_file, sha256_text, load_json, write_json,
    read_jsonl, append_jsonl, normalize_path, ensure_dir,
)
from lib.metrics import record_round

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

PROMPT_PATH   = "prompts/current.md"
BASELINE_PATH = "prompts/baseline.md"
BASELINE_META_PATH = "prompts/baseline.meta.json"
ARCHIVE_DIR   = "prompts/archive"
ELITE_DIR     = "prompts/candidates/elite"
CHAMPIONS_DIR = "prompts/champions"
PYTHON_BIN    = sys.executable or "python3"

DEFAULT_SMOKE_PARALLEL  = get("parallel", "smoke", 6)
DEFAULT_DEV_PARALLEL    = get("parallel", "dev", 24)
DEFAULT_HOLDOUT_PARALLEL = get("parallel", "holdout", 24)
MAX_CANDIDATE_PROMPT_LEN = get("thresholds", "max_candidate_length", 550)
SMOKE_ALLOWED_DROP = get("thresholds", "smoke_allowed_drop", 2.0)
SMOKE_MIN_SCORE = get("thresholds", "smoke_min_score", 75.0)
SMOKE_WORD_RATE_MIN = get("thresholds", "smoke_word_rate_min", 70.0)
DEV_WORD_RATE_MIN = get("thresholds", "word_rate_min", 85.0)
RISK_PERFECT_RATE_MIN = get("thresholds", "risk_perfect_rate_min", 100.0)

def int_env(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default

def parse_parallel_args(argv):
    def read_flag(name, env_name, default):
        if name in argv:
            try:
                return max(1, int(argv[argv.index(name) + 1]))
            except (IndexError, ValueError):
                pass
        return int_env(env_name, default)

    return {
        "smoke_parallel": read_flag("--smoke-parallel", "AUTORESEARCH_SMOKE_PARALLEL", DEFAULT_SMOKE_PARALLEL),
        "dev_parallel": read_flag("--dev-parallel", "AUTORESEARCH_DEV_PARALLEL", DEFAULT_DEV_PARALLEL),
        "holdout_parallel": read_flag("--holdout-parallel", "AUTORESEARCH_HOLDOUT_PARALLEL", DEFAULT_HOLDOUT_PARALLEL),
    }

def parse_run_opt_args(argv):
    config = parse_parallel_args(argv)
    if "--force-direction" in argv:
        try:
            config["force_direction"] = argv[argv.index("--force-direction") + 1]
        except IndexError:
            config["force_direction"] = ""
    if "--avoid-failures" in argv:
        try:
            config["avoid_failures"] = [
                item.strip()
                for item in argv[argv.index("--avoid-failures") + 1].split(",")
                if item.strip()
            ]
        except IndexError:
            config["avoid_failures"] = []
    return config

def compress_candidate_prompt(prompt):
    compress_user = f"""請將以下臺灣國考申論題提示詞壓縮到 520 字以內。

硬性要求：
1. 保留「專家」或「閱卷委員」等角色字眼。
2. 保留「直接輸出正文」或「不得摻雜說明或提問」。
3. 保留「不得編造」或「嚴禁編造」。
4. 保留「比較基準」或「橫向對比」。
5. 保留「三段論法」或「法理／案例」分流。
6. 只輸出壓縮後提示詞正文，不要解釋、不要 markdown。

原提示詞：
{prompt}
"""
    return call_minimax("你是提示詞壓縮編輯。", compress_user, temperature=0.2)

def slugify_type(type_name):
    mapping = {
        "說明題": "general",
        "比較題": "comparison",
        "評析題": "commentary",
        "實務應用題": "practical",
        "法律法理題": "legal_theory",
        "法律案例題": "legal_case",
    }
    return mapping.get(type_name, re.sub(r"[^A-Za-z0-9_]+", "_", type_name).strip("_").lower() or "unknown")

def read_summary(run_dir):
    json_path = os.path.join(run_dir, "summary.json")
    data = load_json(json_path)
    if data:
        return {
            "path": run_dir,
            "score": float(data.get("average_score", 0.0)),
            "question_file": str(data.get("question_file", "")).replace("\\", "/"),
            "prompt_hash": data.get("prompt_hash", ""),
            "type_averages": data.get("type_averages", {}),
            "failure_counts": data.get("failure_counts", {}),
            "word_count_pass_rate": data.get("word_count_pass_rate", 0.0),
            "risk_perfect_rate": data.get("risk_perfect_rate", 0.0),
            "error_count": data.get("error_count", 0),
            "cache_hit_count": data.get("cache_hit_count", 0),
            "estimated_api_calls": data.get("estimated_api_calls", 0),
            "text": load_file(os.path.join(run_dir, "summary.md")),
            "json": data,
        }
    text = load_file(os.path.join(run_dir, "summary.md"))
    if not text:
        return {}
    score_match = re.search(r"總平均分數\*\*:\s*([0-9.]+)", text)
    qfile_match = re.search(r"測試題庫\*\*:\s*([^\s]+)", text)
    return {
        "path": run_dir,
        "score": float(score_match.group(1)) if score_match else 0.0,
        "question_file": qfile_match.group(1).replace("\\", "/") if qfile_match else "",
        "prompt_hash": (re.search(r"Prompt Hash\*\*:\s*`?([0-9a-f]+)`?", text) or [None, ""])[1],
        "type_averages": {},
        "failure_counts": {},
        "word_count_pass_rate": 0.0,
        "risk_perfect_rate": 0.0,
        "error_count": 0,
        "text": text,
    }

def governance_notes(summary, stage):
    notes = []
    word_rate = float(summary.get("word_count_pass_rate", 0.0))
    risk_rate = float(summary.get("risk_perfect_rate", 0.0))
    error_count = int(summary.get("error_count", 0))
    word_min = SMOKE_WORD_RATE_MIN if stage == "smoke" else DEV_WORD_RATE_MIN
    if word_rate < word_min:
        notes.append(f"字數合格率 {word_rate:.1f}% < {word_min:.0f}%")
    if risk_rate < RISK_PERFECT_RATE_MIN:
        notes.append(f"風險滿分率 {risk_rate:.1f}% < {RISK_PERFECT_RATE_MIN:.0f}%")
    if error_count > 0:
        notes.append(f"評估錯誤 {error_count} 筆")
    return notes

def scorecard_path(cand_path):
    return cand_path.replace(".md", ".scorecard.json")

def update_candidate_scorecard(cand_path, **updates):
    card_path = scorecard_path(cand_path)
    card = load_json(card_path)
    card.update(updates)
    card["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(card_path, card)

def read_details(run_dir):
    path = os.path.join(run_dir, "details.jsonl")
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def list_run_dirs():
    if not os.path.exists("runs"):
        return []
    return [
        os.path.join("runs", d)
        for d in sorted(os.listdir("runs"))
        if d != "latest" and os.path.isdir(os.path.join("runs", d))
    ]

def find_latest_run_for(question_file, before=None):
    normalized = question_file.replace("\\", "/")
    candidates = []
    for run_dir in list_run_dirs():
        if before and run_dir >= before:
            continue
        summary = read_summary(run_dir)
        if summary.get("question_file") == normalized:
            candidates.append(run_dir)
    return candidates[-1] if candidates else None

def find_latest_run_for_hash(question_file, prompt_hash):
    normalized = question_file.replace("\\", "/")
    candidates = []
    for run_dir in list_run_dirs():
        summary = read_summary(run_dir)
        if summary.get("question_file") == normalized and summary.get("prompt_hash") == prompt_hash:
            candidates.append(run_dir)
    return candidates[-1] if candidates else None

def collect_recent_failure_trend(question_file="questions/dev.jsonl", limit=4):
    normalized = question_file.replace("\\", "/")
    counts = {}
    runs = []
    for run_dir in reversed(list_run_dirs()):
        summary = read_summary(run_dir)
        if summary.get("question_file") != normalized:
            continue
        rows = read_details(run_dir)
        if not rows:
            continue
        runs.append(run_dir)
        for row in rows:
            for code in row.get("failures", []):
                if code:
                    counts[code] = counts.get(code, 0) + 1
        if len(runs) >= limit:
            break
    return counts, runs

def format_failure_trend(counts, runs):
    if not counts:
        return "無可用趨勢資料。"
    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:8]
    return (
        f"最近 dev runs: {', '.join(runs)}\n"
        + "\n".join(f"- {code}: {count}" for code, count in top)
    )

def champion_context():
    if not os.path.exists(CHAMPIONS_DIR):
        return "目前尚無題型 champion。"
    lines = []
    for name in sorted(os.listdir(CHAMPIONS_DIR)):
        if not name.endswith(".meta.json"):
            continue
        meta = load_json(os.path.join(CHAMPIONS_DIR, name))
        if not meta:
            continue
        lines.append(
            f"- {meta.get('type')}: {meta.get('candidate_avg', 0.0):.2f} "
            f"(baseline {meta.get('baseline_avg', 0.0):.2f}, diff {meta.get('diff', 0.0):+.2f}) "
            f"來源 {meta.get('champion_prompt_path') or meta.get('elite_prompt_path')}"
        )
    return "\n".join(lines) if lines else "目前尚無題型 champion。"

def baseline_runs_from_meta(prompt_hash):
    meta = load_json(BASELINE_META_PATH)
    if meta.get("prompt_hash") != prompt_hash:
        return {}, meta
    return {
        "smoke": meta.get("smoke_run") or "",
        "dev": meta.get("dev_run") or "",
        "holdout": meta.get("holdout_run") or "",
    }, meta

def write_baseline_meta(prompt_hash, smoke_run, dev_run, holdout_run):
    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prompt_path": BASELINE_PATH,
        "prompt_hash": prompt_hash,
        "smoke_run": smoke_run,
        "dev_run": dev_run,
        "holdout_run": holdout_run,
        "smoke_avg": read_summary(smoke_run).get("score", 0.0) if smoke_run else None,
        "dev_avg": read_summary(dev_run).get("score", 0.0) if dev_run else None,
        "holdout_avg": read_summary(holdout_run).get("score", 0.0) if holdout_run else None,
    }
    write_json(BASELINE_META_PATH, payload)

def save_elite_candidate(candidate_prompt, cand_path, direction, hypothesis, dev_run_dir, baseline_dev_run, comparison):
    breakthroughs = comparison.get("type_breakthroughs", []) if comparison else []
    if not breakthroughs:
        return []

    os.makedirs(ELITE_DIR, exist_ok=True)
    os.makedirs(CHAMPIONS_DIR, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    candidate_hash = sha256_text(candidate_prompt)
    saved = []
    for item in breakthroughs:
        type_slug = slugify_type(item["type"])
        elite_prompt_path = os.path.join(ELITE_DIR, f"{type_slug}_{ts}_{candidate_hash[:8]}.md")
        elite_meta_path = elite_prompt_path.replace(".md", ".meta.json")
        shutil.copy(cand_path, elite_prompt_path)
        meta = {
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "elite_candidate",
            "type": item["type"],
            "type_slug": type_slug,
            "candidate_hash": candidate_hash,
            "candidate_source": cand_path,
            "elite_prompt_path": elite_prompt_path,
            "direction": direction,
            "hypothesis": hypothesis,
            "dev_run": dev_run_dir,
            "baseline_dev_run": baseline_dev_run,
            "baseline_avg": item["baseline_avg"],
            "candidate_avg": item["candidate_avg"],
            "diff": item["diff"],
            "overall_diff": comparison.get("score_diff"),
            "risk_rate": comparison.get("risk_rate"),
            "base_risk_rate": comparison.get("base_risk_rate"),
            "decision": "SPECIALTY_RETAINED",
        }
        write_json(elite_meta_path, meta)

        champion_meta_path = os.path.join(CHAMPIONS_DIR, f"{type_slug}.meta.json")
        current_champion = load_json(champion_meta_path)
        current_avg = float(current_champion.get("candidate_avg", -1)) if current_champion else -1
        if item["candidate_avg"] > current_avg:
            champion_prompt_path = os.path.join(CHAMPIONS_DIR, f"{type_slug}.md")
            shutil.copy(cand_path, champion_prompt_path)
            champion_meta = dict(meta)
            champion_meta["kind"] = "type_champion"
            champion_meta["champion_prompt_path"] = champion_prompt_path
            write_json(champion_meta_path, champion_meta)
        saved.append(meta)
    return saved

def newest_run_after(before_dirs):
    before_set = set(before_dirs)
    after = [d for d in list_run_dirs() if d not in before_set]
    return after[-1] if after else None

def run_evaluate(prompt_path, question_file, parallel, capture=False):
    before_dirs = list_run_dirs()
    cmd = [PYTHON_BIN, "scripts/evaluate.py", prompt_path, question_file, "--parallel", str(parallel)]
    if capture:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    else:
        res = subprocess.run(cmd)
    run_dir = newest_run_after(before_dirs)
    return res, run_dir, read_summary(run_dir) if run_dir else {}

def pick_direction(latest_report, trend_counts=None, force_direction=None, avoid_failures=None):
    direction_map = [
        ("D01【精準審題】", ["F01"]),
        ("D02【骨架通用性】", ["F02", "F14"]),
        ("D03【採分點外露】", ["F03"]),
        ("D04【具體化與佐證】", ["F04"]),
        ("D05【比較題對稱結構】", ["F05"]),
        ("D06【評析題正反思辨】", ["F06"]),
        ("D07【法理與爭議分析】", ["F07"]),
        ("D08【嚴格三段論法】", ["F08"]),
        ("D09【起承轉合強化】", ["F09", "F10"]),
        ("D10【風險與語氣控制】", ["F11", "F12", "F13"]),
    ]
    avoid_failures = set(avoid_failures or [])
    if force_direction:
        for direction, codes in direction_map:
            if force_direction in direction or force_direction == direction:
                return direction, codes

    counts = trend_counts or {code: len(re.findall(rf"\b{code}\b", latest_report)) for code in re.findall(r"\bF[0-9]{2}\b", latest_report)}
    best_direction = direction_map[0][0]
    best_score = -1
    target_codes = ["F01"]
    for direction, codes in direction_map:
        if avoid_failures and any(code in avoid_failures for code in codes):
            continue
        score = sum(counts.get(code, 0) for code in codes)
        if score > best_score:
            best_direction = direction
            best_score = score
            target_codes = codes
    if best_score < 0:
        return pick_direction(latest_report, trend_counts, force_direction=None, avoid_failures=None)
    return best_direction, target_codes

def write_decision(run_dir, content):
    if run_dir:
        write_file(os.path.join(run_dir, "decision.md"), content)
    latest_dir = "runs/latest"
    os.makedirs(latest_dir, exist_ok=True)
    write_file(os.path.join(latest_dir, "decision.md"), content)

def _cleanup_old_archives():
    """保留最近 N 個 baseline 備份，刪除更舊的。"""
    max_versions = get("archive", "max_versions", 20)
    if not os.path.exists(ARCHIVE_DIR):
        return
    archives = sorted(
        [f for f in os.listdir(ARCHIVE_DIR) if f.startswith("baseline_") and f.endswith(".md")],
    )
    while len(archives) > max_versions:
        old = archives.pop(0)
        try:
            os.remove(os.path.join(ARCHIVE_DIR, old))
        except OSError:
            pass

def run_opt_pass(smoke_parallel=None, dev_parallel=None, holdout_parallel=None, force_direction=None, avoid_failures=None):
    smoke_parallel = smoke_parallel or int_env("AUTORESEARCH_SMOKE_PARALLEL", DEFAULT_SMOKE_PARALLEL)
    dev_parallel = dev_parallel or int_env("AUTORESEARCH_DEV_PARALLEL", DEFAULT_DEV_PARALLEL)
    holdout_parallel = holdout_parallel or int_env("AUTORESEARCH_HOLDOUT_PARALLEL", DEFAULT_HOLDOUT_PARALLEL)

    print(f"{C_PURPLE}=================================================={C_RESET}")
    print(f"       Prompt AutoResearch v3 — 單次演化優化器")
    print(f"{C_PURPLE}=================================================={C_RESET}")
    print(f"  - 併緒設定：smoke={smoke_parallel}, dev={dev_parallel}, holdout={holdout_parallel}")

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    os.makedirs("prompts/candidates", exist_ok=True)
    os.makedirs(ELITE_DIR, exist_ok=True)
    os.makedirs(CHAMPIONS_DIR, exist_ok=True)

    # --------------------------------------------------
    # 步驟 1：加載當前最強冠軍基線
    # --------------------------------------------------
    print(f"\n{C_YELLOW}[步驟 1] 確立冠軍基線...{C_RESET}")
    current_prompt = load_file(PROMPT_PATH)
    baseline_prompt = load_file(BASELINE_PATH)

    if not baseline_prompt:
        if current_prompt:
            baseline_prompt = current_prompt
            write_file(BASELINE_PATH, baseline_prompt)
        else:
            print(f"{C_RED}[錯誤] prompts/current.md 與 baseline.md 皆不存在。{C_RESET}")
            sys.exit(1)

    if not current_prompt:
        current_prompt = baseline_prompt
        write_file(PROMPT_PATH, current_prompt)

    baseline_hash = sha256_text(baseline_prompt)
    meta_runs, baseline_meta = baseline_runs_from_meta(baseline_hash)
    baseline_smoke_run = meta_runs.get("smoke") or find_latest_run_for_hash("questions/smoke.jsonl", baseline_hash) or find_latest_run_for("questions/smoke.jsonl")
    baseline_dev_run = meta_runs.get("dev") or find_latest_run_for_hash("questions/dev.jsonl", baseline_hash) or find_latest_run_for("questions/dev.jsonl")
    baseline_holdout_run = meta_runs.get("holdout") or find_latest_run_for_hash("questions/holdout.jsonl", baseline_hash) or find_latest_run_for("questions/holdout.jsonl")

    print(f"  - 冠軍基線 (baseline.md) 長度: {len(baseline_prompt)} 字")
    print(f"  - baseline prompt_hash: {baseline_hash[:12]}")
    if baseline_meta and baseline_meta.get("prompt_hash") != baseline_hash:
        print("  - ⚠️ baseline.meta.json 與目前 baseline.md 不一致，已改用 hash/run 掃描回退。")

    # --------------------------------------------------
    # 步驟 2：讀取歷史報告與缺陷分析，呼叫 MiniMax 進行定向突變
    # --------------------------------------------------
    print(f"\n{C_YELLOW}[步驟 2] 分析歷史報告，生成優化候選提示詞...{C_RESET}")
    baseline_report = load_file(os.path.join(baseline_dev_run, "summary.md")) if baseline_dev_run else ""
    latest_report = load_file("runs/latest/summary.md")
    trend_counts, trend_runs = collect_recent_failure_trend("questions/dev.jsonl", limit=4)
    trend_report = format_failure_trend(trend_counts, trend_runs)
    champion_report = champion_context()
    if not latest_report and not baseline_report:
        latest_report = "無歷史報告。此為首次運行，請針對提示詞結構做通盤優化。"
        print("  - ⚠️ 無歷史運行報告，將進行首次全方位優化。")
    else:
        print("  - ✅ 成功讀取歷史運行報告與近期失敗趨勢。")

    program_rules = load_file("program.md")
    force_direction = force_direction or os.environ.get("AUTORESEARCH_FORCE_DIRECTION", "").strip()
    env_avoid_failures = [
        item.strip()
        for item in os.environ.get("AUTORESEARCH_AVOID_FAILURES", "").split(",")
        if item.strip()
    ]
    merged_avoid_failures = list(dict.fromkeys((avoid_failures or []) + env_avoid_failures))
    direction, target_failures = pick_direction(
        latest_report or baseline_report,
        trend_counts,
        force_direction=force_direction,
        avoid_failures=merged_avoid_failures,
    )
    hypothesis = (
        f"本輪方向：{direction}。"
        f"假設：針對 {', '.join(target_failures)} 做單點微調，"
        "可改善對應低分題型，同時不犧牲其他題型、風險控制與每日懶人版精簡度。"
    )
    print(f"  - 單一優化方向: {direction}")
    if merged_avoid_failures:
        print(f"  - 本輪避開失敗碼: {', '.join(merged_avoid_failures)}")
    print(f"  - 本輪假設: {hypothesis}")

    meta_prompt = """你是一位精通臺灣國家考試（高考/特考三等）申論題高分寫作的提示詞優化大師。
請根據【最新評估運行報告】，對當前最高分【冠軍提示詞 (baseline.md)】進行一次精準定向優化。

【不可變更規則】
你只能輸出候選提示詞正文。不得要求、暗示或依賴修改 questions/、rubrics/、scripts/、program.md、results.tsv 或 runs/。
本輪只能做單一優化方向，不得同時重寫多個題型規則。

【本輪唯一優化方向與假設】
{3}

【近期失敗碼趨勢（優先依據，不可只被單次最新 run 帶偏）】
{4}

【題型 champion / elite 候選資訊】
{5}

【最新評估運行報告】
{0}

【目前 baseline dev 評估報告】
{6}

【當前最高分冠軍提示詞 (baseline.md)】
{1}

【重要優化指令】
1. **分析缺陷與優化方向**：上一輪出現了缺陷（如：{2}）。請在維持冠軍提示詞既有優秀結構的基礎上，針對這些缺陷進行局部微調與精確強化。
2. **保留硬性防呆規則**：新提示詞必須【百分之百包含】以下特定關鍵字以通過系統防呆審查：
   - 專家角色：必須包含「專家」或「閱卷委員」或「評分委員」或「寫作名師」。
   - 廢話與前言排除：必須包含「直接輸出正文」或「不得摻雜說明或提問」或「嚴禁任何前導廢話」。
   - 防編造法條：必須包含「杜絕捏造」或「嚴禁編造」或「不得編造」或「不要編造」。
   - 比較基準：必須包含「比較基準」或「橫向對比」。
   - 法律題分流：必須包含「三段論法」或「法源涵攝」或「法理」或「案例」。
3. **字數嚴格控制**：修改後的提示詞總長度必須【控制在 400-500 字以內】，絕對不能超過 550 字，否則會被系統自動攔截淘汰。
4. **輸出格式**：請直接輸出優化後的 System Prompt 全文正文。嚴禁包含任何 markdown 代碼塊（```）、任何 JSON 包裝、任何前導說明、對話或思考過程。直接以第一字開始輸出正文。
5. **保留局部成果**：若題型 champion 顯示某類題型已有明顯突破，請吸收其有效精神，但不可讓其他題型退步超過 3 分。
""".format(latest_report, baseline_prompt, ", ".join(target_failures), hypothesis, trend_report, champion_report, baseline_report)

    # --- 多候選生成 (#5) ---
    multi_cfg = get("multi_candidate") or {}
    use_multi = multi_cfg.get("enabled", True)
    candidate_count = multi_cfg.get("count", 3) if use_multi else 1
    candidate_temps = multi_cfg.get("temperatures", [0.5, 0.7, 0.9]) if use_multi else [0.7]

    candidates = []  # list of (prompt_text, temperature, cand_path)
    try:
        for ci in range(candidate_count):
            temp = candidate_temps[ci % len(candidate_temps)]
            print(f"  - {C_CYAN}[LIVE API] 生成候選 {ci+1}/{candidate_count} (temperature={temp})...{C_RESET}")
            mutated = call_minimax("你是一位提示詞優化大師。", meta_prompt, temperature=temp)
            print(f"  - {C_GREEN}  候選 {ci+1} 長度: {len(mutated)} 字{C_RESET}")

            if len(mutated) > MAX_CANDIDATE_PROMPT_LEN:
                raw_path = f"prompts/candidates/candidate_{int(time.time())}_raw_overlength.md"
                write_file(raw_path, mutated)
                print(f"  - {C_YELLOW}[壓縮] 候選 {ci+1} 超過 {MAX_CANDIDATE_PROMPT_LEN} 字，嘗試壓縮...{C_RESET}")
                compressed = compress_candidate_prompt(mutated)
                if compressed:
                    mutated = compressed.strip()
                    print(f"  - {C_GREEN}[壓縮] 壓縮後長度: {len(mutated)} 字{C_RESET}")

            ts = int(time.time())
            cand_path = f"prompts/candidates/candidate_{ts}_{ci}.md"
            write_file(cand_path, mutated)
            write_file(
                cand_path.replace(".md", ".meta.md"),
                f"# Candidate Metadata\n\n- direction: {direction}\n- target_failures: {', '.join(target_failures)}\n- hypothesis: {hypothesis}\n- temperature: {temp}\n- candidate_index: {ci}\n",
            )
            update_candidate_scorecard(
                cand_path,
                candidate_path=cand_path,
                direction=direction,
                target_failures=target_failures,
                hypothesis=hypothesis,
                temperature=temp,
                candidate_index=ci,
                candidate_length=len(mutated),
                status="generated",
                reject_reasons=[],
            )
            candidates.append((mutated, temp, cand_path))

    except Exception as e:
        print(f"{C_RED}[錯誤] 突變呼叫失敗: {str(e)}{C_RESET}")
        return False

    if not candidates:
        print(f"{C_RED}[錯誤] 無任何候選生成成功。{C_RESET}")
        return False

    # --------------------------------------------------
    # 步驟 3：第一層 — 硬性規則防呆（Gatekeeper）— 對所有候選
    # --------------------------------------------------
    print(f"\n{C_YELLOW}[步驟 3] 第一層：硬性規則防呆審查中（{len(candidates)} 個候選）...{C_RESET}")
    from scripts.gatekeeper import run_gatekeeper
    gk_passed = []  # (prompt, temp, cand_path, gk_data)
    for ci, (mutated, temp, cand_path) in enumerate(candidates):
        passed, violations = run_gatekeeper(mutated)
        gk_data = {"passed": passed, "violations": violations}
        if passed:
            print(f"  - {C_GREEN}✅ 候選 {ci+1} (temp={temp}) 通過防呆{C_RESET}")
            update_candidate_scorecard(
                cand_path,
                gatekeeper={"passed": True, "violations": violations},
                status="gatekeeper_passed",
            )
            gk_passed.append((mutated, temp, cand_path, gk_data))
        else:
            rejects = [v for v in violations if v["severity"] == "reject"]
            print(f"  - {C_RED}❌ 候選 {ci+1} (temp={temp}) 防呆未通過：{', '.join(v['rule'] for v in rejects)}{C_RESET}")
            update_candidate_scorecard(
                cand_path,
                gatekeeper={"passed": False, "violations": violations},
                status="rejected_gatekeeper",
                reject_reasons=[f"gatekeeper:{v['rule']}" for v in rejects],
            )

    if not gk_passed:
        print(f"  - {C_RED}所有候選均未通過防呆，回滾。{C_RESET}")
        write_file(PROMPT_PATH, baseline_prompt)
        return False

    # --------------------------------------------------
    # 步驟 4：第二層 — 快速小題庫篩選（Smoke Test）— 對所有通過防呆的候選
    # --------------------------------------------------
    print(f"\n{C_YELLOW}[步驟 4] 第二層：小題庫快速篩選 ({len(gk_passed)} 個候選)...{C_RESET}")
    baseline_smoke_score = read_summary(baseline_smoke_run).get("score", 0.0) if baseline_smoke_run else 0.0
    smoke_results = []  # (prompt, temp, cand_path, smoke_score, smoke_run, smoke_summary)

    for ci, (mutated, temp, cand_path, _) in enumerate(gk_passed):
        write_file(PROMPT_PATH, mutated)
        smoke_res, smoke_run, smoke_summary = run_evaluate(PROMPT_PATH, "questions/smoke.jsonl", smoke_parallel, capture=True)
        smoke_score = smoke_summary.get("score", 0.0)
        smoke_drop = baseline_smoke_score - smoke_score if baseline_smoke_run else 0.0
        smoke_governance_notes = governance_notes(smoke_summary, "smoke")

        passed_smoke = (
            smoke_res.returncode == 0
            and smoke_score >= SMOKE_MIN_SCORE
            and smoke_drop <= SMOKE_ALLOWED_DROP
            and not smoke_governance_notes
        )
        if passed_smoke:
            print(f"  - {C_GREEN}✅ 候選 {ci+1} (temp={temp}) Smoke 通過：{smoke_score:.2f}{C_RESET}")
            update_candidate_scorecard(
                cand_path,
                smoke={
                    "passed": True,
                    "run": smoke_run,
                    "score": smoke_score,
                    "drop": smoke_drop,
                    "word_count_pass_rate": smoke_summary.get("word_count_pass_rate", 0.0),
                    "risk_perfect_rate": smoke_summary.get("risk_perfect_rate", 0.0),
                    "error_count": smoke_summary.get("error_count", 0),
                },
                status="smoke_passed",
            )
            smoke_results.append((mutated, temp, cand_path, smoke_score, smoke_run, smoke_summary))
        else:
            reasons = []
            if smoke_res.returncode != 0:
                reasons.append(f"returncode={smoke_res.returncode}")
            if smoke_score < SMOKE_MIN_SCORE:
                reasons.append(f"score={smoke_score:.2f} < {SMOKE_MIN_SCORE:.2f}")
            if smoke_drop > SMOKE_ALLOWED_DROP:
                reasons.append(f"drop={smoke_drop:.2f} > {SMOKE_ALLOWED_DROP:.2f}")
            reasons.extend(smoke_governance_notes)
            print(
                f"  - {C_RED}❌ 候選 {ci+1} (temp={temp}) Smoke 未通過："
                f"{'；'.join(reasons) or '未知原因'}{C_RESET}"
            )
            update_candidate_scorecard(
                cand_path,
                smoke={
                    "passed": False,
                    "run": smoke_run,
                    "score": smoke_score,
                    "drop": smoke_drop,
                    "word_count_pass_rate": smoke_summary.get("word_count_pass_rate", 0.0),
                    "risk_perfect_rate": smoke_summary.get("risk_perfect_rate", 0.0),
                    "error_count": smoke_summary.get("error_count", 0),
                    "returncode": smoke_res.returncode,
                },
                status="rejected_smoke",
                reject_reasons=reasons,
            )

    if not smoke_results:
        reason = "所有候選 Smoke 均未通過"
        print(f"  - {C_RED}{reason}，回滾。{C_RESET}")
        write_file(PROMPT_PATH, baseline_prompt)
        write_decision(
            None,
            f"# Decision\n\n- decision: REVERT\n- stage: smoke\n- direction: {direction}\n- hypothesis: {hypothesis}\n- reason: {reason}\n",
        )
        return False

    # 取 Smoke 分數最高的候選
    smoke_results.sort(key=lambda x: x[3], reverse=True)
    mutated_prompt, best_temp, cand_path, smoke_score, smoke_run, smoke_summary = smoke_results[0]
    print(f"  - {C_GREEN}最佳候選：temp={best_temp}，Smoke 分數={smoke_score:.2f}{C_RESET}")
    update_candidate_scorecard(cand_path, status="selected_for_dev", selected=True)
    write_file(PROMPT_PATH, mutated_prompt)

    # --------------------------------------------------
    # 步驟 5：第三層 — 全量開發測試（Dev Test）
    # --------------------------------------------------
    print(f"\n{C_YELLOW}[步驟 5] 第三層：全量開發測試 (Dev Test，36題，併緒 {dev_parallel})...{C_RESET}")
    dev_res, dev_run_dir, dev_summary = run_evaluate(PROMPT_PATH, "questions/dev.jsonl", dev_parallel)
    if dev_res.returncode != 0 or not dev_run_dir:
        reason = f"Dev 評估失敗：returncode={dev_res.returncode}, run_dir={dev_run_dir}"
        print(f"\n{C_RED}❌ {reason}{C_RESET}")
        write_file(PROMPT_PATH, baseline_prompt)
        update_candidate_scorecard(
            cand_path,
            dev={"passed": False, "run": dev_run_dir, "returncode": dev_res.returncode},
            status="rejected_dev_error",
            reject_reasons=[reason],
        )
        write_decision(
            dev_run_dir,
            f"# Decision\n\n- decision: REVERT\n- stage: dev\n- direction: {direction}\n- hypothesis: {hypothesis}\n- reason: {reason}\n",
        )
        return False
    dev_governance_notes = governance_notes(dev_summary, "dev")
    if dev_governance_notes:
        print(f"  - {C_RED}❌ Dev 治理門檻未通過：{'；'.join(dev_governance_notes)}{C_RESET}")
    update_candidate_scorecard(
        cand_path,
        dev={
            "run": dev_run_dir,
            "score": dev_summary.get("score", 0.0),
            "word_count_pass_rate": dev_summary.get("word_count_pass_rate", 0.0),
            "risk_perfect_rate": dev_summary.get("risk_perfect_rate", 0.0),
            "error_count": dev_summary.get("error_count", 0),
            "governance_passed": not dev_governance_notes,
            "governance_notes": dev_governance_notes,
        },
        status="dev_evaluated",
    )

    # --------------------------------------------------
    # 步驟 6：接受條件對比與新冠軍判定
    # --------------------------------------------------
    print(f"\n{C_YELLOW}[步驟 6] 運行對比與冠軍決策...{C_RESET}")

    if not baseline_dev_run:
        print("  - ⚠️ 無 dev 基準 run，此為首次全量測試。若高於 80 分將暫准進入 holdout。")
        accept = dev_summary.get("score", 0.0) >= 80.0
        diff = dev_summary.get("score", 0.0)
        comparison_data = {}
    else:
        from scripts.compare_runs import compare
        accept, new_avg, diff = compare(dev_run_dir, baseline_dev_run)
        from scripts.compare_runs import LAST_COMPARISON
        comparison_data = LAST_COMPARISON
    if dev_governance_notes:
        accept = False

    elite_saved = []
    if not accept and comparison_data.get("type_breakthroughs") and not dev_governance_notes:
        elite_saved = save_elite_candidate(
            mutated_prompt,
            cand_path,
            direction,
            hypothesis,
            dev_run_dir,
            baseline_dev_run,
            comparison_data,
        )
        for meta in elite_saved:
            print(
                f"  - {C_YELLOW}[局部保留] {meta['type']} 專項候選已保存："
                f"{meta['elite_prompt_path']} (diff={meta['diff']:+.2f}){C_RESET}"
            )
        update_candidate_scorecard(
            cand_path,
            champion_retention={
                "skipped": False,
                "saved": len(elite_saved),
                "items": elite_saved,
            },
        )
    elif not accept and comparison_data.get("type_breakthroughs") and dev_governance_notes:
        print(
            f"  - {C_YELLOW}[局部保留略過] 候選有題型突破，但未通過治理門檻，"
            f"不寫入 champion pool。{C_RESET}"
        )
        update_candidate_scorecard(
            cand_path,
            champion_retention={
                "skipped": True,
                "reason": "dev governance failed",
                "governance_notes": dev_governance_notes,
                "type_breakthroughs": comparison_data.get("type_breakthroughs", []),
            },
        )

    holdout_run_dir = None
    holdout_summary = {}
    holdout_accept = True
    holdout_reason = "no baseline holdout"

    if accept:
        print(f"\n{C_YELLOW}[步驟 7] 啟動防過擬合 Holdout 盲測題庫驗證（併緒 {holdout_parallel}）...{C_RESET}")
        holdout_res, holdout_run_dir, holdout_summary = run_evaluate(PROMPT_PATH, "questions/holdout.jsonl", holdout_parallel)
        holdout_governance_notes = governance_notes(holdout_summary, "holdout")
        if holdout_res.returncode != 0 or not holdout_run_dir:
            holdout_accept = False
            holdout_reason = f"Holdout 評估失敗：returncode={holdout_res.returncode}, run_dir={holdout_run_dir}"
        elif holdout_governance_notes:
            holdout_accept = False
            holdout_reason = "；".join(holdout_governance_notes)
        elif baseline_holdout_run:
            baseline_holdout_score = read_summary(baseline_holdout_run).get("score", 0.0)
            holdout_score = holdout_summary.get("score", 0.0)
            holdout_drop = baseline_holdout_score - holdout_score
            holdout_accept = holdout_drop <= 1.0
            holdout_reason = f"candidate={holdout_score:.2f}, baseline={baseline_holdout_score:.2f}, drop={holdout_drop:.2f}"
        else:
            holdout_reason = f"candidate={holdout_summary.get('score', 0.0):.2f}; 無 baseline holdout，僅記錄不阻擋首次驗證"

        print(f"  - Holdout 檢查: {holdout_reason}")
        accept = accept and holdout_accept
        update_candidate_scorecard(
            cand_path,
            holdout={
                "run": holdout_run_dir,
                "score": holdout_summary.get("score", 0.0),
                "word_count_pass_rate": holdout_summary.get("word_count_pass_rate", 0.0),
                "risk_perfect_rate": holdout_summary.get("risk_perfect_rate", 0.0),
                "error_count": holdout_summary.get("error_count", 0),
                "accepted": holdout_accept,
                "reason": holdout_reason,
                "governance_notes": holdout_governance_notes,
            },
        )

    if accept:
        print(f"\n{C_GREEN}🏆 恭喜！新提示詞通過 10 大接受條件，成功晉升為新冠軍！{C_RESET}")
        # 自動備份舊冠軍（#14）
        ensure_dir(ARCHIVE_DIR)
        ts = time.strftime("%Y%m%d_%H%M%S")
        baseline_score_match = re.search(r"總平均分數:\s*([0-9.]+)", latest_report or "")
        old_score = baseline_score_match.group(1) if baseline_score_match else "old"
        archive_file = os.path.join(ARCHIVE_DIR, f"baseline_{ts}_score{old_score}.md")

        if os.path.exists(BASELINE_PATH):
            shutil.copy(BASELINE_PATH, archive_file)
            print(f"  - 舊冠軍已備份至: {archive_file}")
            _cleanup_old_archives()

        # 寫入 baseline.md
        write_file(BASELINE_PATH, mutated_prompt)
        print(f"  - 新冠軍提示詞已寫入 baseline.md。")
        new_baseline_hash = sha256_text(mutated_prompt)
        write_baseline_meta(new_baseline_hash, smoke_run, dev_run_dir, holdout_run_dir)
        print(f"  - baseline metadata 已更新：{BASELINE_META_PATH}")
        decision = (
            "# Decision\n\n"
            "- decision: ACCEPT\n"
            f"- direction: {direction}\n"
            f"- hypothesis: {hypothesis}\n"
            f"- smoke_run: {smoke_run}\n"
            f"- dev_run: {dev_run_dir}\n"
            f"- baseline_dev_run: {baseline_dev_run}\n"
            f"- holdout_run: {holdout_run_dir}\n"
            f"- holdout_check: {holdout_reason}\n"
            f"- score_diff: {diff:+.2f}\n"
            f"- elite_saved: {len(elite_saved)}\n"
        )
        write_decision(dev_run_dir, decision)
        if holdout_run_dir:
            write_decision(holdout_run_dir, decision)
        update_candidate_scorecard(
            cand_path,
            final_decision="ACCEPT",
            status="promoted_baseline",
            score_diff=diff,
            decision_run=dev_run_dir,
            holdout_run=holdout_run_dir,
            elite_saved=len(elite_saved),
        )
        record_round(
            round_no=0, direction=direction, target_failures=target_failures,
            smoke_score=smoke_score, dev_score=dev_summary.get("score"),
            holdout_score=holdout_summary.get("score"), accept=True, score_diff=diff,
        )
        return True
    else:
        print(f"\n{C_RED}❌ 回滾：新提示詞未滿足 10 大接受條件。差距為 {diff:+.2f} 分。{C_RESET}")
        print(f"  - 正在將 prompts/current.md 回滾至 baseline.md 冠軍版本。")
        write_file(PROMPT_PATH, baseline_prompt)
        if dev_governance_notes:
            reason = "dev governance failed: " + "；".join(dev_governance_notes)
        else:
            reason = "dev acceptance failed" if holdout_accept else f"holdout failed: {holdout_reason}"
        decision = (
            "# Decision\n\n"
            "- decision: REVERT\n"
            f"- direction: {direction}\n"
            f"- hypothesis: {hypothesis}\n"
            f"- reason: {reason}\n"
            f"- smoke_run: {smoke_run}\n"
            f"- dev_run: {dev_run_dir}\n"
            f"- baseline_dev_run: {baseline_dev_run}\n"
            f"- holdout_run: {holdout_run_dir}\n"
            f"- score_diff: {diff:+.2f}\n"
            f"- elite_saved: {len(elite_saved)}\n"
        )
        write_decision(dev_run_dir, decision)
        if holdout_run_dir:
            write_decision(holdout_run_dir, decision)
        update_candidate_scorecard(
            cand_path,
            final_decision="REVERT",
            status="reverted",
            reject_reasons=[reason],
            score_diff=diff,
            decision_run=dev_run_dir,
            holdout_run=holdout_run_dir,
            elite_saved=len(elite_saved),
        )
        record_round(
            round_no=0, direction=direction, target_failures=target_failures,
            smoke_score=smoke_score, dev_score=dev_summary.get("score"),
            holdout_score=holdout_summary.get("score"), accept=False, score_diff=diff,
        )
        return False

if __name__ == "__main__":
    run_opt_pass(**parse_run_opt_args(sys.argv[1:]))
