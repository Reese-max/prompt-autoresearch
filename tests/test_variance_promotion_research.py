"""Offline issue #3 fixtures. These never call a provider or save a champion."""

import json

import pytest

import route_evolve
import scripts.compare_runs as compare_runs
from research.variance_promotion import (
    calibrate_paired_noise,
    paired_decision,
    replicate_receipt,
    sha256_text,
    simulate,
    single_run_score_gate,
    unknown_usage,
)


COHORT = {
    "dataset_split": "dev",
    "dataset_sha256": sha256_text("fixed dev items"),
    "provider": "fixture",
    "model_version": "fixture-model-v1",
    "judge_sha256": sha256_text("fixture judge"),
    "evaluator_sha256": sha256_text("fixture evaluator"),
    "scorer_sha256": sha256_text("fixture scorer"),
}


def receipt(scores, *, prompt="baseline", cohort=None):
    trials = [
        {
            "replicate_index": index,
            "seed": None,
            "cached": False,
            "error": None,
            "items": {
                "q1": {
                    "type": "legal",
                    "total_score": score,
                    "risk_score": 10,
                    "failures": [],
                }
            },
            "usage": unknown_usage(),
            "latency_ms": {"status": "UNKNOWN", "value": None},
        }
        for index, score in enumerate(scores)
    ]
    return replicate_receipt(sha256_text(prompt), cohort or COHORT, trials)


def paired(base, candidate, *, budget=8, width=2.0, hard_gates=True):
    profile = {
        "profile_version": 1,
        "evidence_kind": "SYNTHETIC",
        "cohort": base["cohort"],
        "guard_width": width,
    }
    return paired_decision(
        base,
        candidate,
        min_improvement=2.0,
        noise_profile=profile,
        min_pairs=2,
        budget_eval_units=budget,
        hard_gates_passed=hard_gates,
    )


def test_current_compare_runs_accepts_one_lucky_run(tmp_path):
    """Run the real current comparator with all non-score gates passing."""
    for name, score in (("baseline", 80), ("candidate", 86)):
        run = tmp_path / name
        run.mkdir()
        row = {
            "id": "q1",
            "type": "legal",
            "answer": "valid answer",
            "total_score": score,
            "risk_score": 10,
            "failures": [],
            "char_count": 1000,
        }
        (run / "details.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    accepted, _, diff = compare_runs.compare(
        str(tmp_path / "candidate"), str(tmp_path / "baseline"), mode="pragmatic"
    )
    assert accepted is True
    assert diff == 6
    assert compare_runs.LAST_COMPARISON["score_diff"] == 6


def test_route_evolution_uses_one_candidate_run_per_split_before_promotion(monkeypatch):
    """Pin the current call path, including DEV then holdout and champion write."""
    calls = []
    monkeypatch.setattr(route_evolve, "write_subset", lambda path, _kind: (path, 1))
    monkeypatch.setattr(route_evolve, "current_champion_path", lambda _kind: "baseline.md")
    monkeypatch.setattr(route_evolve, "load_file", lambda _path: "baseline prompt")
    monkeypatch.setattr(route_evolve, "build_type_prompt", lambda *_args: "candidate prompt")
    monkeypatch.setattr(route_evolve, "write_text", lambda *_args: None)
    monkeypatch.setattr(route_evolve, "run_gatekeeper", lambda *_args: (True, []))
    monkeypatch.setattr(route_evolve, "append_jsonl", lambda *_args: None)
    monkeypatch.setattr(route_evolve, "update_route", lambda: None)

    def evaluate(path, split, _parallel):
        calls.append(("evaluate", path, split))
        return 0, f"run-{len(calls)}", {}

    def compare(new, base, **_kwargs):
        calls.append(("compare", new, base))
        return True, 6.0, {"avg_new": 86, "avg_base": 80}

    def champion(*_args):
        calls.append(("save_champion",))
        return "champion.md", {}

    monkeypatch.setattr(route_evolve, "evaluate_prompt", evaluate)
    monkeypatch.setattr(route_evolve, "compare_run", compare)
    monkeypatch.setattr(route_evolve, "save_champion", champion)
    assert route_evolve.evolve_one_type(next(iter(route_evolve.TYPE_SLUGS)), 1, 1, "pragmatic") is True
    assert [call[0] for call in calls] == [
        "evaluate", "evaluate", "evaluate", "compare", "evaluate", "compare", "save_champion"
    ]
    assert calls[2][2] == "questions/dev.jsonl"
    assert calls[4][2] == "questions/holdout.jsonl"


def test_versioned_receipt_tracks_cohort_dispersion_risk_and_unknown_usage():
    record = receipt([80, 82, 78])
    assert record["schema_version"] == 1
    assert record["cohort"] == COHORT
    assert record["summary"]["total_score"]["mean"] == 80
    assert record["summary"]["total_score"]["stddev"] == 2
    assert record["summary"]["risk_score"]["mean"] == 10
    assert record["summary"]["by_type"]["legal"]["n"] == 3
    assert record["trials"][0]["seed"] is None
    assert record["trials"][0]["usage"]["judge"]["status"] == "UNKNOWN"


