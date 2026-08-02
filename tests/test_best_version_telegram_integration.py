# -*- coding: utf-8 -*-
"""最佳版本報告與 Telegram 交付的受控整合測試。"""
import hashlib
import json
from urllib.parse import parse_qs

import pytest

import scripts.best_version_report as bvr
from lib import notifications


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok": true, "result": {"message_id": 1}}'


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _report_payload(report):
    block = report.split("```json\n", 1)[1].split("\n```", 1)[0]
    return json.loads(block)


@pytest.fixture
def evidence_sandbox(tmp_path, monkeypatch):
    prompts = tmp_path / "prompts"
    champions = prompts / "champions"
    candidates = prompts / "candidates"
    champions.mkdir(parents=True)
    candidates.mkdir()

    monkeypatch.setattr(bvr, "ROOT", str(tmp_path))
    monkeypatch.setattr(bvr, "BASELINE_META_PATH", str(prompts / "baseline.meta.json"))
    monkeypatch.setattr(bvr, "CHAMPIONS_DIR", str(champions))
    monkeypatch.setattr(bvr, "CANDIDATES_DIR", str(candidates))
    monkeypatch.setattr(bvr, "EVOLUTION_LOG_PATH", str(tmp_path / "evolution_log.jsonl"))
    monkeypatch.setattr(bvr, "CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(bvr, "RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(bvr, "collect_git_commit", lambda: "controlled-commit")

    winner_prompt = prompts / "baseline.md"
    winner_prompt.write_text("controlled winner prompt\n", encoding="utf-8")
    winner_hash = _sha256(winner_prompt)
    (prompts / "baseline.meta.json").write_text(
        json.dumps({
            "prompt_path": "prompts/baseline.md",
            "prompt_hash": winner_hash,
            "dev_avg": 91.0,
            "holdout_avg": 90.5,
            "dev_run": "runs/dev-winner",
            "holdout_run": "runs/holdout-winner",
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    champion_prompt = champions / "legal_case.md"
    champion_prompt.write_text("controlled type champion\n", encoding="utf-8")
    (champions / "legal_case.meta.json").write_text(
        json.dumps({
            "type": "法律案例題",
            "type_slug": "legal_case",
            "candidate_hash": _sha256(champion_prompt),
            "champion_prompt_path": "prompts/champions/legal_case.md",
            "candidate_avg": 92.0,
            "diff": 3.0,
            "decision": "SPECIALTY_RETAINED",
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    accepted_prompt = candidates / "accepted.md"
    accepted_prompt.write_text("controlled accepted candidate\n", encoding="utf-8")
    (candidates / "accepted.scorecard.json").write_text(
        json.dumps({
            "candidate_path": "prompts/candidates/accepted.md",
            "candidate_hash": _sha256(accepted_prompt),
            "status": "completed",
            "final_decision": "ACCEPT",
            "direction": "D01",
            "dev": {"score": 92.0},
            "holdout": {"score": 90.5},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    rejected_prompt = candidates / "rejected.md"
    rejected_prompt.write_text("controlled rejected candidate\n", encoding="utf-8")
    (candidates / "rejected.scorecard.json").write_text(
        json.dumps({
            "candidate_path": "prompts/candidates/rejected.md",
            "candidate_hash": _sha256(rejected_prompt),
            "status": "rejected_holdout",
            "final_decision": "REJECT",
            "reject_reasons": ["holdout regression"],
            "direction": "D02",
            "dev": {"score": 91.5},
            "holdout": {"score": 80.0},
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    (tmp_path / "evolution_log.jsonl").write_text(
        json.dumps({
            "event": "start",
            "timestamp": "2026-08-02 10:00:00",
            "args": {"max_rounds": 1},
        }, ensure_ascii=False)
        + "\n"
        + json.dumps({
            "event": "stop",
            "timestamp": "2026-08-02 10:01:00",
            "reason": "complete",
            "best_score": 92.0,
            "elapsed_seconds": 60,
        }, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        "api:\n  url: https://evaluator.invalid/v1\n  model: controlled-model\n"
        "thresholds:\n  dev_min_improvement: 2.0\n",
        encoding="utf-8",
    )
    return {"root": tmp_path, "winner_hash": winner_hash}


def test_complete_evidence_report_identifies_adopts_and_reruns_winner(evidence_sandbox):
    report = bvr.build_report()
    payload = _report_payload(report)

    assert payload["evidence_integrity"]["valid"] is True
    assert payload["evidence_verification"]["valid"] is True
    assert payload["champion"]["prompt_hash"] == evidence_sandbox["winner_hash"]
    assert payload["rerun_settings"]["winner_input"] == {
        "prompt_path": "prompts/baseline.md",
        "prompt_hash": evidence_sandbox["winner_hash"],
    }
    assert payload["rerun_settings"]["evaluator"]["evaluate_script"] == "scripts/evaluate.py"
    assert payload["rerun_settings"]["evaluator"]["compare_script"] == "scripts/compare_runs.py"
    assert payload["rerun_settings"]["version"]["commit"] == "controlled-commit"
    assert "## 1. Winner（冠軍）" in report
    assert "## 2. 可直接採用的流程" in report
    assert "holdout regression" in report


@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_missing_or_tampered_key_evidence_rejects_best_claim(evidence_sandbox, mutation):
    winner_prompt = evidence_sandbox["root"] / "prompts" / "baseline.md"
    if mutation == "missing":
        winner_prompt.unlink()
    else:
        winner_prompt.write_text("tampered winner prompt\n", encoding="utf-8")

    report = bvr.build_report()
    payload = _report_payload(report)

    assert payload["evidence_integrity"]["valid"] is False
    assert payload["evidence_verification"]["valid"] is False
    assert payload["champion"] == {
        "prompt_hash": "",
        "dev_avg": None,
        "holdout_avg": None,
        "dev_run": "",
        "holdout_run": "",
    }
    assert "## ⚠️ 證據完整性閘門：INCONCLUSIVE" in report
    assert "報告判定：inconclusive" in report
    assert "因證據不完整，無法選出冠軍" in report
    assert "## ✅ 證據完整性閘門：PASS" not in report
    assert "拒絕選優" in report


@pytest.mark.parametrize("mutation,expected_status", [(None, "valid"), ("tampered", "inconclusive")])
def test_telegram_payload_contains_decision_reason_and_report_path(
    evidence_sandbox, monkeypatch, mutation, expected_status
):
    winner_prompt = evidence_sandbox["root"] / "prompts" / "baseline.md"
    if mutation == "tampered":
        winner_prompt.write_text("tampered winner prompt\n", encoding="utf-8")

    report = bvr.build_report()
    report_path = "output/best_version_report.md"
    report_file = evidence_sandbox["root"] / report_path
    report_file.parent.mkdir()
    report_file.write_text(report, encoding="utf-8")
    sent_payloads = []

    def capture(request, timeout):
        sent_payloads.append(parse_qs(request.data.decode("utf-8"))["text"][0])
        return _Response()

    monkeypatch.setattr(notifications, "urlopen", capture)
    result = notifications.send_report_to_telegram(
        report,
        report_path=report_path,
        settings={
            "enabled": True,
            "bot_token": "controlled-token",
            "chat_id": "controlled-chat",
            "api_base_url": "https://telegram.invalid",
            "timeout": 1,
        },
        failure_path=str(evidence_sandbox["root"] / "delivery_failures.jsonl"),
    )

    combined_payload = "\n".join(sent_payloads)
    assert result["status"] == "delivered"
    assert f"判定：{expected_status}" in combined_payload
    if mutation is None:
        assert evidence_sandbox["winner_hash"] in combined_payload
    else:
        assert "因證據不完整，無法選出冠軍" in combined_payload
    assert "holdout regression" in combined_payload
    assert "完整報告路徑：output/best_version_report.md" in combined_payload
    assert "完整報告內容" in combined_payload
    assert report_path.replace("/", "\\") not in combined_payload
    assert report_file.is_file()
