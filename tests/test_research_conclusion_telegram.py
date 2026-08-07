# -*- coding: utf-8 -*-
"""研究結論交付事件的 Telegram Bot API 通知通道測試。

重點：僅在 API 回傳 ok=true 且含有效 result.message_id 時才確認送達。
"""
import json
from urllib.parse import parse_qs

from lib import notifications


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload.encode("utf-8")


def _settings(**overrides):
    values = {
        "enabled": True,
        "bot_token": "token",
        "chat_id": "chat",
        "api_base_url": "https://telegram.invalid",
        "timeout": 1,
    }
    values.update(overrides)
    return values


def _structured():
    return {
        "generated_at": "2026-08-07 10:00:00",
        "decision": {
            "status": "valid",
            "code": "VALID",
            "reason": "證據完整且通過重新驗證",
            "best_candidate_id": "hash-winner",
        },
        "winner": {
            "candidate_id": "hash-winner",
            "kind": "global_baseline",
            "decision": "ADOPT",
            "prompt": {"path": "prompts/baseline.md", "hash": "hash-winner"},
            "scores": {"dev": {"score": 92.0}, "holdout": {"score": 91.0}},
        },
        "quality_ranking": {
            "best_status": "proven",
            "best_scope": "global",
            "eligible_candidate_ids": ["hash-winner", "hash-runner"],
            "excluded_candidate_ids": ["hash-reject"],
        },
        "candidate_comparison": [
            {
                "candidate_id": "hash-winner",
                "path": "prompts/candidates/winner.md",
                "decision": "ACCEPT",
                "quality_eligible": True,
                "scores": {"dev": {"score": 92.0}, "holdout": {"score": 91.0}},
            },
            {
                "candidate_id": "hash-runner",
                "path": "prompts/candidates/runner.md",
                "decision": "ACCEPT",
                "quality_eligible": True,
                "scores": {"dev": {"score": 86.0}, "holdout": {"score": 85.0}},
            },
            {
                "candidate_id": "hash-reject",
                "path": "prompts/candidates/reject.md",
                "decision": "REJECT",
                "quality_eligible": False,
                "scores": {"dev": {"score": None}, "holdout": {"score": 80.0}},
            },
        ],
        "evidence_files": {
            "baseline_meta": "prompts/baseline.meta.json",
            "champions_dir": "prompts/champions",
            "candidates_dir": "prompts/candidates",
            "evolution_log": "evolution_log.jsonl",
        },
        "reproduction": {
            "settings": {
                "winner_input": {"prompt_path": "prompts/baseline.md"},
            },
            "rerun_commands": [],
        },
    }


def test_build_conclusion_message_contains_all_sections():
    message = notifications.build_conclusion_message(_structured())

    assert "研究結論" in message
    assert "判定：valid" in message
    assert "勝出候選" in message
    assert "hash-winner" in message
    assert "prompts/baseline.md" in message
    assert "品質比較摘要" in message
    assert "可比對候選數：2" in message
    assert "排除候選數：1" in message
    assert "證據路徑" in message
    assert "prompts/baseline.meta.json" in message
    assert "prompts/candidates" in message
    assert "採用建議" in message
    assert "建議採用" in message


def test_build_conclusion_message_backslash_paths_normalized():
    structured = _structured()
    structured["winner"]["prompt"]["path"] = "output\\best_version_report.md"
    message = notifications.build_conclusion_message(structured, report_path="output\\report.md")
    assert "\\" not in message
    assert "output/best_version_report.md" in message
    assert "output/report.md" in message


def test_build_conclusion_message_invalid_state_recommends_not_adopting():
    structured = _structured()
    structured["decision"] = {
        "status": "inconclusive",
        "code": "INCOMPLETE_EVIDENCE",
        "reason": "證據不完整，拒絕選優",
        "best_candidate_id": None,
    }
    structured["winner"]["candidate_id"] = None
    structured["winner"]["decision"] = "INCOMPLETE_EVIDENCE"
    structured["winner"]["scores"] = {}
    message = notifications.build_conclusion_message(structured)

    assert "判定：inconclusive" in message
    assert "無（證據不完整，未產生勝出候選）" in message
    assert "暫不採用" in message
    assert "最佳狀態：n/a" in message or "最佳狀態：" in message


