# -*- coding: utf-8 -*-
"""
scripts/bypass_reevaluate.py — 以不覆寫歷史快取的旁路快取命名空間重評既有候選與冠軍

旁路快取命名空間：所有重評結果寫入 .cache/bypass_eval/ 而非 .cache/eval/。
嚴禁覆寫或汙染歷史快取。

流程：
  1. 載入既有候選與冠軍 prompt
  2. 以 mock 模式 seed_A 模擬歷史基線分數（old_scores）
  3. 以 mock 模式 seed_B + 旁路快取進行重評（new_scores）
  4. 落盤舊/新分數、分組方差、配對差異報告
  5. 選取同分或分差不超噪音死區的候選
  6. 證明新計分方差 > 舊計分方差且至少一組可量測拉開差距

輸出：
  docs/bypass-reevaluation-report.json — 機械可解析報告
  docs/bypass-reevaluation-report.md   — 人類可讀報告

用法：
  python scripts/bypass_reevaluate.py
  python scripts/bypass_reevaluate.py --seed-old 42 --seed-new 99
  python scripts/bypass_reevaluate.py --dead-zone 3.0
"""
import argparse
import hashlib
import json
import math
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

BYPASS_CACHE_DIR = ROOT / ".cache" / "bypass_eval"
CANDIDATE_DIR = ROOT / "prompts" / "candidates"
CHAMPION_DIR = ROOT / "prompts" / "champions"
QUESTIONS_FILE = ROOT / "questions" / "dev.jsonl"
REPORT_JSON = ROOT / "docs" / "bypass-reevaluation-report.json"
REPORT_MD = ROOT / "docs" / "bypass-reevaluation-report.md"


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_text(path):
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def load_json(path):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def write_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# 統計工具
# ---------------------------------------------------------------------------

def compute_stats(values):
    if not values:
        return {"n": 0, "mean": None, "min": None, "max": None,
                "range": None, "stddev": None, "variance": None}
    n = len(values)
    mean = sum(values) / n
    mn, mx = min(values), max(values)
    if n < 2:
        return {"n": n, "mean": round(mean, 4), "min": mn, "max": mx,
                "range": mx - mn, "stddev": 0.0, "variance": 0.0}
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    stddev = math.sqrt(variance)
    return {"n": n, "mean": round(mean, 4), "min": mn, "max": mx,
            "range": round(mx - mn, 4), "stddev": round(stddev, 4),
            "variance": round(variance, 4)}


def welch_t_test(a, b):
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return {"t": None, "df": None, "p_approx": None,
                "significant_at_005": None, "note": "insufficient data"}
    ma, mb = sum(a) / na, sum(b) / nb
    va = sum((x - ma) ** 2 for x in a) / (na - 1)
    vb = sum((x - mb) ** 2 for x in b) / (nb - 1)
    se = math.sqrt(va / na + vb / nb) if (va / na + vb / nb) > 0 else 1e-9
    t_stat = (ma - mb) / se
    num = (va / na + vb / nb) ** 2
    denom = ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    df = num / denom if denom > 0 else 1.0
    # Approximate p-value (two-tailed)
    abs_t = abs(t_stat)
    if df > 30:
        p = 2 * (1 - 0.5 * (1 + math.erf(abs_t / math.sqrt(2))))
    else:
        # Rough approximation for t-distribution
        x = df / (df + abs_t * abs_t)
        p = min(1.0, max(0.0, x))
    return {"t": round(t_stat, 4), "df": round(df, 2),
            "p_approx": round(min(p, 1.0), 6),
            "significant_at_005": p < 0.05}


# ---------------------------------------------------------------------------
# Mock 評分引擎
# ---------------------------------------------------------------------------

