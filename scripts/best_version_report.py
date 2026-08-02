# -*- coding: utf-8 -*-
"""
scripts/best_version_report.py — 最佳版本證據報告產生器。

從有效候選比較、評測明細、淘汰決策、champion 與執行紀錄組裝
單一機械可解析且人可讀的結構化輸出，明確列出：
  - winner（冠軍候選）
  - 可直接採用的提示詞／流程
  - 品質分數與量測基準
  - 逐候選比較
  - 重現設定
  - 證據檔案位置

用法：
  python scripts/best_version_report.py
  python scripts/best_version_report.py --out docs/best_version_report.md
  python scripts/best_version_report.py --limit 20
"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import time

if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASELINE_META_PATH = os.path.join(ROOT, "prompts", "baseline.meta.json")
CHAMPIONS_DIR = os.path.join(ROOT, "prompts", "champions")
CANDIDATES_DIR = os.path.join(ROOT, "prompts", "candidates")
EVOLUTION_LOG_PATH = os.path.join(ROOT, "evolution_log.jsonl")
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
RUNS_DIR = os.path.join(ROOT, "runs")


def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return json.load(f)


def read_text(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def load_baseline_meta():
    return load_json(BASELINE_META_PATH, {})


def load_champion_metas():
    champions = []
    if not os.path.isdir(CHAMPIONS_DIR):
        return champions
    for name in sorted(os.listdir(CHAMPIONS_DIR)):
        if name.endswith(".meta.json"):
            meta = load_json(os.path.join(CHAMPIONS_DIR, name))
            if meta:
                meta["_meta_file"] = repo_rel(os.path.join(CHAMPIONS_DIR, name))
                champions.append(meta)
    return champions


def load_candidate_scorecards(limit=None):
    cards = []
    if not os.path.isdir(CANDIDATES_DIR):
        return cards
    count = 0
    for name in sorted(os.listdir(CANDIDATES_DIR)):
        if not name.endswith(".scorecard.json"):
            continue
        card = load_json(os.path.join(CANDIDATES_DIR, name))
        if not card:
            continue
        card["_scorecard_file"] = repo_rel(os.path.join(CANDIDATES_DIR, name))
        cards.append(card)
        count += 1
        if limit and count >= limit:
            break
    return cards


def load_evolution_summary():
    rows = read_jsonl(EVOLUTION_LOG_PATH)
    sessions = []
    current = None
    for row in rows:
        event = row.get("event")
        if event == "start":
            current = {
                "start": row.get("timestamp", ""),
                "args": row.get("args", {}),
                "baseline_dev_score": row.get("baseline_dev_score", 0.0),
                "rounds": [],
                "promotions": 0,
            }
        elif event == "round_complete" and current is not None:
            current["rounds"].append(row)
            if row.get("promoted"):
                current["promotions"] += 1
        elif event == "stop" and current is not None:
            current["stop"] = row.get("timestamp", "")
            current["stop_reason"] = row.get("reason", "")
            current["best_score"] = row.get("best_score", 0.0)
            current["total_api_calls"] = row.get("estimated_api_calls_total", 0)
            current["elapsed"] = row.get("elapsed_seconds", 0.0)
            sessions.append(current)
            current = None
    if current is not None:
        sessions.append(current)
    return sessions


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return _parse_config_simple(CONFIG_PATH)
    except Exception:
        return {}


def _parse_config_simple(path):
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val:
                    result[key] = val
    return result


def classify_candidate(card):
    """回傳 ('accepted', 'rejected', 'pending') 其中之一。"""
    decision = card.get("final_decision", "")
    status = card.get("status", "")
    if decision in ("ACCEPT", "SPECIALTY_RETAINED"):
        return "accepted"
    if decision in ("REVERT", "REJECT") or status.startswith("rejected"):
        return "rejected"
    return "pending"


# ---------- 路徑正規化、證據驗證與重跑設定 ----------


def sha256_file(path):
    """計算檔案的 sha256 十六進位摘要。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_rel(path):
    """把任意路徑（絕對或相對、反斜線分隔）轉成 repo 相對路徑（正斜線）。

    若路徑無法解析進 repo 內（例如在 repo 之外），回傳 None。
    回傳值一律為正斜線分隔，確保跨平台可存取。
    """
    if not path:
        return None
    text = str(path).replace("\\", "/")
    if os.path.isabs(text):
        abs_path = os.path.abspath(text)
    else:
        abs_path = os.path.abspath(os.path.join(ROOT, text))
    try:
        rel = os.path.relpath(abs_path, ROOT).replace("\\", "/")
    except ValueError:
        return None
    if rel == ".." or rel.startswith("../"):
        return None
    return rel


