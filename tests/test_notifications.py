# -*- coding: utf-8 -*-
"""Telegram 報告交付的最小可觀察行為測試。"""
import json

from lib import notifications


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"ok": true, "result": {"message_id": 1}}'


def _settings():
    return {
        "enabled": True,
        "bot_token": "token",
        "chat_id": "chat",
        "api_base_url": "https://telegram.invalid",
        "timeout": 1,
    }


def test_report_messages_include_summary_and_complete_content():
    report = "- 報告判定：inconclusive\n" + ("證據\n" * 2000)

    messages = notifications.build_report_messages(report, "output/report.md")
    chunks = notifications._split_text(report, 100)

    assert "判定：inconclusive" in messages[0]
    assert "完整報告路徑：output/report.md" in messages[0]
    assert "".join(chunks) == report
    assert "".join(messages).count("證據") == report.count("證據")
    assert all(len(message) <= notifications.MAX_MESSAGE_LENGTH for message in messages)


def test_failed_delivery_is_persisted_and_retryable(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"

    def fail(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(notifications, "urlopen", fail)
    result = notifications.send_report_to_telegram(
        "- 報告判定：valid\n完整報告",
        settings=_settings(),
        failure_path=str(failure_path),
    )

    assert result["status"] == "failed"
    saved = json.loads(failure_path.read_text(encoding="utf-8"))
    assert saved["retryable"] is True
    assert saved["status"] == "failed"
    assert saved["messages"]


def test_retry_sends_remaining_messages_and_records_delivery(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    failure_path.write_text(json.dumps({
        "notification_id": "n1",
        "channel": "telegram",
        "status": "failed",
        "retryable": True,
        "attempts": 1,
        "next_message_index": 0,
        "messages": ["摘要", "完整報告"],
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    calls = []

    def succeed(request, timeout):
        calls.append((request.full_url, timeout))
        return _Response()

    monkeypatch.setattr(notifications, "urlopen", succeed)
    result = notifications.retry_failed_deliveries(str(failure_path), _settings())

    assert result[0]["status"] == "delivered"
    assert result[0]["retryable"] is False
    assert len(calls) == 2
    records = [json.loads(line) for line in failure_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["status"] == "delivered"