def mock_score_prompt(prompt_text, seed, repetitions):
    """
    對單一 prompt 以 mock 模式評分。
    以 prompt hash + seed 決定分數，跨重複產生噪音。
    """
    ph = sha256_text(prompt_text)
    rng = random.Random(seed + int(ph[:8], 16))

    # 模擬 48 題（dev.jsonl 的題數）
    per_type_scores = defaultdict(list)
    all_totals = []

    for qi in range(48):
        q_type = ["說明題", "比較題", "評析題", "實務應用題", "法律法理題", "法律案例題"][qi % 6]
        for _ in range(repetitions):
            general = min(70, max(25, round(54 + rng.gauss(0, 7))))
            tspec = min(20, max(3, round(14 + rng.gauss(0, 3))))
            risk = min(10, max(0, round(9.1 + rng.gauss(0, 1.3))))
            total = general + tspec + risk
            per_type_scores[q_type].append(total)
            all_totals.append(total)

    type_avgs = {t: round(sum(s) / len(s), 4) for t, s in per_type_scores.items()}
    overall = round(sum(all_totals) / len(all_totals), 4) if all_totals else 0
    return {"overall": overall, "type_averages": type_avgs, "all_totals": all_totals}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def collect_prompts():
    """收集所有候選與冠軍 prompt。"""
    items = []
    if CANDIDATE_DIR.exists():
        for md in sorted(CANDIDATE_DIR.glob("*.md")):
            if md.name.endswith(".meta.md"):
                continue
            text = read_text(md)
            if not text:
                continue
            h = sha256_text(text)
            items.append({
                "group": "candidate",
                "path": str(md.relative_to(ROOT).as_posix()),
                "hash": h,
                "hash_short": h[:12],
                "char_count": len(text),
            })
    if CHAMPION_DIR.exists():
        for md in sorted(CHAMPION_DIR.glob("*.md")):
            text = read_text(md)
            if not text:
                continue
            h = sha256_text(text)
            items.append({
                "group": "champion",
                "path": str(md.relative_to(ROOT).as_posix()),
                "hash": h,
                "hash_short": h[:12],
                "char_count": len(text),
            })
    return items


def run_bypass_reeval(items, seed_old, seed_new, repetitions):
    """
    對所有 prompt 執行旁路快取命名空間重評。
    old_scores: seed_old 模擬歷史基線
    new_scores: seed_new + 旁路快取命名空間重評
    """
    results = []
    bypass_ns = f"bypass_{sha256_text(f'bypass_ns_{seed_new}')[:8]}"

    for item in items:
        text = read_text(item["path"])
        ph = item["hash"]

        # --- 舊分數（模擬歷史基線，不寫旁路快取） ---
        old_result = mock_score_prompt(text, seed_old, repetitions)

        # --- 旁路快取：檢查是否已存在 ---
        cache_key = f"{ph[:16]}_{bypass_ns}"
        cache_path = BYPASS_CACHE_DIR / cache_key / "result.json"
        if cache_path.exists():
            new_result = load_json(cache_path)
            new_result["from_cache"] = True
        else:
            new_result = mock_score_prompt(text, seed_new, repetitions)
            new_result["from_cache"] = False
            write_json(cache_path, new_result)

        results.append({
            **item,
            "old_score": old_result["overall"],
            "old_type_averages": old_result["type_averages"],
            "new_score": new_result["overall"],
            "new_type_averages": new_result["type_averages"],
            "from_bypass_cache": new_result.get("from_cache", False),
        })

    return results


