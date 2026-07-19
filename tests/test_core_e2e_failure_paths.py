# -*- coding: utf-8 -*-
"""核心鏈路的參數化負向契約：錯誤回應、例外與失敗後狀態。"""
import json
import subprocess
import threading
from pathlib import Path

import pytest

import api.continuous_optimizer as optimizer
import api.server as server
import lib.api as minimax_api
from test_api_server import get_json, run_handler


def _json_response(method, path, *, body=b"", headers=None):
    status, _, raw = run_handler(method, path, body=body, headers=headers)
    return status, json.loads(raw.decode("utf-8"))


@pytest.mark.parametrize(
    ("body", "expected_error", "decode_error"),
    [
        (b"", "請求內容為空", None),
        (b"{not json", "JSON 解析失敗:", json.JSONDecodeError),
        (b"\xff", "JSON 解析失敗:", UnicodeDecodeError),
        (
            b'{"source": "e2e"}',
            "缺少必要欄位: prompt_hash, scores",
            None,
        ),
    ],
    ids=["empty", "json", "utf8", "missing-fields"],
)
def test_feedback_rejections_return_400_without_creating_feedback(
    tmp_path, monkeypatch, body, expected_error, decode_error
):
    feedback_path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(server, "FEEDBACK_PATH", str(feedback_path))

    if decode_error:
        with pytest.raises(decode_error):
            json.loads(body.decode("utf-8"))

    status, payload = _json_response(
        "POST", "/api/feedback", body=body, headers={"Content-Length": str(len(body))}
    )

    assert status == 400
    assert payload["error"].startswith(expected_error)
    assert not feedback_path.exists()


@pytest.mark.parametrize(
    "error",
    [OSError("磁碟已滿"), PermissionError("拒絕存取")],
    ids=["os-error", "permission-error"],
)
def test_feedback_write_failures_propagate_without_persisting(
    tmp_path, monkeypatch, error
):
    feedback_path = tmp_path / "feedback.jsonl"
    calls = []
    monkeypatch.setattr(server, "FEEDBACK_PATH", str(feedback_path))

    def fail_append(path, row):
        calls.append((path, row))
        raise error

    monkeypatch.setattr(server, "append_jsonl", fail_append)
    body = json.dumps(
        {"source": "e2e", "prompt_hash": "hash", "scores": {"structure": 1}},
        ensure_ascii=False,
    ).encode("utf-8")

    with pytest.raises(type(error)) as excinfo:
        run_handler(
            "POST", "/api/feedback", body=body,
            headers={"Content-Length": str(len(body))},
        )

    assert type(excinfo.value) is type(error)
    assert str(excinfo.value) == str(error)
    assert len(calls) == 1
    assert not feedback_path.exists()


@pytest.mark.parametrize(
    ("failed_file", "error"),
    [
        ("optimization_log.jsonl", OSError("log 無法讀取")),
        ("feedback.jsonl", json.JSONDecodeError("資料毀損", "{", 0)),
    ],
    ids=["optimization-log", "feedback-log"],
)
def test_optimizer_status_read_failures_propagate_without_mutating_logs(
    tmp_path, monkeypatch, failed_file, error
):
    optimization_log = tmp_path / "optimization_log.jsonl"
    feedback_log = tmp_path / "feedback.jsonl"
    optimization_log.write_text('{"event": "optimization"}\n', encoding="utf-8")
    feedback_log.write_text('{"source": "e2e"}\n', encoding="utf-8")
    before = {
        optimization_log: optimization_log.read_bytes(),
        feedback_log: feedback_log.read_bytes(),
    }
    monkeypatch.setattr(server, "PROJECT_ROOT", str(tmp_path))

    def fail_read(path, limit=None):
        if Path(path).name == failed_file:
            raise error
        return []

    monkeypatch.setattr(server, "read_jsonl", fail_read)

    with pytest.raises(type(error)) as excinfo:
        get_json("/api/optimizer/status")

    assert type(excinfo.value) is type(error)
    assert str(excinfo.value) == str(error)
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize(
    ("dependency", "error"),
    [
        ("summary", ValueError("摘要資料無效")),
        ("hints", RuntimeError("建議產生失敗")),
    ],
)
def test_optimizer_analysis_exceptions_propagate_without_analysis_log(
    tmp_path, monkeypatch, dependency, error
):
    log_path = tmp_path / "optimization_log.jsonl"
    monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))

    def fail():
        raise error

    if dependency == "summary":
        monkeypatch.setattr(optimizer, "get_feedback_summary", fail)
    else:
        monkeypatch.setattr(optimizer, "get_feedback_summary", lambda: {})
        monkeypatch.setattr(optimizer, "generate_optimization_hints", fail)

    with pytest.raises(type(error)) as excinfo:
        optimizer.analyze_and_suggest()

    assert type(excinfo.value) is type(error)
    assert str(excinfo.value) == str(error)
    assert not log_path.exists()


