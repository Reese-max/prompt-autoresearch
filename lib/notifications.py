# -*- coding: utf-8 -*-
"""報告通知與可重試的 Telegram 交付。"""
import hashlib
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lib.config import get
from lib.io import append_jsonl, read_jsonl


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FAILURES_PATH = os.path.join(ROOT, "output", "delivery_failures.jsonl")
MAX_MESSAGE_LENGTH = 3900


def get_telegram_settings():
    """讀取既有 notifications.telegram 設定，並以環境變數補足。"""
    configured = get("notifications", "telegram", {}) or {}
    if not isinstance(configured, dict):
        configured = {}

    token = (
        configured.get("bot_token")
        or configured.get("token")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or os.environ.get("TELEGRAM_TOKEN", "")
    )
    chat_id = (
        configured.get("chat_id")
        or os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("TELEGRAM_TARGET_CHAT_ID", "")
    )
    enabled = configured.get("enabled")
    if enabled is None:
        enabled = bool(token or chat_id)

    return {
        "enabled": bool(enabled),
        "bot_token": str(token).strip(),
        "chat_id": str(chat_id).strip(),
        "api_base_url": str(
            configured.get("api_base_url")
            or os.environ.get("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
        ).rstrip("/"),
        "timeout": float(configured.get("timeout", 20)),
    }


def _report_status(report):
    if "報告判定：inconclusive" in report:
        return "inconclusive"
    return "valid"


def build_report_summary(report, report_path=None):
    """從報告擷取短摘要；完整內容由後續訊息一併送出。"""
    fields = {}
    for line in report.splitlines():
        if line.startswith("- 產生時間："):
            fields["time"] = line.split("：", 1)[1].strip()
        elif line.startswith("- 候選總數："):
            fields["candidates"] = line.split("：", 1)[1].strip()
        elif line.startswith("- 演化 session 數："):
            fields["sessions"] = line.split("：", 1)[1].strip()

    lines = [
        "Prompt AutoResearch 選優結論",
        f"判定：{_report_status(report)}",
    ]
    if fields.get("time"):
        lines.append(f"產生時間：{fields['time']}")
    if fields.get("candidates"):
        lines.append(f"候選總數：{fields['candidates']}")
    if fields.get("sessions"):
        lines.append(f"演化 session 數：{fields['sessions']}")
    if report_path:
        lines.append(f"完整報告路徑：{str(report_path).replace(chr(92), '/')}")
    return "\n".join(lines)


def _split_text(text, limit=MAX_MESSAGE_LENGTH):
    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
            chunks.append(remaining[:cut])
            remaining = remaining[cut:]
        else:
            chunks.append(remaining[:cut + 1])
            remaining = remaining[cut + 1:]
    return chunks or [""]


def build_report_messages(report, report_path=None):
    summary = build_report_summary(report, report_path)
    report_chunks = _split_text(report, MAX_MESSAGE_LENGTH - len(summary) - 40)
    messages = [
        f"{summary}\n\n完整報告內容（第 1/{len(report_chunks)} 段）：\n{report_chunks[0]}"
    ]
    messages.extend(
        f"完整報告內容（第 {index}/{len(report_chunks)} 段）：\n{chunk}"
        for index, chunk in enumerate(report_chunks[1:], 2)
    )
    return messages


def _send_message(settings, text):
    url = f"{settings['api_base_url']}/bot{settings['bot_token']}/sendMessage"
    body = urlencode({
        "chat_id": settings["chat_id"],
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    request = Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(request, timeout=settings["timeout"]) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError) as exc:
        raise RuntimeError(f"Telegram HTTP 交付失敗：{exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Telegram 回應不是有效 JSON") from exc
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API 拒絕交付：{payload.get('description', 'unknown error')}")
    return payload


def _failure_record(notification_id, messages, report_path, next_index, attempts, error):
    return {
        "notification_id": notification_id,
        "channel": "telegram",
        "status": "failed",
        "retryable": True,
        "attempts": attempts,
        "next_message_index": next_index,
        "messages": messages,
        "report_path": report_path or "",
        "error": str(error),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def _persist_failure(record, failure_path):
    append_jsonl(failure_path or FAILURES_PATH, record)


def _persist_failure_safely(record, failure_path):
    try:
        _persist_failure(record, failure_path)
        return ""
    except Exception as exc:
        return f"；交付失敗持久化失敗：{exc}"


def send_report_to_telegram(report, report_path=None, settings=None, failure_path=None):
    """送出摘要與完整報告；未完成全量送出時回傳 failed，且持久化佇列。"""
    settings = settings or get_telegram_settings()
    messages = build_report_messages(report, report_path)
    notification_id = hashlib.sha256(
        ("telegram\0" + (report_path or "") + "\0" + report).encode("utf-8")
    ).hexdigest()

    if not settings.get("enabled"):
        return {
            "notification_id": notification_id,
            "status": "skipped",
            "delivered": False,
            "reason": "telegram_disabled",
        }

    if not settings.get("bot_token") or not settings.get("chat_id"):
        error = "Telegram 設定不完整：需要 bot_token 與 chat_id"
        record = _failure_record(notification_id, messages, report_path, 0, 1, error)
        persistence_error = _persist_failure_safely(record, failure_path)
        return {
            "notification_id": notification_id,
            "status": "failed",
            "delivered": False,
            "error": error + persistence_error,
        }

    for index, message in enumerate(messages):
        try:
            _send_message(settings, message)
        except Exception as exc:
            record = _failure_record(notification_id, messages, report_path, index, 1, exc)
            persistence_error = _persist_failure_safely(record, failure_path)
            return {
                "notification_id": notification_id,
                "status": "failed",
                "delivered": False,
                "delivered_messages": index,
                "error": str(exc) + persistence_error,
            }

    return {
        "notification_id": notification_id,
        "status": "delivered",
        "delivered": True,
        "message_count": len(messages),
    }


def retry_failed_deliveries(failure_path=None, settings=None):
    """重試尚未完整送出的失敗記錄，只送出尚未成功的訊息段。"""
    path = failure_path or FAILURES_PATH
    if not os.path.exists(path):
        return []
    try:
        records = read_jsonl(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    latest = {}
    for record in records:
        notification_id = record.get("notification_id")
        if notification_id:
            latest[notification_id] = record

    settings = settings or get_telegram_settings()
    results = []
    for notification_id, record in latest.items():
        if record.get("status") != "failed" or not record.get("retryable"):
            continue
        messages = record.get("messages") or []
        next_index = int(record.get("next_message_index", 0))
        attempts = int(record.get("attempts", 0)) + 1
        error = None
        if not settings.get("enabled"):
            error = "Telegram 通知目前停用"
        elif not settings.get("bot_token") or not settings.get("chat_id"):
            error = "Telegram 設定不完整：需要 bot_token 與 chat_id"
        if error is None:
            for index in range(next_index, len(messages)):
                try:
                    _send_message(settings, messages[index])
                except Exception as exc:
                    error = exc
                    next_index = index
                    break
        if error is not None:
            updated = _failure_record(
                notification_id, messages, record.get("report_path", ""),
                next_index, attempts, error,
            )
            _persist_failure_safely(updated, path)
            results.append(updated)
            continue

        delivered = {
            "notification_id": notification_id,
            "channel": "telegram",
            "status": "delivered",
            "retryable": False,
            "attempts": attempts,
            "message_count": len(messages),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _persist_failure_safely(delivered, path)
        results.append(delivered)
    return results


deliver_report = send_report_to_telegram