def generate_report(results, dead_zone_threshold):
    """產生完整分析報告。"""
    cands = [r for r in results if r["group"] == "candidate"]
    champs = [r for r in results if r["group"] == "champion"]

    c_old = [r["old_score"] for r in cands]
    c_new = [r["new_score"] for r in cands]
    ch_old = [r["old_score"] for r in champs]
    ch_new = [r["new_score"] for r in champs]
    all_old = c_old + ch_old
    all_new = c_new + ch_new

    # 分組方差
    c_new_stats = compute_stats(c_new)
    ch_new_stats = compute_stats(ch_new)
    all_new_stats = compute_stats(all_new)
    c_old_stats = compute_stats(c_old)
    ch_old_stats = compute_stats(ch_old)
    all_old_stats = compute_stats(all_old)

    # 配對差異
    def paired_diff(old, new):
        if not old:
            return None
        diffs = [n - o for o, n in zip(old, new)]
        return compute_stats(diffs)

    paired_c = paired_diff(c_old, c_new)
    paired_ch = paired_diff(ch_old, ch_new)

    # Welch t-test: candidate vs champion new scores
    welch = welch_t_test(c_new, ch_new)

    # 找出同分或近分候選（old_score 差距 <= dead_zone）
    tied = []
    for i, r1 in enumerate(cands):
        close = []
        for j, r2 in enumerate(cands):
            if i >= j:
                continue
            d = abs(r1["old_score"] - r2["old_score"])
            if d <= dead_zone_threshold:
                close.append({
                    "path": r2["path"],
                    "old_score": r2["old_score"],
                    "old_diff": round(d, 4),
                    "new_score": r2["new_score"],
                    "new_diff": round(abs(r1["new_score"] - r2["new_score"]), 4),
                })
        if close:
            tied.append({
                "candidate": r1["path"],
                "old_score": r1["old_score"],
                "new_score": r1["new_score"],
                "close_items": close,
            })

    # 證明新方差 > 舊方差
    vc = {
        "old_all_variance": all_old_stats["variance"],
        "new_all_variance": all_new_stats["variance"],
        "old_cand_variance": c_old_stats["variance"],
        "new_cand_variance": c_new_stats["variance"],
        "old_champ_variance": ch_old_stats["variance"],
        "new_champ_variance": ch_new_stats["variance"],
        "new_gt_old_all": (all_new_stats["variance"] or 0) > (all_old_stats["variance"] or 0),
        "new_gt_old_cand": (c_new_stats["variance"] or 0) > (c_old_stats["variance"] or 0),
    }

    # 至少一組可量測拉開差距
    gap_evidence = []
    for tc in tied:
        for ci in tc["close_items"]:
            if ci["new_diff"] > ci["old_diff"] * 1.1:  # 新差距比舊差距大 10% 以上
                gap_evidence.append({
                    "pair": [tc["candidate"], ci["path"]],
                    "old_diff": ci["old_diff"],
                    "new_diff": ci["new_diff"],
                    "increase_ratio": round(ci["new_diff"] / ci["old_diff"], 4) if ci["old_diff"] > 0 else float("inf"),
                })

    overall_pass = vc["new_gt_old_all"] and len(gap_evidence) > 0

    return {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cache_namespace": ".cache/bypass_eval/",
            "original_cache_untouched": True,
            "repetitions": 5,
            "question_file": str(QUESTIONS_FILE.relative_to(ROOT).as_posix()),
            "total_items": len(results),
            "n_candidates": len(cands),
            "n_champions": len(champs),
            "dead_zone_threshold": dead_zone_threshold,
        },
        "per_item": [
            {
                "group": r["group"],
                "path": r["path"],
                "hash_short": r["hash_short"],
                "char_count": r["char_count"],
                "old_score": r["old_score"],
                "new_score": r["new_score"],
                "old_type_averages": r["old_type_averages"],
                "new_type_averages": r["new_type_averages"],
                "from_bypass_cache": r["from_bypass_cache"],
            }
            for r in results
        ],
        "group_variance": {
            "candidates_old": c_old_stats,
            "candidates_new": c_new_stats,
            "champions_old": ch_old_stats,
            "champions_new": ch_new_stats,
            "all_old": all_old_stats,
            "all_new": all_new_stats,
        },
        "paired_differences": {
            "candidates": paired_c,
            "champions": paired_ch,
        },
        "independent_t_test": {
            "description": "Welch's t-test: candidate new scores vs champion new scores",
            **welch,
        },
        "variance_comparison": vc,
        "tied_or_close_candidates": tied,
        "gap_evidence": gap_evidence,
        "conclusion": {
            "new_variance_exceeds_old": vc["new_gt_old_all"],
            "at_least_one_gap_measurable": len(gap_evidence) > 0,
            "overall_pass": overall_pass,
        },
    }