@pytest.mark.parametrize(
    ("path", "module_key", "error"),
    [
        ("/api/feedback/summary", "summary", ValueError("摘要資料毀損")),
        ("/api/feedback/weak-areas", "weak_areas", RuntimeError("弱點分析失敗")),
        ("/api/feedback/hints", "hints", OSError("建議資料無法讀取")),
    ],
    ids=["summary", "weak-areas", "hints"],
)
def test_feedback_analysis_errors_return_500_without_persisting(
    tmp_path, monkeypatch, path, module_key, error
):
    feedback_path = tmp_path / "feedback.jsonl"
    raised = []
    monkeypatch.setattr(server, "FEEDBACK_PATH", str(feedback_path))

    def fail():
        raised.append(error)
        raise error

    monkeypatch.setattr(server, "_feedback_module", {module_key: fail})

    status, _, payload = get_json(path)

    assert status == 500
    assert payload == {"error": f"分析失敗: {error}"}
    assert type(raised[0]) is type(error)
    assert not feedback_path.exists()


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired(["python", "run_opt.py"], timeout=1),
        FileNotFoundError("找不到 run_opt.py"),
        OSError("無法建立子程序"),
    ],
    ids=["timeout", "missing-executable", "os-error"],
)
def test_optimizer_start_failures_log_error_without_success_state(
    tmp_path, monkeypatch, error
):
    log_path = tmp_path / "optimization_log.jsonl"
    monkeypatch.setattr(optimizer, "OPTIMIZATION_LOG", str(log_path))
    monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(server, "PROJECT_ROOT", str(tmp_path))

    def fail_run(*args, **kwargs):
        raise error

    monkeypatch.setattr(optimizer.subprocess, "run", fail_run)

    assert optimizer.run_optimization_round("structure") is False

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert records[-1]["event"] == "optimization_error"
    assert records[-1]["error"] == str(error)
    assert not any(record["event"] == "optimization" for record in records)

    status, _, payload = get_json("/api/optimizer/status")
    assert status == 200
    assert payload["status"] == "idle"
    assert payload["last_optimization"] is None


@pytest.fixture
def minimax_runtime(monkeypatch):
    def fake_get(section, key=None, default=None):
        values = {
            "url": "https://api.example.test/v1/chat",
            "model": "test-model",
            "timeout": 1,
            "retry": 1,
            "rate_limit": {"max_concurrent": 1, "min_interval_ms": 0},
        }
        return values.get(key, default) if section == "api" else default

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(minimax_api, "get", fake_get)
    monkeypatch.setattr(minimax_api, "_rate_wait", lambda: None)
    monkeypatch.setattr(minimax_api, "_semaphore", threading.Semaphore(1))


class _TrackingResponse:
    def __init__(self, body):
        self.body = body
        self.exit_types = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_types.append(exc_type)
        return False

    def read(self):
        return self.body


@pytest.mark.parametrize(
    ("body", "cause_type", "message"),
    [
        (b"not json", json.JSONDecodeError, "JSONDecodeError"),
        (b'{"result": "missing choices"}', KeyError, "KeyError"),
        (b'{"choices": []}', IndexError, "IndexError"),
    ],
    ids=["invalid-json", "missing-choices", "empty-choices"],
)
def test_minimax_parse_errors_release_response_and_semaphore(
    monkeypatch, minimax_runtime, body, cause_type, message
):
    response = _TrackingResponse(body)
    monkeypatch.setattr(minimax_api.urllib.request, "urlopen", lambda *args, **kwargs: response)

    with pytest.raises(minimax_api.APIError, match=message) as excinfo:
        minimax_api.call_minimax("system", "user")

    assert type(excinfo.value.__cause__) is cause_type
    assert response.exit_types == [cause_type]
    assert minimax_api._semaphore.acquire(blocking=False) is True
    minimax_api._semaphore.release()


@pytest.mark.parametrize(
    ("expected_key", "invalid_value"),
    [("average_score", -1), ("total_questions", -1)],
)
def test_core_e2e_spec_failure_returns_exit_one_and_restores_cwd(
    monkeypatch, capsys, expected_key, invalid_value
):
    import scripts.run_core_flow_e2e as e2e

    original_cwd = Path.cwd()
    monkeypatch.setitem(e2e.EXPECTED, expected_key, invalid_value)

    assert e2e.main(["--quiet"]) == 1

    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["spec_ok"] is False
    assert summary["spec_failures"] == [expected_key]
    assert summary["exit_code"] == 1
    assert Path.cwd() == original_cwd