def display_path(value):
    """將路徑顯示為 repo 相對路徑；無法存取時顯示 '-'。"""
    rel = repo_rel(value)
    return rel if rel else "-"


def verify_evidence_file(path_rel, recorded_hash=None):
    """驗證單一證據檔：存在性、非空性、與已記錄雜湊一致性。

    回傳 dict，欄位皆可機械解析。
    """
    abs_path = os.path.join(ROOT, path_rel) if path_rel else ""
    result = {
        "path": path_rel or "",
        "exists": False,
        "nonempty": False,
        "recorded_hash": recorded_hash or "",
        "actual_hash": "",
        "hash_match": None,
    }
    if path_rel and os.path.isfile(abs_path):
        result["exists"] = True
        result["nonempty"] = os.path.getsize(abs_path) > 0
        if recorded_hash:
            result["actual_hash"] = sha256_file(abs_path)
            result["hash_match"] = result["actual_hash"] == recorded_hash
    result["ok"] = (
        result["exists"]
        and result["nonempty"]
        and (result["hash_match"] is True or not recorded_hash)
    )
    return result


def collect_evidence_verification(baseline_meta, champions, cards):
    """在產生報告時，重新驗證所有被引用的證據檔。

    含核心檔案、baseline 提示詞（比對已記錄 prompt_hash）、
    題型冠軍 meta 與提示詞、候選 scorecard 與候選提示詞。
    """
    checks = []
    for rel in (
        repo_rel(BASELINE_META_PATH),
        repo_rel(EVOLUTION_LOG_PATH),
        repo_rel(CONFIG_PATH),
    ):
        if rel:
            checks.append(verify_evidence_file(rel))
    if baseline_meta:
        prompt_rel = repo_rel(baseline_meta.get("prompt_path")) or "prompts/baseline.md"
        checks.append(verify_evidence_file(prompt_rel, baseline_meta.get("prompt_hash")))
    for ch in champions:
        meta_rel = ch.get("_meta_file")
        if meta_rel:
            checks.append(verify_evidence_file(meta_rel))
        prompt_rel = repo_rel(ch.get("champion_prompt_path"))
        if prompt_rel:
            checks.append(verify_evidence_file(prompt_rel, ch.get("candidate_hash")))
    for card in cards:
        sc_rel = card.get("_scorecard_file")
        if sc_rel:
            checks.append(verify_evidence_file(sc_rel))
        cand_rel = repo_rel(card.get("candidate_path"))
        if cand_rel:
            checks.append(verify_evidence_file(cand_rel, card.get("candidate_hash")))
    return checks


def collect_git_commit():
    """取得目前 repo 的 git commit（唯讀）。失敗時回傳空字串。"""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ""


def collect_rerun_settings(baseline_meta, champions, config, sessions):
    """收集重跑所需的設定：winner 輸入、評測器／模型、seed、版本／commit、
    候選識別、執行時間。
    """
    api = config.get("api", {}) if config else {}
    settings = {
        "winner_input": {},
        "evaluator": {
            "url": api.get("url", ""),
            "model": api.get("model", ""),
            "evaluate_script": "scripts/evaluate.py",
            "compare_script": "scripts/compare_runs.py",
            "gatekeeper_script": "scripts/gatekeeper.py",
        },
        "seed": os.environ.get("PYTHONHASHSEED", "not set"),
        "version": {"commit": collect_git_commit()},
        "candidate_identification": [],
        "execution_time": {},
    }
    if baseline_meta:
        settings["winner_input"] = {
            "prompt_path": repo_rel(baseline_meta.get("prompt_path")) or "prompts/baseline.md",
            "prompt_hash": baseline_meta.get("prompt_hash", ""),
        }
    for ch in champions:
        settings["candidate_identification"].append({
            "type": ch.get("type", ""),
            "prompt_path": repo_rel(ch.get("champion_prompt_path")) or "",
            "candidate_hash": ch.get("candidate_hash", ""),
        })
    if sessions:
        settings["execution_time"] = {
            "sessions": len(sessions),
            "first_start": sessions[0].get("start", ""),
            "last_stop": sessions[-1].get("stop", ""),
            "total_elapsed_seconds": round(
                sum(s.get("elapsed", 0) for s in sessions), 2
            ),
        }
    return settings