def test_delivered_only_when_ok_and_valid_message_id(tmp_path, monkeypatch):
    calls = []

    def capture(request, timeout):
        calls.append(parse_qs(request.data.decode("utf-8"))["text"][0])
        return _Response('{"ok": true, "result": {"message_id": 42}}')

    monkeypatch.setattr(notifications, "urlopen", capture)
    result = notifications.send_research_conclusion(
        _structured(),
        settings=_settings(),
        report_path="output/report.md",
        failure_path=str(tmp_path / "failures.jsonl"),
    )

    assert result["status"] == "delivered"
    assert result["delivered"] is True
    assert result["message_id"] == 42
    assert len(calls) == 1
    sent = calls[0]
    assert "hash-winner" in sent
    assert "採用建議" in sent
    assert "output/report.md" in sent


def test_missing_message_id_is_not_confirmed_delivered(tmp_path, monkeypatch):
    monkeypatch.setattr(
        notifications, "urlopen",
        lambda request, timeout: _Response('{"ok": true, "result": {}}'),
    )
    result = notifications.send_research_conclusion(
        _structured(),
        settings=_settings(),
        report_path="output/report.md",
        failure_path=str(tmp_path / "failures.jsonl"),
    )

    assert result["status"] == "failed"
    assert result["delivered"] is False
    assert result["error_code"] == "invalid_response"
    assert result["error_class"] == "temporary"
    assert result["retryable"] is True
    assert "message_id" in result["error"]
    records = [json.loads(line) for line in (tmp_path / "failures.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[-1]["status"] == "failed"
    assert records[-1]["error_code"] == "invalid_response"


def test_ok_false_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        notifications, "urlopen",
        lambda request, timeout: _Response('{"ok": false, "description": "403 Forbidden"}'),
    )
    result = notifications.send_research_conclusion(
        _structured(),
        settings=_settings(),
        report_path="output/report.md",
        failure_path=str(tmp_path / "failures.jsonl"),
    )

    assert result["status"] == "failed"
    assert result["delivered"] is False
    assert result["error_code"] == "forbidden"
    assert result["error_class"] == "blocking"
    assert result["retryable"] is False


def test_ok_false_without_error_keyword_not_delivered(tmp_path, monkeypatch):
    monkeypatch.setattr(
        notifications, "urlopen",
        lambda request, timeout: _Response('{"ok": false, "description": "bot is not a member"}'),
    )
    result = notifications.send_research_conclusion(
        _structured(),
        settings=_settings(),
        report_path="output/report.md",
        failure_path=str(tmp_path / "failures.jsonl"),
    )

    assert result["status"] == "failed"
    assert result["delivered"] is False


def test_network_error_is_retryable(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(notifications, "urlopen", fail)
    result = notifications.send_research_conclusion(
        _structured(),
        settings=_settings(),
        report_path="output/report.md",
        failure_path=str(tmp_path / "failures.jsonl"),
    )

    assert result["status"] == "failed"
    assert result["delivered"] is False
    assert result["error_code"] == "network_error"
    assert result["error_class"] == "temporary"
    assert result["retryable"] is True
    records = [json.loads(line) for line in (tmp_path / "failures.jsonl").read_text(encoding="utf-8").splitlines()]
    assert records[-1]["retryable"] is True


def test_disabled_settings_blocked(tmp_path):
    result = notifications.send_research_conclusion(
        _structured(),
        settings=_settings(enabled=False, bot_token="", chat_id=""),
        report_path="output/report.md",
        failure_path=str(tmp_path / "failures.jsonl"),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "disabled"
    assert result["error_class"] == "blocking"
    assert result["retryable"] is False


def test_missing_settings_blocked(tmp_path):
    result = notifications.send_research_conclusion(
        _structured(),
        settings=_settings(bot_token=""),
        report_path="output/report.md",
        failure_path=str(tmp_path / "failures.jsonl"),
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "missing_settings"
    assert result["error_class"] == "blocking"
    assert result["retryable"] is False
