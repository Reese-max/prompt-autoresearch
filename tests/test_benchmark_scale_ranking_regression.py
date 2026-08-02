# -*- coding: utf-8 -*-
"""不同 benchmark 的 raw score 不得被放在同一條量尺上排名。"""
import auto_evolve


def _candidate(benchmark, candidate_path, raw_score, score_scale):
    dataset = f"benchmarks/{benchmark}.jsonl"
    evaluation = {
        "stage": "dev",
        "score": raw_score,
        "comparable": True,
        "basis": {
            "stage": "dev",
            "dataset": dataset,
            "metric": "raw_score",
            "evaluator_version": "judge-v1",
            "measurement_settings": {"score_scale": score_scale},
        },
    }
    return {
        "candidate_path": candidate_path,
        "status": "evaluated",
        "stage_evaluations": [evaluation],
    }


def test_raw_scores_select_each_benchmark_highest_version_without_cross_scale_mix():
    candidates = [
        _candidate("fractional", "fractional-v1", 0.81, "0-1"),
        _candidate("fractional", "fractional-v2", 0.94, "0-1"),
        _candidate("percentage", "percentage-v1", 72, "0-100"),
        _candidate("percentage", "percentage-v2", 88, "0-100"),
    ]

    # 修復前的全域 raw-score max 會把不同 benchmark 當成同一量尺，錯選 percentage-v2。
    legacy_winner = max(
        candidates,
        key=lambda candidate: candidate["stage_evaluations"][0]["score"],
    )
    assert legacy_winner["candidate_path"] == "percentage-v2"
    assert legacy_winner["candidate_path"] != "fractional-v2"

    winner, report = auto_evolve._rank_candidate_evaluations(candidates)

    assert winner is None  # benchmark 不可互相比較，不應產生單一跨組 winner
    groups = {
        group["basis"]["dataset"]: group
        for group in report[0]["benchmark_groups"]
    }
    assert groups["benchmarks/fractional.jsonl"]["winner"]["candidate_path"] == "fractional-v2"
    assert groups["benchmarks/percentage.jsonl"]["winner"]["candidate_path"] == "percentage-v2"