# ---------- 證據完整性閘門 ----------

EVIDENCE_INTEGRITY_ERRORS = []


def verify_evidence_integrity(baseline_meta, champions, cards, sessions, config):
    """驗證冠軍選優所需的關鍵證據是否齊全。

    回傳 (is_valid: bool, errors: list[str])：
    - is_valid: True 表示所有關鍵證據齊全，可安全選優。
    - errors: 缺失的證據類型描述列表。

    缺少任一項關鍵證據時，報告必須輸出 inconclusive 並拒絕選優。
    """
    global EVIDENCE_INTEGRITY_ERRORS
    errors = []

    # 1. 可讀提示詞／流程：baseline_meta 必須存在且含有 prompt_hash
    has_prompt = False
    if baseline_meta:
        prompt_hash = baseline_meta.get("prompt_hash", "")
        if isinstance(prompt_hash, str) and prompt_hash.strip():
            has_prompt = True
    if not has_prompt:
        errors.append("缺少可讀提示詞／流程（baseline.meta.json 中無有效 prompt_hash）")

    # 2. 可驗證分數與量測基準：baseline_meta 必須含有 dev_avg 和 holdout_avg
    has_scores = False
    if baseline_meta:
        dev_avg = baseline_meta.get("dev_avg")
        holdout_avg = baseline_meta.get("holdout_avg")
        try:
            dev_valid = dev_avg is not None and math.isfinite(float(dev_avg))
            holdout_valid = holdout_avg is not None and math.isfinite(float(holdout_avg))
            has_scores = dev_valid and holdout_valid
        except (TypeError, ValueError):
            has_scores = False
    if not has_scores:
        errors.append("缺少可驗證分數與量測基準（baseline.meta.json 中無有效 dev_avg/holdout_avg）")

    # 3. 有效比較對象／淘汰依據：至少有一個候選且有有效的決策記錄
    has_comparison = False
    if cards:
        accepted, rejected, pending = classify_candidates(cards)
        has_comparison = len(accepted) > 0 or len(rejected) > 0
    if not has_comparison:
        errors.append("缺少有效比較對象／淘汰依據（無候選分數卡或無有效決策記錄）")

    # 4. 重現設定與執行紀錄：
    #    4a. 至少有一個完整的演化 session（含 start + stop）
    #    4b. config.yaml 可讀取
    has_reproduction = False
    if sessions:
        complete_sessions = [
            s for s in sessions
            if s.get("start") and s.get("stop")
        ]
        has_reproduction = len(complete_sessions) > 0
    if not has_reproduction:
        errors.append("缺少重現設定與執行紀錄（無完整演化 session）")

    has_config = False
    if config:
        has_config = len(config) > 0
    if not has_config:
        errors.append("缺少重現設定（config.yaml 無法讀取或為空）")

    EVIDENCE_INTEGRITY_ERRORS = errors
    return len(errors) == 0, errors


def classify_candidates(cards):
    accepted = []
    rejected = []
    pending = []
    for card in cards:
        kind = classify_candidate(card)
        if kind == "accepted":
            accepted.append(card)
        elif kind == "rejected":
            rejected.append(card)
        else:
            pending.append(card)
    return accepted, rejected, pending


def find_smoke_run():
    if not os.path.isdir(RUNS_DIR):
        return None
    for name in sorted(os.listdir(RUNS_DIR)):
        if name == "latest":
            continue
        run_dir = os.path.join(RUNS_DIR, name)
        if not os.path.isdir(run_dir):
            continue
        summary = load_json(os.path.join(run_dir, "summary.json"))
        if not summary:
            continue
        qf = summary.get("question_file", "")
        if "smoke" in qf.lower():
            return {"name": name, "summary": summary, "path": os.path.relpath(run_dir, ROOT)}
    return None