def test_fixed_prompt_calibration_records_paired_and_type_noise():
    base = receipt([80, 80, 80])
    control = receipt([78, 80, 82])
    profile = calibrate_paired_noise(base, control, guard_multiplier=2.0)
    assert profile["cohort"] == COHORT
    assert profile["paired_score_delta"]["mean"] == 0
    assert profile["paired_score_delta"]["stddev"] == 2
    assert profile["paired_risk_delta"]["stddev"] == 0
    assert profile["paired_type_delta"]["legal"]["stddev"] == 2
    assert profile["guard_width"] == 4
    with pytest.raises(ValueError, match="same prompt"):
        calibrate_paired_noise(base, receipt([78, 80, 82], prompt="new"), guard_multiplier=2.0)


@pytest.mark.parametrize("field,value", [("cached", True), ("error", "timeout")])
def test_invalid_or_cached_trial_cannot_be_counted_as_fresh_replicate(field, value):
    base = receipt([80, 80])
    candidate = receipt([86, 86], prompt="candidate")
    candidate["trials"][1][field] = value
    result = paired(base, candidate)
    assert result["decision"] == "INCONCLUSIVE_NEEDS_MORE_TRIALS"
    assert result["pairs_used"] == 0


def test_reused_or_mismatched_controlled_seed_does_not_count_as_pair():
    base = receipt([80, 80])
    candidate = receipt([86, 86], prompt="candidate")
    base["trials"][0]["seed"] = 10
    base["trials"][1]["seed"] = 11
    candidate["trials"][0]["seed"] = 10
    candidate["trials"][1]["seed"] = 12
    assert paired(base, candidate)["decision"] == "BLOCKED_EVIDENCE_DRIFT"
    candidate["trials"][1]["seed"] = 10
    assert paired(base, candidate)["decision"] == "INCONCLUSIVE_NEEDS_MORE_TRIALS"


def test_lucky_first_run_promotes_old_score_gate_but_paired_rule_rejects():
    base = receipt([80, 80, 80, 80])
    candidate = receipt([86, 79, 79, 79], prompt="candidate")
    assert single_run_score_gate(base, candidate, min_improvement=2.0)
    result = paired(base, candidate)
    assert result["decision"] == "REJECT"
    assert result["pairs_used"] == 4


def test_large_improvement_stops_early_and_budget_never_auto_promotes():
    base = receipt([80, 80, 80, 80])
    candidate = receipt([85, 85, 85, 85], prompt="candidate")
    early = paired(base, candidate)
    assert (early["decision"], early["pairs_used"], early["eval_units"]) == (
        "PROMOTE", 2, 4
    )
    capped = paired(base, candidate, budget=2)
    assert capped["decision"] == "INCONCLUSIVE_NEEDS_MORE_TRIALS"
    assert capped["pairs_used"] == 1
    assert paired(base, candidate, hard_gates=False)["decision"] == "REJECT"


@pytest.mark.parametrize("field", ["dataset_sha256", "model_version", "judge_sha256", "evaluator_sha256"])
def test_cohort_drift_blocks_comparison(field):
    base = receipt([80, 80])
    changed = {**COHORT, field: "new-cohort" if field == "model_version" else sha256_text("new-cohort")}
    candidate = receipt([86, 86], prompt="candidate", cohort=changed)
    assert paired(base, candidate)["decision"] == "BLOCKED_EVIDENCE_DRIFT"


def test_old_noise_profile_is_stale_after_shared_model_drift():
    old = receipt([80, 80])
    profile = calibrate_paired_noise(old, receipt([79, 81]), guard_multiplier=2.0)
    changed = {**COHORT, "model_version": "fixture-model-v2"}
    new_base = receipt([80, 80], cohort=changed)
    new_candidate = receipt([86, 86], prompt="candidate", cohort=changed)
    result = paired_decision(
        new_base, new_candidate, min_improvement=2.0, noise_profile=profile,
        min_pairs=2, budget_eval_units=4, hard_gates_passed=True,
    )
    assert result["decision"] == "BLOCKED_EVIDENCE_DRIFT"


def test_holdout_input_is_not_a_dev_replicate():
    base = receipt([80, 80])
    holdout = receipt([86, 86], prompt="candidate")
    holdout["cohort"] = {**COHORT, "dataset_split": "holdout"}
    assert paired(base, holdout)["decision"] == "BLOCKED_EVIDENCE_DRIFT"


def test_seeded_simulation_replays_and_compares_false_promotion():
    params = dict(
        seed=20260929,
        cases=100,
        max_pairs=5,
        min_pairs=2,
        budget_eval_units=10,
        calibration_pairs=24,
        guard_multiplier=2.0,
        min_improvement=2.0,
    )
    report = simulate(**params)
    assert report == simulate(**params)
    null = report["scenarios"]["no_improvement"]
    improved = report["scenarios"]["large_improvement"]
    assert null["paired_research_rule"].get("PROMOTE", 0) < null["single_run_score_gate"].get("PROMOTE", 0)
    assert improved["paired_research_rule"].get("PROMOTE", 0) > 0
    assert null["paired_eval_units"] <= 100 * 10
    assert improved["paired_eval_units"] <= 100 * 10
    assert report["evidence_kind"] == "SYNTHETIC_ONLY"
    assert "No holdout input" in report["holdout_policy"]
