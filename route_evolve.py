# -*- coding: utf-8 -*-
"""
route_evolve.py — 分題型 champion 演化器。

核心概念：
  1. 每個題型有自己的 champion prompt。
  2. 候選只在該題型的 dev 子題庫上比較，不再要求單一 prompt 同時打全部題型。
  3. dev 通過後，必須通過該題型 holdout，才更新 champion。
  4. 更新 champion 後，重建 route，再用 evaluate_routed.py 做全題庫驗證。

範例：
  python route_evolve.py --type 評析題 --rounds 3 --parallel 24
  python route_evolve.py --all --rounds 1 --parallel 24
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from run_opt import (  # noqa: E402
    _selection_evidence_failure,
    call_minimax,
    compress_candidate_prompt,
    load_file,
    sha256_text,
    write_json,
)
from scripts.gatekeeper import run_gatekeeper  # noqa: E402

C_GREEN = "\033[92m"
C_CYAN = "\033[96m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_PURPLE = "\033[95m"
C_RESET = "\033[0m"

PYTHON_BIN = sys.executable or "python"
TYPE_SLUGS = {
    "說明題": "explain",
    "比較題": "compare",
    "評析題": "commentary",
    "實務應用題": "practical",
    "法律法理題": "legal_theory",
    "法律案例題": "legal_case",
}
SLUG_TYPES = {v: k for k, v in TYPE_SLUGS.items()}
BASELINE_PROMPT = "prompts/baseline.md"
CHAMPIONS_DIR = "prompts/champions"
ROUTE_PATH = "prompts/routes/type_champions.json"
SUBSET_DIR = ".cache/type_questions"
LOG_PATH = "route_evolution_log.jsonl"


def read_json(path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


def append_jsonl(path, payload):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_type(type_or_slug):
    return SLUG_TYPES.get(type_or_slug, type_or_slug)


def type_slug(type_name):
    if type_name not in TYPE_SLUGS:
        raise ValueError(f"未知題型：{type_name}")
    return TYPE_SLUGS[type_name]


def load_questions(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_subset(question_file, type_name):
    slug = type_slug(type_name)
    split = os.path.splitext(os.path.basename(question_file))[0]
    out_path = os.path.join(SUBSET_DIR, f"{split}_{slug}.jsonl")
    rows = [row for row in load_questions(question_file) if row.get("type") == type_name]
    if not rows:
        raise RuntimeError(f"{question_file} 找不到題型 {type_name}")
    os.makedirs(SUBSET_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return out_path, len(rows)


def newest_run_after(before_dirs):
    before = set(before_dirs)
    runs = [
        os.path.join("runs", name)
        for name in sorted(os.listdir("runs"))
        if name != "latest" and os.path.isdir(os.path.join("runs", name)) and os.path.join("runs", name) not in before
    ]
    return runs[-1] if runs else ""


def list_run_dirs():
    if not os.path.exists("runs"):
        return []
    return [
        os.path.join("runs", name)
        for name in sorted(os.listdir("runs"))
        if name != "latest" and os.path.isdir(os.path.join("runs", name))
    ]


def evaluate_prompt(prompt_path, question_file, parallel):
    before = list_run_dirs()
    cmd = [PYTHON_BIN, "scripts/evaluate.py", prompt_path, question_file, "--parallel", str(parallel)]
    print(f"{C_CYAN}$ {' '.join(cmd)}{C_RESET}")
    res = subprocess.run(cmd)
    run_dir = newest_run_after(before)
    return res.returncode, run_dir, read_json(os.path.join(run_dir, "summary.json"), {}) if run_dir else {}


def evaluate_routed(route_path, question_file, parallel):
    before = list_run_dirs()
    cmd = [PYTHON_BIN, "scripts/evaluate_routed.py", route_path, question_file, "--parallel", str(parallel)]
    print(f"{C_CYAN}$ {' '.join(cmd)}{C_RESET}")
    res = subprocess.run(cmd)
    run_dir = newest_run_after(before)
    return res.returncode, run_dir, read_json(os.path.join(run_dir, "summary.json"), {}) if run_dir else {}


def compare_run(new_run, base_run, mode="pragmatic", candidate_id=None):
    import scripts.compare_runs as compare_runs

    accepted, _, diff = compare_runs.compare(new_run, base_run, mode=mode, candidate_id=candidate_id)
    return accepted, diff, dict(compare_runs.LAST_COMPARISON)


def current_champion_path(type_name):
    slug = type_slug(type_name)
    path = os.path.join(CHAMPIONS_DIR, f"{slug}.md")
    return path if os.path.exists(path) else BASELINE_PROMPT


def champion_meta_path(type_name):
    return os.path.join(CHAMPIONS_DIR, f"{type_slug(type_name)}.meta.json")


def build_type_prompt(type_name, source_prompt, dev_subset, baseline_summary, round_no):
    example_questions = load_questions(dev_subset)[:3]
    examples = "\n".join(f"- {row['question']}" for row in example_questions)
    prompt = f"""你是臺灣國考申論題提示詞研究員。請只針對「{type_name}」優化下列提示詞。

