# -*- coding: utf-8 -*-
"""最佳版本報告的端到端驗收測試。"""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_opt
import scripts.best_version_report as bvr
import scripts.gatekeeper  # noqa: F401


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


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _report_json(report):
    match = re.search(r"```json\n(.*?)\n```", report, re.DOTALL)
    assert match, "單一報告必須包含可解析的結構化 JSON"
    return json.loads(match.group(1))


@pytest.fixture
def report_workspace(tmp_path, monkeypatch):
    """實際執行多候選閉環，留下可供報告重新驗證的完整證據。"""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "baseline.md").write_text("baseline", encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        "thresholds:\n"
        "  dev_min_improvement: 2.0\n"
        "  type_max_regression: 3.0\n"
        "  word_rate_min: 85.0\n"
        "parallel:\n"
        "  smoke: 1\n"
        "  dev: 1\n"
        "  holdout: 1\n"
        "multi_candidate:\n"
        "  enabled: true\n"
        "  count: 3\n",
        encoding="utf-8",
    )

    generated = []
    evaluations = []
    round_records = []
    run_number = 0

    def fake_minimax(*_args, **_kwargs):
        marker = list(QUALITY)[len(generated)]
        generated.append(marker)
        return _prompt(marker)

    def fake_evaluate(prompt_path, question_file, parallel, capture=False):
        nonlocal run_number
        run_number += 1
        text = Path(prompt_path).read_text(encoding="utf-8")
        marker = next(name for name in QUALITY if name in text)
        stage = Path(question_file).stem
        score = QUALITY[marker][stage]
        evaluations.append((marker, stage, score, parallel, capture))

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
            f"總平均分數: {score:.2f}\n", encoding="utf-8"
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
    monkeypatch.setattr(run_opt, "record_round", lambda **payload: round_records.append(payload))
    monkeypatch.setattr(run_opt, "SMOKE_MIN_SCORE", 75.0)
    monkeypatch.setattr(run_opt, "SMOKE_ALLOWED_DROP", 2.0)
    monkeypatch.setattr(run_opt, "DEV_WORD_RATE_MIN", 85.0)
    monkeypatch.setattr(run_opt, "RISK_PERFECT_RATE_MIN", 100.0)

    assert run_opt.run_opt_pass(smoke_parallel=1, dev_parallel=1, holdout_parallel=1)
    assert len(generated) == 3
    assert len({stage for _, stage, *_ in evaluations}) == 3
    assert len(round_records) == 1
    assert (tmp_path / "prompts" / "baseline.meta.json").exists()

    round_record = round_records[0]
    _write_jsonl(
        tmp_path / "evolution_log.jsonl",
        [
            {
                "event": "start",
                "timestamp": "2026-08-02 00:00:00",
                "args": {
                    "max_rounds": 1,
                    "smoke_parallel": 1,
                    "dev_parallel": 1,
                    "holdout_parallel": 1,
                },
                "baseline_dev_score": 0.0,
            },
            {
                "event": "round_complete",
                "round": 1,
                "promoted": round_record["accept"],
                "winner_id": round_record["winner_id"],
                "score_diff": round_record["score_diff"],
                "candidate_scores": round_record["candidate_scores"],
            },
            {
                "event": "stop",
                "timestamp": "2026-08-02 00:01:00",
                "reason": "done",
                "best_score": round_record["holdout_score"],
                "elapsed_seconds": 60,
            },
        ],
    )

    monkeypatch.setattr(bvr, "ROOT", str(tmp_path))
    monkeypatch.setattr(bvr, "BASELINE_META_PATH", str(tmp_path / "prompts" / "baseline.meta.json"))
    monkeypatch.setattr(bvr, "CHAMPIONS_DIR", str(tmp_path / "prompts" / "champions"))
    monkeypatch.setattr(bvr, "CANDIDATES_DIR", str(tmp_path / "prompts" / "candidates"))
    monkeypatch.setattr(bvr, "EVOLUTION_LOG_PATH", str(tmp_path / "evolution_log.jsonl"))
    monkeypatch.setattr(bvr, "CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(bvr, "RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(bvr, "send_report_to_telegram", lambda *_args, **_kwargs: {"status": "sent"})
    return tmp_path


def _generate_report(workspace, monkeypatch):
    report_path = workspace / "reports" / "best-version.md"
    monkeypatch.setattr(
        bvr.sys,
        "argv",
        [
            "best_version_report.py",
            "--out",
            "reports/best-version.md",
            "--validate-schema",
        ],
    )
    assert bvr.main() == 0
    return report_path, report_path.read_text(encoding="utf-8")


def test_report_e2e_selects_best_candidate_from_single_report(report_workspace, monkeypatch):
    """三個候選實際執行後，單一報告包含選優、採用內容與重跑命令。"""
    report_path, report = _generate_report(report_workspace, monkeypatch)
    data = _report_json(report)

    assert report_path.exists()
    assert data["decision"] == {
        "status": "valid",
        "code": "VALID",
        "reason": "證據完整且通過重新驗證",
        "best_candidate_id": data["winner"]["candidate_id"],
    }
    assert data["candidates_summary"]["total"] >= 2
    assert len(data["candidate_comparison"]) >= 2

    accepted = [row for row in data["candidate_comparison"] if row["decision"] == "ACCEPT"]
    assert len(accepted) == 1
    assert accepted[0]["sha256"] == data["winner"]["candidate_id"]
    assert data["winner"]["decision"] == "ADOPT"
    assert data["winner"]["prompt"]["verified"] is True
    assert "HIGH" in data["winner"]["prompt"]["content"]
    assert data["winner"]["workflow"]["commands"]
    assert any(
        "scripts/evaluate.py" in command["argv"]
        and data["winner"]["prompt"]["path"] in command["argv"]
        for command in data["winner"]["workflow"]["commands"]
    )
    assert any("scripts/gatekeeper.py" in command["argv"] for command in data["reproduction"]["commands"])
    rounds = [row for row in data["execution"]["records"] if row.get("event") == "round_complete"]
    assert len(rounds) == 1
    assert rounds[0]["winner_id"] == accepted[0]["path"]
    assert rounds[0]["score_diff"] > 0


def test_report_e2e_contains_adoptable_complete_evidence(report_workspace, monkeypatch):
    """最佳版本報告必須能獨立支撐採用、比較與重現，而非只顯示通過數。"""
    report_path, report = _generate_report(report_workspace, monkeypatch)
    data = _report_json(report)

    assert list(report_path.parent.glob("best-version.md")) == [report_path]

    winner = data["winner"]
    prompt = winner["prompt"]
    prompt_path = report_workspace / prompt["path"]
    assert prompt["verified"] is True
    assert prompt["content"] == prompt_path.read_text(encoding="utf-8")
    assert len(prompt["content"]) >= 100
    assert all(winner["workflow"][key] for key in ("steps", "commands"))
    assert len(winner["workflow"]["steps"]) >= 3

    quality = data["quality"]
    for dataset in ("smoke", "dev", "holdout"):
        assert isinstance(quality["winner"][dataset]["score"], (int, float))
        assert isinstance(quality["baseline"][dataset]["score"], (int, float))
    basis = quality["measurement_basis"]
    assert basis["score_scale"] == {"minimum": 0, "maximum": 100}
    assert {item["name"] for item in basis["datasets"]} == {"smoke", "dev", "holdout"}
    assert basis["thresholds"]
    assert basis["acceptance_criteria"]

    scorecards = sorted(report_workspace.glob("prompts/candidates/*.scorecard.json"))
    comparisons = data["candidate_comparison"]
    assert len(comparisons) == len(scorecards) == 3
    comparison_by_path = {row["path"]: row for row in comparisons}
    assert len(comparison_by_path) == len(comparisons)
    for scorecard_path in scorecards:
        card = json.loads(scorecard_path.read_text(encoding="utf-8"))
        candidate_path = card["candidate_path"]
        row = comparison_by_path[candidate_path]
        candidate = report_workspace / candidate_path
        assert row["candidate_id"]
        assert row["sha256"] == run_opt.sha256_text(candidate.read_text(encoding="utf-8"))
        assert row["decision"]
        assert row["classification"] in {"accepted", "rejected", "pending"}
        assert set(row["scores"]) == {"smoke", "dev", "holdout"}
        assert set(row["baseline_scores"]) == {"smoke", "dev", "holdout"}
        assert set(row["deltas"]) == {"smoke", "dev", "holdout"}
        for dataset in ("smoke", "dev", "holdout"):
            expected = card.get(dataset, {}).get("score")
            assert row["scores"][dataset]["score"] == expected

    reproduction = data["reproduction"]
    settings = reproduction["settings"]
    assert settings["winner_input"]["prompt_path"] == prompt["path"]
    assert settings["winner_input"]["prompt_hash"] == prompt["sha256"]
    assert {"url", "model", "evaluate_script", "compare_script", "gatekeeper_script"} <= set(settings["evaluator"])
    assert isinstance(settings["candidate_identification"], list)
    assert settings["execution_time"]
    assert all(
        command["argv"] and command["command"] and command["cwd"] == "."
        for command in reproduction["commands"]
    )
    assert {"scripts/evaluate.py", "scripts/gatekeeper.py"} <= {
        part for command in reproduction["commands"] for part in command["argv"]
    }

    environment = reproduction["environment"]
    assert all(environment.get(key) for key in ("python_version", "python_executable", "platform", "architecture", "os_name", "encoding", "cwd"))

    records = data["execution"]["records"]
    assert [record["event"] for record in records] == ["start", "round_complete", "stop"]
    assert data["execution"]["sessions"]
    assert data["execution"]["sessions"][0]["start"]
    assert data["execution"]["sessions"][0]["stop"]


def _remove_evidence(workspace, kind):
    if kind == "winner_prompt":
        (workspace / "prompts" / "baseline.md").unlink()
    elif kind == "baseline_scores":
        path = workspace / "prompts" / "baseline.meta.json"
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta.pop("dev_avg", None)
        meta.pop("holdout_avg", None)
        path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    elif kind == "candidate_comparison":
        for path in (workspace / "prompts" / "candidates").glob("*.scorecard.json"):
            path.unlink()
    elif kind == "measurement_basis":
        (workspace / "config.yaml").unlink()
    elif kind == "reproduction_session":
        _write_jsonl(
            workspace / "evolution_log.jsonl",
            [{"event": "start", "timestamp": "2026-08-02 00:00:00", "args": {}}],
        )
    elif kind == "execution_records":
        (workspace / "evolution_log.jsonl").unlink()
    else:
        raise AssertionError(f"unknown evidence kind: {kind}")


@pytest.mark.parametrize(
    "kind",
    [
        "winner_prompt",
        "baseline_scores",
        "candidate_comparison",
        "measurement_basis",
        "reproduction_session",
        "execution_records",
    ],
)
def test_report_e2e_missing_any_key_evidence_never_claims_best(
    report_workspace, monkeypatch, kind
):
    """刪除任一類關鍵證據後，報告只能為 inconclusive，不能宣稱最佳。"""
    _remove_evidence(report_workspace, kind)
    _report_path, report = _generate_report(report_workspace, monkeypatch)
    data = _report_json(report)

    assert data["decision"]["status"] == "inconclusive"
    assert data["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert data["decision"]["best_candidate_id"] is None
    assert data["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    assert data["winner"]["candidate_id"] is None
    assert "因證據不完整，無法選出冠軍" in report
