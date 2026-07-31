# -*- coding: utf-8 -*-
"""手動驗證噪音報告、連續計分與 baseline 完整性。

可直接執行：
    python -m pytest -q tests/manual-goal-scoring-deadzone.py
"""

import hashlib
import json
import statistics
from pathlib import Path

import pytest

import scripts.evaluate as evaluate
from scripts.measure_noise import compute_stats


ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "docs" / "noise-report.json"
BASELINE_PATH = ROOT / "prompts" / "baseline.md"
BASELINE_SHA256 = "b3ed82170e676db65ccf36474088740708fd3da72041f18c57285910e2feb605"


def _load_report():
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def test_noise_report_has_raw_10_by_5_data_and_consistent_statistics():
    report = _load_report()
    meta = report["meta"]
    per_question = report["per_question"]

    assert meta["n_questions"] >= 10
    assert meta["repetitions"] >= 5
    assert len(per_question) >= 10
    assert meta["total_attempts"] == meta["n_questions"] * meta["repetitions"]
    assert meta["errors"] == 0

    pooled_scores = []
    for question in per_question.values():
        attempts = question["attempts"]
        raw_scores = [attempt["total_score"] for attempt in attempts]
        assert len(attempts) >= 5
        assert question["total_scores"] == raw_scores
        assert all(
            attempt["total_score"]
            == attempt["general_score"]
            + attempt["type_specific_score"]
            + attempt["risk_score"]
            for attempt in attempts
        )
        assert question["total_stats"] == compute_stats(raw_scores)
        assert question["general_stats"] == compute_stats(
            [attempt["general_score"] for attempt in attempts]
        )
        assert question["type_specific_stats"] == compute_stats(
            [attempt["type_specific_score"] for attempt in attempts]
        )
        assert question["risk_stats"] == compute_stats(
            [attempt["risk_score"] for attempt in attempts]
        )
        pooled_scores.extend(raw_scores)

    assert len(pooled_scores) == meta["total_attempts"]
    overall = report["overall"]
    assert overall["pooled_stats"] == compute_stats(pooled_scores)
    assert report["step_dead_zone_analysis"]["total_dead_zone_width"] > 0
    assert report["step_dead_zone_analysis"]["dead_zones"]


@pytest.mark.parametrize(
    "name, scorer, expected, direction",
    [
        ("topic_relevance", evaluate.score_topic_relevance, (4, 8, 11), "up"),
        ("structure", evaluate.score_structure, (2, 4, 6), "up"),
        (
            "scoring_points_visible",
            evaluate.score_scoring_points_visible,
            (3, 6, 9),
            "up",
        ),
        (
            "content_concreteness",
            evaluate.score_content_concreteness,
            (3, 6, 9),
            "up",
        ),
        ("exam_tone", evaluate.score_exam_tone, (2, 4, 6), "up"),
        ("conclusion", evaluate.score_conclusion, (2, 3, 4), "up"),
        ("type_specific", evaluate.score_type_specific, (4, 8, 12), "up"),
        ("risk", evaluate.score_risk, (7.5, 5.0, 2.5), "down"),
    ],
)
def test_count_1_2_3_have_continuous_observable_scores(
    name, scorer, expected, direction
):
    scores = [scorer(count) for count in (1, 2, 3)]

    assert scores == pytest.approx(expected), name
    if direction == "up":
        assert scores[0] < scores[1] < scores[2]
    else:
        assert scores[0] > scores[1] > scores[2]


def test_rescoring_has_positive_variance_increase_evidence():
    report = _load_report()
    raw_scores = [
        score
        for question in report["per_question"].values()
        for score in question["total_scores"]
    ]
    reported_stddev = report["overall"]["pooled_stats"]["stddev"]
    assert statistics.variance(raw_scores) > 0
    assert reported_stddev > 0
    assert reported_stddev**2 == pytest.approx(
        statistics.variance(raw_scores), rel=1e-4
    )

    legacy_step_scores = [0.0, 0.0, 0.0]
    rescored = [evaluate.score_topic_relevance(count) for count in (1, 2, 3)]
    assert statistics.variance(rescored) > statistics.variance(legacy_step_scores)


def test_baseline_sha256_is_unchanged():
    actual = hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest()
    assert actual == BASELINE_SHA256
