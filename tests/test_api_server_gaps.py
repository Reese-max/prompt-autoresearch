# -*- coding: utf-8 -*-
"""api/server.py 覆蓋補洞測試（補 test_api_server.py 未覆蓋的分支）。

1. _get_feedback_module 的 ImportError 降級分支
2. /api/feedback/weak-areas 分析拋例外 → 500
3. main()：argparse、HTTPServer 建構、KeyboardInterrupt 收尾
   （HTTPServer 換成 fake class，不開真實 socket）
"""
import sys

import pytest

import api.server as server

from test_api_server import get_json


# --- _get_feedback_module ImportError 降級 ---

def test_feedback_module_import_error_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(server, "_feedback_module", None)
    # sys.modules 中的 None 會讓 from api.feedback import ... 拋 ImportError
    monkeypatch.setitem(sys.modules, "api.feedback", None)

    assert server._get_feedback_module() == {}

    # 端點走降級回應而非 500
    status, _, data = get_json("/api/feedback/summary")
    assert status == 200
    assert data == {"message": "回饋分析模組不可用", "total_feedback": 0}


# --- /api/feedback/weak-areas 分析例外 → 500 ---

def test_feedback_weak_areas_analysis_error_returns_500(monkeypatch):
    def boom():
        raise ValueError("資料毀損")

    monkeypatch.setattr(server, "_feedback_module", {"weak_areas": boom})
    status, _, data = get_json("/api/feedback/weak-areas")
    assert status == 500
    assert data == {"error": "分析失敗: 資料毀損"}


# --- main() ---

class FakeHTTPServer:
    instances = []

    def __init__(self, addr, handler_cls):
        self.addr = addr
        self.handler_cls = handler_cls
        self.closed = False
        FakeHTTPServer.instances.append(self)

    def serve_forever(self):
        raise KeyboardInterrupt

    def server_close(self):
        self.closed = True


@pytest.fixture
def fake_server(monkeypatch):
    FakeHTTPServer.instances = []
    monkeypatch.setattr(server, "HTTPServer", FakeHTTPServer)
    return FakeHTTPServer


def test_main_default_args(fake_server, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["server.py"])

    server.main()

    assert len(fake_server.instances) == 1
    inst = fake_server.instances[0]
    assert inst.addr == ("127.0.0.1", 5001)
    assert inst.handler_cls is server.PromptAPIHandler
    assert inst.closed is True  # KeyboardInterrupt → server_close

    out = capsys.readouterr().out
    assert "http://127.0.0.1:5001" in out
    assert "GET  /api/health" in out
    assert "伺服器已停止" in out


def test_main_custom_host_port(fake_server, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["server.py", "--host", "0.0.0.0", "--port", "8080"]
    )

    server.main()

    inst = fake_server.instances[0]
    assert inst.addr == ("0.0.0.0", 8080)
    assert "http://0.0.0.0:8080" in capsys.readouterr().out
