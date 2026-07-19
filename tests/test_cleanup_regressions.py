# -*- coding: utf-8 -*-
"""中途失敗後的資源清理回歸測試。"""
import os
import sys
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

import api.server as server
import lib.api as minimax_api


def test_server_interrupt_closes_created_server(monkeypatch):
    fake_server = Mock()
    fake_server.serve_forever.side_effect = KeyboardInterrupt
    monkeypatch.setattr(server, "HTTPServer", lambda *_args: fake_server)
    monkeypatch.setattr(sys, "argv", ["server.py"])

    server.main()

    assert fake_server.server_close.call_count == 1


def test_server_cleanup_failure_is_not_swallowed(monkeypatch):
    cleanup_failure = OSError("伺服器關閉失敗")
    fake_server = Mock()
    fake_server.serve_forever.side_effect = KeyboardInterrupt
    fake_server.server_close.side_effect = cleanup_failure
    monkeypatch.setattr(server, "HTTPServer", lambda *_args: fake_server)
    monkeypatch.setattr(sys, "argv", ["server.py"])

    with pytest.raises(OSError, match="伺服器關閉失敗") as excinfo:
        server.main()

    assert excinfo.value is cleanup_failure
    assert isinstance(excinfo.value.__context__, KeyboardInterrupt)


def test_core_e2e_failure_deletes_temporary_workspace(monkeypatch):
    import scripts.run_core_flow_e2e as e2e

    original_cwd = Path.cwd()
    workspace = None
    partial_file = None

    def fail_midway(path):
        nonlocal workspace, partial_file
        workspace = path
        partial_file = path / "partial.tmp"
        partial_file.write_text("partial", encoding="utf-8")
        raise RuntimeError("核心流程中途失敗")

    monkeypatch.setattr(e2e, "_run_core_evaluation", fail_midway)

    with pytest.raises(RuntimeError, match="核心流程中途失敗"):
        e2e.run_e2e()

    assert Path.cwd() == original_cwd
    assert workspace is not None
    assert partial_file is not None
    assert not partial_file.exists()
    assert not workspace.exists()


def test_rate_wait_failure_releases_lock(monkeypatch):
    lock = threading.Lock()
    monkeypatch.setattr(minimax_api, "_rate_lock", lock)
    monkeypatch.setattr(
        minimax_api,
        "get",
        lambda *_args, **_kwargs: {"min_interval_ms": 0},
    )
    monkeypatch.setattr(
        minimax_api.time,
        "time",
        Mock(side_effect=RuntimeError("時鐘讀取失敗")),
    )

    with pytest.raises(RuntimeError, match="時鐘讀取失敗"):
        minimax_api._rate_wait()

    assert lock.acquire(blocking=False) is True
    lock.release()


def test_archive_cleanup_failure_is_not_swallowed(tmp_path, monkeypatch):
    import run_opt

    oldest = tmp_path / "baseline_001.md"
    newest = tmp_path / "baseline_002.md"
    oldest.write_text("old", encoding="utf-8")
    newest.write_text("new", encoding="utf-8")
    failure = PermissionError("無法刪除舊封存檔")
    real_remove = os.remove

    def fail_oldest(path):
        if Path(path) == oldest:
            raise failure
        real_remove(path)

    monkeypatch.setattr(run_opt, "ARCHIVE_DIR", str(tmp_path))
    monkeypatch.setattr(
        run_opt,
        "get",
        lambda section, key, default=None: 1
        if (section, key) == ("archive", "max_versions")
        else default,
    )
    monkeypatch.setattr(run_opt.os, "remove", fail_oldest)

    with pytest.raises(PermissionError, match="無法刪除舊封存檔") as excinfo:
        run_opt._cleanup_old_archives()

    assert excinfo.value is failure
    assert oldest.exists()
    assert newest.exists()
