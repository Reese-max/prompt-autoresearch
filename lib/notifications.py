# -*- coding: utf-8 -*-
"""報告通知與可重試的 Telegram 交付。"""
import hashlib
import json
import os
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lib.config import get
from lib.io import append_jsonl, read_jsonl


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FAILURES_PATH = os.path.join(ROOT, "output", "delivery_failures.jsonl")
MAX_MESSAGE_LENGTH = 3900
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2

BLOCKING_ERROR_CODES = {
    "missing_settings",
    "auth_failed",
    "forbidden",
    "disabled",
}
TEMPORARY_ERROR_CODES = {
    "network_error",
    "rate_limited",
    "server_error",
    "timeout",
    "invalid_response",
}


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


def classify_error(error):
    """分類錯誤為 temporary（可重試）或 blocking（阻塞）。"""
    error_str = str(error).lower()
    if "設定不完整" in error_str or "需要 bot_token" in error_str:
        return "missing_settings", "blocking"
    if "disabled" in error_str or "停用" in error_str:
        return "disabled", "blocking"
    if "401" in error_str or "unauthorized" in error_str:
        return "auth_failed", "blocking"
    if "403" in error_str or "forbidden" in error_str:
        return "forbidden", "blocking"
    if "429" in error_str or "rate limit" in error_str or "too many" in error_str:
        return "rate_limited", "temporary"
    if "timeout" in error_str or "timed out" in error_str:
        return "timeout", "temporary"
    if "500" in error_str or "502" in error_str or "503" in error_str:
        return "server_error", "temporary"
    if "ssl" in error_str or "certificate" in error_str:
        return "network_error", "temporary"
    if "connection" in error_str or "refused" in error_str or "reset" in error_str:
        return "network_error", "temporary"
    if "json" in error_str or "invalid" in error_str or "decode" in error_str:
        return "invalid_response", "temporary"
    return "network_error", "temporary"


def _failure_record(notification_id, messages, report_path, next_index, attempts, error, attempt_id=None, original_attempt_id=None):
    error_code, error_class = classify_error(error)
    retryable = error_class == "temporary"
    return {
        "notification_id": notification_id,
        "attempt_id": attempt_id or uuid.uuid4().hex,
        "original_attempt_id": original_attempt_id or uuid.uuid4().hex,
        "channel": "telegram",
        "status": "failed",
        "retryable": retryable,
        "error_code": error_code,
        "error_class": error_class,
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
    attempt_id = uuid.uuid4().hex
    original_attempt_id = attempt_id

    if not settings.get("enabled"):
        error = "Telegram 通知已停用"
        record = _failure_record(notification_id, messages, report_path, 0, 1, error, attempt_id, original_attempt_id)
        persistence_error = _persist_failure_safely(record, failure_path)
        return {
            "notification_id": notification_id,
            "attempt_id": attempt_id,
            "original_attempt_id": original_attempt_id,
            "status": "failed",
            "delivered": False,
            "error": error + persistence_error,
            "error_code": record["error_code"],
            "error_class": "blocking",
            "retryable": False,
        }

    if not settings.get("bot_token") or not settings.get("chat_id"):
        error = "Telegram 設定不完整：需要 bot_token 與 chat_id"
        record = _failure_record(notification_id, messages, report_path, 0, 1, error, attempt_id, original_attempt_id)
        persistence_error = _persist_failure_safely(record, failure_path)
        return {
            "notification_id": notification_id,
            "attempt_id": attempt_id,
            "original_attempt_id": original_attempt_id,
            "status": "failed",
            "delivered": False,
            "error": error + persistence_error,
            "error_code": record["error_code"],
            "error_class": "blocking",
            "retryable": False,
        }

    for index, message in enumerate(messages):
        try:
            _send_message(settings, message)
        except Exception as exc:
            record = _failure_record(notification_id, messages, report_path, index, 1, exc, attempt_id, original_attempt_id)
            persistence_error = _persist_failure_safely(record, failure_path)
            return {
                "notification_id": notification_id,
                "attempt_id": attempt_id,
                "original_attempt_id": original_attempt_id,
                "status": "failed",
                "delivered": False,
                "delivered_messages": index,
                "error": str(exc) + persistence_error,
                "error_code": record["error_code"],
                "error_class": record["error_class"],
                "retryable": record["retryable"],
            }

    return {
        "notification_id": notification_id,
        "attempt_id": attempt_id,
        "original_attempt_id": original_attempt_id,
        "status": "delivered",
        "delivered": True,
        "message_count": len(messages),
    }


def build_resend_command(notification_id, failure_path=None):
    """產生可執行的重送命令。"""
    path = failure_path or FAILURES_PATH
    return (
        f"python -c \""
        f"from lib.notifications import retry_failed_deliveries; "
        f"retry_failed_deliveries(failure_path='{path}')"
        f"\""
    )


def retry_failed_deliveries(failure_path=None, settings=None, max_retries=None):
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
    retry_limit = max_retries or get("notifications", "max_retries", DEFAULT_MAX_RETRIES)
    results = []
    for notification_id, record in latest.items():
        if record.get("status") != "failed":
            continue
        if not record.get("retryable", True):
            error_class = record.get("error_class", "")
            error_code = record.get("error_code", "")
            if error_class == "blocking" or error_code in BLOCKING_ERROR_CODES:
                resend_cmd = build_resend_command(notification_id, path)
                results.append({
                    "notification_id": notification_id,
                    "status": "blocked",
                    "retryable": False,
                    "error_code": error_code,
                    "error_class": "blocking",
                    "error": record.get("error", ""),
                    "resend_command": resend_cmd,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                })
                continue

        attempts = int(record.get("attempts", 0))
        if attempts >= retry_limit:
            resend_cmd = build_resend_command(notification_id, path)
            results.append({
                "notification_id": notification_id,
                "status": "retry_exhausted",
                "retryable": False,
                "attempts": attempts,
                "max_retries": retry_limit,
                "error": record.get("error", ""),
                "error_code": record.get("error_code", ""),
                "error_class": record.get("error_class", ""),
                "resend_command": resend_cmd,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            continue

        messages = record.get("messages") or []
        next_index = int(record.get("next_message_index", 0))
        new_attempt_id = uuid.uuid4().hex
        original_attempt_id = record.get("original_attempt_id") or record.get("attempt_id", new_attempt_id)
        error = None

        backoff_seconds = DEFAULT_BACKOFF_BASE ** min(attempts, 5)
        time.sleep(min(backoff_seconds, 30))

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
                next_index, attempts + 1, error, new_attempt_id, original_attempt_id,
            )
            updated["original_attempt_id"] = original_attempt_id
            _persist_failure_safely(updated, path)
            resend_cmd = build_resend_command(notification_id, path)
            updated["resend_command"] = resend_cmd
            results.append(updated)
            continue

        delivered = {
            "notification_id": notification_id,
            "attempt_id": new_attempt_id,
            "original_attempt_id": original_attempt_id,
            "channel": "telegram",
            "status": "delivered",
            "retryable": False,
            "attempts": attempts + 1,
            "message_count": len(messages),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        _persist_failure_safely(delivered, path)
        results.append(delivered)
    return results


deliver_report = send_report_to_telegram
