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
from lib.completion_gate import verify_persisted_run_evidence

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

_RANKING_STAGE_PRIORITY = {"dev": 0, "smoke": 1, "holdout": 2}
_RANKING_FIELDS = ("dataset", "metric", "evaluator_version", "measurement_settings")


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


def _canonical_comparison_value(value):
    if isinstance(value, str):
        return value.replace("\\", "/")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _first_value(sources, *keys):
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            if value not in (None, "", {}):
                return value
    return None


def _stage_comparison(card, stage, stage_data):
    run_dir = stage_data.get("run")
    summary = load_json(os.path.join(run_dir, "summary.json"), {}) if run_dir else {}
    sources = [stage_data, card, summary]
    evaluator = _first_value(sources, "evaluator")
    evaluator_version = _first_value(
        sources, "evaluator_version", "evaluatorVersion"
    )
    if evaluator_version is None and isinstance(evaluator, dict):
        evaluator_version = evaluator.get("version")
    metric = _first_value(sources, "metric", "metric_name", "score_metric")
    if metric is None and stage_data.get("score") is not None:
        metric = "average_score"
    basis = {
        "stage": stage,
        "dataset": _first_value(sources, "dataset", "data_set", "dataset_id", "question_file"),
        "metric": metric,
        "evaluator_version": evaluator_version,
        "measurement_settings": _first_value(
            sources, "measurement_settings", "measurement", "measurement_config"
        ),
    }
    missing = [field for field in _RANKING_FIELDS if basis[field] in (None, "", {})]
    if missing:
        return {
            "stage": stage,
            "score": stage_data.get("score"),
            "comparable": False,
            "basis": basis,
            "missing_fields": missing,
            "reason": "不可比較：缺少 " + "、".join(missing),
        }
    comparison_key = tuple(
        [basis["stage"]]
        + [_canonical_comparison_value(basis[field]) for field in _RANKING_FIELDS]
    )
    return {
        "stage": stage,
        "score": float(stage_data["score"]),
        "comparable": True,
        "basis": basis,
        "comparison_key": comparison_key,
    }


def _candidate_stage_evaluations(card):
    evaluations = []
    for stage in ("smoke", "dev", "holdout"):
        stage_data = card.get(stage) or {}
        if not isinstance(stage_data, dict) or stage_data.get("score") is None:
            continue
        evaluations.append(_stage_comparison(card, stage, stage_data))
    return evaluations


def _preferred_stage_evaluation(evaluations):
    rankable = [item for item in evaluations if item.get("comparable")]
    return min(
        rankable or evaluations,
        key=lambda item: _RANKING_STAGE_PRIORITY.get(item["stage"], 99),
        default=None,
    )


