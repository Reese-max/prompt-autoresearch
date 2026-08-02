# -*- coding: utf-8 -*-
"""受控閉環排名必須只比較同一評測基準。"""
import auto_evolve


def _evaluation(stage, score, dataset="questions/dev.jsonl", version="evaluate-v1", settings=None):
    settings = settings or {"max_workers": 24, "early_stop_threshold": None}
    basis = {
        "stage": stage,
        "dataset": dataset,
        "metric": "average_score",
        "evaluator_version": version,
        "measurement_settings": settings,
    }
    key = tuple(
        [stage, dataset, "average_score", version, auto_evolve._canonical_comparison_value(settings)]
    )
    return {"stage": stage, "score": score, "comparable": True, "basis": basis, "comparison_key": key}


def _candidate(path, evaluations):
    return {"candidate_path": path, "status": "evaluated", "stage_evaluations": evaluations}


def test_ranking_does_not_mix_smoke_and_dev_scores():
    smoke = _candidate("smoke-99", [_evaluation("smoke", 99.0, "questions/smoke.jsonl")])
    dev = _candidate("dev-90", [_evaluation("dev", 90.0)])

    winner, report = auto_evolve._rank_candidate_evaluations([smoke, dev])

    assert winner["candidate_path"] == "dev-90"
    assert {row["candidate_path"]: row["outcome"] for row in report} == {
        "smoke-99": "淘汰",
        "dev-90": "勝出",
    }
    assert "排名基準" in next(row["reason"] for row in report if row["candidate_path"] == "smoke-99")


def test_ranking_marks_group_winner_unproven_when_candidate_lacks_selected_basis():
    dev = _candidate("dev-90", [_evaluation("dev", 90.0)])
    smoke = _candidate("smoke-99", [_evaluation("smoke", 99.0, "questions/smoke.jsonl")])

    winner, report = auto_evolve._rank_candidate_evaluations([dev, smoke])

    assert winner["best_status"] == "unproven"
    assert winner["best_scope"] == "comparison_group"
    assert winner["best_label"] == "該比較群組內最佳"
    assert winner["missing_candidates"] == ["smoke-99"]
    assert winner["pending_evaluation_fields"]["smoke-99"] == [
        "stage", "dataset", "metric", "evaluator_version", "measurement_settings"
    ]
    assert "該比較群組內最佳" in next(
        row["reason"] for row in report if row["candidate_path"] == "dev-90"
    )


def test_ranking_rejects_mismatched_evaluator_basis_but_keeps_same_group():
    good_a = _candidate("dev-90", [_evaluation("dev", 90.0)])
    good_b = _candidate("dev-80", [_evaluation("dev", 80.0)])
    mismatched = _candidate("dev-v2-100", [_evaluation("dev", 100.0, version="evaluate-v2")])

    winner, report = auto_evolve._rank_candidate_evaluations([good_a, good_b, mismatched])

    assert winner["candidate_path"] == "dev-90"
    by_path = {row["candidate_path"]: row for row in report}
    assert by_path["dev-80"]["outcome"] == "落敗"
    assert by_path["dev-v2-100"]["outcome"] == "淘汰"
    assert by_path["dev-v2-100"]["elimination_basis"] == ["comparison_basis_mismatch"]


def test_controlled_loop_persists_candidate_reasons(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    smoke = _candidate("smoke-99", [_evaluation("smoke", 99.0, "questions/smoke.jsonl")])
    dev = _candidate("dev-90", [_evaluation("dev", 90.0)])
    snapshots = iter(([smoke, dev], [smoke, dev]))
    reports = []

    monkeypatch.setattr(auto_evolve, "scan_candidate_evaluations", lambda: next(snapshots))
    monkeypatch.setattr(auto_evolve, "append_jsonl", lambda _path, payload: reports.append(payload))
    import run_opt
    monkeypatch.setattr(run_opt, "get", lambda section, key=None, default=None: {
        "enabled": True,
        "count": 2,
    } if section == "multi_candidate" and key is None else default)
    monkeypatch.setattr(run_opt, "run_opt_pass", lambda **_kwargs: True)

    success, winner = auto_evolve.run_controlled_closed_loop({})

    assert success is True
    assert winner["candidate_path"] == "dev-90"
    report = reports[0]
    assert report["event"] == "controlled_closed_loop_ranking"
    by_path = {row["candidate_path"]: row for row in report["candidate_reports"]}
    assert by_path["dev-90"]["outcome"] == "勝出"
    assert by_path["smoke-99"]["elimination_basis"] == ["comparison_basis_mismatch"]