def format_table(headers, rows):
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def build_json_block(data):
    return "```json\n" + json.dumps(data, ensure_ascii=False, indent=2) + "\n```"


def build_champion_section(baseline_meta, champions):
    lines = []
    lines.append("## 1. Winner（冠軍）")
    lines.append("")

    if baseline_meta:
        prompt_hash = baseline_meta.get("prompt_hash", "-")
        dev_avg = baseline_meta.get("dev_avg", "-")
        holdout_avg = baseline_meta.get("holdout_avg", "-")
        dev_run = baseline_meta.get("dev_run", "-")
        holdout_run = baseline_meta.get("holdout_run", "-")
        lines.append(f"- **全域冠軍 prompt hash**：`{prompt_hash}`")
        lines.append(f"- **dev 均分**：{dev_avg}")
        lines.append(f"- **holdout 均分**：{holdout_avg}")
        lines.append(f"- **dev run**：`{display_path(dev_run)}`")
        lines.append(f"- **holdout run**：`{display_path(holdout_run)}`")
    else:
        lines.append("_尚無全域冠軍_")

    if champions:
        lines.append("")
        lines.append("### 題型冠軍")
        lines.append("")
        table_rows = []
        for ch in champions:
            ch_type = ch.get("type", "-")
            ch_score = ch.get("candidate_avg", ch.get("diff", "-"))
            ch_hash = ch.get("candidate_hash", "-")[:12]
            ch_decision = ch.get("decision", "-")
            ch_prompt = display_path(ch.get("champion_prompt_path"))
            table_rows.append([ch_type, ch_score, ch_hash, ch_decision, ch_prompt])
        lines.append(format_table(
            ["題型", "均分/提升", "hash", "決策", "提示詞路徑"],
            table_rows,
        ))
    lines.append("")
    return lines


def build_process_section(sessions):
    lines = []
    lines.append("## 2. 可直接採用的流程")
    lines.append("")
    lines.append("### 演化流程概述")
    lines.append("")

    if sessions:
        total_rounds = sum(len(s.get("rounds", [])) for s in sessions)
        total_promotions = sum(s.get("promotions", 0) for s in sessions)
        total_api_calls = sum(s.get("total_api_calls", 0) for s in sessions)
        total_elapsed = sum(s.get("elapsed", 0) for s in sessions)
        lines.append(f"- 演化 session 數：{len(sessions)}")
        lines.append(f"- 總輪次：{total_rounds}")
        lines.append(f"- 成功晉升次數：{total_promotions}")
        lines.append(f"- 總 API 呼叫數：{total_api_calls}")
        lines.append(f"- 總耗時：{total_elapsed / 3600:.2f} 小時")
    else:
        lines.append("_尚無演化記錄_")

    lines.append("")
    lines.append("### 晉升條件（acceptance criteria）")
    lines.append("")
    lines.append("| # | 條件 | 門檻 |")
    lines.append("| --- | --- | --- |")
    lines.append("| 1 | 總平均分晉升 | >= +2.0 分，或均分>=92且不退步 |")
    lines.append("| 2 | 單項退步限制 | 退步 <= 3.0 分 |")
    lines.append("| 3 | 風險控制 | strict: 100%；pragmatic: >=90%且不低於baseline |")
    lines.append("| 4 | 字數合格率 | >= 85%（dev/holdout） |")
    lines.append("")
    return lines


def build_scores_section(baseline_meta, champions):
    lines = []
    lines.append("## 3. 品質分數與量測基準")
    lines.append("")

    lines.append("### 全域分數")
    lines.append("")
    if baseline_meta:
        table_rows = [
            ["smoke", baseline_meta.get("smoke_avg", "-")],
            ["dev", baseline_meta.get("dev_avg", "-")],
            ["holdout", baseline_meta.get("holdout_avg", "-")],
        ]
        lines.append(format_table(["資料集", "均分"], table_rows))
    else:
        lines.append("_無基準分數_")
    lines.append("")

    lines.append("### 題型冠軍分數")
    lines.append("")
    if champions:
        table_rows = []
        for ch in champions:
            ch_type = ch.get("type", "-")
            baseline_avg = ch.get("baseline_avg", "-")
            candidate_avg = ch.get("candidate_avg", "-")
            diff = ch.get("diff", "-")
            risk = ch.get("risk_rate", "-")
            table_rows.append([ch_type, baseline_avg, candidate_avg, diff, risk])
        lines.append(format_table(
            ["題型", "baseline 均分", "候選均分", "差異", "風險滿分率"],
            table_rows,
        ))
    else:
        lines.append("_無題型冠軍_")
    lines.append("")
    return lines


