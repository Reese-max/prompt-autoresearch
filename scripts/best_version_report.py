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
import platform
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from lib.notifications import send_report_to_telegram
from scripts.git_reproducibility import classify_git_provenance, collect_git_snapshot

if hasattr(__import__("sys").stdout, "reconfigure"):
    __import__("sys").stdout.reconfigure(encoding="utf-8", errors="replace")

BASELINE_META_PATH = os.path.join(ROOT, "prompts", "baseline.meta.json")
CHAMPIONS_DIR = os.path.join(ROOT, "prompts", "champions")
CANDIDATES_DIR = os.path.join(ROOT, "prompts", "candidates")
EVOLUTION_LOG_PATH = os.path.join(ROOT, "evolution_log.jsonl")
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
RUNS_DIR = os.path.join(ROOT, "runs")
SCHEMA_REL_PATH = "schemas/best_version_evidence_report.schema.json"
VALIDATION_STATE_REL_PATH = "output/research_validation_state.json"


def load_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def read_text(path):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    return rows


def load_validation_state():
    """讀取分階段驗證 checkpoint；不存在時維持既有報告相容性。"""
    return load_json(os.path.join(ROOT, VALIDATION_STATE_REL_PATH), {})


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
        "readable": False,
    }
    if path_rel and os.path.isfile(abs_path):
        result["exists"] = True
        try:
            result["nonempty"] = os.path.getsize(abs_path) > 0
            with open(abs_path, "rb") as evidence_file:
                digest = hashlib.sha256()
                for chunk in iter(lambda: evidence_file.read(65536), b""):
                    digest.update(chunk)
            result["readable"] = True
            if recorded_hash:
                result["actual_hash"] = digest.hexdigest()
                result["hash_match"] = result["actual_hash"] == recorded_hash
        except OSError:
            pass
    result["ok"] = (
        result["exists"]
        and result["nonempty"]
        and result["readable"]
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
    if os.path.isfile(os.path.join(ROOT, VALIDATION_STATE_REL_PATH)):
        checks.append(verify_evidence_file(VALIDATION_STATE_REL_PATH))
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


def _number(value):
    """回傳有限浮點數；輸入缺失或非法時回傳 None。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _list(value):
    """把歷史 scorecard 的字串／清單格式統一成 JSON 清單。"""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _path_hash(path_rel):
    """收集 repo 內檔案的可追溯版本；不讀取 repo 外路徑。"""
    path_rel = repo_rel(path_rel)
    result = {
        "path": path_rel or "",
        "sha256": "",
        "exists": False,
        "size": 0,
    }
    if path_rel:
        path = os.path.join(ROOT, path_rel)
        if os.path.isfile(path):
            try:
                result["exists"] = True
                result["size"] = os.path.getsize(path)
                result["sha256"] = sha256_file(path)
            except OSError:
                result["exists"] = False
    result["version"] = result["sha256"] or "missing"
    return result


def _prompt_artifact(path, recorded_hash=""):
    path_rel = repo_rel(path) or ""
    actual_hash = ""
    content = ""
    if path_rel:
        absolute = os.path.join(ROOT, path_rel)
        if os.path.isfile(absolute):
            content = read_text(absolute)
            try:
                actual_hash = sha256_file(absolute)
            except OSError:
                actual_hash = ""
    return {
        "path": path_rel,
        "sha256": recorded_hash or actual_hash,
        "recorded_sha256": recorded_hash or "",
        "actual_sha256": actual_hash,
        "verified": bool(content) and (not recorded_hash or recorded_hash == actual_hash),
        "content": content,
    }


_EXECUTION_COMPLETED_STATUSES = {"completed", "quality_measurement_obtained"}


def _score_entry(value):
    if isinstance(value, dict):
        return {
            "score": _number(value.get("score", value.get("average_score"))),
            "passed": value.get("passed"),
            "risk_perfect_rate": _number(value.get("risk_perfect_rate", value.get("risk_rate"))),
            "word_count_pass_rate": _number(value.get("word_count_pass_rate", value.get("word_rate"))),
            "run": display_path(value.get("run", value.get("run_dir", ""))),
        }
    return {
        "score": _number(value),
        "passed": None,
        "risk_perfect_rate": None,
        "word_count_pass_rate": None,
        "run": "",
    }


def _execution_records(card, stage=None):
    records = card.get("execution_records") if isinstance(card, dict) else []
    if not isinstance(records, list):
        return []
    return [
        record for record in records
        if isinstance(record, dict) and (stage is None or record.get("stage") == stage)
    ]


def _execution_reliability(card):
    """把失敗／逾時 attempt 作為可靠性證據獨立呈現。"""
    records = _execution_records(card)
    failures = [
        dict(record) for record in records
        if record.get("execution_status") not in _EXECUTION_COMPLETED_STATUSES
    ]
    timeouts = [
        record for record in failures
        if record.get("execution_status") == "timeout"
    ]
    return {
        "attempt_count": len(records),
        "completed_attempt_count": len(records) - len(failures),
        "failed_attempt_count": len(failures),
        "timeout_attempt_count": len(timeouts),
        "failed_attempts": failures,
    }


def _stage_quality_evidence(card, dataset, stage_data):
    """只允許完成執行且量測證據完整的 stage 進入品質分數。"""
    stage_data = stage_data if isinstance(stage_data, dict) else {}
    records = _execution_records(card, dataset)
    latest_record = records[-1] if records else {}
    status = stage_data.get("execution_status") or latest_record.get("execution_status")
    completion = stage_data.get("completion")
    measurement = stage_data.get("measurement_evidence")
    quality_measurement = stage_data.get("quality_measurement")
    if not isinstance(quality_measurement, dict):
        quality_measurement = latest_record.get("quality_measurement")
    explicit = bool(
        status
        or records
        or isinstance(completion, dict)
        or isinstance(measurement, dict)
        or stage_data.get("evidence_complete") is not None
    )
    score = _number(stage_data.get("score"))
    if score is None and isinstance(quality_measurement, dict):
        score = _number(quality_measurement.get("score"))
    reasons = []
    if explicit:
        if status not in _EXECUTION_COMPLETED_STATUSES:
            reasons.append("execution_status_not_completed")
        if score is None:
            reasons.append("quality_measurement_missing")
        if isinstance(completion, dict):
            if completion.get("status") != "completed":
                reasons.append("measurement_completion_not_completed")
            if completion.get("missing_evidence_types"):
                reasons.append("measurement_evidence_incomplete")
            if completion.get("evidence_errors"):
                reasons.append("measurement_evidence_invalid")
        elif isinstance(measurement, dict):
            if measurement.get("complete") is not True and measurement.get("status") not in {"completed", "complete", "valid"}:
                reasons.append("measurement_evidence_incomplete")
        elif stage_data.get("evidence_complete") is not True and not isinstance(quality_measurement, dict):
            reasons.append("measurement_evidence_missing")
    return {
        "eligible": not reasons,
        "score": score if not reasons else None,
        "execution_status": status,
        "measurement_evidence_complete": not reasons,
        "quality_exclusion_reasons": reasons,
    }


def _baseline_scores(baseline_meta):
    return {
        dataset: {
            "score": _number(baseline_meta.get(f"{dataset}_avg")),
            "passed": None,
            "risk_perfect_rate": None,
            "word_count_pass_rate": None,
            "run": display_path(baseline_meta.get(f"{dataset}_run", "")),
        }
        for dataset in ("smoke", "dev", "holdout")
    }


_COMPARISON_BASIS_FIELDS = (
    "dataset",
    "metric",
    "evaluator_version",
    "measurement_settings",
)
_SCORE_DATASETS = ("smoke", "dev", "holdout")
_REQUIRED_SCORE_DATASETS = ("dev", "holdout")


def _canonical_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _basis_from_card(card, baseline_scores):
    """取得候選明確記錄的比較基準；舊 scorecard 沿用全域 baseline。"""
    explicit = card.get("comparison_basis")
    if not isinstance(explicit, dict):
        explicit = card.get("measurement_basis")
    if not isinstance(explicit, dict):
        explicit = card.get("basis")
    if isinstance(explicit, dict):
        return explicit, "explicit"

    evaluations = card.get("stage_evaluations")
    if isinstance(evaluations, list):
        preferred = sorted(
            (item for item in evaluations if isinstance(item, dict)),
            key=lambda item: {"dev": 0, "smoke": 1, "holdout": 2}.get(item.get("stage"), 99),
        )
        if preferred and isinstance(preferred[0].get("basis"), dict):
            return preferred[0]["basis"], "explicit"
        return {}, "explicit"

    for stage in ("dev", "smoke", "holdout"):
        stage_data = card.get(stage)
        if not isinstance(stage_data, dict):
            continue
        run = repo_rel(stage_data.get("run"))
        summary = load_json(os.path.join(ROOT, run, "summary.json"), {}) if run else {}
        if not isinstance(summary, dict):
            continue
        basis = {
            "dataset": summary.get("dataset") or summary.get("question_file"),
            "metric": summary.get("metric") or summary.get("score_metric"),
            "evaluator_version": summary.get("evaluator_version"),
            "measurement_settings": summary.get("measurement_settings") or summary.get("measurement"),
        }
        if all(basis[field] not in (None, "", {}) for field in _COMPARISON_BASIS_FIELDS):
            return basis, "explicit"

    return {
        "baseline_scores": {
            dataset: (baseline_scores.get(dataset) or {}).get("score")
            for dataset in _SCORE_DATASETS
        }
    }, "baseline_scores"


def _measurement_gaps(card, scores, basis, basis_source):
    gaps = [
        f"{dataset}.score"
        for dataset in _REQUIRED_SCORE_DATASETS
        if _number((scores.get(dataset) or {}).get("score")) is None
    ]
    if basis_source == "explicit":
        evaluations = card.get("stage_evaluations")
        if isinstance(evaluations, list):
            for item in evaluations:
                if not isinstance(item, dict):
                    gaps.append("stage_evaluations")
                    continue
                missing = item.get("missing_fields")
                if item.get("comparable") is False:
                    gaps.extend(str(field) for field in (missing or _COMPARISON_BASIS_FIELDS))
                item_basis = item.get("basis")
                if isinstance(item_basis, dict):
                    gaps.extend(
                        field for field in _COMPARISON_BASIS_FIELDS
                        if item_basis.get(field) in (None, "", {})
                    )
        gaps.extend(
            field for field in _COMPARISON_BASIS_FIELDS
            if basis.get(field) in (None, "", {})
        )
    return sorted(set(gaps))


def build_candidate_comparisons(cards, baseline_meta):
    """保留所有候選，並以同一組 smoke/dev/holdout 基準呈現。"""
    baseline = _baseline_scores(baseline_meta)
    comparisons = []
    for index, card in enumerate(cards, 1):
        path = repo_rel(card.get("candidate_path")) or ""
        actual_hash = _path_hash(path)["sha256"] if path else ""
        candidate_hash = card.get("candidate_hash") or actual_hash
        raw_scores = {
            dataset: _score_entry(card.get(dataset))
            for dataset in _SCORE_DATASETS
        }
        quality_evidence = {
            dataset: _stage_quality_evidence(card, dataset, card.get(dataset))
            for dataset in _SCORE_DATASETS
        }
        scores = {}
        for dataset in _SCORE_DATASETS:
            evidence = quality_evidence[dataset]
            stage_data = card.get(dataset) if isinstance(card.get(dataset), dict) else {}
            scores[dataset] = _score_entry({
                **stage_data,
                "score": evidence["score"] if evidence["eligible"] else None,
            })
        supplied_baseline = card.get("baseline_scores")
        if not isinstance(supplied_baseline, dict):
            supplied_baseline = card.get("baseline")
        baseline_scores = {
            dataset: _score_entry(supplied_baseline.get(dataset))
            if isinstance(supplied_baseline, dict) and dataset in supplied_baseline
            else baseline[dataset]
            for dataset in _SCORE_DATASETS
        }
        comparison_basis, basis_source = _basis_from_card(card, baseline_scores)
        measurement_gaps = _measurement_gaps(
            card, raw_scores, comparison_basis, basis_source,
        )
        deltas = {}
        for dataset, score in scores.items():
            value = score["score"]
            base = baseline_scores[dataset]["score"]
            deltas[dataset] = round(value - base, 6) if value is not None and base is not None else None
        comparisons.append({
            "ordinal": index,
            "candidate_id": candidate_hash or path or f"candidate-{index}",
            "path": path,
            "sha256": candidate_hash,
            "scorecard_path": card.get("_scorecard_file", ""),
            "decision": card.get("final_decision") or card.get("status") or "PENDING",
            "classification": classify_candidate(card),
            "direction": card.get("direction", ""),
            "target_failures": _list(card.get("target_failures")),
            "scores": scores,
            "baseline_scores": baseline_scores,
            "deltas": deltas,
            "execution_records": card.get("execution_records", []),
            "execution_reliability": _execution_reliability(card),
            "quality_measurement_evidence": quality_evidence,
            "quality_eligible": all(
                quality_evidence[dataset]["eligible"]
                and scores[dataset]["score"] is not None
                for dataset in _REQUIRED_SCORE_DATASETS
            ),
            "quality_exclusion_reasons": {
                dataset: quality_evidence[dataset]["quality_exclusion_reasons"]
                for dataset in _SCORE_DATASETS
                if quality_evidence[dataset]["quality_exclusion_reasons"]
            },
            "comparison_basis": comparison_basis,
            "comparison_basis_source": basis_source,
            "measurement_gaps": measurement_gaps,
            "reject_reasons": _list(card.get("reject_reasons")),
            "hypothesis": card.get("hypothesis", ""),
        })
    return comparisons


def _validation_recovery(state):
    """讀取逾時恢復資料；舊 checkpoint 沒有新欄位時仍可相容。"""
    if not isinstance(state, dict):
        state = {}
    recovery = state.get("recovery") if isinstance(state.get("recovery"), dict) else {}
    recoverable_failure = state.get("status") in {"timed_out", "failed"} or bool(
        state.get("timed_out_stages")
    )
    return {
        "status": recovery.get(
            "status", "recoverable" if recoverable_failure else "complete"
        ),
        "timed_out_stage": state.get("timed_out_stage"),
        "timed_out_stages": state.get("timed_out_stages", []),
        "isolated_stages": state.get("isolated_stages", recovery.get("isolated_stages", [])),
        "isolated_candidates": state.get(
            "isolated_candidates", recovery.get("isolated_candidates", [])
        ),
        "completed_candidates": state.get(
            "completed_candidates", recovery.get("completed_candidates", [])
        ),
        "rerun_commands": state.get("rerun_commands", recovery.get("rerun_commands", [])),
        "remaining_work": state.get("remaining_work", recovery.get("remaining_work", [])),
        "global_best_allowed": state.get("global_best_allowed", not recoverable_failure),
    }


def _merge_unique(items, additions):
    merged = list(items or [])
    for item in additions or []:
        if item not in merged:
            merged.append(item)
    return merged


def _incomplete_quality_evidence(comparisons, config, validation_state=None):
    """找出模型失敗／逾時且沒有足夠成功量測的候選。"""
    affected = []
    parallel = config.get("parallel", {}) if isinstance(config, dict) else {}
    for comparison in comparisons:
        if comparison.get("quality_eligible"):
            continue
        failed_attempts = [
            dict(record)
            for record in comparison.get("execution_records", [])
            if isinstance(record, dict)
            and record.get("execution_status") not in _EXECUTION_COMPLETED_STATUSES
        ]
        failed_stages = {record.get("stage") for record in failed_attempts}
        for dataset in _SCORE_DATASETS:
            if dataset in failed_stages:
                continue
            stage_data = comparison.get("quality_measurement_evidence", {}).get(dataset, {})
            raw_stage = comparison.get("scores", {}).get(dataset) or {}
            status = raw_stage.get("execution_status") or stage_data.get("execution_status")
            if status in _EXECUTION_COMPLETED_STATUSES or not status:
                continue
            failed_attempts.append({
                "stage": dataset,
                "attempt": raw_stage.get("attempt", "-"),
                "model": raw_stage.get("model", ""),
                "execution_status": status,
                "failure_classification": raw_stage.get("failure_classification", status),
                "error_evidence": raw_stage.get("error_evidence", {}),
            })
        if not failed_attempts:
            continue
        missing = []
        for dataset in _REQUIRED_SCORE_DATASETS:
            evidence = comparison.get("quality_measurement_evidence", {}).get(dataset, {})
            score = (comparison.get("scores", {}).get(dataset) or {}).get("score")
            if not evidence.get("eligible") or score is None:
                missing.append({
                    "dataset": dataset,
                    "metric": "average_score",
                    "reasons": evidence.get("quality_exclusion_reasons", []),
                })
        commands = []
        for measurement in missing:
            dataset = measurement["dataset"]
            path = comparison.get("path")
            if not path:
                continue
            workers = parallel.get(dataset, 6)
            command = _command(
                [
                    sys.executable,
                    "scripts/evaluate.py",
                    path,
                    f"questions/{dataset}.jsonl",
                    "--parallel",
                    str(workers),
                ],
                f"補評候選：{dataset}",
            )
            command.update({
                "candidate_id": comparison.get("candidate_id", ""),
                "candidate_path": path,
                "dataset": dataset,
                "metric": measurement["metric"],
            })
            commands.append(command)
        affected.append({
            "candidate_id": comparison.get("candidate_id", ""),
            "candidate_path": comparison.get("path", ""),
            "status": "unproven",
            "failed_attempts": failed_attempts,
            "missing_quality_measurements": missing,
            "supplemental_evaluation_commands": commands,
        })
    recovery = _validation_recovery(validation_state)
    recovery_commands = recovery["rerun_commands"]
    recovery_work = recovery["remaining_work"]
    return {
        "status": "unproven" if affected or recovery["status"] == "recoverable" else "not_triggered",
        "affected_candidates": affected,
        "supplemental_evaluation_commands": _merge_unique([
            command
            for item in affected
            for command in item["supplemental_evaluation_commands"]
        ], recovery_commands),
        "rerun_commands": recovery_commands,
        "remaining_work": recovery_work,
        "isolated_stages": recovery["isolated_stages"],
        "isolated_candidates": recovery["isolated_candidates"],
        "completed_candidates": recovery["completed_candidates"],
        "global_best_allowed": recovery["global_best_allowed"],
    }


def _run_dir_from_value(value):
    if not isinstance(value, str) or not value:
        return ""
    path = repo_rel(value)
    return path if path and os.path.isdir(os.path.join(ROOT, path)) else ""


def collect_run_inputs(baseline_meta, champions, cards, sessions):
    """從已記錄 run 的 summary 追溯題庫版本與執行產物版本。"""
    run_dirs = set()

    def visit(value):
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        else:
            run = _run_dir_from_value(value)
            if run:
                run_dirs.add(run)

    visit(baseline_meta)
    visit(champions)
    visit(cards)
    visit(sessions)
    inputs = []
    for run in sorted(run_dirs):
        summary_path = f"{run}/summary.json"
        summary = load_json(os.path.join(ROOT, summary_path), {})
        inputs.append(_path_hash(summary_path))
        for name in ("details.jsonl", "decision.md", "route.json"):
            candidate = f"{run}/{name}"
            if os.path.isfile(os.path.join(ROOT, candidate)):
                inputs.append(_path_hash(candidate))
        question = repo_rel(summary.get("question_file")) if summary else None
        if question:
            inputs.append(_path_hash(question))
    return inputs


def collect_input_versions(baseline_meta, champions, cards, sessions):
    paths = [
        repo_rel(BASELINE_META_PATH),
        repo_rel(CONFIG_PATH),
        repo_rel(EVOLUTION_LOG_PATH),
        baseline_meta.get("prompt_path") if baseline_meta else "prompts/baseline.md",
    ]
    for champion in champions:
        paths.extend([champion.get("_meta_file"), champion.get("champion_prompt_path")])
    for card in cards:
        paths.extend([card.get("_scorecard_file"), card.get("candidate_path")])
    seen = set()
    inputs = []
    for path in paths:
        path_rel = repo_rel(path)
        if path_rel and path_rel not in seen:
            seen.add(path_rel)
            inputs.append(_path_hash(path_rel))
    for item in collect_run_inputs(baseline_meta, champions, cards, sessions):
        if item["path"] not in seen:
            seen.add(item["path"])
            inputs.append(item)
    return inputs


def collect_environment():
    """收集不含 secrets 的重現環境資訊。"""
    return {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "os_name": os.name,
        "encoding": getattr(sys.stdout, "encoding", ""),
        "hashseed": os.environ.get("PYTHONHASHSEED", "not set"),
        "cwd": ".",
        "commit": collect_git_commit(),
    }


def _command(argv, purpose):
    return {
        "purpose": purpose,
        "argv": argv,
        "command": subprocess.list2cmdline(argv),
        "cwd": ".",
    }


def collect_reproduction_commands(baseline_meta, config):
    prompt = repo_rel(baseline_meta.get("prompt_path")) if baseline_meta else None
    prompt = prompt or "prompts/baseline.md"
    parallel = config.get("parallel", {}) if config else {}
    commands = []
    for dataset in ("smoke", "dev", "holdout"):
        workers = parallel.get(dataset, 6)
        question = f"questions/{dataset}.jsonl"
        commands.append(_command(
            [sys.executable, "scripts/evaluate.py", prompt, question, "--parallel", str(workers)],
            f"評測 winner：{dataset}",
        ))
    commands.append(_command(
        [sys.executable, "scripts/gatekeeper.py", prompt, "--json"],
        "驗證 winner 硬性規則",
    ))
    return commands


def collect_measurement_basis(config, baseline_meta, input_versions):
    thresholds = config.get("thresholds", {}) if config else {}
    datasets = []
    for dataset in ("smoke", "dev", "holdout"):
        question = next(
            (item for item in input_versions if item["path"] == f"questions/{dataset}.jsonl"),
            None,
        )
        datasets.append({
            "name": dataset,
            "question_file": question or {"path": f"questions/{dataset}.jsonl", "version": "unavailable"},
            "baseline_score": _number(baseline_meta.get(f"{dataset}_avg")),
        })
    return {
        "datasets": datasets,
        "score_scale": {"minimum": 0, "maximum": 100},
        "thresholds": thresholds,
        "acceptance_criteria": [
            {"name": "總平均分晉升", "rule": "delta >= thresholds.dev_min_improvement 或 score >= 92 且不退步"},
            {"name": "單項退步限制", "rule": "每一題型退步 <= thresholds.type_max_regression"},
            {"name": "風險控制", "rule": "strict 100%；pragmatic >= 90% 且不低於 baseline"},
            {"name": "字數合格率", "rule": ">= thresholds.word_rate_min"},
        ],
    }


def load_report_schema():
    path = os.path.join(ROOT, SCHEMA_REL_PATH)
    if os.path.isfile(path):
        return load_json(path, {})
    return {
        "type": "object",
        "required": ["schema_version", "report_type", "decision", "winner", "quality", "candidate_comparison", "reproduction", "execution", "evidence", "schema_validation"],
    }


def _schema_type_matches(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _validate_schema_fragment(value, schema, location, errors):
    expected = schema.get("type")
    if isinstance(expected, list):
        if not any(_schema_type_matches(value, item) for item in expected):
            errors.append(f"{location}: type 必須為 {expected}")
            return
    elif expected and not _schema_type_matches(value, expected):
        errors.append(f"{location}: type 必須為 {expected}")
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{location}: 不在 enum {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{location}: 必須等於 {schema['const']!r}")
    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{location}.{name}: 缺少必要欄位")
        for name, child in schema.get("properties", {}).items():
            if name in value:
                _validate_schema_fragment(value[name], child, f"{location}.{name}", errors)
    if isinstance(value, list) and schema.get("items"):
        for index, item in enumerate(value):
            _validate_schema_fragment(item, schema["items"], f"{location}[{index}]", errors)
    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{location}: 長度不足")


def schema_validation_errors(report, schema=None):
    schema = schema or load_report_schema()
    try:
        import jsonschema
    except ImportError:
        pass
    else:
        validator = jsonschema.Draft202012Validator(schema)
        return [
            "$%s: %s" % (
                ".".join(str(part) for part in error.absolute_path),
                error.message,
            )
            for error in sorted(
                validator.iter_errors(report),
                key=lambda item: list(item.absolute_path),
            )
        ]
    errors = []
    _validate_schema_fragment(report, schema, "$", errors)
    return errors


def validate_report_schema(report, schema=None):
    """以 repo 內 JSON Schema 驗證報告；回傳 True／False。"""
    return not schema_validation_errors(report, schema)


def _winner_data(baseline_meta, is_valid, rerun_settings, commands):
    prompt_path = baseline_meta.get("prompt_path", "prompts/baseline.md") if baseline_meta else "prompts/baseline.md"
    prompt = _prompt_artifact(prompt_path, baseline_meta.get("prompt_hash", "") if baseline_meta else "")
    return {
        "candidate_id": baseline_meta.get("prompt_hash") if baseline_meta and is_valid else None,
        "kind": "global_baseline",
        "decision": "ADOPT" if is_valid else INCOMPLETE_EVIDENCE,
        "prompt": prompt,
        "workflow": _winner_workflow(commands),
        "scores": _baseline_scores(baseline_meta or {}) if is_valid else {},
    }


def _winner_workflow(commands):
    return {
        "steps": [
            "讀取完整 winner 提示詞",
            "依序以 smoke、dev、holdout 題庫評測",
            "執行 gatekeeper 與接受條件檢查",
            "保留 scorecard、summary、details 與執行紀錄",
        ],
        "commands": commands,
    }


# ---------- 證據完整性閘門 ----------

EVIDENCE_INTEGRITY_ERRORS = []
INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"


def verify_evidence_integrity(
    baseline_meta,
    champions,
    cards,
    sessions,
    config,
    *,
    workflow=None,
    measurement_basis=None,
    candidate_comparison=None,
    evidence_checks=None,
    execution_records=None,
    incomplete_evidence=None,
):
    """驗證冠軍選優所需的關鍵證據是否齊全。

    回傳 (is_valid: bool, errors: list[str])：
    - is_valid: True 表示所有關鍵證據齊全，可安全選優。
    - errors: 缺失的證據類型描述列表。

    缺少任一項關鍵證據時，報告必須輸出 INCOMPLETE_EVIDENCE 並拒絕選優。
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

    if workflow is not None:
        steps = workflow.get("steps") if isinstance(workflow, dict) else None
        commands = workflow.get("commands") if isinstance(workflow, dict) else None
        if not (
            isinstance(steps, list)
            and any(isinstance(step, str) and step.strip() for step in steps)
            and isinstance(commands, list)
            and any(commands)
        ):
            errors.append("缺少提示詞／流程內容（workflow steps 或 commands 為空）")

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

    if candidate_comparison is not None:
        incomplete_candidates = [
            row for row in candidate_comparison
            if isinstance(row, dict)
            and row.get("classification") in {"accepted", "rejected"}
            and not row.get("path")
        ]
        if incomplete_candidates:
            errors.append("缺少提示詞／流程內容（候選沒有可讀 candidate_path）")
        baseline_rows = [
            row for row in candidate_comparison
            if isinstance(row, dict)
            and isinstance(row.get("baseline_scores"), dict)
            and all(
                _number((row["baseline_scores"].get(dataset) or {}).get("score")) is not None
                for dataset in ("dev", "holdout")
            )
        ]
        if len(baseline_rows) != len(candidate_comparison):
            errors.append("缺少同基準評測結果（候選未攜帶可驗證的 dev/holdout baseline 分數）")

        measurement_gaps = [
            row for row in candidate_comparison
            if isinstance(row, dict)
            and row.get("classification") == "accepted"
            and row.get("measurement_gaps")
        ]
        if measurement_gaps:
            errors.append(
                "缺少關鍵量測欄位（" + "；".join(
                    f"{row.get('path') or row.get('candidate_id')}: {', '.join(row['measurement_gaps'])}"
                    for row in measurement_gaps
                ) + "）"
            )

        basis_signatures = {
            _canonical_value((row.get("comparison_basis_source"), row.get("comparison_basis")))
            for row in candidate_comparison
            if isinstance(row, dict)
        }
        if len(basis_signatures) > 1:
            errors.append("候選評測基準不同（不得在不同資料集、指標、評測器版本或量測設定間選優）")

        accepted_rows = [
            row for row in candidate_comparison
            if isinstance(row, dict)
            and row.get("classification") == "accepted"
            and row.get("quality_eligible", True)
            and not row.get("measurement_gaps")
            and _number((row.get("scores", {}).get("dev") or {}).get("score")) is not None
        ]
        if accepted_rows:
            highest = max(row["scores"]["dev"]["score"] for row in accepted_rows)
            tied = [row for row in accepted_rows if row["scores"]["dev"]["score"] == highest]
            if len(tied) > 1:
                errors.append(
                    f"最高分同分（dev={highest:.6g}；候選未定義可稽核 tie-breaker）"
                )

    if incomplete_evidence and incomplete_evidence.get("affected_candidates"):
        affected = incomplete_evidence["affected_candidates"]
        names = ", ".join(
            item.get("candidate_path") or item.get("candidate_id", "-")
            for item in affected
        )
        errors.append(
            "候選因免費模型失敗或逾時而缺少足夠成功品質量測"
            f"（{names}；不得宣稱其他候選為全域最佳）"
        )
    if incomplete_evidence and incomplete_evidence.get("global_best_allowed") is False:
        stages = ", ".join(
            item.get("stage", "-")
            for item in incomplete_evidence.get("isolated_stages", [])
            if isinstance(item, dict)
        ) or "未知階段"
        errors.append(
            f"驗證逾時或隔離（{stages}）；僅保留已完成候選證據，"
            "不得把部分結果升格為全域最佳"
        )

    # 3. 有效比較對象／淘汰依據：至少有一個候選且有有效的決策記錄
    has_comparison = False
    if cards:
        accepted, rejected, pending = classify_candidates(cards)
        has_comparison = len(accepted) > 0 or len(rejected) > 0
    if candidate_comparison is not None:
        has_comparison = any(
            isinstance(row, dict)
            and row.get("candidate_id")
            and row.get("path")
            and row.get("classification") in {"accepted", "rejected"}
            for row in candidate_comparison
        )
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

    if measurement_basis is not None:
        thresholds = config.get("thresholds") if isinstance(config, dict) else None
        if not (
            isinstance(measurement_basis, dict)
            and measurement_basis.get("datasets")
            and measurement_basis.get("acceptance_criteria")
            and isinstance(thresholds, dict)
            and thresholds
        ):
            errors.append("缺少量測方法（datasets、acceptance_criteria 或 thresholds 不完整）")

    if execution_records is not None and not isinstance(execution_records, list):
        errors.append("缺少有效執行證據（execution records 格式無效）")
    elif execution_records is not None and not execution_records:
        errors.append("缺少有效執行證據（沒有可追溯的 execution records）")

    if evidence_checks is not None:
        invalid_checks = [
            check for check in evidence_checks
            if not isinstance(check, dict) or check.get("ok") is not True
        ]
        if invalid_checks:
            errors.append("缺少有效執行證據（關鍵證據檔案不存在、為空或雜湊不一致）")

    EVIDENCE_INTEGRITY_ERRORS = errors
    return len(errors) == 0, errors


_GIT_COMMIT_KEYS = {
    "commit", "head_commit", "git_commit", "base_commit", "candidate_commit",
}
_GIT_DIFF_KEYS = {
    "git_diff", "diff_tracked", "diff_patch", "patch", "recorded_diff",
    "git_diff_hash", "diff_hash", "diff_paths", "changed_paths",
}


def _recorded_git_fields(value, source, commits=None, diffs=None):
    """從持久化證據取出明確記錄的 commit／Git diff 欄位。"""
    commits = commits if commits is not None else []
    diffs = diffs if diffs is not None else []
    if isinstance(value, dict):
        for key, item in value.items():
            location = f"{source}.{key}" if source else str(key)
            if key in _GIT_COMMIT_KEYS and isinstance(item, str) and item.strip():
                commits.append({"source": location, "value": item.strip()})
            if key in _GIT_DIFF_KEYS and item not in (None, "", [], {}):
                diffs.append({"source": location, "key": key, "value": item})
            _recorded_git_fields(item, location, commits, diffs)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _recorded_git_fields(item, f"{source}[{index}]", commits, diffs)
    return commits, diffs


def _snapshot_status_paths(snapshot):
    paths = snapshot.get("status_paths") if isinstance(snapshot, dict) else None
    if paths:
        return sorted(set(str(path).replace("\\", "/") for path in paths))
    status = snapshot.get("status_porcelain", "") if isinstance(snapshot, dict) else ""
    paths = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        path = path.strip().strip('"').replace("\\", "/")
        if path:
            paths.append(path)
    return sorted(set(paths))


def _declared_evidence_paths(evidence_checks, input_versions, candidate_comparison):
    declared = set()
    for item in evidence_checks or []:
        if isinstance(item, dict) and item.get("path"):
            declared.add(str(item["path"]).replace("\\", "/"))
    for item in input_versions or []:
        if isinstance(item, dict) and item.get("path"):
            declared.add(str(item["path"]).replace("\\", "/"))
    for item in candidate_comparison or []:
        if not isinstance(item, dict):
            continue
        for key in ("path", "scorecard_path"):
            if item.get(key):
                declared.add(str(item[key]).replace("\\", "/"))
    return declared


def _path_declared(path, declared):
    return path in declared or any(
        item.endswith("/") and path.startswith(item)
        for item in declared
    )


def _diff_matches_snapshot(recorded, snapshot, key=""):
    actual_diff = snapshot.get("diff_tracked", "")
    if key in {"diff_paths", "changed_paths"}:
        actual_paths = sorted(set(
            snapshot.get(key, [])
            or snapshot.get("diff_paths", [])
            or _snapshot_status_paths(snapshot)
        ))
    else:
        actual_paths = sorted(set(
            snapshot.get("changed_paths", [])
            or snapshot.get("diff_paths", [])
            or _snapshot_status_paths(snapshot)
        ))
    if key.endswith("_hash") and isinstance(recorded, str):
        return hashlib.sha256(actual_diff.encode("utf-8")).hexdigest() == recorded
    if isinstance(recorded, str):
        return recorded == actual_diff
    if isinstance(recorded, list):
        return sorted(str(item).replace("\\", "/") for item in recorded) == actual_paths
    if isinstance(recorded, dict):
        expected_hash = recorded.get("sha256") or recorded.get("hash")
        if expected_hash:
            return hashlib.sha256(actual_diff.encode("utf-8")).hexdigest() == expected_hash
        expected_paths = recorded.get("paths")
        if isinstance(expected_paths, list):
            return sorted(str(item).replace("\\", "/") for item in expected_paths) == actual_paths
    return False


def verify_delivery_consistency(
    git_snapshot,
    rerun_settings,
    baseline_meta,
    champions,
    cards,
    sessions,
    records,
    evidence_checks,
    input_versions,
    candidate_comparison,
):
    """確認報告版本、候選內容與目前 Git 工作樹可互相追溯。"""
    snapshot = git_snapshot if isinstance(git_snapshot, dict) else {}
    actual_head = str(snapshot.get("head_commit") or "").strip()
    commits, diffs = _recorded_git_fields(
        baseline_meta, "baseline_meta",
    )
    for name, value in (
        ("champions", champions),
        ("cards", cards),
        ("sessions", sessions),
        ("evolution_log", records),
    ):
        _recorded_git_fields(value, name, commits, diffs)

    # rerun_settings.version 是本次報告對外宣稱的版本；沒有 Git HEAD 的
    # 非 Git 單元測試環境不具備可比對對象，維持既有相容性。
    reported_commit = ((rerun_settings or {}).get("version") or {}).get("commit")
    if actual_head and isinstance(reported_commit, str) and reported_commit.strip():
        commits.append({"source": "report.reproduction.settings.version.commit", "value": reported_commit.strip()})

    inconsistencies = []
    if commits:
        if not actual_head:
            inconsistencies.append("已宣稱 commit，但目前 HEAD 無法解析")
        else:
            mismatches = [
                item for item in commits
                if item["value"] != actual_head
            ]
            for item in mismatches:
                inconsistencies.append(
                    f"{item['source']}={item['value']} 與實際 HEAD={actual_head} 不一致"
                )

    declared = _declared_evidence_paths(evidence_checks, input_versions, candidate_comparison)
    changed = _snapshot_status_paths(snapshot)
    undeclared = [path for path in changed if not _path_declared(path, declared)]
    if undeclared:
        inconsistencies.append(
            "工作樹變更未納入候選／證據宣告：" + ", ".join(undeclared)
        )

    candidate_checks = []
    for index, (card, comparison) in enumerate(
        zip(cards or [], candidate_comparison or []), 1
    ):
        candidate_path = comparison.get("path") or card.get("candidate_path")
        candidate_commits, candidate_diffs = _recorded_git_fields(
            card, f"candidate[{index}]",
        )
        candidate_errors = []
        for item in candidate_commits:
            if not actual_head:
                candidate_errors.append(f"{item['source']} 無法以 HEAD 驗證")
            elif item["value"] != actual_head:
                candidate_errors.append(
                    f"{item['source']}={item['value']} 與 HEAD={actual_head} 不一致"
                )
        for item in candidate_diffs:
            if not _diff_matches_snapshot(item["value"], snapshot, item["key"]):
                candidate_errors.append(f"{item['source']} 與目前 Git diff 無法驗證一致")
        candidate_checks.append({
            "candidate_id": comparison.get("candidate_id", ""),
            "candidate_path": candidate_path or "",
            "valid": not candidate_errors,
            "errors": candidate_errors,
        })
        inconsistencies.extend(candidate_errors)

    git_provenance = []
    for path in sorted(declared):
        provenance = classify_git_provenance(path, snapshot)
        git_provenance.append({"path": path, "provenance": provenance})
    for path in sorted(undeclared):
        git_provenance.append({"path": path, "provenance": "untracked_worktree"})

    rerun_commands = []
    if inconsistencies:
        rerun_commands.extend([
            _command(["git", "rev-parse", "HEAD"], "重新確認實際 HEAD"),
            _command(["git", "status", "--short"], "重新確認工作樹變更"),
            _command(["git", "diff", "HEAD", "--"], "重新取得候選／證據 diff"),
            _command(
                [sys.executable, "scripts/best_version_report.py", "--validate-schema", "--json-out", "output/best-version-report.json"],
                "修復後重新產生交付報告",
            ),
        ])
    if undeclared:
        rerun_commands.insert(
            2,
            _command(["git", "add", "-A"], "將確認屬於交付範圍的變更納入提交"),
        )
        rerun_commands.insert(
            3,
            _command(["git", "commit", "-m", "chore: record delivery evidence"], "提交已確認的交付證據"),
        )

    return {
        "status": "proven" if not inconsistencies else "unproven",
        "code": "VALID" if not inconsistencies else INCOMPLETE_EVIDENCE,
        "valid": not inconsistencies,
        "actual_head": actual_head,
        "claimed_commits": commits,
        "changed_paths": changed,
        "declared_paths": sorted(declared),
        "undeclared_changes": undeclared,
        "git_provenance": git_provenance,
        "candidate_checks": candidate_checks,
        "inconsistencies": inconsistencies,
        "rerun_commands": rerun_commands,
    }


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


def build_candidate_comparison_section(cards, limit, baseline_meta=None):
    lines = []
    lines.append("## 4. 逐候選比較")
    lines.append("")

    accepted, rejected, pending = classify_candidates(cards)
    lines.append(f"- ACCEPTED：{len(accepted)}")
    lines.append(f"- REJECTED：{len(rejected)}")
    lines.append(f"- PENDING/其他：{len(pending)}")
    lines.append("")

    comparisons = build_candidate_comparisons(
        cards, baseline_meta if baseline_meta is not None else load_baseline_meta(),
    )
    display_comparisons = comparisons[:limit] if limit else comparisons
    if display_comparisons:
        table_rows = []
        for comparison in display_comparisons:
            decision = comparison.get("decision", "-")
            direction = comparison.get("direction", "-")
            target = ",".join(comparison.get("target_failures", [])) or "-"
            smoke_score = "-"
            dev_score = "-"
            holdout_score = "-"
            smoke_data = comparison.get("scores", {}).get("smoke") or {}
            dev_data = comparison.get("scores", {}).get("dev") or {}
            holdout_data = comparison.get("scores", {}).get("holdout") or {}
            if smoke_data.get("score") is not None:
                smoke_score = f"{smoke_data['score']:.1f}"
            if dev_data.get("score") is not None:
                dev_score = f"{dev_data['score']:.1f}"
            if holdout_data.get("score") is not None:
                holdout_score = f"{holdout_data['score']:.1f}"
            exclusions = comparison.get("quality_exclusion_reasons", {})
            exclusion = next(
                (reason for reasons in exclusions.values() for reason in reasons),
                "",
            )
            reject_reasons = comparison.get("reject_reasons", [])
            reason = exclusion or (reject_reasons[0] if reject_reasons else "-")
            reliability = comparison.get("execution_reliability", {})
            reliability_text = (
                f"{reliability.get('attempt_count', 0)} attempts / "
                f"{reliability.get('failed_attempt_count', 0)} failed / "
                f"{reliability.get('timeout_attempt_count', 0)} timeout"
            )
            quality_status = "可排名" if comparison.get("quality_eligible") else "不納入品質排名"
            table_rows.append([
                decision, direction, target,
                smoke_score, dev_score, holdout_score,
                quality_status,
                reliability_text,
                reason[:60],
            ])
        lines.append(format_table(
            ["決策", "方向", "目標 F",
             "smoke", "dev", "holdout", "品質排名", "執行可靠性", "淘汰理由"],
            table_rows,
        ))
    else:
        lines.append("_無候選記錄_")
    lines.append("")
    return lines


def build_incomplete_evidence_section(incomplete_evidence):
    lines = [
        "## ⚠️ 比較證據不足：INCOMPLETE_EVIDENCE / unproven",
        "",
        "免費模型失敗或逾時使下列候選缺少足夠可比較的成功品質量測；不得據此宣稱其他候選為全域最佳。",
        "",
    ]
    for item in incomplete_evidence.get("affected_candidates", []):
        candidate = item.get("candidate_path") or item.get("candidate_id", "-")
        lines.append(f"### 候選：`{candidate}`（unproven）")
        lines.append("")
        lines.append("失敗 attempt：")
        for attempt in item.get("failed_attempts", []):
            lines.append(
                "- "
                f"stage={attempt.get('stage', '-')}, "
                f"attempt={attempt.get('attempt', '-')}, "
                f"status={attempt.get('execution_status', '-')}, "
                f"model={attempt.get('model', '-')}"
            )
        lines.append("")
        lines.append("缺少的品質量測：")
        for measurement in item.get("missing_quality_measurements", []):
            reasons = ", ".join(measurement.get("reasons", [])) or "未取得成功量測"
            lines.append(
                f"- `{measurement.get('dataset', '-')}.{measurement.get('metric', '-')}`：{reasons}"
            )
        lines.append("")
        lines.append("可獨立執行的補評命令：")
        for command in item.get("supplemental_evaluation_commands", []):
            lines.append(f"- `{command['command']}`")
        if not item.get("supplemental_evaluation_commands"):
            lines.append("- 無法建立：候選提示詞路徑不存在或不在 repo 內")
        lines.append("")
    if incomplete_evidence.get("isolated_stages") or incomplete_evidence.get("isolated_candidates"):
        lines.append("### 逾時隔離範圍")
        lines.append("")
        for item in incomplete_evidence.get("isolated_stages", []):
            lines.append(
                f"- stage={item.get('stage', '-')}, status={item.get('status', '-')}, "
                f"reason={item.get('reason', '-')}"
            )
        for item in incomplete_evidence.get("isolated_candidates", []):
            lines.append(
                f"- candidate={item.get('candidate_id', '-')}, "
                f"stage={item.get('stage', '-')}, status={item.get('status', '-')}, "
                f"reason={item.get('reason', '-')}"
            )
        lines.append("")
    if incomplete_evidence.get("rerun_commands"):
        lines.append("### 機械可解析重跑命令")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(incomplete_evidence["rerun_commands"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    if incomplete_evidence.get("remaining_work"):
        lines.append("### 剩餘工作清單")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(incomplete_evidence["remaining_work"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return lines


def build_delivery_consistency_section(consistency):
    """輸出版本／工作樹／候選 Git 證據的一致性結果與重跑命令。"""
    consistency = consistency if isinstance(consistency, dict) else {}
    valid = consistency.get("valid") is True
    lines = [
        "## 交付一致性閘門：" + ("PROVEN" if valid else "INCOMPLETE_EVIDENCE / unproven"),
        "",
        f"- 實際 HEAD：`{consistency.get('actual_head') or '-'}`",
        f"- 工作樹變更：`{len(consistency.get('changed_paths') or [])}`",
        f"- 未宣告變更：`{len(consistency.get('undeclared_changes') or [])}`",
        "",
    ]

    git_provenance = consistency.get("git_provenance") or []
    if git_provenance:
        lines.append("### Git 歸屬追溯")
        lines.append("")
        lines.append(
            "以下標示每個被採用內容的 Git 取得狀態："
            "committed（已提交版本）、diff_tracked（已記錄 diff）、"
            "untracked_worktree（未追蹤工作樹，不可交付）。"
        )
        lines.append("")
        table_rows = []
        for item in git_provenance:
            table_rows.append([item.get("path", ""), item.get("provenance", "")])
        lines.append(format_table(["檔案路徑", "Git 歸屬"], table_rows))
        lines.append("")

    if not valid:
        lines.append("不一致項目：")
        lines.extend(f"- {item}" for item in consistency.get("inconsistencies", []))
        lines.append("")
        lines.append("可重跑／修復命令：")
        for command in consistency.get("rerun_commands", []):
            lines.append(f"- `{command.get('command', command) if isinstance(command, dict) else command}`")
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


def build_validation_execution_section(state):
    lines = ["## 9. 分階段驗證執行器", ""]
    if not state:
        lines.append("_尚無分階段驗證 checkpoint_")
        lines.append("")
        return lines
    lines.append(f"- 執行狀態：`{state.get('status', '-')}`")
    lines.append(f"- 逾時階段：`{state.get('timed_out_stage') or '-'}`")
    lines.append("")
    rows = []
    for name, stage in (state.get("stages") or {}).items():
        rows.append([
            name,
            stage.get("status", "-"),
            stage.get("started_at", "-"),
            stage.get("ended_at", "-"),
            stage.get("deadline", "-"),
            len(stage.get("heartbeats") or []),
            "有" if stage.get("last_available_output") is not None else "無",
        ])
    if rows:
        lines.append(format_table(
            ["階段", "狀態", "開始", "結束", "deadline", "心跳", "最後輸出"],
            rows,
        ))
    else:
        lines.append("_checkpoint 沒有階段紀錄_")
    lines.append("")
    recovery = _validation_recovery(state)
    lines.append(f"- 恢復狀態：`{recovery['status']}`")
    lines.append(f"- 全域最佳允許：`{str(recovery['global_best_allowed']).lower()}`")
    lines.append("")
    lines.append("### 機械可解析重跑命令")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(recovery["rerun_commands"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("### 剩餘工作清單")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(recovery["remaining_work"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    lines.append(f"- checkpoint：`{VALIDATION_STATE_REL_PATH}`")
    lines.append("")
    return lines


def build_structured_report(limit=10):
    """產生唯一的結構化最佳版本證據資料來源。"""
    baseline_meta = load_baseline_meta()
    champions = load_champion_metas()
    cards = load_candidate_scorecards()
    sessions = load_evolution_summary()
    config = load_config()
    records = read_jsonl(EVOLUTION_LOG_PATH)
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    rerun_settings = collect_rerun_settings(baseline_meta, champions, config, sessions)
    commands = collect_reproduction_commands(baseline_meta, config)
    environment = collect_environment()
    input_versions = collect_input_versions(baseline_meta, champions, cards, sessions)
    validation_state = load_validation_state()
    git_snapshot = collect_git_snapshot(cwd=ROOT)
    measurement_basis = collect_measurement_basis(config, baseline_meta, input_versions)
    candidate_comparison = build_candidate_comparisons(cards, baseline_meta)
    incomplete_evidence = _incomplete_quality_evidence(
        candidate_comparison, config, validation_state,
    )
    evidence_checks = collect_evidence_verification(baseline_meta, champions, cards)
    is_valid, evidence_errors = verify_evidence_integrity(
        baseline_meta,
        champions,
        cards,
        sessions,
        config,
        workflow=_winner_workflow(commands),
        measurement_basis=measurement_basis,
        candidate_comparison=candidate_comparison,
        evidence_checks=evidence_checks,
        execution_records=records,
        incomplete_evidence=incomplete_evidence,
    )
    verification_valid = all(c["ok"] for c in evidence_checks)
    if not verification_valid and not any("有效執行證據" in error for error in evidence_errors):
        evidence_errors.append("關鍵證據檔案缺漏或雜湊不一致")
    is_valid = is_valid and verification_valid
    delivery_consistency = verify_delivery_consistency(
        git_snapshot,
        rerun_settings,
        baseline_meta,
        champions,
        cards,
        sessions,
        records,
        evidence_checks,
        input_versions,
        candidate_comparison,
    )
    if not delivery_consistency["valid"]:
        evidence_errors.extend(delivery_consistency["inconsistencies"])
    is_valid = is_valid and delivery_consistency["valid"]

    winner = _winner_data(baseline_meta, is_valid, rerun_settings, commands)

    type_champions = []
    for champion in champions:
        item = {
            "type": champion.get("type", ""),
            "type_slug": champion.get("type_slug", ""),
            "candidate_id": champion.get("candidate_hash", ""),
            "candidate_avg": _number(champion.get("candidate_avg")),
            "baseline_avg": _number(champion.get("baseline_avg")),
            "diff": _number(champion.get("diff")),
            "risk_rate": _number(champion.get("risk_rate")),
            "decision": champion.get("decision", ""),
            "prompt": _prompt_artifact(
                champion.get("champion_prompt_path", ""),
                champion.get("candidate_hash", ""),
            ),
            "meta_path": champion.get("_meta_file", ""),
            "dev_run": display_path(champion.get("dev_run", "")),
            "holdout_run": display_path(champion.get("holdout_run", "")),
        }
        type_champions.append(item)

    data = {
        "$schema": SCHEMA_REL_PATH,
        "schema_version": "1.0.0",
        "report_type": "best_version_evidence",
        "generated_at": now,
        "decision": {
            "status": "valid" if is_valid else "inconclusive",
            "code": "VALID" if is_valid else INCOMPLETE_EVIDENCE,
            "reason": "證據完整且通過重新驗證" if is_valid else "證據不完整，拒絕選優",
            "best_candidate_id": winner["candidate_id"],
        },
        "evidence_integrity": {
            "valid": is_valid,
            "status": "VALID" if is_valid else INCOMPLETE_EVIDENCE,
            "errors": evidence_errors,
        },
        "evidence_verification": {
            "valid": verification_valid,
            "total": len(evidence_checks),
            "checks": evidence_checks,
        },
        "delivery_consistency": delivery_consistency,
        "winner": winner,
        # 保留既有欄位，避免通知與既有整合使用者破壞性變更。
        "champion": {
            "prompt_hash": baseline_meta.get("prompt_hash", "") if is_valid else "",
            "dev_avg": baseline_meta.get("dev_avg") if is_valid else None,
            "holdout_avg": baseline_meta.get("holdout_avg") if is_valid else None,
            "dev_run": display_path(baseline_meta.get("dev_run", "")) if is_valid else "",
            "holdout_run": display_path(baseline_meta.get("holdout_run", "")) if is_valid else "",
        },
        "type_champions": type_champions if is_valid else [],
        "quality": {
            "baseline": _baseline_scores(baseline_meta),
            "winner": winner["scores"],
            "type_champions": type_champions if is_valid else [],
            "measurement_basis": measurement_basis,
        },
        "quality_ranking": {
            "policy": "same_benchmark_completed_measurement_only",
            "best_status": (
                "unproven"
                if incomplete_evidence["affected_candidates"]
                or not incomplete_evidence["global_best_allowed"]
                or not delivery_consistency["valid"]
                else ("proven" if is_valid else "inconclusive")
            ),
            "best_scope": "global" if is_valid and incomplete_evidence["global_best_allowed"] and delivery_consistency["valid"] else "none",
            "affected_candidates": incomplete_evidence["affected_candidates"],
            "supplemental_evaluation_commands": incomplete_evidence[
                "supplemental_evaluation_commands"
            ],
            "rerun_commands": incomplete_evidence["rerun_commands"],
            "remaining_work": incomplete_evidence["remaining_work"],
            "isolated_stages": incomplete_evidence["isolated_stages"],
            "isolated_candidates": incomplete_evidence["isolated_candidates"],
            "delivery_consistency": delivery_consistency,
            "completed_candidates": incomplete_evidence["completed_candidates"],
            "eligible_candidate_ids": [
                row["candidate_id"] for row in candidate_comparison
                if row.get("quality_eligible")
            ],
            "excluded_candidate_ids": [
                row["candidate_id"] for row in candidate_comparison
                if not row.get("quality_eligible")
            ],
        },
        "incomplete_evidence": incomplete_evidence,
        "candidate_comparison": candidate_comparison,
        "commands": commands,
        "environment": environment,
        "input_data_versions": input_versions,
        "execution_log": records,
        "candidates_summary": {
            "total": len(cards),
            "accepted": len([c for c in cards if classify_candidate(c) == "accepted"]),
            "rejected": len([c for c in cards if classify_candidate(c) == "rejected"]),
            "pending": len([c for c in cards if classify_candidate(c) == "pending"]),
        },
        "rerun_settings": rerun_settings,
        "reproduction": {
            "settings": rerun_settings,
            "commands": commands,
            "supplemental_evaluation_commands": incomplete_evidence[
                "supplemental_evaluation_commands"
            ],
            "rerun_commands": incomplete_evidence["rerun_commands"],
            "remaining_work": incomplete_evidence["remaining_work"],
            "environment": environment,
            "input_data_versions": input_versions,
            "git_reproducibility_snapshot": git_snapshot,
            "delivery_consistency": delivery_consistency,
        },
        "execution": {
            "log_path": repo_rel(EVOLUTION_LOG_PATH) or "",
            "records": records,
            "sessions": sessions,
            "validation": validation_state,
            "git_reproducibility_snapshot": git_snapshot,
            "delivery_consistency": delivery_consistency,
        },
        "evolution_sessions": len(sessions),
        "config": {
            "thresholds": config.get("thresholds", {}),
            "parallel": config.get("parallel", {}),
            "multi_candidate": config.get("multi_candidate", {}),
        },
        "evidence": {
            "files": {
                "baseline_meta": display_path(BASELINE_META_PATH),
                "evolution_log": display_path(EVOLUTION_LOG_PATH),
                "config": display_path(CONFIG_PATH),
                "champions_dir": display_path(CHAMPIONS_DIR),
                "candidates_dir": display_path(CANDIDATES_DIR),
                "validation_state": VALIDATION_STATE_REL_PATH if validation_state else "",
            },
            "input_data_versions": input_versions,
            "checks": evidence_checks,
        },
        "evidence_files": {
            "baseline_meta": display_path(BASELINE_META_PATH),
            "evolution_log": display_path(EVOLUTION_LOG_PATH),
            "config": display_path(CONFIG_PATH),
            "champions_dir": display_path(CHAMPIONS_DIR),
            "candidates_dir": display_path(CANDIDATES_DIR),
            "validation_state": VALIDATION_STATE_REL_PATH if validation_state else "",
        },
        "schema_validation": {
            "schema_path": SCHEMA_REL_PATH,
            "valid": True,
            "errors": [],
        },
    }
    schema_errors = schema_validation_errors(data)
    data["schema_validation"] = {
        "schema_path": SCHEMA_REL_PATH,
        "valid": not schema_errors,
        "errors": schema_errors,
    }
    return data


def build_report(limit=10, structured=None):
    baseline_meta = load_baseline_meta()
    champions = load_champion_metas()
    cards = load_candidate_scorecards()
    sessions = load_evolution_summary()
    config = load_config()

    json_data = structured or build_structured_report(limit=limit)
    now = json_data["generated_at"]
    is_valid = json_data["evidence_integrity"]["valid"]
    evidence_errors = json_data["evidence_integrity"]["errors"]
    evidence_checks = json_data["evidence_verification"]["checks"]
    verification_valid = json_data["evidence_verification"]["valid"]
    rerun_settings = json_data["rerun_settings"]

    lines = []
    lines.append("# 最佳版本證據報告")
    lines.append("")

    if not is_valid:
        lines.append("## ⚠️ 證據完整性閘門：INCONCLUSIVE")
        lines.append("")
        lines.append(f"**選優狀態碼：{INCOMPLETE_EVIDENCE}**")
        lines.append("**報告判定：inconclusive** — 缺少關鍵證據，拒絕選優。")
        lines.append("")
        lines.append("缺失項目：")
        for err in evidence_errors:
            lines.append(f"- {err}")
        lines.append("")
        lines.append("根據證據完整性閘門規則，缺少以下任一關鍵證據時，不得宣稱任何版本為最佳：")
        lines.append("1. 提示詞／流程內容")
        lines.append("2. 同基準評測結果")
        lines.append("3. 有效比較母體／淘汰依據")
        lines.append("4. 量測方法")
        lines.append("5. 重現設定")
        lines.append("6. 有效執行證據")
        lines.append("")
        lines.append("### 可獨立執行的補證命令")
        lines.append("")
        lines.append("以下命令各自可在 repo 根目錄獨立執行，用於補齊缺失證據：")
        for command in json_data["reproduction"]["commands"]:
            lines.append(f"- `{command['command']}`")
        lines.append("")
    else:
        lines.append("## ✅ 證據完整性閘門：PASS")
        lines.append("")

    if json_data.get("incomplete_evidence", {}).get("affected_candidates"):
        lines.extend(build_incomplete_evidence_section(json_data["incomplete_evidence"]))

    lines.extend(build_delivery_consistency_section(json_data.get("delivery_consistency")))

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
    lines.extend(build_validation_execution_section(json_data["execution"].get("validation", {})))

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="產生最佳版本證據報告")
    parser.add_argument("--limit", type=int, default=10, help="候選比較最多列出幾筆")
    parser.add_argument("--out", help="可選：寫出報告路徑")
    parser.add_argument("--json-out", help="可選：寫出完整結構化 JSON 路徑")
    parser.add_argument("--json", action="store_true", help="只輸出完整結構化 JSON")
    parser.add_argument("--validate-schema", action="store_true", help="Schema 無效時以失敗結束")
    args = parser.parse_args()

    structured = build_structured_report(limit=args.limit)
    report = build_report(limit=args.limit, structured=structured)
    if args.json:
        print(json.dumps(structured, ensure_ascii=False, indent=2))
    else:
        print(report)

    report_path = None
    if args.out:
        out_rel = repo_rel(args.out)
        if not out_rel:
            parser.error("--out 必須位於目前 repo 內")
        out_path = os.path.join(ROOT, out_rel)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)
        report_path = repo_rel(out_path)

    if args.json_out:
        json_rel = repo_rel(args.json_out)
        if not json_rel:
            parser.error("--json-out 必須位於目前 repo 內")
        json_path = os.path.join(ROOT, json_rel)
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(structured, f, ensure_ascii=False, indent=2)
            f.write("\n")

    if not args.json:
        delivery = send_report_to_telegram(
            report,
            report_path=report_path,
            failure_path=os.path.join(ROOT, "output", "delivery_failures.jsonl"),
        )
        if delivery["status"] == "failed":
            print("[通知失敗] Telegram 未確認收到結論；失敗已持久化，可重試。")
    if args.validate_schema and not structured["schema_validation"]["valid"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
