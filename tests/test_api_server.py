# -*- coding: utf-8 -*-
"""api/server.py 契約測試。

不開真實 socket：直接建構 PromptAPIHandler，以 BytesIO 模擬 rfile/wfile，
解析 wfile 原始輸出斷言狀態碼、headers 與 JSON payload。
所有檔案 I/O 透過 monkeypatch 模組內的 load_file/load_json/append_jsonl/read_jsonl
與路徑常數（指向 tmp_path）隔離；回饋分析模組以覆寫 _feedback_module 控制分支。
（server.py 無認證機制，權限面僅有 CORS preflight，於 OPTIONS 測試覆蓋。）
"""
import hashlib
import io
import json
from email.message import Message

import pytest

import api.server as server


# --- 測試 harness ---

def run_handler(method, path, body=b"", headers=None):
    """不經 socket 直接執行 handler，回傳 (status, headers, raw_body)。"""
    handler = server.PromptAPIHandler.__new__(server.PromptAPIHandler)
    handler.command = method
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"{method} {path} HTTP/1.1"
    handler.client_address = ("127.0.0.1", 0)
    msg = Message()
    for key, value in (headers or {}).items():
        msg[key] = value
    handler.headers = msg
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()

    getattr(handler, f"do_{method}")()

    raw = handler.wfile.getvalue()
    head, _, payload = raw.partition(b"\r\n\r\n")
    lines = head.decode("utf-8", errors="replace").split("\r\n")
    status = int(lines[0].split()[1])
    resp_headers = {}
    for line in lines[1:]:
        key, _, value = line.partition(":")
        resp_headers[key.strip().lower()] = value.strip()
    return status, resp_headers, payload


def get_json(path, headers=None):
    status, resp_headers, payload = run_handler("GET", path, headers=headers)
    return status, resp_headers, json.loads(payload.decode("utf-8"))


def post_json(path, data, content_length=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if not isinstance(data, bytes) else data
    length = content_length if content_length is not None else len(body)
    status, resp_headers, payload = run_handler(
        "POST", path, body=body, headers={"Content-Length": str(length)}
    )
    return status, resp_headers, json.loads(payload.decode("utf-8"))


# --- GET /api/current-prompt ---

def test_current_prompt_success(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "優化後提示詞")
    status, _, data = get_json("/api/current-prompt")
    assert status == 200
    assert data["prompt"] == "優化後提示詞"
    assert data["hash"] == hashlib.sha256("優化後提示詞".encode("utf-8")).hexdigest()
    assert data["length"] == len("優化後提示詞")
    assert data["source"] == "current.md"


def test_current_prompt_missing_returns_404(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "")
    status, _, data = get_json("/api/current-prompt")
    assert status == 404
    assert data == {"error": "提示詞檔案不存在"}


# --- GET /api/prompt-meta ---

def test_prompt_meta_success(monkeypatch):
    meta = {"type": "baseline", "dev_avg": 87.5}
    monkeypatch.setattr(server, "load_json", lambda path, default=None: meta)
    status, _, data = get_json("/api/prompt-meta")
    assert status == 200
    assert data == meta


def test_prompt_meta_missing_returns_404(monkeypatch):
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {})
    status, _, data = get_json("/api/prompt-meta")
    assert status == 404
    assert data == {"error": "metadata 檔案不存在"}


# --- GET /api/baseline ---

def test_baseline_success(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "baseline 內容")
    status, _, data = get_json("/api/baseline")
    assert status == 200
    assert data["prompt"] == "baseline 內容"
    assert data["source"] == "baseline.md"
    assert data["hash"] == hashlib.sha256("baseline 內容".encode("utf-8")).hexdigest()


def test_baseline_missing_returns_404(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "")
    status, _, data = get_json("/api/baseline")
    assert status == 404
    assert data == {"error": "baseline 檔案不存在"}


# --- GET /api/route ---

def test_route_success(monkeypatch):
    route = {"申論": "essay", "測驗": "quiz"}
    monkeypatch.setattr(server, "load_json", lambda path, default=None: route)
    status, _, data = get_json("/api/route")
    assert status == 200
    assert data == route


def test_route_missing_returns_404(monkeypatch):
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {})
    status, _, data = get_json("/api/route")
    assert status == 404
    assert data == {"error": "路由配置不存在"}


# --- GET /api/champions 與 /api/champion/<type> ---