def build_candidate_comparison_section(cards, limit):
    lines = []
    lines.append("## 4. 逐候選比較")
    lines.append("")

    accepted, rejected, pending = classify_candidates(cards)
    lines.append(f"- ACCEPTED：{len(accepted)}")
    lines.append(f"- REJECTED：{len(rejected)}")
    lines.append(f"- PENDING/其他：{len(pending)}")
    lines.append("")

    display_cards = cards[:limit] if limit else cards
    if display_cards:
        table_rows = []
        for card in display_cards:
            decision = card.get("final_decision", card.get("status", "-"))
            direction = card.get("direction", "-")
            target = ",".join(card.get("target_failures", [])) or "-"
            smoke_score = "-"
            dev_score = "-"
            holdout_score = "-"
            smoke_data = card.get("smoke") or {}
            dev_data = card.get("dev") or {}
            holdout_data = card.get("holdout") or {}
            if smoke_data.get("score") is not None:
                smoke_score = f"{smoke_data['score']:.1f}"
            if dev_data.get("score") is not None:
                dev_score = f"{dev_data['score']:.1f}"
            if holdout_data.get("score") is not None:
                holdout_score = f"{holdout_data['score']:.1f}"
            reject_reasons = card.get("reject_reasons", [])
            reason = reject_reasons[0] if reject_reasons else "-"
            table_rows.append([
                decision, direction, target,
                smoke_score, dev_score, holdout_score,
                reason[:60],
            ])
        lines.append(format_table(
            ["決策", "方向", "目標 F",
             "smoke", "dev", "holdout", "淘汰理由"],
            table_rows,
        ))
    else:
        lines.append("_無候選記錄_")
    lines.append("")
    return lines


def build_reproduction_section(sessions, config):
    lines = []
    lines.append("## 5. 重現設定")
    lines.append("")

    if sessions:
        last_session = sessions[-1]
        args = last_session.get("args", {})
        lines.append("### 最近一次演化參數")
        lines.append("")
        table_rows = []
        key_map = [
            ("max_rounds", "最大輪次"),
            ("parallel", "平行數"),
            ("smoke_parallel", "smoke 平行數"),
            ("dev_parallel", "dev 平行數"),
            ("holdout_parallel", "holdout 平行數"),
            ("no_improve_limit", "無改善停止輪次"),
            ("same_failure_limit", "相同失敗停止輪次"),
            ("budget_usd", "預算 (USD)"),
            ("route_every", "路由間隔"),
            ("sleep_seconds", "休眠秒數"),
            ("round_timeout_seconds", "輪次逾時"),
            ("dry_run", "乾跑模式"),
        ]
        for key, label in key_map:
            val = args.get(key, "-")
            table_rows.append([label, str(val)])
        lines.append(format_table(["參數", "值"], table_rows))
    else:
        lines.append("_尚無演化記錄_")

    lines.append("")
    lines.append("### config.yaml 關鍵設定")
    lines.append("")
    if config:
        thresholds = config.get("thresholds", {})
        parallel = config.get("parallel", {})
        multi = config.get("multi_candidate", {})
        table_rows = []
        for k, v in thresholds.items():
            table_rows.append([f"thresholds.{k}", str(v)])
        for k, v in parallel.items():
            table_rows.append([f"parallel.{k}", str(v)])
        if multi:
            table_rows.append(["multi_candidate.enabled", str(multi.get("enabled", "-"))])
            table_rows.append(["multi_candidate.count", str(multi.get("count", "-"))])
        lines.append(format_table(["設定路徑", "值"], table_rows))
    else:
        lines.append("_無法讀取 config.yaml_")
    lines.append("")
    return lines


