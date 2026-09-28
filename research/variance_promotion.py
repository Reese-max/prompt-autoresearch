"""Reproducible, DEV-only variance experiment for issue #3.

This module never calls a provider or changes the champion. The guard width,
replicate budget, and synthetic noise below are experiment inputs, not a
production acceptance policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path


RECEIPT_VERSION = 1
DECISIONS = (
    "PROMOTE",
    "REJECT",
    "INCONCLUSIVE_NEEDS_MORE_TRIALS",
    "BLOCKED_EVIDENCE_DRIFT",
)
COHORT_FIELDS = (
    "dataset_split",
    "dataset_sha256",
    "provider",
    "model_version",
    "judge_sha256",
    "evaluator_sha256",
    "scorer_sha256",
)
USAGE_CENTERS = ("primary", "judge", "retry")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def unknown_usage() -> dict:
    """Separate provider spend centers without inventing token or price data."""
    return {
        name: {"status": "UNKNOWN", "tokens": None, "cost_usd": None}
        for name in USAGE_CENTERS
    }


def _stats(values: list[float]) -> dict:
    return {
        "n": len(values),
        "mean": statistics.mean(values) if values else None,
        "median": statistics.median(values) if values else None,
        "stddev": statistics.stdev(values) if len(values) > 1 else None,
    }


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate(receipt: dict) -> tuple[str, ...]:
    if receipt.get("schema_version") != RECEIPT_VERSION:
        raise ValueError("unsupported receipt version")
    if receipt.get("evidence_kind") not in ("SYNTHETIC", "LIVE_DEV"):
        raise ValueError("unknown evidence kind")
    cohort = receipt.get("cohort")
    if not isinstance(cohort, dict) or any(not cohort.get(key) for key in COHORT_FIELDS):
        raise ValueError("incomplete cohort")
    if cohort["dataset_split"] != "dev":
        raise ValueError("research receipt must use DEV, never holdout")
    if not all(_is_sha256(cohort[key]) for key in ("dataset_sha256", "judge_sha256", "evaluator_sha256", "scorer_sha256")):
        raise ValueError("cohort hashes must be SHA-256")
    if not _is_sha256(receipt.get("prompt_sha256")):
        raise ValueError("missing prompt hash")
    trials = receipt.get("trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("missing trials")
    expected_ids = None
    expected_types = None
    controlled_seeds = set()
    for index, trial in enumerate(trials):
        if trial.get("replicate_index") != index:
            raise ValueError("replicate indices must be unique and ordered")
        if trial.get("seed") is not None and not isinstance(trial["seed"], int):
            raise ValueError("seed must be an integer or null")
        if trial.get("seed") is not None:
            if trial["seed"] in controlled_seeds:
                raise ValueError("controlled seeds must be unique within an arm")
            controlled_seeds.add(trial["seed"])
        if trial.get("cached") is not False or trial.get("error") is not None:
            raise ValueError("cached or failed trials are not independent evidence")
        items = trial.get("items")
        if not isinstance(items, dict) or not items:
            raise ValueError("missing per-item evidence")
        ids = tuple(sorted(items))
        types = tuple(items[qid].get("type") for qid in ids)
        if any(not isinstance(kind, str) or not kind for kind in types):
            raise ValueError("missing item type")
        if expected_ids is None:
            expected_ids, expected_types = ids, types
        elif ids != expected_ids or types != expected_types:
            raise ValueError("item set or type changed within a replicate set")
        for item in items.values():
            for key in ("total_score", "risk_score"):
                value = item.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"invalid {key}")
            if not isinstance(item.get("failures"), list):
                raise ValueError("missing failures")
            if not all(isinstance(code, str) for code in item["failures"]):
                raise ValueError("invalid failure code")
        usage = trial.get("usage")
        if not isinstance(usage, dict) or set(usage) != set(USAGE_CENTERS):
            raise ValueError("primary/judge/retry usage must be separate")
        for entry in usage.values():
            if entry.get("status") not in ("MEASURED", "ESTIMATED", "UNKNOWN"):
                raise ValueError("usage needs evidence status")
            if entry["status"] == "UNKNOWN" and (
                entry.get("tokens") is not None or entry.get("cost_usd") is not None
            ):
                raise ValueError("unknown usage cannot have numeric values")
            if entry["status"] != "UNKNOWN" and (
                not isinstance(entry.get("tokens"), (int, float))
                or not isinstance(entry.get("cost_usd"), (int, float))
                or not math.isfinite(entry["tokens"])
                or not math.isfinite(entry["cost_usd"])
                or entry["tokens"] < 0
                or entry["cost_usd"] < 0
            ):
                raise ValueError("measured/estimated usage needs nonnegative numbers")
        latency = trial.get("latency_ms")
        if not isinstance(latency, dict) or latency.get("status") not in ("MEASURED", "ESTIMATED", "UNKNOWN"):
            raise ValueError("latency needs evidence status")
        if latency["status"] == "UNKNOWN" and latency.get("value") is not None:
            raise ValueError("unknown latency cannot have a numeric value")
    return expected_ids


def replicate_receipt(prompt_sha256: str, cohort: dict, trials: list[dict], *, evidence_kind="SYNTHETIC") -> dict:
    """Create a versioned receipt; a null seed means no seed control is claimed."""
    receipt = {
        "schema_version": RECEIPT_VERSION,
        "evidence_kind": evidence_kind,
        "prompt_sha256": prompt_sha256,
        "cohort": dict(cohort),
        "trials": trials,
    }
    ids = _validate(receipt)
    scores = [item["total_score"] for trial in trials for item in trial["items"].values()]
    risks = [item["risk_score"] for trial in trials for item in trial["items"].values()]
    by_type = {}
    for qid in ids:
        kind = trials[0]["items"][qid]["type"]
        by_type.setdefault(kind, []).extend(trial["items"][qid]["total_score"] for trial in trials)
    receipt["summary"] = {
        "total_score": _stats(scores),
        "risk_score": _stats(risks),
        "failure_rate": sum(bool(item["failures"]) for trial in trials for item in trial["items"].values()) / len(scores),
        "by_type": {kind: _stats(values) for kind, values in sorted(by_type.items())},
    }
    return receipt


def calibrate_paired_noise(baseline: dict, control: dict, *, guard_multiplier: float) -> dict:
    """Calibrate from repeated fixed-prompt paired DEV trials, separately from candidates."""
    ids = _validate(baseline)
    if _validate(control) != ids or baseline["cohort"] != control["cohort"]:
        raise ValueError("calibration cohort or item drift")
    if baseline["prompt_sha256"] != control["prompt_sha256"]:
        raise ValueError("calibration must rerun the same prompt")
    if len(baseline["trials"]) != len(control["trials"]) or len(baseline["trials"]) < 2:
        raise ValueError("calibration needs matching repeated trials")
    if not math.isfinite(guard_multiplier) or guard_multiplier < 0:
        raise ValueError("invalid illustrative guard multiplier")
    score_deltas = []
    risk_deltas = []
    type_deltas = {}
    for base_trial, control_trial in zip(baseline["trials"], control["trials"]):
        if base_trial["seed"] != control_trial["seed"]:
            raise ValueError("controlled calibration seeds must match by pair")
        base_items, control_items = base_trial["items"], control_trial["items"]
        score_deltas.append(statistics.mean(control_items[qid]["total_score"] - base_items[qid]["total_score"] for qid in ids))
        risk_deltas.append(statistics.mean(control_items[qid]["risk_score"] - base_items[qid]["risk_score"] for qid in ids))
        for kind in {base_items[qid]["type"] for qid in ids}:
            of_type = [qid for qid in ids if base_items[qid]["type"] == kind]
            type_deltas.setdefault(kind, []).append(statistics.mean(control_items[qid]["total_score"] - base_items[qid]["total_score"] for qid in of_type))
    score_stats = _stats(score_deltas)
    return {
        "profile_version": 1,
        "evidence_kind": baseline["evidence_kind"],
        "cohort": dict(baseline["cohort"]),
        "prompt_sha256": baseline["prompt_sha256"],
        "calibration_pairs": len(score_deltas),
        "paired_score_delta": score_stats,
        "paired_risk_delta": _stats(risk_deltas),
        "paired_type_delta": {kind: _stats(values) for kind, values in sorted(type_deltas.items())},
        "guard_multiplier": guard_multiplier,
        "guard_width": guard_multiplier * score_stats["stddev"],
        "provider_tokens_cost_latency": "UNKNOWN",
    }


def single_run_score_gate(baseline: dict, candidate: dict, *, min_improvement: float) -> bool:
    """The existing compare_runs score condition only; all other gates are held fixed."""
    _validate(baseline)
    _validate(candidate)
    base = statistics.mean(item["total_score"] for item in baseline["trials"][0]["items"].values())
    new = statistics.mean(item["total_score"] for item in candidate["trials"][0]["items"].values())
    delta = new - base
    return delta >= min_improvement or (new >= 92 and delta >= 0)


def paired_decision(
    baseline: dict,
    candidate: dict,
    *,
    min_improvement: float,
    noise_profile: dict,
    min_pairs: int,
    budget_eval_units: int,
    hard_gates_passed: bool,
) -> dict:
    """Illustrative sequential rule; each paired replicate costs two eval units.

    The width is supplied by the experiment. It is not a p-value or a live
    confidence guarantee; real use requires independent empirical calibration.
    """
    if baseline.get("cohort") != candidate.get("cohort") or baseline.get("cohort") != noise_profile.get("cohort"):
        return {"decision": "BLOCKED_EVIDENCE_DRIFT", "reason": "cohort_mismatch", "pairs_used": 0, "eval_units": 0}
    try:
        ids = _validate(baseline)
        candidate_ids = _validate(candidate)
    except (ValueError, AttributeError, TypeError) as exc:
        return {"decision": "INCONCLUSIVE_NEEDS_MORE_TRIALS", "reason": f"invalid_evidence: {exc}", "pairs_used": 0, "eval_units": 0}
    if ids != candidate_ids:
        return {"decision": "BLOCKED_EVIDENCE_DRIFT", "reason": "item_mismatch", "pairs_used": 0, "eval_units": 0}
    base_types = tuple(baseline["trials"][0]["items"][qid]["type"] for qid in ids)
    candidate_types = tuple(candidate["trials"][0]["items"][qid]["type"] for qid in ids)
    if base_types != candidate_types:
        return {"decision": "BLOCKED_EVIDENCE_DRIFT", "reason": "type_mismatch", "pairs_used": 0, "eval_units": 0}
    if baseline["evidence_kind"] != candidate["evidence_kind"] or baseline["evidence_kind"] != noise_profile.get("evidence_kind"):
        return {"decision": "BLOCKED_EVIDENCE_DRIFT", "reason": "evidence_kind_mismatch", "pairs_used": 0, "eval_units": 0}
    calibration_width = noise_profile.get("guard_width")
    if noise_profile.get("profile_version") != 1 or not isinstance(calibration_width, (int, float)) or not math.isfinite(calibration_width) or calibration_width < 0:
        return {"decision": "INCONCLUSIVE_NEEDS_MORE_TRIALS", "reason": "invalid_noise_profile", "pairs_used": 0, "eval_units": 0}
    if min_pairs < 2 or budget_eval_units < 0:
        raise ValueError("invalid experiment parameters")
    if not hard_gates_passed:
        return {"decision": "REJECT", "reason": "existing_hard_gate", "pairs_used": 0, "eval_units": 0}
    available = min(len(baseline["trials"]), len(candidate["trials"]), budget_eval_units // 2)
    deltas = []
    for index in range(available):
        if baseline["trials"][index]["seed"] != candidate["trials"][index]["seed"]:
            return {"decision": "BLOCKED_EVIDENCE_DRIFT", "reason": "paired_seed_mismatch", "pairs_used": index, "eval_units": 2 * index}
        base_items = baseline["trials"][index]["items"]
        candidate_items = candidate["trials"][index]["items"]
        deltas.append(statistics.mean(candidate_items[qid]["total_score"] - base_items[qid]["total_score"] for qid in ids))
        n = len(deltas)
        if n < min_pairs:
            continue
        mean = statistics.mean(deltas)
        width = calibration_width / math.sqrt(n)
        common = {"pairs_used": n, "eval_units": 2 * n, "paired_mean_delta": mean, "guard_width": width}
        if mean - width >= min_improvement:
            return {"decision": "PROMOTE", "reason": "paired_margin_above_boundary", **common}
        if mean + width < min_improvement:
            return {"decision": "REJECT", "reason": "paired_margin_below_boundary", **common}
    return {
        "decision": "INCONCLUSIVE_NEEDS_MORE_TRIALS",
        "reason": "budget_or_trials_exhausted",
        "pairs_used": available,
        "eval_units": 2 * available,
        "paired_mean_delta": statistics.mean(deltas) if deltas else None,
    }


def _synthetic_pair(rng: random.Random, index: int, true_delta: float, item_ids: tuple[str, ...]) -> tuple[dict, dict]:
    seed = rng.randrange(2**32)
    trial_rng = random.Random(seed)
    baseline_items, candidate_items = {}, {}
    for position, qid in enumerate(item_ids):
        difficulty = position - (len(item_ids) - 1) / 2
        shared = trial_rng.gauss(0, 1.0)
        baseline_score = 75 + difficulty + shared + trial_rng.gauss(0, 2.0)
        candidate_score = 75 + difficulty + true_delta + shared + trial_rng.gauss(0, 2.0)
        common = {"type": "legal" if position % 2 else "analysis", "risk_score": 10, "failures": []}
        baseline_items[qid] = {**common, "total_score": baseline_score}
        candidate_items[qid] = {**common, "total_score": candidate_score}
    base = {"replicate_index": index, "seed": seed, "items": baseline_items, "cached": False, "error": None, "usage": unknown_usage(), "latency_ms": {"status": "UNKNOWN", "value": None}}
    candidate = {"replicate_index": index, "seed": seed, "items": candidate_items, "cached": False, "error": None, "usage": unknown_usage(), "latency_ms": {"status": "UNKNOWN", "value": None}}
    return base, candidate


def simulate(*, seed: int, cases: int, max_pairs: int, min_pairs: int, budget_eval_units: int, calibration_pairs: int, guard_multiplier: float, min_improvement: float) -> dict:
    if cases < 1 or max_pairs < 1 or calibration_pairs < 2:
        raise ValueError("cases/max_pairs must be positive and calibration_pairs >= 2")
    rng = random.Random(seed)
    item_ids = ("q1", "q2", "q3", "q4")
    source_hash = sha256_text(Path(__file__).read_text(encoding="utf-8").replace("\r\n", "\n"))
    cohort = {
        "dataset_split": "dev",
        "dataset_sha256": sha256_text(json.dumps(item_ids)),
        "provider": "synthetic",
        "model_version": "known-noise-v1",
        "judge_sha256": sha256_text("synthetic-judge-v1"),
        "evaluator_sha256": source_hash,
        "scorer_sha256": source_hash,
    }
    calibration_trials = [_synthetic_pair(rng, index, 0.0, item_ids) for index in range(calibration_pairs)]
    calibration_baseline = replicate_receipt(
        sha256_text("baseline prompt"), cohort, [pair[0] for pair in calibration_trials]
    )
    calibration_control = replicate_receipt(
        sha256_text("baseline prompt"), cohort, [pair[1] for pair in calibration_trials]
    )
    noise_profile = calibrate_paired_noise(
        calibration_baseline, calibration_control, guard_multiplier=guard_multiplier
    )
    scenarios = {}
    example = None
    for label, true_delta in (("no_improvement", 0.0), ("large_improvement", 3.0)):
        old_counts, paired_counts = Counter(), Counter()
        units = 0
        for _ in range(cases):
            pairs = [_synthetic_pair(rng, index, true_delta, item_ids) for index in range(max_pairs)]
            baseline = replicate_receipt(sha256_text("baseline prompt"), cohort, [pair[0] for pair in pairs])
            candidate = replicate_receipt(sha256_text("candidate prompt"), cohort, [pair[1] for pair in pairs])
            old_counts["PROMOTE" if single_run_score_gate(baseline, candidate, min_improvement=min_improvement) else "REJECT"] += 1
            result = paired_decision(
                baseline, candidate, min_improvement=min_improvement,
                noise_profile=noise_profile, min_pairs=min_pairs,
                budget_eval_units=budget_eval_units, hard_gates_passed=True,
            )
            paired_counts[result["decision"]] += 1
            units += result["eval_units"]
            if example is None:
                example = {"baseline": baseline, "candidate": candidate, "paired_decision": result}
        scenarios[label] = {
            "true_delta": true_delta,
            "single_run_score_gate": dict(old_counts),
            "paired_research_rule": dict(paired_counts),
            "single_run_eval_units": 2 * cases,
            "paired_eval_units": units,
            "extra_eval_units": units - 2 * cases,
        }
    return {
        "report_version": 1,
        "evidence_kind": "SYNTHETIC_ONLY",
        "decision": "NARROW",
        "seed": seed,
        "parameters": {
            "cases_per_scenario": cases,
            "items_per_trial": len(item_ids),
            "max_pairs": max_pairs,
            "min_pairs": min_pairs,
            "budget_eval_units_per_case": budget_eval_units,
            "calibration_pairs": calibration_pairs,
            "calibration_eval_units": 2 * calibration_pairs,
            "guard_multiplier": guard_multiplier,
            "score_gate_min_improvement": min_improvement,
            "noise_model": "paired shared N(0,1) plus independent arm N(0,2) per item",
        },
        "scenarios": scenarios,
        "noise_profile": noise_profile,
        "example_receipt": example,
        "holdout_policy": "No holdout input or item-level holdout output; reserve one bounded final gate outside this research module.",
        "provider_tokens_cost_latency": "UNKNOWN: synthetic evaluation units are not provider billing or elapsed time",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260929)
    parser.add_argument("--cases", type=int, default=1000)
    parser.add_argument("--max-pairs", type=int, default=5)
    parser.add_argument("--min-pairs", type=int, default=2)
    parser.add_argument("--budget-eval-units", type=int, default=10)
    parser.add_argument("--calibration-pairs", type=int, default=24)
    parser.add_argument("--guard-multiplier", type=float, default=2.0)
    parser.add_argument("--min-improvement", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = simulate(
        seed=args.seed, cases=args.cases, max_pairs=args.max_pairs,
        min_pairs=args.min_pairs, budget_eval_units=args.budget_eval_units,
        calibration_pairs=args.calibration_pairs, guard_multiplier=args.guard_multiplier,
        min_improvement=args.min_improvement,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
