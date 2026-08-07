# -*- coding: utf-8 -*-
"""研究結果交付驗收：成功送達、失敗後可辨識 pending、重試成功、冪等重跑與不可交付不得通知。"""
import json

import scripts.best_version_report as bvr
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


def _long_report():
    return "- 報告判定：valid\n- 候選總數：2\n" + ("完整證據段落\n" * 2000)


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------------------
# 成功送達
# ---------------------------------------------------------------------------


def test_research_result_delivery_success_sends_all_messages_and_confirms(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    calls = []

    def succeed(request, timeout):
        calls.append(request.full_url)
        return _Response()

    monkeypatch.setattr(notifications, "urlopen", succeed)
    result = notifications.send_report_to_telegram(
        _long_report(),
        report_path="output/report.md",
        settings=_settings(),
        failure_path=str(failure_path),
    )

    assert result["status"] == "delivered"
    assert result["delivered"] is True
    assert result["message_count"] >= 2
    assert len(calls) == result["message_count"]
    assert all("report.md" in url or "sendMessage" in url for url in calls)
    assert not failure_path.exists()


# ---------------------------------------------------------------------------
# 傳送失敗後可辨識 pending / failed
# ---------------------------------------------------------------------------


def test_research_result_delivery_failure_persists_pending_failed_record(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    calls = {"count": 0}

    def fail_after_first(request, timeout):
        calls["count"] += 1
        if calls["count"] == 1:
            return _Response()
        raise OSError("offline")

    monkeypatch.setattr(notifications, "urlopen", fail_after_first)
    result = notifications.send_report_to_telegram(
        _long_report(),
        report_path="output/report.md",
        settings=_settings(),
        failure_path=str(failure_path),
    )

    assert result["status"] == "failed"
    assert result["delivered"] is False
    assert result["delivered_messages"] == 1
    assert result["retryable"] is True
    assert result["error_class"] == "temporary"

    record = json.loads(failure_path.read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert record["retryable"] is True
    assert record["notification_id"] == result["notification_id"]
    assert record["next_message_index"] == 1
    assert len(record["messages"]) >= 2
    assert record["next_message_index"] < len(record["messages"])


# ---------------------------------------------------------------------------
# 重試成功（只補送尚未送出的 pending 訊息段）
# ---------------------------------------------------------------------------


def test_research_result_delivery_retry_recovers_pending_and_marks_delivered(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    failure_path.write_text(json.dumps({
        "notification_id": "retry-id-1",
        "channel": "telegram",
        "status": "failed",
        "retryable": True,
        "attempts": 1,
        "next_message_index": 1,
        "messages": ["摘要", "完整報告段二", "完整報告段三"],
        "original_attempt_id": "orig-a",
        "attempt_id": "attempt-a",
        "error_code": "network_error",
        "error_class": "temporary",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    calls = []

    def succeed(request, timeout):
        calls.append(request.full_url)
        return _Response()

    monkeypatch.setattr(notifications, "urlopen", succeed)
    result = notifications.retry_failed_deliveries(str(failure_path), _settings())

    assert len(result) == 1
    assert result[0]["status"] == "delivered"
    assert result[0]["retryable"] is False
    assert len(calls) == 2
    records = _records(failure_path)
    assert records[-1]["status"] == "delivered"
    assert records[-1]["message_count"] == 3
    assert records[-1]["original_attempt_id"] == "orig-a"


# ---------------------------------------------------------------------------
# 冪等重跑
# ---------------------------------------------------------------------------


def test_research_result_delivery_rerun_skips_delivered_records(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"
    failure_path.write_text(json.dumps({
        "notification_id": "delivered-1",
        "channel": "telegram",
        "status": "delivered",
        "retryable": False,
        "attempts": 2,
        "next_message_index": 2,
        "messages": ["摘要", "段二", "段三"],
        "original_attempt_id": "orig-x",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    calls = []

    def fail_never(*_args, **_kwargs):
        calls.append(1)
        return _Response()

    monkeypatch.setattr(notifications, "urlopen", fail_never)
    first = notifications.retry_failed_deliveries(str(failure_path), _settings())
    second = notifications.retry_failed_deliveries(str(failure_path), _settings())

    assert first == []
    assert second == []
    assert calls == []
    assert len(_records(failure_path)) == 1


def test_research_result_delivery_notification_id_is_idempotency_key(tmp_path, monkeypatch):
    failure_path = tmp_path / "delivery_failures.jsonl"

    def succeed(*_args, **_kwargs):
        return _Response()

    monkeypatch.setattr(notifications, "urlopen", succeed)
    first = notifications.send_report_to_telegram(
        _long_report(), report_path="output/report.md",
        settings=_settings(), failure_path=str(failure_path),
    )
    second = notifications.send_report_to_telegram(
        _long_report(), report_path="output/report.md",
        settings=_settings(), failure_path=str(failure_path),
    )

    assert first["notification_id"]
    assert first["notification_id"] == second["notification_id"]


# ---------------------------------------------------------------------------
# 不可交付研究不得通知
# ---------------------------------------------------------------------------


def test_research_result_delivery_notify_skipped_when_not_deliverable(monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(
        bvr, "send_report_to_telegram",
        lambda *_args, **_kwargs: sent.append(1) or {"status": "delivered"},
    )
    not_deliverable = {"execution_identity": {"deliverable_allowed": False}}
    monkeypatch.setattr(bvr, "build_structured_report", lambda limit=10: not_deliverable)
    monkeypatch.setattr(bvr, "build_report", lambda limit=10, structured=None: "# 最佳版本證據報告\n不可交付\n")
    monkeypatch.setattr(bvr.sys, "argv", ["best_version_report.py"])

    assert bvr.main() == 0
    assert sent == []
    assert "不可交付" in capsys.readouterr().out


def test_research_result_delivery_notify_sent_when_deliverable(monkeypatch):
    sent = []
    monkeypatch.setattr(
        bvr, "send_report_to_telegram",
        lambda *_args, **_kwargs: sent.append(1) or {"status": "delivered"},
    )
    deliverable = {"execution_identity": {"deliverable_allowed": True}}
    monkeypatch.setattr(bvr, "build_structured_report", lambda limit=10: deliverable)
    monkeypatch.setattr(bvr, "build_report", lambda limit=10, structured=None: "# 最佳版本證據報告\n")
    monkeypatch.setattr(bvr.sys, "argv", ["best_version_report.py"])

    assert bvr.main() == 0
    assert len(sent) == 1