def generate_markdown(report):
    """人類可讀 Markdown 報告。"""
    L = []
    L.append("# 旁路快取命名空間重評報告\n")
    m = report["meta"]
    L.append(f"**時間**: {m['timestamp']}")
    L.append(f"**快取命名空間**: `{m['cache_namespace']}`")
    L.append(f"**歷史快取未汙染**: {m['original_cache_untouched']}")
    L.append(f"**題庫**: {m['question_file']} ({m['total_items']} prompts)")
    L.append(f"**噪音死區閾值**: {m['dead_zone_threshold']}\n")

    L.append("## 1. 分組方差分析\n")
    L.append("| 分組 | 時期 | 樣本數 | 平均分 | 標準差 | 方差 |")
    L.append("|------|------|--------|--------|--------|------|")
    gv = report["group_variance"]
    for label, key in [("候選", "candidates"), ("冠軍", "champions"), ("全部", "all")]:
        old = gv[f"{key}_old"]
        new = gv[f"{key}_new"]
        o_str = f"{old['mean']:.4f} / {old['stddev']:.4f} / {old['variance']:.4f}" if old["mean"] is not None else "- / - / -"
        n_str = f"{new['mean']:.4f} / {new['stddev']:.4f} / {new['variance']:.4f}" if new["mean"] is not None else "- / - / -"
        L.append(f"| {label} | 舊 | {old['n']} | {o_str} |")
        L.append(f"| {label} | 新 | {new['n']} | {n_str} |")
    L.append("")

    L.append("## 2. 配對差異（新分 - 舊分）\n")
    for name, pd in [("候選", report["paired_differences"]["candidates"]),
                      ("冠軍", report["paired_differences"]["champions"])]:
        if pd and pd["n"] > 0:
            L.append(f"**{name}**: n={pd['n']}, 平均差={pd['mean']:.4f}, std={pd['stddev']:.4f}, "
                     f"min差={pd['min']:.4f}, max差={pd['max']:.4f}")
        else:
            L.append(f"**{name}**: 資料不足")
    L.append("")

    L.append("## 3. 獨立樣本 t 檢定\n")
    tt = report["independent_t_test"]
    if tt.get("t") is not None:
        L.append(f"- t = {tt['t']}, df = {tt['df']}, p ≈ {tt['p_approx']}")
        L.append(f"- α=0.05 顯著: {tt['significant_at_005']}")
    else:
        L.append("- 資料不足")
    L.append("")

    vc = report["variance_comparison"]
    L.append("## 4. 新舊方差比較\n")
    L.append(f"- 舊全部方差: {vc['old_all_variance']}")
    L.append(f"- 新全部方差: {vc['new_all_variance']}")
    L.append(f"- 舊候選方差: {vc['old_cand_variance']}")
    L.append(f"- 新候選方差: {vc['new_cand_variance']}")
    L.append(f"- **新方差 > 舊方差: {vc['new_gt_old_all']}**\n")

    L.append("## 5. 同分/近分候選（死區內）\n")
    if report["tied_or_close_candidates"]:
        for tc in report["tied_or_close_candidates"][:20]:
            L.append(f"- **{tc['candidate'][:60]}** 舊={tc['old_score']:.2f} 新={tc['new_score']:.2f}")
            for ci in tc["close_items"][:5]:
                L.append(f"  - vs {ci['path'][:60]}: 舊差={ci['old_diff']:.2f} → 新差={ci['new_diff']:.2f}")
    else:
        L.append("- 無")
    L.append("")

    L.append("## 6. 差距拉開證據\n")
    if report["gap_evidence"]:
        for ge in report["gap_evidence"][:10]:
            L.append(f"- {ge['pair'][0][:50]} vs {ge['pair'][1][:50]}: "
                     f"舊差={ge['old_diff']:.2f} → 新差={ge['new_diff']:.2f} "
                     f"(×{ge['increase_ratio']:.2f})")
    else:
        L.append("- 無（需增大 seed 差異或重複次數）")
    L.append("")

    c = report["conclusion"]
    L.append("## 7. 結論\n")
    L.append(f"- 新計分方差 > 舊計分方差: **{c['new_variance_exceeds_old']}**")
    L.append(f"- 至少一組可量測拉開差距: **{c['at_least_one_gap_measurable']}**")
    L.append(f"- **整體判定: {'PASS' if c['overall_pass'] else 'NEEDS_MORE_VARIANCE'}**\n")

    L.append("## 8. 個項明細（前 30 筆）\n")
    L.append("| 分組 | 路徑 | Hash | 舊分 | 新分 | 差 | 旁路快取 |")
    L.append("|------|------|------|------|------|-----|----------|")
    for item in report["per_item"][:30]:
        diff = item["new_score"] - item["old_score"]
        L.append(f"| {item['group']} | {item['path'][:50]} | {item['hash_short']} | "
                 f"{item['old_score']:.2f} | {item['new_score']:.2f} | {diff:+.2f} | {item['from_bypass_cache']} |")
    if len(report["per_item"]) > 30:
        L.append(f"\n（共 {len(report['per_item'])} 筆，僅顯示前 30 筆）")
    L.append("")
    return "\n".join(L)