目標：
1. 讓此題型答案更像高分答案卷，採分點明確、結構穩定。
2. 不需要照顧其他題型，但仍要保留基本防呆：不得反問、不得輸出審題過程、不得編造法條、判決、年份、統計或制度。
3. 提示詞長度上限 550 字，越短越好。
4. 必須保留「專家／閱卷」角色、「比較基準」、「法律法理／法律案例分流」、「三段論法或涵攝」、「直接輸出正文」等 gatekeeper 會檢查的關鍵防線。
5. 只輸出新的 system prompt 正文，不要 markdown，不要解釋。

此題型代表題：
{examples}

目前此題型 baseline/champion dev 摘要：
{json.dumps(baseline_summary, ensure_ascii=False)[:1600]}

目前 prompt：
{source_prompt}

本輪是第 {round_no} 輪。請做小幅、單一方向的改動，避免把 prompt 改成規則百科。
"""
    candidate = call_minimax("你是提示詞優化大師。", prompt, temperature=0.7).strip()
    if len(candidate) > 550:
        raw = candidate
        candidate = compress_candidate_prompt(candidate).strip()
        if len(candidate) > 550:
            print(f"{C_YELLOW}候選壓縮後仍超過 550 字：{len(candidate)}，保留但 gate 可能淘汰。原長度 {len(raw)}。{C_RESET}")
    return candidate


def acceptance_summary(comparison):
    return {
        "completion_status": comparison.get("completion_status", ""),
        "reason_code": comparison.get("reason_code", ""),
        "rejection_reason": comparison.get("rejection_reason", ""),
        "rejection_reasons": comparison.get("rejection_reasons", []),
        "score_diff": comparison.get("score_diff"),
        "risk_rate": comparison.get("risk_rate"),
        "base_risk_rate": comparison.get("base_risk_rate"),
        "failure_new": comparison.get("failure_new", {}),
        "failure_base": comparison.get("failure_base", {}),
        "type_diffs": comparison.get("type_diffs", {}),
        "evidence_manifest": comparison.get("evidence_manifest", []),
        "base_evidence_manifest": comparison.get("base_evidence_manifest", []),
        "evidence_errors": comparison.get("evidence_errors", []),
    }


def update_route():
    route = {
        "name": "baseline_plus_type_champions",
        "default_prompt": BASELINE_PROMPT,
        "by_type": {},
    }
    for type_name, slug in TYPE_SLUGS.items():
        path = os.path.join(CHAMPIONS_DIR, f"{slug}.md")
        if os.path.exists(path):
            route["by_type"][type_name] = path.replace("\\", "/")
    os.makedirs(os.path.dirname(ROUTE_PATH), exist_ok=True)
    with open(ROUTE_PATH, "w", encoding="utf-8") as f:
        json.dump(route, f, ensure_ascii=False, indent=2)
    return ROUTE_PATH, route


def save_champion(type_name, candidate_path, candidate_prompt, dev_run, holdout_run, dev_comparison, holdout_comparison):
    failure = _selection_evidence_failure(
        dev_comparison,
        (("dev", dev_run),),
    ) or _selection_evidence_failure(
        holdout_comparison,
        (("holdout", holdout_run),),
    )
    if failure:
        rejection = {
            "status": "failed",
            "completion_status": "failed",
            "final_decision": "FAILED",
            "reason_code": failure["reason_code"],
            "rejection_reason": failure["rejection_reason"],
            "rejection_reasons": failure["rejection_reasons"],
            "reject_reasons": failure["rejection_reasons"],
            "missing_evidence_types": ["evidence_manifest"],
        }
        write_json(candidate_path.replace(".md", ".scorecard.json"), rejection)
        return None, rejection
    os.makedirs(CHAMPIONS_DIR, exist_ok=True)
    slug = type_slug(type_name)
    champion_path = os.path.join(CHAMPIONS_DIR, f"{slug}.md")
    shutil.copy2(candidate_path, champion_path)
    meta = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": "type_champion",
        "type": type_name,
        "type_slug": slug,
        "champion_prompt_path": champion_path.replace("\\", "/"),
        "candidate_path": candidate_path.replace("\\", "/"),
        "candidate_hash": sha256_text(candidate_prompt),
        "dev_run": dev_run,
        "holdout_run": holdout_run,
        "dev_comparison": acceptance_summary(dev_comparison),
        "holdout_comparison": acceptance_summary(holdout_comparison),
    }
    write_json(champion_meta_path(type_name), meta)
    return champion_path, meta


def evolve_one_type(type_name, rounds, parallel, mode):
    slug = type_slug(type_name)
    dev_subset, dev_count = write_subset("questions/dev.jsonl", type_name)
    holdout_subset, holdout_count = write_subset("questions/holdout.jsonl", type_name)
    print(f"{C_PURPLE}題型 {type_name}: dev {dev_count} 題, holdout {holdout_count} 題{C_RESET}")

    source_path = current_champion_path(type_name)
    best_source_prompt = load_file(source_path)

    # 先評估目前 champion/baseline 在該題型子題庫上的分數，作為專項 baseline。
    _, base_dev_run, base_dev_summary = evaluate_prompt(source_path, dev_subset, parallel)
    _, base_holdout_run, _ = evaluate_prompt(source_path, holdout_subset, parallel)

    accepted_any = False
    for round_no in range(1, rounds + 1):
        print(f"\n{C_PURPLE}=== {type_name} champion evolution round {round_no}/{rounds} ==={C_RESET}")
        candidate_prompt = build_type_prompt(type_name, best_source_prompt, dev_subset, base_dev_summary, round_no)
        candidate_path = os.path.join("prompts/candidates", f"{slug}_champion_candidate_{int(time.time())}.md")
        write_text(candidate_path, candidate_prompt)

        gate_ok, violations = run_gatekeeper(candidate_prompt)
        if not gate_ok:
            print(f"{C_RED}Gatekeeper 淘汰：{candidate_path}{C_RESET}")
            append_jsonl(LOG_PATH, {
                "event": "gate_reject",
                "type": type_name,
                "candidate": candidate_path,
                "candidate_hash": sha256_text(candidate_prompt),
                "round": round_no,
                "violations": violations,
            })
            continue

        _, cand_dev_run, _ = evaluate_prompt(candidate_path, dev_subset, parallel)
        dev_accept, dev_diff, dev_comparison = compare_run(cand_dev_run, base_dev_run, mode=mode, candidate_id=candidate_path)
        if not dev_accept:
            print(f"{C_RED}Dev 未通過：diff={dev_diff:+.2f}{C_RESET}")
            append_jsonl(LOG_PATH, {
                "event": "dev_reject",
                "type": type_name,
                "candidate": candidate_path,
                "candidate_hash": sha256_text(candidate_prompt),
                "round": round_no,
                "dev_run": cand_dev_run,
                "base_dev_run": base_dev_run,
                "dev_avg": dev_comparison.get("avg_new"),
                "baseline_avg": dev_comparison.get("avg_base"),
                "comparison": acceptance_summary(dev_comparison),
            })
            continue

        _, cand_holdout_run, _ = evaluate_prompt(candidate_path, holdout_subset, parallel)
        holdout_accept, holdout_diff, holdout_comparison = compare_run(cand_holdout_run, base_holdout_run, mode=mode, candidate_id=candidate_path)
        if not holdout_accept:
            print(f"{C_RED}Holdout 未通過：diff={holdout_diff:+.2f}{C_RESET}")
            append_jsonl(LOG_PATH, {
                "event": "holdout_reject",
                "type": type_name,
                "candidate": candidate_path,
                "candidate_hash": sha256_text(candidate_prompt),
                "round": round_no,
                "dev_run": cand_dev_run,
                "holdout_run": cand_holdout_run,
                "holdout_avg": holdout_comparison.get("avg_new"),
                "baseline_avg": holdout_comparison.get("avg_base"),
                "comparison": acceptance_summary(holdout_comparison),
            })
            continue

        champion_path, meta = save_champion(
            type_name,
            candidate_path,
            candidate_prompt,
            cand_dev_run,
            cand_holdout_run,
            dev_comparison,
            holdout_comparison,
        )
        if not champion_path:
            append_jsonl(LOG_PATH, {
                "event": "champion_reject",
                "type": type_name,
                "candidate": candidate_path,
                "candidate_hash": sha256_text(candidate_prompt),
                "round": round_no,
                "meta": meta,
            })
            continue
        update_route()
        print(f"{C_GREEN}✅ 新題型 champion 已更新：{champion_path}{C_RESET}")
        append_jsonl(LOG_PATH, {
            "event": "champion_accept",
            "type": type_name,
            "candidate": candidate_path,
            "candidate_hash": sha256_text(candidate_prompt),
            "round": round_no,
            "champion": champion_path,
            "dev_avg": dev_comparison.get("avg_new"),
            "baseline_avg": dev_comparison.get("avg_base"),
            "meta": meta,
        })
        accepted_any = True
        best_source_prompt = candidate_prompt
        source_path = champion_path
        base_dev_run = cand_dev_run
        base_holdout_run = cand_holdout_run

    return accepted_any


def evaluate_route(parallel):
    route_path, _ = update_route()
    print(f"\n{C_PURPLE}=== 全題型 route dev/holdout 驗證 ==={C_RESET}")
    _, route_dev_run, _ = evaluate_routed(route_path, "questions/dev.jsonl", parallel)
    _, route_holdout_run, _ = evaluate_routed(route_path, "questions/holdout.jsonl", parallel)
    baseline_meta = read_json("prompts/baseline.meta.json", {})
    dev_accepted, dev_diff, dev_comparison = compare_run(
        route_dev_run,
        baseline_meta.get("dev_run", "runs/20260524_041843"),
        mode="pragmatic",
    )
    holdout_accepted, holdout_diff, holdout_comparison = compare_run(
        route_holdout_run,
        baseline_meta.get("holdout_run", "runs/20260524_162523"),
        mode="pragmatic",
    )
    accepted = bool(dev_accepted and holdout_accepted)
    decision = {
        "route": route_path,
        "dev_run": route_dev_run,
        "holdout_run": route_holdout_run,
        "baseline_dev_run": baseline_meta.get("dev_run"),
        "baseline_holdout_run": baseline_meta.get("holdout_run"),
        "dev_accepted": dev_accepted,
        "holdout_accepted": holdout_accepted,
        "accepted": accepted,
        "decision": "ACCEPT_ROUTE" if accepted else "REJECT_ROUTE",
        "dev_diff": dev_diff,
        "holdout_diff": holdout_diff,
        "dev_comparison": acceptance_summary(dev_comparison),
        "holdout_comparison": acceptance_summary(holdout_comparison),
    }
    write_json("prompts/routes/type_champions.decision.json", decision)
    print(f"{C_GREEN}Route dev run: {route_dev_run}{C_RESET}")
    print(f"{C_GREEN}Route holdout run: {route_holdout_run}{C_RESET}")
    print(f"{C_GREEN if accepted else C_RED}Route decision: {decision['decision']}{C_RESET}")
    append_jsonl(LOG_PATH, {
        "event": "route_eval",
        "route": route_path,
        "dev_run": route_dev_run,
        "holdout_run": route_holdout_run,
        "decision": decision["decision"],
        "dev_diff": dev_diff,
        "holdout_diff": holdout_diff,
    })


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", dest="type_name", help="題型名稱或 slug，例如 評析題 / commentary")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--parallel", type=int, default=24)
    parser.add_argument("--mode", choices=["strict", "pragmatic"], default="pragmatic")
    parser.add_argument("--skip-route-eval", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.all and not args.type_name:
        print("請指定 --type 題型 或 --all")
        return 1

    types = list(TYPE_SLUGS.keys()) if args.all else [normalize_type(args.type_name)]
    accepted = False
    for type_name in types:
        accepted = evolve_one_type(type_name, args.rounds, args.parallel, args.mode) or accepted

    update_route()
    if not args.skip_route_eval and (accepted or args.all):
        evaluate_route(args.parallel)
    else:
        print(f"{C_YELLOW}未產生新 champion，略過全題型 route 評估。{C_RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