@pytest.fixture
def champions_dir(tmp_path, monkeypatch):
    d = tmp_path / "champions"
    d.mkdir()
    (d / "essay.md").write_text("essay champion prompt", encoding="utf-8")
    (d / "essay.meta.json").write_text(
        json.dumps({"type": "申論", "score": 90}, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(server, "CHAMPIONS_DIR", str(d))
    return d


def test_list_champions_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "CHAMPIONS_DIR", str(tmp_path / "nonexistent"))
    status, _, data = get_json("/api/champions")
    assert status == 200
    assert data == {"champions": []}


def test_list_champions_success(champions_dir):
    status, _, data = get_json("/api/champions")
    assert status == 200
    assert len(data["champions"]) == 1
    champ = data["champions"][0]
    assert champ["type_slug"] == "essay"
    assert champ["type_name"] == "申論"
    assert champ["length"] == len("essay champion prompt")
    assert champ["meta"] == {"type": "申論", "score": 90}


def test_get_champion_by_slug(champions_dir):
    status, _, data = get_json("/api/champion/essay")
    assert status == 200
    assert data["prompt"] == "essay champion prompt"
    assert data["type_slug"] == "essay"
    assert data["meta"]["type"] == "申論"
    assert data["hash"] == hashlib.sha256(
        "essay champion prompt".encode("utf-8")
    ).hexdigest()


def test_get_champion_by_chinese_type_name(champions_dir):
    status, _, data = get_json("/api/champion/申論")
    assert status == 200
    assert data["prompt"] == "essay champion prompt"
    assert data["type_slug"] == "申論"


def test_get_champion_not_found(champions_dir):
    status, _, data = get_json("/api/champion/nonexistent")
    assert status == 404
    assert data == {"error": "找不到題型 'nonexistent' 的 champion prompt"}


# --- POST /api/feedback ---

@pytest.fixture
def feedback_recorder(monkeypatch):
    records = []
    monkeypatch.setattr(
        server, "append_jsonl", lambda path, row: records.append((path, row))
    )
    return records


def test_post_feedback_success(feedback_recorder):
    payload = {
        "source": "shenlun",
        "prompt_hash": "abc123",
        "scores": {"結構": 8, "論證": 7},
        "total_score": 15,
        "question_id": "q-01",
    }
    status, _, data = post_json("/api/feedback", payload)
    assert status == 200
    assert data["status"] == "accepted"
    assert "feedback_id" in data

    assert len(feedback_recorder) == 1
    path, row = feedback_recorder[0]
    assert path == server.FEEDBACK_PATH
    assert row["source"] == "shenlun"
    assert row["prompt_hash"] == "abc123"
    assert row["scores"] == {"結構": 8, "論證": 7}
    assert row["total_score"] == 15
    assert row["question_id"] == "q-01"
    assert row["metadata"] == {}
    assert data["feedback_id"] == row["timestamp"]


def test_post_feedback_empty_body_returns_400(feedback_recorder):
    status, _, data = post_json("/api/feedback", b"", content_length=0)
    assert status == 400
    assert data == {"error": "請求內容為空"}
    assert feedback_recorder == []


def test_post_feedback_invalid_json_returns_400(feedback_recorder):
    status, _, data = post_json("/api/feedback", b"{not json")
    assert status == 400
    assert data["error"].startswith("JSON 解析失敗")
    assert feedback_recorder == []


def test_post_feedback_missing_fields_returns_400(feedback_recorder):
    status, _, data = post_json("/api/feedback", {"source": "shenlun"})
    assert status == 400
    assert data["error"] == "缺少必要欄位: prompt_hash, scores"
    assert feedback_recorder == []


# --- GET /api/feedback/* 分析端點 ---

def test_feedback_summary_module_unavailable(monkeypatch):
    monkeypatch.setattr(server, "_feedback_module", {})
    status, _, data = get_json("/api/feedback/summary")
    assert status == 200
    assert data == {"message": "回饋分析模組不可用", "total_feedback": 0}


def test_feedback_summary_success(monkeypatch):
    summary = {"total_feedback": 3, "avg_score": 12.5}
    monkeypatch.setattr(server, "_feedback_module", {"summary": lambda: summary})
    status, _, data = get_json("/api/feedback/summary")
    assert status == 200
    assert data == summary


def test_feedback_summary_analysis_error_returns_500(monkeypatch):
    def boom():
        raise ValueError("壞資料")

    monkeypatch.setattr(server, "_feedback_module", {"summary": boom})
    status, _, data = get_json("/api/feedback/summary")
    assert status == 500
    assert data == {"error": "分析失敗: 壞資料"}


def test_feedback_weak_areas_module_unavailable(monkeypatch):
    monkeypatch.setattr(server, "_feedback_module", {})
    status, _, data = get_json("/api/feedback/weak-areas")
    assert status == 200
    assert data == {"weak_dimensions": [], "weak_types": []}


def test_feedback_weak_areas_success(monkeypatch):
    weak = {"weak_dimensions": ["論證"], "weak_types": ["申論"]}
    monkeypatch.setattr(server, "_feedback_module", {"weak_areas": lambda: weak})
    status, _, data = get_json("/api/feedback/weak-areas")
    assert status == 200
    assert data == weak


def test_feedback_hints_module_unavailable(monkeypatch):
    monkeypatch.setattr(server, "_feedback_module", {})
    status, _, data = get_json("/api/feedback/hints")
    assert status == 200
    assert data == {"hints": []}


def test_feedback_hints_success(monkeypatch):
    monkeypatch.setattr(
        server, "_feedback_module", {"hints": lambda: ["加強論證結構"]}
    )
    status, _, data = get_json("/api/feedback/hints")
    assert status == 200
    assert data == {"hints": ["加強論證結構"]}


def test_feedback_hints_analysis_error_returns_500(monkeypatch):
    def boom():
        raise RuntimeError("模組壞掉")

    monkeypatch.setattr(server, "_feedback_module", {"hints": boom})
    status, _, data = get_json("/api/feedback/hints")
    assert status == 500
    assert data == {"error": "分析失敗: 模組壞掉"}


# --- GET /api/optimizer/status ---

def test_optimizer_status_no_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROJECT_ROOT", str(tmp_path))
    status, _, data = get_json("/api/optimizer/status")
    assert status == 200
    assert data == {
        "feedback_count": 0,
        "recent_logs": [],
        "last_optimization": None,
        "status": "idle",
    }


def test_optimizer_status_with_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROJECT_ROOT", str(tmp_path))
    (tmp_path / "optimization_log.jsonl").write_text("x\n", encoding="utf-8")
    (tmp_path / "feedback.jsonl").write_text("x\n", encoding="utf-8")
    logs = [
        {"event": "optimization", "round": 1},
        {"event": "eval", "round": 2},
    ]

    def fake_read_jsonl(path, limit=None):
        if path.endswith("optimization_log.jsonl"):
            return logs
        return [{"source": "shenlun"}, {"source": "shenlun"}]

    monkeypatch.setattr(server, "read_jsonl", fake_read_jsonl)
    status, _, data = get_json("/api/optimizer/status")
    assert status == 200
    assert data["feedback_count"] == 2
    assert data["recent_logs"] == logs
    assert data["last_optimization"] == {"event": "optimization", "round": 1}
    assert data["status"] == "active"


# --- GET /api/health ---

def test_health_check(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "prompt 內容")
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {"dev_avg": 88.0})
    status, _, data = get_json("/api/health")
    assert status == 200
    assert data["status"] == "healthy"
    assert data["prompt_available"] is True
    assert data["meta_available"] is True
    assert data["prompt_length"] == len("prompt 內容")
    assert data["baseline_score"] == 88.0