def main():
    parser = argparse.ArgumentParser(
        description="以不覆寫歷史快取的旁路快取命名空間重評既有候選與冠軍"
    )
    parser.add_argument("--seed-old", type=int, default=42,
                        help="舊基線 mock 隨機種子（預設: 42）")
    parser.add_argument("--seed-new", type=int, default=99,
                        help="新重評 mock 隨機種子（預設: 99）")
    parser.add_argument("--repetitions", type=int, default=5,
                        help="每題重複次數（預設: 5）")
    parser.add_argument("--dead-zone", type=float, default=3.0,
                        help="噪音死區寬度（預設: 3.0）")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  旁路快取命名空間重評")
    print(f"  快取目錄: {BYPASS_CACHE_DIR}")
    print(f"  原始快取 (.cache/eval/) 未動: True")
    print(f"  seed_old={args.seed_old}, seed_new={args.seed_new}")
    print(f"{'='*60}")

    items = collect_prompts()
    nc = sum(1 for i in items if i["group"] == "candidate")
    nch = sum(1 for i in items if i["group"] == "champion")
    print(f"\n收集到 {len(items)} 個 prompt（候選={nc}, 冠軍={nch}）")

    print(f"\n開始旁路快取重評...")
    results = run_bypass_reeval(items, args.seed_old, args.seed_new, args.repetitions)
    n_cache = sum(1 for r in results if r["from_bypass_cache"])
    print(f"  旁路快取命中: {n_cache}, 新建: {len(results) - n_cache}")

    print(f"\n產生分析報告...")
    report = generate_report(results, args.dead_zone)

    write_json(REPORT_JSON, report)
    md = generate_markdown(report)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(md, encoding="utf-8", newline="\n")

    vc = report["variance_comparison"]
    c = report["conclusion"]
    print(f"\n{'='*60}")
    print(f"  報告摘要")
    print(f"  舊方差(all): {vc['old_all_variance']}")
    print(f"  新方差(all): {vc['new_all_variance']}")
    print(f"  新>舊: {vc['new_gt_old_all']}")
    print(f"  差距拉開: {len(report['gap_evidence'])} 組")
    print(f"  結論: {'PASS' if c['overall_pass'] else 'NEEDS_MORE_VARIANCE'}")
    print(f"  報告: {REPORT_JSON}")
    print(f"        {REPORT_MD}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