def build_evidence_section(baseline_meta, champions, cards, sessions):
    lines = []
    lines.append("## 6. 證據檔案位置")
    lines.append("")

    lines.append("### 核心檔案")
    lines.append("")
    evidence_files = []
    if baseline_meta:
        evidence_files.append(("baseline.meta.json", display_path(BASELINE_META_PATH)))
    evidence_files.append(("evolution_log.jsonl", display_path(EVOLUTION_LOG_PATH)))
    evidence_files.append(("config.yaml", display_path(CONFIG_PATH)))
    table_rows = [[name, path] for name, path in evidence_files]
    lines.append(format_table(["檔案", "路徑"], table_rows))
    lines.append("")

    if champions:
        lines.append("### 題型冠軍證據")
        lines.append("")
        table_rows = []
        for ch in champions:
            ch_type = ch.get("type", "-")
            meta_file = ch.get("_meta_file", "-")
            prompt_file = display_path(ch.get("champion_prompt_path"))
            dev_run = display_path(ch.get("dev_run"))
            table_rows.append([ch_type, meta_file, prompt_file, dev_run])
        lines.append(format_table(
            ["題型", "meta 檔", "提示詞", "dev run"],
            table_rows,
        ))
        lines.append("")

    lines.append("### 演化 session 證據")
    lines.append("")
    if sessions:
        table_rows = []
        for i, s in enumerate(sessions, 1):
            start = s.get("start", "-")
            stop = s.get("stop", "-")
            rounds_count = len(s.get("rounds", []))
            promotions = s.get("promotions", 0)
            best = s.get("best_score", 0)
            table_rows.append([
                i, start, stop, rounds_count, promotions, f"{best:.2f}",
            ])
        lines.append(format_table(
            ["session", "開始", "結束", "輪次", "晉升", "最佳分數"],
            table_rows,
        ))
    else:
        lines.append("_無演化 session_")
    lines.append("")
    return lines


