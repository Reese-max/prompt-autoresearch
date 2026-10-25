"""Issue #5: finite, inactive text-complexity research. No provider or champion I/O.

Only chosen synthetic truth can produce a candidate recommendation. Historical
machine scores are descriptive metadata, never quality-equivalence labels.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import math
import re
from pathlib import Path


VERSION = 1
MAX_TEXT_BYTES = 1024 * 1024
COHORT_FIELDS = (
    "dataset_split", "dataset_sha256", "provider", "model_version", "tokenizer",
    "judge_sha256", "evaluator_sha256", "scorer_sha256", "price_basis",
)
METRICS = (
    "input_tokens", "avg_eval_input_tokens", "avg_eval_output_tokens",
    "avg_eval_tool_call_tokens", "cost_usd_per_successful_task",
    "latency_p50_ms", "latency_p95_ms",
)
GATES = ("Gatekeeper", "Smoke", "Dev", "Holdout")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(text: str) -> None:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("prompt must be bounded UTF-8 text")


def _number(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value >= 0)


def _hash(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def observation(value=None, *, status="UNKNOWN", provenance="not observed") -> dict:
    if status not in ("MEASURED", "ESTIMATED", "UNKNOWN"):
        raise ValueError("unknown observation status")
    if (status == "UNKNOWN" and value is not None) or (status != "UNKNOWN" and not _number(value)):
        raise ValueError("observation status/value mismatch")
    if not isinstance(provenance, str) or not provenance.strip():
        raise ValueError("observation needs provenance")
    return {"status": status, "value": value, "provenance": provenance}


def _validate_cohort(cohort: dict) -> None:
    if not isinstance(cohort, dict) or set(cohort) != set(COHORT_FIELDS) or any(
        not isinstance(value, str) or not value.strip() or value != value.strip()
        for value in cohort.values()
    ) or cohort["dataset_split"] != "dev":
        raise ValueError("complete DEV-only cohort required")
    for key in ("dataset_sha256", "judge_sha256", "evaluator_sha256", "scorer_sha256"):
        if cohort[key] != "UNKNOWN" and not _hash(cohort[key]):
            raise ValueError("invalid cohort hash")


def _validate_metrics(metrics: dict, cohort: dict) -> None:
    if not isinstance(metrics, dict) or set(metrics) != set(METRICS):
        raise ValueError("incomplete metrics")
    for entry in metrics.values():
        if not isinstance(entry, dict) or set(entry) != {"status", "value", "provenance"}:
            raise ValueError("invalid observation shape")
        observation(**entry)
    tokens = metrics["input_tokens"]
    if tokens["status"] != "UNKNOWN":
        if type(tokens["value"]) is not int:
            raise ValueError("input token count must be an integer")
        if cohort["tokenizer"] == "UNKNOWN":
            raise ValueError("token counts require a tokenizer cohort")
    p50, p95 = metrics["latency_p50_ms"], metrics["latency_p95_ms"]
    if p50["status"] != "UNKNOWN" and p50["status"] == p95["status"] and p50["value"] > p95["value"]:
        raise ValueError("latency quantiles are reversed")


def complexity_receipt(text: str, *, version: str, cohort: dict,
                       evidence_kind="HISTORICAL", observations=None,
                       cache_fingerprint=None) -> dict:
    _text(text)
    if not isinstance(version, str) or not version or len(version) > 256:
        raise ValueError("missing prompt version")
    if evidence_kind not in ("SYNTHETIC", "HISTORICAL"):
        raise ValueError("only offline evidence is supported")
    _validate_cohort(cohort)
    supplied = observations or {}
    if set(supplied) - set(METRICS):
        raise ValueError("unknown metric")
    metrics = {name: observation(**supplied[name]) if name in supplied else observation()
               for name in METRICS}
    _validate_metrics(metrics, cohort)
    if cache_fingerprint is not None and not _hash(cache_fingerprint):
        raise ValueError("invalid cache eligibility fingerprint")
    return {
        "schema_version": VERSION, "prompt_version": version,
        "prompt_sha256": digest(text), "evidence_kind": evidence_kind,
        "cohort": dict(cohort), "characters": len(text),
        "utf8_bytes": len(text.encode("utf-8")),
        "nonempty_lines": sum(bool(line.strip()) for line in text.splitlines()),
        "heading_count": sum(bool(re.match(r"^#{1,6} +", line)) for line in text.splitlines()),
        "semantic_rule_count": observation(),
        "cache_eligibility_fingerprint": cache_fingerprint,
        "metrics": metrics,
    }


def _validate_receipt(receipt: dict) -> None:
    if type(receipt.get("schema_version")) is not int or receipt["schema_version"] != VERSION or not _hash(receipt.get("prompt_sha256")):
        raise ValueError("invalid receipt identity")
    if receipt.get("evidence_kind") not in ("SYNTHETIC", "HISTORICAL"):
        raise ValueError("unsupported evidence kind")
    cohort = receipt.get("cohort", {})
    _validate_cohort(cohort)
    for key in ("characters", "utf8_bytes"):
        if type(receipt.get(key)) is not int or not 0 <= receipt[key] <= MAX_TEXT_BYTES:
            raise ValueError("invalid measured text count")
    _validate_metrics(receipt.get("metrics"), cohort)
    fingerprint = receipt.get("cache_eligibility_fingerprint")
    if fingerprint is not None and not _hash(fingerprint):
        raise ValueError("invalid cache eligibility fingerprint")


def pareto_decision(baseline: dict, candidate: dict, quality: dict, *,
                    absolute_chars: int, max_token_growth: float) -> dict:
    """Research classification, with explicit illustrative caller-owned budgets.

    This accepts no production stability certificate. The future #3 adapter must
    bind repeated DEV evidence to both prompt hashes and the same cohort. Holdout
    item outcomes are deliberately absent from this interface.
    """
    _validate_receipt(baseline)
    _validate_receipt(candidate)
    if baseline["prompt_sha256"] == candidate["prompt_sha256"] and any(
        baseline[key] != candidate[key] for key in ("characters", "utf8_bytes")
    ):
        raise ValueError("identical prompt hash has inconsistent literal size")
    if type(absolute_chars) is not int or not 1 <= absolute_chars <= MAX_TEXT_BYTES:
        raise ValueError("invalid illustrative absolute budget")
    if not _number(max_token_growth) or max_token_growth > 1:
        raise ValueError("invalid illustrative relative budget")
    if set(quality) != {"kind", "baseline_sha256", "candidate_sha256", "cohort",
                        "relation", "safety", "types", "gates"}:
        raise ValueError("quality interface excludes item-level/holdout evidence")
    if quality["relation"] not in ("EQUIVALENT", "BETTER", "WORSE", "UNKNOWN"):
        raise ValueError("unknown quality relation")
    if quality["safety"] not in ("PASS", "FAIL", "UNKNOWN") or quality["types"] not in ("PASS", "FAIL", "UNKNOWN"):
        raise ValueError("invalid safety/type status")
    if set(quality["gates"]) != set(GATES) or any(
        value not in ("PASS", "FAIL", "UNVERIFIED") for value in quality["gates"].values()
    ):
        raise ValueError("all existing gates need explicit status")
    result = {"schema_version": VERSION, "active": False, "promotion_allowed": False,
              "policy": {"absolute_chars": absolute_chars, "max_token_growth": max_token_growth},
              "baseline_sha256": baseline["prompt_sha256"], "candidate_sha256": candidate["prompt_sha256"]}

    def decide(decision, reason):
        return {**result, "decision": decision, "reason": reason}

    if quality["safety"] == "FAIL" or quality["types"] == "FAIL" or "FAIL" in quality["gates"].values() or quality["relation"] == "WORSE":
        return decide("REJECT", "quality, safety, type or existing hard gate regressed")
    if (baseline["cohort"] != candidate["cohort"] or quality["cohort"] != baseline["cohort"]
            or quality["baseline_sha256"] != baseline["prompt_sha256"]
            or quality["candidate_sha256"] != candidate["prompt_sha256"]
            or baseline["cache_eligibility_fingerprint"] != candidate["cache_eligibility_fingerprint"]):
        return decide("BLOCKED_EVIDENCE_DRIFT", "prompt/cohort/cache identity differs")
    if candidate["characters"] > absolute_chars:
        return decide("REJECT", "illustrative absolute text budget exceeded")
    before, after = baseline["metrics"]["input_tokens"], candidate["metrics"]["input_tokens"]
    if before["status"] != "UNKNOWN" and before["status"] == after["status"]:
        if after["value"] > before["value"] * (1 + max_token_growth):
            return decide("REJECT", "relative same-tokenizer growth budget exceeded")
    else:
        return decide("INCONCLUSIVE", "input-token growth is unverified")
    if (quality["kind"] != "SYNTHETIC_TRUTH" or baseline["evidence_kind"] != "SYNTHETIC"
            or candidate["evidence_kind"] != "SYNTHETIC"
            or "UNKNOWN" in baseline["cohort"].values()
            or quality["relation"] == "UNKNOWN" or quality["safety"] != "PASS"
            or quality["types"] != "PASS" or set(quality["gates"].values()) != {"PASS"}):
        return decide("INCONCLUSIVE", "no complete chosen synthetic truth; real stability adapter is pending")
    deltas = [candidate["characters"] - baseline["characters"], candidate["utf8_bytes"] - baseline["utf8_bytes"]]
    for name in METRICS:
        old, new = baseline["metrics"][name], candidate["metrics"][name]
        if old["status"] == "UNKNOWN" or old["status"] != new["status"]:
            return decide("INCONCLUSIVE", f"incomparable or unknown {name}")
        deltas.append(new["value"] - old["value"])
    if any(delta > 0 for delta in deltas):
        if quality["relation"] == "BETTER" or any(delta < 0 for delta in deltas):
            return decide("TRADEOFF_REVIEW", "quality or some dimensions improve while another worsens")
        return decide("KEEP", "candidate is dominated")
    if any(delta < 0 for delta in deltas):
        return decide("COMPACT_CANDIDATE", "chosen synthetic quality/safety equivalent or better, all comparable dimensions no worse")
    return decide("KEEP", "no complexity advantage")


def _space_only(text: str) -> str:
    # Deliberately excludes semantic paraphrasing, newline removal and token joins.
    return "\n".join(re.sub(r" {2,}", " ", line.rstrip(" \t")) for line in text.split("\n"))


def compaction_candidate(sections: list[dict], operations: list[dict], *, protected: dict) -> dict:
    """Conservative DELETE/MERGE/REWRITE lane: exact duplicates/spacing only.

    This cannot establish semantic equivalence for arbitrary paraphrases, so they
    are refused. Even supported patches are candidates requiring the full gates.
    """
    if not 1 <= len(sections) <= 100 or not 1 <= len(operations) <= 100 or not protected:
        raise ValueError("bounded sections, operations and protected manifest required")
    content = {}
    for section in sections:
        if set(section) != {"id", "text"} or not isinstance(section["id"], str) or not section["id"] or section["id"] in content:
            raise ValueError("unique section identity required")
        _text(section["text"])
        content[section["id"]] = section["text"]
    if any(key not in content or not _hash(value) or digest(content[key]) != value for key, value in protected.items()):
        raise ValueError("protected manifest mismatch")
    before = "\n\n".join(content.values())
    _text(before)
    for op in operations:
        if not isinstance(op, dict):
            raise ValueError("operation must be an explicit object")
        kind = op.get("kind")
        expected_keys = {"kind", "ids"} if kind in ("DELETE", "MERGE") else {"kind", "ids", "text"}
        if kind not in ("DELETE", "MERGE", "REWRITE") or set(op) != expected_keys:
            raise ValueError("only conservative DELETE/MERGE/REWRITE supported")
        ids = op["ids"]
        if not isinstance(ids, list) or not ids or any(not isinstance(key, str) or key not in content for key in ids) or len(set(ids)) != len(ids):
            raise ValueError("operation needs unique existing section IDs")
        if any(key in protected for key in ids):
            raise ValueError("protected constraints are immutable")
        if kind == "DELETE":
            if len(ids) != 1 or not any(value == content[ids[0]] for key, value in content.items() if key != ids[0]):
                raise ValueError("DELETE requires a retained exact duplicate")
            del content[ids[0]]
        elif kind == "MERGE":
            if len(ids) < 2 or len({content[key] for key in ids}) != 1:
                raise ValueError("MERGE only accepts exact duplicates")
            for key in ids[1:]:
                del content[key]
        else:
            if len(ids) != 1 or op["text"] != _space_only(content[ids[0]]):
                raise ValueError("REWRITE is whitespace-only; semantic rewrites need separate research")
            content[ids[0]] = op["text"]
    if any(key not in content or digest(content[key]) != value for key, value in protected.items()):
        raise ValueError("protected constraint changed")
    after = "\n\n".join(content.values())
    if len(after.encode("utf-8")) >= len(before.encode("utf-8")):
        raise ValueError("compaction must reduce literal size")
    return {"schema_version": VERSION, "active": False, "promotion_allowed": False,
            "baseline_sha256": digest(before), "candidate_sha256": digest(after),
            "candidate_text": after, "operations": json.loads(json.dumps(operations)),
            "protected": dict(protected), "remaining_sections": list(content),
            "diff": "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="baseline", tofile="candidate")),
            "required_gates": list(GATES), "semantic_review_required": True}


def _history_inputs(root: Path) -> tuple[dict, dict]:
    path = root / "research/fixtures/complexity-history-v1.json"
    if path.is_symlink() or path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("unbounded or symlink historical fixture")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    roles = {"archived_predecessor", "current_baseline", "baseline_metadata", "dev_summary", "evolution_log"}
    if (type(manifest.get("schema_version")) is not int or manifest["schema_version"] != VERSION
            or len(manifest.get("artifacts", [])) != len(roles)
            or {entry["role"] for entry in manifest["artifacts"]} != roles):
        raise ValueError("historical fixture inventory mismatch")
    texts = {}
    for entry in manifest["artifacts"]:
        text = entry["content"]
        _text(text)
        if not _hash(entry["source_sha256_lf_utf8"]) or digest(text) != entry["content_sha256_lf_utf8"]:
            raise ValueError(f"historical artifact drift: {entry['path']}")
        expected = "JSONL_ROWS_WHERE_PROMOTED_IS_TRUE" if entry["role"] == "evolution_log" else "FULL_LF_UTF8"
        if entry["projection"] != expected or (expected == "FULL_LF_UTF8" and entry["source_sha256_lf_utf8"] != digest(text)):
            raise ValueError("historical projection mismatch")
        texts[entry["role"]] = text
    return manifest, texts


def historical_replay(root: Path) -> dict:
    """Read only frozen copies/projections; never mutable champions or Holdout."""
    manifest, texts = _history_inputs(root)
    cohort = {key: "UNKNOWN" for key in COHORT_FIELDS}
    cohort["dataset_split"] = "dev"
    sequence = [complexity_receipt(texts[role], version=role, cohort=cohort)
                for role in ("archived_predecessor", "current_baseline")]
    meta, summary = json.loads(texts["baseline_metadata"]), json.loads(texts["dev_summary"])
    log = [json.loads(line) for line in texts["evolution_log"].splitlines() if line.strip()]
    if any(row.get("promoted") is not True for row in log):
        raise ValueError("historical promoted-row projection mismatch")
    dev_path = meta["dev_run"].replace("\\", "/")
    bound = [row for row in log if row.get("promoted") is True and row.get("dev_run", "").replace("\\", "/") == dev_path]
    if (meta["prompt_hash"] != sequence[1]["prompt_sha256"]
            or summary["prompt_hash"] != meta["prompt_hash"]
            or summary["question_file"] != "questions/dev.jsonl" or len(bound) != 1):
        raise ValueError("historical transition provenance mismatch")
    return {
        "manifest_version": manifest["schema_version"],
        "source_manifest": {**manifest, "artifacts": [{key: value for key, value in entry.items() if key != "content"} for entry in manifest["artifacts"]]},
        "normalization": "UTF-8 decoded text; universal newlines to LF; counts refer to that prompt input",
        "sequence": sequence, "bound_promotion_log_rows": len(bound),
        "unbound_promoted_rows_excluded": sum(row.get("promoted") is True and not row.get("dev_run") for row in log),
        "characters_delta": sequence[1]["characters"] - sequence[0]["characters"],
        "utf8_bytes_delta": sequence[1]["utf8_bytes"] - sequence[0]["utf8_bytes"],
        "documented_10_percent_token_policy": "UNKNOWN: no matching tokenizer observation",
        "existing_gatekeeper_700_character_cap": "both historical texts below cap; not evidence of all quality gates",
        "historical_dev_machine_summary_only": {key: summary[key] for key in ("average_score", "total_questions", "elapsed_seconds", "word_count_pass_rate", "risk_perfect_rate", "cache_hit_count", "error_count")},
        "quality_equivalence": "UNKNOWN: no matched repeated DEV pair/stability evidence",
        "provider_cost_latency_cohort": "UNKNOWN: wall time is not a matched latency distribution or billing",
        "holdout_evidence": "NOT_READ", "decision": "NO_VERIFIED_COMPACTION_OPPORTUNITY",
    }


def synthetic_receipt(text: str, *, version: str, scale=1.0) -> dict:
    cohort = {key: "synthetic-v1" for key in COHORT_FIELDS}
    cohort.update(dataset_split="dev", tokenizer="synthetic-whitespace-v1",
                  price_basis="SYNTHETIC_ASSUMPTION_NOT_PROVIDER_PRICING")
    for key in ("dataset_sha256", "judge_sha256", "evaluator_sha256", "scorer_sha256"):
        cohort[key] = digest("synthetic-" + key)
    metrics = {name: observation(scale, status="ESTIMATED", provenance="chosen synthetic assumption, not provider measurement") for name in METRICS}
    metrics["input_tokens"] = observation(len(text.split()), status="MEASURED", provenance="Python str.split toy tokenizer, not a provider tokenizer")
    return complexity_receipt(text, version=version, cohort=cohort, evidence_kind="SYNTHETIC", observations=metrics)


def synthetic_quality(baseline: dict, candidate: dict, *, relation="EQUIVALENT") -> dict:
    return {"kind": "SYNTHETIC_TRUTH", "baseline_sha256": baseline["prompt_sha256"],
            "candidate_sha256": candidate["prompt_sha256"], "cohort": dict(baseline["cohort"]),
            "relation": relation, "safety": "PASS", "types": "PASS", "gates": {name: "PASS" for name in GATES}}


def experiment(root: Path) -> dict:
    # This is the documented relative-token rule in a toy world, not runtime code.
    counts = [100]
    for _ in range(12):
        counts.append(counts[-1] + max(1, int(counts[-1] * 0.09)))
    ratchet = []
    for old, new in zip(counts, counts[1:]):
        before = synthetic_receipt(" ".join(["rule"] * old), version=f"toy-{old}")
        after = synthetic_receipt(" ".join(["rule"] * new), version=f"toy-{new}")
        ratchet.append({"before_tokens": old, "after_tokens": new,
                        "relative_only_reference_accepts": new <= old * 1.1,
                        "absolute_plus_relative_decision": pareto_decision(before, after, synthetic_quality(before, after, relation="BETTER"), absolute_chars=900, max_token_growth=0.1)})
    base = synthetic_receipt("safe legal rule repeated repeated", version="synthetic-baseline", scale=2)
    compact = synthetic_receipt("safe legal rule repeated", version="synthetic-compact")
    worse_cost = synthetic_receipt("safe legal rule repeated", version="synthetic-costly", scale=3)
    unsafe = synthetic_quality(base, compact)
    unsafe["safety"] = "FAIL"
    drifted = synthetic_receipt("safe legal rule repeated", version="synthetic-drift")
    drifted["cohort"]["tokenizer"] = "synthetic-whitespace-v2"
    unknown = synthetic_receipt("safe legal rule repeated", version="synthetic-unknown")
    unknown["metrics"]["cost_usd_per_successful_task"] = observation()
    protected_text = _history_inputs(root)[1]["current_baseline"]
    patch = compaction_candidate(
        [{"id": "protected-current-core", "text": protected_text},
         {"id": "duplicate-a", "text": "以清楚標題整理答案。"},
         {"id": "duplicate-b", "text": "以清楚標題整理答案。"}],
        [{"kind": "MERGE", "ids": ["duplicate-a", "duplicate-b"]}],
        protected={"protected-current-core": digest(protected_text)},
    )
    def decide(candidate, quality):
        return pareto_decision(base, candidate, quality, absolute_chars=900, max_token_growth=0.1)
    return {"schema_version": VERSION, "decision": "NARROW", "active": False,
            "promotion_allowed": False, "evidence_kind": "OFFLINE_SYNTHETIC_AND_FROZEN_HISTORY",
            "source_sha256_lf_utf8": digest(Path(__file__).read_text(encoding="utf-8")),
            "ratchet": ratchet,
            "known_equivalent": decide(compact, synthetic_quality(base, compact)),
            "quality_cost_tradeoff": decide(worse_cost, synthetic_quality(base, worse_cost, relation="BETTER")),
            "safety_regression": decide(compact, unsafe),
            "tokenizer_drift": decide(drifted, synthetic_quality(base, drifted)),
            "unknown_operational_cost": decide(unknown, synthetic_quality(base, unknown)),
            "synthetic_duplicate_compaction_patch": patch,
            "historical": historical_replay(root),
            "remaining_gates": ["#3 real repeated DEV stability/equivalence adapter", "#4 complete required CI/evidence", "Gatekeeper/Smoke/Dev/bounded final Holdout for each real candidate", "authorized measured provider cost/latency canary"],
            "limits": ["No human quality labels or live/provider conformance", "Toy token counts are not model/provider tokens", "No champion writes, mutation feedback or holdout item reads", "Only exact-duplicate/spacing compaction; arbitrary semantic rewrites unsupported"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    print(json.dumps(experiment(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
