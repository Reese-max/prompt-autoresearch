"""Finite synthetic truth and immutable historical replay; never provider calls."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from research.complexity_pareto import (
    COHORT_FIELDS, GATES, METRICS, compaction_candidate, complexity_receipt,
    digest, experiment, historical_replay, observation, pareto_decision,
    synthetic_quality, synthetic_receipt,
)
from scripts.gatekeeper import run_gatekeeper


ROOT = Path(__file__).resolve().parents[1]


def frozen_prompt():
    fixture = json.loads((ROOT / "research/fixtures/complexity-history-v1.json").read_text(encoding="utf-8"))
    return next(entry["content"] for entry in fixture["artifacts"] if entry["role"] == "current_baseline")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline research attempted network access")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def pair():
    return (synthetic_receipt("safe legal rule repeated repeated", version="base", scale=2),
            synthetic_receipt("safe legal rule repeated", version="candidate"))


def decide(base, candidate, quality=None, **policy):
    return pareto_decision(base, candidate, quality or synthetic_quality(base, candidate),
                           absolute_chars=policy.get("absolute_chars", 900),
                           max_token_growth=policy.get("max_token_growth", 0.1))


def sections():
    # The immutable legal/role passage is real current text; duplicate line is a
    # chosen synthetic no-op. This is not a measured real compaction win.
    prompt = frozen_prompt()
    parts = [{"id": "protected-core", "text": prompt},
             {"id": "style-a", "text": "以清楚標題整理答案。"},
             {"id": "style-b", "text": "以清楚標題整理答案。"},
             {"id": "style-c", "text": "以清楚標題整理答案。"},
             {"id": "spacing", "text": "清楚  表達。  "}]
    return parts, {"protected-core": digest(prompt)}


def test_known_equivalent_compact_candidate_is_inactive():
    base, new = pair()
    result = decide(base, new)
    assert result["decision"] == "COMPACT_CANDIDATE"
    assert result["active"] is False and result["promotion_allowed"] is False
    assert result["baseline_sha256"] == base["prompt_sha256"]


def test_ratchet_relative_reference_passes_but_absolute_budget_stops_it():
    report = experiment(ROOT)
    assert len(report["ratchet"]) == 12
    assert all(row["relative_only_reference_accepts"] for row in report["ratchet"])
    assert report["ratchet"][-1]["after_tokens"] > 2 * report["ratchet"][0]["before_tokens"]
    assert any(row["absolute_plus_relative_decision"]["reason"] == "illustrative absolute text budget exceeded"
               for row in report["ratchet"])
    assert report["decision"] == "NARROW" and not report["promotion_allowed"]


def test_relative_guard_is_retained_even_when_absolute_budget_allows_growth():
    base = synthetic_receipt(" ".join(["x"] * 10), version="base")
    candidate = synthetic_receipt(" ".join(["x"] * 12), version="candidate")
    assert decide(base, candidate)["reason"] == "relative same-tokenizer growth budget exceeded"


def test_tradeoff_never_silently_promotes():
    base, new = pair()
    new = synthetic_receipt("safe legal rule repeated", version="expensive", scale=3)
    quality = synthetic_quality(base, new, relation="BETTER")
    assert decide(base, new, quality)["decision"] == "TRADEOFF_REVIEW"
    assert not decide(base, new, quality)["promotion_allowed"]


@pytest.mark.parametrize("which", ["safety", "types", "quality", *GATES])
def test_regression_rejects_before_any_size_advantage(which):
    base, new = pair()
    q = synthetic_quality(base, new)
    if which in GATES:
        q["gates"][which] = "FAIL"
    elif which == "quality":
        q["relation"] = "WORSE"
    else:
        q[which] = "FAIL"
    assert decide(base, new, q)["decision"] == "REJECT"


def test_actual_gatekeeper_blocks_removed_legal_and_role_constraints():
    prompt = frozen_prompt()
    assert run_gatekeeper(prompt)[0] is True
    for altered, expected_rule in (
        (prompt.replace("杜絕捏造", ""), "R04_NO_ANTI_FABRICATION"),
        (prompt.replace("專家", ""), "R05_NO_EXPERT_ROLE"),
    ):
        passed, violations = run_gatekeeper(altered)
        assert passed is False
        assert any(v["rule"] == expected_rule and v["severity"] == "reject" for v in violations)
        base, new = synthetic_receipt(prompt, version="base"), synthetic_receipt(altered, version="unsafe")
        q = synthetic_quality(base, new)
        q["gates"]["Gatekeeper"] = "PASS" if passed else "FAIL"
        assert decide(base, new, q)["decision"] == "REJECT"


@pytest.mark.parametrize("field", COHORT_FIELDS)
def test_tokenizer_model_provider_dataset_pricing_drift_is_not_compared(field):
    base, new = pair()
    new["cohort"][field] = digest("changed") if field.endswith("sha256") else "changed"
    if field == "dataset_split":
        new["cohort"][field] = "holdout"
        with pytest.raises(ValueError, match="DEV-only"):
            decide(base, new)
    else:
        assert decide(base, new)["decision"] == "BLOCKED_EVIDENCE_DRIFT"


@pytest.mark.parametrize("target", ["baseline_sha256", "candidate_sha256", "cache"])
def test_receipts_bound_to_prompt_and_cache(target):
    base, new = pair()
    q = synthetic_quality(base, new)
    if target == "cache":
        new["cache_eligibility_fingerprint"] = digest("different prefix eligibility")
    else:
        q[target] = digest("other prompt")
    assert decide(base, new, q)["decision"] == "BLOCKED_EVIDENCE_DRIFT"


@pytest.mark.parametrize("name", METRICS)
def test_unknown_or_mixed_evidence_does_not_become_a_win(name):
    base, new = pair()
    new["metrics"][name] = observation()
    assert decide(base, new)["decision"] == "INCONCLUSIVE"
    base, new = pair()
    new["metrics"][name]["status"] = "MEASURED" if new["metrics"][name]["status"] == "ESTIMATED" else "ESTIMATED"
    assert decide(base, new)["decision"] == "INCONCLUSIVE"


@pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan"), "10"])
def test_invalid_observations_rejected(value):
    with pytest.raises(ValueError):
        observation(value, status="MEASURED", provenance="test")


def test_fractional_input_token_count_is_not_a_valid_receipt():
    base, _ = pair()
    metrics = {name: dict(entry) for name, entry in base["metrics"].items()}
    metrics["input_tokens"]["value"] = 2.5
    with pytest.raises(ValueError, match="integer"):
        complexity_receipt("safe legal", version="fractional", cohort=base["cohort"],
                           evidence_kind="SYNTHETIC", observations=metrics)


def test_reversed_latency_quantiles_are_not_valid_evidence():
    base, new = pair()
    new["metrics"]["latency_p50_ms"]["value"] = 5
    new["metrics"]["latency_p95_ms"]["value"] = 1
    with pytest.raises(ValueError, match="quantiles"):
        decide(base, new)


def test_identical_prompt_hash_cannot_claim_different_literal_size():
    base, new = pair()
    new["prompt_sha256"] = base["prompt_sha256"]
    q = synthetic_quality(base, new)
    with pytest.raises(ValueError, match="identical prompt"):
        decide(base, new, q)


@pytest.mark.parametrize("field", ["provider", "model_version", "tokenizer", "price_basis"])
@pytest.mark.parametrize("value", [" \t ", " UNKNOWN "])
@pytest.mark.parametrize("entrypoint", ["constructor", "serialized"])
def test_cohort_identity_cannot_be_blank_or_wrap_unknown(field, value, entrypoint):
    base, new = pair()
    base["cohort"][field] = new["cohort"][field] = value
    with pytest.raises(ValueError, match="cohort"):
        if entrypoint == "constructor":
            complexity_receipt("safe legal", version="invalid", cohort=base["cohort"],
                               evidence_kind="SYNTHETIC", observations=base["metrics"])
        else:
            decide(base, new)


def test_unknown_is_not_zero_and_historical_scores_are_not_equivalence():
    base, new = pair()
    with pytest.raises(ValueError):
        observation(0, status="UNKNOWN")
    q = synthetic_quality(base, new)
    q["kind"] = "HISTORICAL_MACHINE_SCORE"
    assert decide(base, new, q)["decision"] == "INCONCLUSIVE"
    new["evidence_kind"] = "HISTORICAL"
    assert decide(base, new)["decision"] == "INCONCLUSIVE"


def test_unverified_gates_and_holdout_payload_cannot_bypass_stability():
    base, new = pair()
    q = synthetic_quality(base, new)
    q["gates"]["Holdout"] = "UNVERIFIED"
    assert decide(base, new, q)["decision"] == "INCONCLUSIVE"
    q["holdout_items"] = {"q1": "not eligible as mutation feedback"}
    with pytest.raises(ValueError, match="holdout"):
        decide(base, new, q)


def test_conservative_compaction_exact_diff_and_all_gates_still_required():
    parts, protected = sections()
    ops = [{"kind": "DELETE", "ids": ["style-c"]},
           {"kind": "MERGE", "ids": ["style-a", "style-b"]},
           {"kind": "REWRITE", "ids": ["spacing"], "text": "清楚 表達。"}]
    old = "\n\n".join(p["text"] for p in parts)
    patch = compaction_candidate(parts, ops, protected=protected)
    assert patch["baseline_sha256"] == digest(old)
    assert patch["candidate_sha256"] == digest(patch["candidate_text"])
    assert patch["protected"] == protected
    assert patch["remaining_sections"] == ["protected-core", "style-a", "spacing"]
    assert "-以清楚標題整理答案。" in patch["diff"]
    assert patch["operations"] == ops and patch["required_gates"] == list(GATES)
    assert patch["semantic_review_required"] is True
    assert patch["promotion_allowed"] is False
    assert run_gatekeeper(old)[0] and run_gatekeeper(patch["candidate_text"])[0]


@pytest.mark.parametrize("operation", [
    {"kind": "ADD", "ids": ["spacing"], "text": "new requirement"},
    {"kind": "DELETE", "ids": ["protected-core"]},
    {"kind": "DELETE", "ids": ["spacing"]},
    {"kind": "MERGE", "ids": ["style-a", "spacing"]},
    {"kind": "REWRITE", "ids": ["spacing"], "text": "清楚表達。新增義務。"},
    {"kind": "REWRITE", "ids": ["protected-core"], "text": "unsafe"},
    {"kind": "MERGE", "ids": ["style-a", "style-a"]},
])
def test_unsupported_semantic_changes_and_protected_removal_fail_closed(operation):
    parts, protected = sections()
    with pytest.raises(ValueError):
        compaction_candidate(parts, [operation], protected=protected)


def test_protected_manifest_cannot_change_silently():
    parts, protected = sections()
    protected["protected-core"] = digest("different source")
    with pytest.raises(ValueError, match="manifest"):
        compaction_candidate(parts, [{"kind": "DELETE", "ids": ["style-c"]}], protected=protected)


def test_frozen_history_replay_honestly_records_opposing_size_measures():
    report = historical_replay(ROOT)
    assert [r["characters"] for r in report["sequence"]] == [442, 438]
    assert [r["utf8_bytes"] for r in report["sequence"]] == [1270, 1282]
    assert report["characters_delta"] == -4 and report["utf8_bytes_delta"] == 12
    assert report["bound_promotion_log_rows"] == 1
    assert report["unbound_promoted_rows_excluded"] == 6
    assert report["holdout_evidence"] == "NOT_READ"
    assert report["decision"] == "NO_VERIFIED_COMPACTION_OPPORTUNITY"
    assert report["historical_dev_machine_summary_only"]["word_count_pass_rate"] == 0
    assert all(metric["value"] is None for receipt in report["sequence"] for metric in receipt["metrics"].values())


def test_historical_drift_is_not_silently_replayed(tmp_path):
    manifest = json.loads((ROOT / "research/fixtures/complexity-history-v1.json").read_text(encoding="utf-8"))
    manifest["artifacts"][0]["content"] += "changed"
    path = tmp_path / "research/fixtures/complexity-history-v1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="drift"):
        historical_replay(tmp_path)


def test_boolean_historical_schema_is_not_version_one(tmp_path):
    manifest = json.loads((ROOT / "research/fixtures/complexity-history-v1.json").read_text(encoding="utf-8"))
    manifest["schema_version"] = True
    fixture = tmp_path / "research/fixtures/complexity-history-v1.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        historical_replay(tmp_path)


def test_future_canonical_or_history_changes_do_not_change_frozen_replay(tmp_path):
    fixture = tmp_path / "research/fixtures/complexity-history-v1.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes((ROOT / fixture.relative_to(tmp_path)).read_bytes())
    for filename in ("prompts/baseline.md", "prompts/current.md", "evolution_log.jsonl"):
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("legitimate future evolution content", encoding="utf-8")
    assert experiment(tmp_path) == experiment(ROOT)


def test_replay_deterministic_and_never_reads_holdout_or_writes(monkeypatch):
    real_read = Path.read_text
    def guarded_read(path, *args, **kwargs):
        assert "holdout" not in str(path)
        return real_read(path, *args, **kwargs)
    def no_write(*args, **kwargs):
        raise AssertionError("research tried writing")
    monkeypatch.setattr(Path, "read_text", guarded_read)
    monkeypatch.setattr(Path, "write_text", no_write)
    monkeypatch.setattr(Path, "write_bytes", no_write)
    assert experiment(ROOT) == experiment(ROOT)


def test_cli_outputs_only_inactive_research_receipt():
    result = subprocess.run([sys.executable, "-m", "research.complexity_pareto"], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["known_equivalent"]["decision"] == "COMPACT_CANDIDATE"
    assert payload["quality_cost_tradeoff"]["decision"] == "TRADEOFF_REVIEW"
    assert payload["safety_regression"]["decision"] == "REJECT"
    assert payload["active"] is False and payload["promotion_allowed"] is False
    assert payload["tokenizer_drift"]["decision"] == "BLOCKED_EVIDENCE_DRIFT"
    assert payload["unknown_operational_cost"]["decision"] == "INCONCLUSIVE"
    assert payload == json.loads((ROOT / "docs/research/complexity-pareto-report-v1.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("inherited_encoding", ["cp1252", "gbk", "ascii", "utf-8"])
def test_cli_emits_lossless_utf8_json_with_legacy_stdout_encoding(inherited_encoding):
    child_env = {**os.environ, "PYTHONIOENCODING": inherited_encoding}
    result = subprocess.run(
        [sys.executable, "-m", "research.complexity_pareto"], cwd=ROOT,
        env=child_env, capture_output=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    text = result.stdout.decode("utf-8")
    expected = (ROOT / "docs/research/complexity-pareto-report-v1.json").read_text(encoding="utf-8")
    assert result.stdout == expected.encode("utf-8")
    payload = json.loads(text)
    assert "杜絕捏造" in payload["synthetic_duplicate_compaction_patch"]["candidate_text"]
    assert "\ufffd" not in text
    assert payload["active"] is False and payload["promotion_allowed"] is False
