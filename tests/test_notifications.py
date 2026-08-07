# -*- coding: utf-8 -*-
"""Telegram 報告交付的最小可觀察行為測試。"""
import json
import time

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
    assert result["retryable"] is True
    assert "attempt_id" in result
    assert "original_attempt_id" in result
    assert result["error_code"] == "network_error"
    assert result["error_class"] == "temporary"
    saved = json.loads(failure_path.read_text(encoding="utf-8"))
    assert saved["retryable"] is True
    assert saved["status"] == "failed"
    assert saved["messages"]
    assert "attempt_id" in saved
    assert "original_attempt_id" in saved


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


def test_classify_error_blocking_for_settings():
    error_code, error_class = notifications.classify_error("Telegram 設定不完整：需要 bot_token 與 chat_id")
    assert error_code == "missing_settings"
    assert error_class == "blocking"


def test_classify_error_blocking_for_disabled():
    error_code, error_class = notifications.classify_error("Telegram 通知已停用")
    assert error_code == "disabled"
    assert error_class == "blocking"


def test_classify_error_blocking_for_auth():
    error_code, error_class = notifications.classify_error("401 Unauthorized")
    assert error_code == "auth_failed"
    assert error_class == "blocking"


def test_classify_error_blocking_for_forbidden():
    error_code, error_class = notifications.classify_error("403 Forbidden")
    assert error_code == "forbidden"
    assert error_class == "blocking"


def test_classify_error_temporary_for_timeout():
    error_code, error_class = notifications.classify_error("Connection timed out")
    assert error_code == "timeout"
    assert error_class == "temporary"


def test_classify_error_temporary_for_rate_limit():
    error_code, error_class = notifications.classify_error("429 Too Many Requests")
    assert error_code == "rate_limited"
    assert error_class == "temporary"


def test_classify_error_temporary_for_server_error():
    error_code, error_class = notifications.classify_error("HTTP Error 503: Service Unavailable")
    assert error_code == "server_error"
    assert error_class == "temporary"


def test_bounded_retry_stops_at_max_retries(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    failure_path.write_text(json.dumps({
        "notification_id": "n2",
        "channel": "telegram",
        "status": "failed",
        "retryable": True,
        "attempts": 3,
        "next_message_index": 0,
        "messages": ["摘要"],
        "error_code": "network_error",
        "error_class": "temporary",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(notifications, "urlopen", fail)
    result = notifications.retry_failed_deliveries(str(failure_path), _settings(), max_retries=3)

    assert len(result) == 1
    assert result[0]["status"] == "retry_exhausted"
    assert result[0]["retryable"] is False
    assert result[0]["attempts"] == 3
    assert result[0]["max_retries"] == 3
    assert "resend_command" in result[0]


def test_blocking_error_skips_retry(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    failure_path.write_text(json.dumps({
        "notification_id": "n3",
        "channel": "telegram",
        "status": "failed",
        "retryable": False,
        "attempts": 1,
        "next_message_index": 0,
        "messages": ["摘要"],
        "error_code": "auth_failed",
        "error_class": "blocking",
        "error": "401 Unauthorized",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    result = notifications.retry_failed_deliveries(str(failure_path), _settings())

    assert len(result) == 1
    assert result[0]["status"] == "blocked"
    assert result[0]["retryable"] is False
    assert result[0]["error_code"] == "auth_failed"
    assert result[0]["error_class"] == "blocking"
    assert "resend_command" in result[0]


def test_attempt_id_preserved_across_retries(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    original_attempt_id = "orig123"
    failure_path.write_text(json.dumps({
        "notification_id": "n4",
        "attempt_id": "attempt1",
        "original_attempt_id": original_attempt_id,
        "channel": "telegram",
        "status": "failed",
        "retryable": True,
        "attempts": 1,
        "next_message_index": 0,
        "messages": ["摘要"],
        "error_code": "network_error",
        "error_class": "temporary",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    calls = []

    def succeed(request, timeout):
        calls.append((request.full_url, timeout))
        return _Response()

    monkeypatch.setattr(notifications, "urlopen", succeed)
    result = notifications.retry_failed_deliveries(str(failure_path), _settings())

    assert result[0]["status"] == "delivered"
    assert result[0]["original_attempt_id"] == original_attempt_id
    assert result[0]["attempt_id"] != "attempt1"
    records = [json.loads(line) for line in failure_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["original_attempt_id"] == original_attempt_id


def test_resend_command_generated_on_failure(tmp_path, monkeypatch):
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
    records = [json.loads(line) for line in failure_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["status"] == "failed"


def test_retry_exhausted_provides_resend_command(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    failure_path.write_text(json.dumps({
        "notification_id": "n5",
        "channel": "telegram",
        "status": "failed",
        "retryable": True,
        "attempts": 2,
        "next_message_index": 0,
        "messages": ["摘要"],
        "error_code": "network_error",
        "error_class": "temporary",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(notifications, "urlopen", fail)
    result = notifications.retry_failed_deliveries(str(failure_path), _settings(), max_retries=2)

    assert len(result) == 1
    assert result[0]["status"] == "retry_exhausted"
    assert "resend_command" in result[0]
    assert "retry_failed_deliveries" in result[0]["resend_command"]


def test_disabled_settings_returns_blocking_error(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"

    result = notifications.send_report_to_telegram(
        "- 報告判定：valid\n完整報告",
        settings={"enabled": False, "bot_token": "", "chat_id": "", "api_base_url": "", "timeout": 1},
        failure_path=str(failure_path),
    )

    assert result["status"] == "failed"
    assert result["error_class"] == "blocking"
    assert result["retryable"] is False
    assert result["error_code"] == "disabled"
    saved = json.loads(failure_path.read_text(encoding="utf-8"))
    assert saved["error_code"] == "disabled"
    assert saved["retryable"] is False