def build_rerun_section(rerun_settings):
    lines = []
    lines.append("## 7. 重跑所需設定（Rerun Settings）")
    lines.append("")
    lines.append("以下欄位為重跑本選優所需的最小可複現設定：")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(rerun_settings, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    return lines


def build_evidence_verification_section(evidence_checks):
    lines = []
    lines.append("## 8. 證據驗證（產生時重新驗證）")
    lines.append("")
    ok_count = sum(1 for c in evidence_checks if c["ok"])
    lines.append(
        f"共 {len(evidence_checks)} 項證據，通過 {ok_count} 項，"
        f"未通過 {len(evidence_checks) - ok_count} 項。"
    )
    lines.append("")

    if not evidence_checks:
        lines.append("_無證據可驗證_")
        lines.append("")
        return lines

    table_rows = []
    for c in evidence_checks:
        exists = "✔" if c["exists"] else "✘"
        nonempty = "✔" if c["nonempty"] else "✘"
        if c["hash_match"] is True:
            hash_mark = "✔"
        elif c["hash_match"] is False:
            hash_mark = "✘"
        else:
            hash_mark = "-"
        table_rows.append([
            c["path"], exists, nonempty, hash_mark, "OK" if c["ok"] else "FAIL",
        ])
    lines.append(format_table(
        ["證據路徑", "存在", "非空", "雜湊一致", "結果"],
        table_rows,
    ))
    lines.append("")
    return lines


def build_report(limit=10):
    baseline_meta = load_baseline_meta()
    champions = load_champion_metas()
    cards = load_candidate_scorecards()
    sessions = load_evolution_summary()
    config = load_config()

    now = time.strftime("%Y-%m-%d %H:%M:%S")

    # 證據完整性閘門檢查
    is_valid, evidence_errors = verify_evidence_integrity(
        baseline_meta, champions, cards, sessions, config
    )

    # 產生時重新驗證所有證據引用 + 收集重跑所需設定
    evidence_checks = collect_evidence_verification(baseline_meta, champions, cards)
    verification_valid = all(c["ok"] for c in evidence_checks)
    rerun_settings = collect_rerun_settings(baseline_meta, champions, config, sessions)

    json_data = {
        "report_type": "best_version_evidence",
        "generated_at": now,
        "evidence_integrity": {
            "valid": is_valid,
            "errors": evidence_errors,
        },
        "evidence_verification": {
            "valid": verification_valid,
            "total": len(evidence_checks),
            "checks": evidence_checks,
        },
        "rerun_settings": rerun_settings,
        "champion": {
            "prompt_hash": baseline_meta.get("prompt_hash", "") if is_valid else "",
            "dev_avg": baseline_meta.get("dev_avg") if is_valid else None,
            "holdout_avg": baseline_meta.get("holdout_avg") if is_valid else None,
            "dev_run": display_path(baseline_meta.get("dev_run", "")) if is_valid else "",
            "holdout_run": display_path(baseline_meta.get("holdout_run", "")) if is_valid else "",
        },
        "type_champions": [
            {
                "type": ch.get("type", ""),
                "candidate_avg": ch.get("candidate_avg"),
                "diff": ch.get("diff"),
                "champion_prompt_path": display_path(ch.get("champion_prompt_path", "")),
                "dev_run": display_path(ch.get("dev_run", "")),
            }
            for ch in champions
        ] if is_valid else [],
        "candidates_summary": {
            "total": len(cards),
            "accepted": len([c for c in cards if classify_candidate(c) == "accepted"]),
            "rejected": len([c for c in cards if classify_candidate(c) == "rejected"]),
            "pending": len([c for c in cards if classify_candidate(c) == "pending"]),
        },
        "evolution_sessions": len(sessions),
        "config": {
            "thresholds": config.get("thresholds", {}),
            "parallel": config.get("parallel", {}),
            "multi_candidate": config.get("multi_candidate", {}),
        },
        "evidence_files": {
            "baseline_meta": display_path(BASELINE_META_PATH),
            "evolution_log": display_path(EVOLUTION_LOG_PATH),
            "config": display_path(CONFIG_PATH),
            "champions_dir": display_path(CHAMPIONS_DIR),
            "candidates_dir": display_path(CANDIDATES_DIR),
        },
    }

    lines = []
    lines.append("# 最佳版本證據報告")
    lines.append("")

    if not is_valid:
        lines.append("## ⚠️ 證據完整性閘門：INCONCLUSIVE")
        lines.append("")
        lines.append("**報告判定：inconclusive** — 缺少關鍵證據，拒絕選優。")
        lines.append("")
        lines.append("缺失項目：")
        for err in evidence_errors:
            lines.append(f"- {err}")
        lines.append("")
        lines.append("根據證據完整性閘門規則，缺少以下任一關鍵證據時，不得宣稱任何版本為最佳：")
        lines.append("1. 可讀提示詞／流程")
        lines.append("2. 可驗證分數與量測基準")
        lines.append("3. 有效比較對象／淘汰依據")
        lines.append("4. 重現設定與執行紀錄")
        lines.append("")
    else:
        lines.append("## ✅ 證據完整性閘門：PASS")
        lines.append("")

    lines.append(f"- 產生時間：{now}")
    lines.append(f"- 候選總數：{len(cards)}")
    lines.append(f"- 演化 session 數：{len(sessions)}")
    lines.append(f"- 報告判定：{'inconclusive' if not is_valid else 'valid'}")
    lines.append("")
    lines.append(build_json_block(json_data))
    lines.append("")

    if is_valid:
        lines.extend(build_champion_section(baseline_meta, champions))
    else:
        lines.append("## 1. Winner（冠軍）")
        lines.append("")
        lines.append("_因證據不完整，無法選出冠軍_")
        lines.append("")

    lines.extend(build_process_section(sessions))
    lines.extend(build_scores_section(baseline_meta, champions))
    lines.extend(build_candidate_comparison_section(cards, limit))
    lines.extend(build_reproduction_section(sessions, config))
    lines.extend(build_evidence_section(baseline_meta, champions, cards, sessions))
    lines.extend(build_rerun_section(rerun_settings))
    lines.extend(build_evidence_verification_section(evidence_checks))

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="產生最佳版本證據報告")
    parser.add_argument("--limit", type=int, default=10, help="候選比較最多列出幾筆")
    parser.add_argument("--out", help="可選：寫出報告路徑")
    args = parser.parse_args()

    report = build_report(limit=args.limit)
    print(report)
    if args.out:
        out_path = os.path.abspath(os.path.join(ROOT, args.out))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)


if __name__ == "__main__":
    main()