def test_health_check_degraded(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "")
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {})
    status, _, data = get_json("/api/health")
    assert status == 200
    assert data["prompt_available"] is False
    assert data["meta_available"] is False
    assert data["prompt_length"] == 0
    assert data["baseline_score"] is None


# --- 未知端點與 CORS ---

def test_get_unknown_path_returns_404():
    status, _, data = get_json("/api/nope")
    assert status == 404
    assert data == {"error": "未知端點: /api/nope"}


def test_post_unknown_path_returns_404():
    status, _, data = post_json("/api/nope", {"a": 1})
    assert status == 404
    assert data == {"error": "未知端點: /api/nope"}


def test_trailing_slash_is_normalized(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "p")
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {})
    status, _, data = get_json("/api/health/")
    assert status == 200
    assert data["status"] == "healthy"


def test_options_preflight_cors_headers():
    status, headers, _ = run_handler(
        "OPTIONS", "/api/feedback", headers={"Origin": "http://example.com"}
    )
    assert status == 200
    assert headers["access-control-allow-origin"] == "http://example.com"
    assert headers["access-control-allow-methods"] == "GET, POST, OPTIONS"
    assert "content-type" in headers["access-control-allow-headers"].lower()


def test_json_response_includes_cors_and_content_type(monkeypatch):
    monkeypatch.setattr(server, "load_file", lambda path, default="": "p")
    monkeypatch.setattr(server, "load_json", lambda path, default=None: {})
    status, headers, _ = run_handler("GET", "/api/health")
    assert status == 200
    assert headers["content-type"] == "application/json; charset=utf-8"
    assert headers["access-control-allow-origin"] == "*"
    assert int(headers["content-length"]) > 0