def _rank_candidate_evaluations(candidates):
    """只在同一比較基準內排名，回傳（勝者、逐候選報告）。"""
    entries = []
    qualified_candidates = []
    reports = {}
    for candidate in candidates:
        path = candidate.get("candidate_path") or ""
        if not path:
            continue
        status = str(candidate.get("status", "")).lower()
        qualified = status not in {"failed", "incomplete"} and not status.startswith("rejected_")
        if qualified:
            qualified_candidates.append(candidate)
        evaluations = candidate.get("stage_evaluations") or []
        reports[path] = {
            "candidate_path": path,
            "status": candidate.get("status", ""),
            "evaluations": evaluations,
            "outcome": "淘汰",
            "reason": "沒有可排名的同基準評測資料",
            "elimination_basis": ["no_comparable_evaluation"],
        }
        for evaluation in evaluations:
            item = {"candidate": candidate, "evaluation": evaluation}
            if evaluation.get("comparable") and qualified:
                entries.append(item)
            else:
                reports[path]["elimination_basis"].append(
                    {"stage": evaluation["stage"], "missing_fields": evaluation["missing_fields"]}
                )

    groups = {}
    for item in entries:
        groups.setdefault(item["evaluation"]["comparison_key"], []).append(item)
    winner = None
    selected_key = None
    tied_paths = []
    tied_score = None
    if groups:
        preferred_stage = min(
            (item["evaluation"]["stage"] for item in entries),
            key=lambda stage: _RANKING_STAGE_PRIORITY.get(stage, 99),
        )
        preferred_groups = [
            (key, group)
            for key, group in groups.items()
            if group[0]["evaluation"]["stage"] == preferred_stage
        ]
        largest_groups = [
            (key, group)
            for key, group in preferred_groups
            if len(group) == max(len(items) for _, items in preferred_groups)
        ]
        if len(largest_groups) == 1:
            selected_key, group = largest_groups[0]
            top_score = max(item["evaluation"]["score"] for item in group)
            top_items = [
                item for item in group
                if item["evaluation"]["score"] == top_score
            ]
            if len(top_items) == 1:
                winner = top_items[0]["candidate"]
            else:
                tied_score = top_score
                tied_paths = [
                    item["candidate"].get("candidate_path", "")
                    for item in top_items
                ]

    winner_item = next(
        (
            item for item in entries
            if selected_key is not None
            and item["evaluation"]["comparison_key"] == selected_key
            and item["candidate"] is winner
        ),
        None,
    )
    winner_score = (
        winner_item["evaluation"]["score"]
        if winner_item
        else tied_score
    )
    best_status = "unproven"
    best_scope = "comparison_group"
    best_label = "該比較群組內最佳"
    missing_candidates = []
    pending_evaluations = []
    if selected_key is not None:
        selected_evaluation = next(
            item["evaluation"]
            for item in entries
            if item["evaluation"]["comparison_key"] == selected_key
        )
        expected_basis = selected_evaluation["basis"]
        expected_fields = ("stage",) + _RANKING_FIELDS
        for candidate in qualified_candidates:
            evaluations = candidate.get("stage_evaluations") or []
            if any(
                evaluation.get("comparable")
                and evaluation.get("comparison_key") == selected_key
                for evaluation in evaluations
            ):
                continue
            path = candidate["candidate_path"]
            missing_candidates.append(path)
            same_stage = [
                evaluation for evaluation in evaluations
                if evaluation.get("stage") == expected_basis["stage"]
            ]
            pending_fields = [
                field for field in expected_fields
                if not any(
                    _canonical_comparison_value(
                        (evaluation.get("basis") or {}).get(field)
                    ) == _canonical_comparison_value(expected_basis.get(field))
                    for evaluation in same_stage
                )
            ]
            pending_evaluations.append({
                "candidate_path": path,
                "required_basis": expected_basis,
                "missing_fields": pending_fields or ["comparison_key"],
            })
        if tied_paths:
            best_status = "inconclusive"
            best_label = "並列最佳"
        elif not missing_candidates:
            best_status = "proven"
            best_scope = "global"
            best_label = "全域最佳版本"

    ranking_metadata = {
        "best_status": best_status,
        "best_scope": best_scope,
        "best_label": best_label,
        "best_candidates": tied_paths,
        "missing_candidates": missing_candidates,
        "pending_evaluation_fields": {
            item["candidate_path"]: item["missing_fields"]
            for item in pending_evaluations
        },
        "pending_evaluations": pending_evaluations,
    }
    if winner_item is not None:
        winner = dict(winner)
        winner.setdefault("score", winner_score)
        winner.update(ranking_metadata)
    for path, report in reports.items():
        report.update(ranking_metadata)
        matching = [
            item for item in entries
            if item["candidate"].get("candidate_path") == path
        ]
        selected = [
            item for item in matching
            if selected_key is not None
            and item["evaluation"]["comparison_key"] == selected_key
        ]
        if tied_paths and path in tied_paths and selected:
            report.update({
                "outcome": "並列最佳",
                "reason": f"同一比較基準下最高分 {winner_score:.2f}，沒有預先定義且可稽核的 tie-breaker",
                "elimination_basis": [],
            })
        elif winner and path == winner.get("candidate_path") and selected:
            report.update({
                "outcome": "勝出",
                "reason": (
                    f"{best_label}，同一比較基準下最高分 {winner_score:.2f}"
                ),
                "elimination_basis": [],
            })
        elif selected:
            score = selected[0]["evaluation"]["score"]
            comparison_target = "並列最佳" if tied_paths else "勝者"
            report.update({
                "outcome": "落敗",
                "reason": f"{best_label}，同一比較基準下低於{comparison_target} {score:.2f} < {winner_score:.2f}",
                "elimination_basis": ["lower_score_in_same_comparison_group"],
            })
        elif matching:
            report.update({
                "reason": "未納入排名：與選定排名基準的資料集、指標、評測器版本或量測設定不一致",
                "elimination_basis": ["comparison_basis_mismatch"],
            })
    return winner, list(reports.values())


