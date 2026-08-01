# -*- coding: utf-8 -*-
"""固定 seed 的受控候選集整合測試。"""
import json
import random
from pathlib import Path
from types import SimpleNamespace

import run_opt
import scripts.gatekeeper  # noqa: F401


FIXED_SEED = 20260801
QUALITY = {
    "HIGH": {"smoke": 96.0, "dev": 94.0, "holdout": 93.0},
    "MEDIUM": {"smoke": 88.0, "dev": 86.0, "holdout": 85.0},
    "LOW": {"smoke": 40.0, "dev": 40.0, "holdout": 40.0},
}


def _prompt(marker):
    return (
        f"{marker} 品質候選：你是一位申論題專家，直接輸出正文，"
        "不得編造，建立比較基準，法律題採三段論法。"
        "不得摻雜說明或提問。"
        + "補充內容以確保測試候選具備完整可評估提示詞。" * 4
    )


def test_fixed_seed_closed_loop_selects_highest_candidate_with_evidence(
    tmp_path, monkeypatch
):
    """一輪真實 run_opt_pass 應完成比較、淘汰、選優並保存逐候選證據。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "baseline.md").write_text("baseline", encoding="utf-8")

    rng = random.Random(FIXED_SEED)
    markers = rng.sample(["HIGH", "MEDIUM", "LOW"], 3)
    generated = []
    evaluations = []
    rounds = []
    run_number = 0

    def fake_minimax(*_args, **_kwargs):
        marker = markers[len(generated)]
        generated.append(marker)
        return _prompt(marker)

    def fake_evaluate(prompt_path, question_file, parallel, capture=False):
        nonlocal run_number
        run_number += 1
        text = Path(prompt_path).read_text(encoding="utf-8")
        marker = next(name for name in QUALITY if name in text)
        stage = Path(question_file).stem
        score = QUALITY[marker][stage]
        evaluations.append({"marker": marker, "stage": stage, "score": score})

        run_dir = tmp_path / "runs" / f"run-{run_number:02d}-{stage}-{marker.lower()}"
        run_dir.mkdir(parents=True)
        summary = {
            "average_score": score,
            "score": score,
            "question_file": question_file,
            "prompt_hash": run_opt.sha256_text(text),
            "word_count_pass_rate": 100.0,
            "risk_perfect_rate": 100.0,
            "error_count": 0,
        }
        (run_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False), encoding="utf-8"
        )
        (run_dir / "summary.md").write_text(
            f"總平均分數**: {score:.2f}\n", encoding="utf-8"
        )
        return SimpleNamespace(returncode=0), str(run_dir), summary

    original_get = run_opt.get

    def controlled_get(section, key=None, default=None):
        if section == "multi_candidate" and key is None:
            return {"enabled": True, "count": 3, "temperatures": [0.5, 0.7, 0.9]}
        return original_get(section, key, default)

    monkeypatch.setattr(run_opt, "call_minimax", fake_minimax)
    monkeypatch.setattr(run_opt, "run_evaluate", fake_evaluate)
    monkeypatch.setattr(run_opt, "get", controlled_get)
    monkeypatch.setattr(run_opt, "record_round", lambda **payload: rounds.append(payload))

    assert run_opt.run_opt_pass(smoke_parallel=1, dev_parallel=1, holdout_parallel=1) is True

    assert len(rounds) == 1
    assert rounds[0]["accept"] is True
    assert len(generated) == 3
    assert len(evaluations) == 5
    smoke = {row["marker"]: row["score"] for row in evaluations if row["stage"] == "smoke"}
    assert smoke == {"HIGH": 96.0, "MEDIUM": 88.0, "LOW": 40.0}
    assert smoke["HIGH"] > smoke["MEDIUM"] > smoke["LOW"]

    scorecards = []
    for card_path in sorted((tmp_path / "prompts" / "candidates").glob("*.scorecard.json")):
        card = json.loads(card_path.read_text(encoding="utf-8"))
        card["marker"] = next(
            name
            for name in QUALITY
            if name in (tmp_path / card["candidate_path"]).read_text(encoding="utf-8")
        )
        scorecards.append(card)

    assert len(scorecards) == 3
    assert all(card["candidate_path"] and card["candidate_length"] > 0 for card in scorecards)
    assert len({card["candidate_path"] for card in scorecards}) == 3
    assert all("smoke" in card and "score" in card["smoke"] for card in scorecards)

    by_marker = {card["marker"]: card for card in scorecards}
    assert by_marker["LOW"]["status"] == "rejected_smoke"
    assert by_marker["LOW"]["smoke"]["passed"] is False
    assert by_marker["MEDIUM"]["status"] == "smoke_passed"
    assert by_marker["MEDIUM"].get("selected") is not True
    assert by_marker["HIGH"]["status"] == "promoted_baseline"
    assert by_marker["HIGH"]["selected"] is True
    assert "HIGH" in (tmp_path / "prompts" / "current.md").read_text(encoding="utf-8")
    assert "HIGH" in (tmp_path / "prompts" / "baseline.md").read_text(encoding="utf-8")