def _scorecard_elimination_reports(known_paths):
    reports = []
    cand_dir = "prompts/candidates"
    if not os.path.isdir(cand_dir):
        return reports
    for name in sorted(os.listdir(cand_dir)):
        if not name.endswith(".scorecard.json"):
            continue
        card = load_json(os.path.join(cand_dir, name), {})
        path = card.get("candidate_path") or ""
        status = card.get("status") or ""
        if not path or path in known_paths or not (
            status in {"failed", "incomplete"} or status.startswith("rejected_")
        ):
            continue
        reasons = card.get("reject_reasons") or card.get("rejection_reasons") or []
        reports.append({
            "candidate_path": path,
            "status": status,
            "evaluations": [],
            "outcome": "淘汰",
            "reason": "；".join(str(reason) for reason in reasons) or status,
            "elimination_basis": reasons or [status],
        })
    return reports


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
        status = card.get("status") or ""
        if (
            status in {"failed", "incomplete"}
            or status.startswith("rejected_")
            or card.get("completion_status") in {"failed", "incomplete"}
        ):
            continue
        if card.get("missing_evidence_types"):
            continue
        if any(
            (card.get(stage) or {}).get("completion", {}).get("status") == "failed"
            for stage in ("smoke", "dev", "holdout")
        ):
            continue
        stage_evaluations = _candidate_stage_evaluations(card)
        preferred = _preferred_stage_evaluation(stage_evaluations)
        if preferred is None:
            continue

        evidence_checks = {}
        evidence_errors = []
        for stage in ("smoke", "dev", "holdout"):
            stage_data = card.get(stage) or {}
            if not isinstance(stage_data, dict) or not (
                stage_data.get("score") is not None or stage_data.get("completion")
            ):
                continue
            run_dir = stage_data.get("run")
            check = verify_persisted_run_evidence(run_dir)
            evidence_checks[stage] = check
            if check["status"] != "completed":
                evidence_errors.extend(
                    f"{stage}: {reason}"
                    for reason in check["rejection_reasons"]
                )
        if evidence_errors:
            failed_checks = [
                check for check in evidence_checks.values()
                if check["status"] != "completed"
            ]
            first_failure = failed_checks[0] if failed_checks else {}
            card.update({
                "status": "failed",
                "completion_status": "failed",
                "final_decision": "FAILED",
                "reason_code": first_failure.get("reason_code") or "INVALID_EVIDENCE_MANIFEST",
                "rejection_reason": "candidate evidence revalidation failed",
                "rejection_reasons": evidence_errors,
                "reject_reasons": evidence_errors,
                "missing_evidence_types": ["evidence_manifest"],
                "evidence_errors": evidence_errors,
                "evidence_validation": evidence_checks,
            })
            with open(os.path.join(cand_dir, name), "w", encoding="utf-8") as handle:
                json.dump(card, handle, ensure_ascii=False, indent=2)
            continue
        results.append({
            "candidate_path": card.get("candidate_path") or "",
            "smoke_score": (card.get("smoke") or {}).get("score"),
            "dev_score": (card.get("dev") or {}).get("score"),
            "score": float(preferred["score"]),
            "status": card.get("status", ""),
            "selected": bool(card.get("selected")),
            "evidence_validation": evidence_checks,
            "stage_evaluations": stage_evaluations,
        })
    return results


def run_controlled_closed_loop(parallel_config):
    """受控執行路徑：串接「評測既有候選 → 依結果產生迭代候選 → 比較並淘汰 → 回傳排名結論」。

    1. 評測既有候選：scan_candidate_evaluations() 收錄既有候選評估證據。
    2. 依結果產生迭代候選：run_opt.run_opt_pass 依歷史結果產生多候選並評估。
    3. 比較並淘汰：run_opt_pass 以 smoke/dev/holdout 比較並淘汰較差候選。
    4. 回傳排名結論：回傳 (success, best_candidate)。

    multi_candidate 停用或 count<2 時直接 raise，避免單一候選捷徑跳過「比較並淘汰」階段。
    """
    import run_opt

    existing = scan_candidate_evaluations()
    prior_best, prior_report = _rank_candidate_evaluations(existing)

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
        f"，最高 {prior_best['candidate_path']} (score={prior_best['score']:.2f})"
        if prior_best
        else "（無）"
    )
    print(f"{C_CYAN}[受控閉環] 既有已評測候選 {len(existing)} 個{existing_info}"
          f"，本輪多候選 count={count}，產生迭代候選...{C_RESET}")

    success = run_opt.run_opt_pass(**parallel_config)

    after = scan_candidate_evaluations()
    merged = {c["candidate_path"]: c for c in existing + after if c.get("candidate_path")}
    best_candidate, ranking_report = _rank_candidate_evaluations(list(merged.values()))
    known_paths = set(merged)
    ranking_report.extend(_scorecard_elimination_reports(known_paths))
    append_jsonl(
        LOG_PATH,
        {
            "event": "controlled_closed_loop_ranking",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "winner": best_candidate,
            "candidate_reports": ranking_report,
            "prior_candidate_reports": prior_report,
        },
    )
    if best_candidate:
        print(f"{C_CYAN}[受控閉環] {best_candidate.get('best_label', '排名候選')}: {best_candidate['candidate_path']} "
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
        print(f"  - {best_candidate.get('best_label', '排名候選')}: {best_candidate['candidate_path']} "
              f"(score={best_candidate['score']:.2f}, status={best_candidate['status']})")
    print(f"  - 總運行耗時: {total_elapsed/3600:.2f} 小時 ({total_elapsed/60:.1f} 分鐘)")
    print(f"{C_PURPLE}=================================================={C_RESET}")
    
    return 0

if __name__ == "__main__":
    main()
