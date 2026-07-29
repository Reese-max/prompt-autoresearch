# -*- coding: utf-8 -*-
"""
auto_evolve.py 的 no_improve 控制流單元測試。

覆蓋需求：
- 達門檻後必須有限次調整變異方向重試
- 或寫入含 baseline 比較與證據位置的 converged_at_baseline 結論
- 為兩條出口路徑加入單元測試
- 禁止無窮迴圈、直接 return 或無日誌退出
"""
import hashlib
import json
import sys
import types
from types import SimpleNamespace

import pytest

import auto_evolve


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASELINE_PROMPT = "你是一位專精臺灣國家考試的專家。"


def _write_baseline(tmp_path):
    """寫入 baseline.md 並回傳其 sha256。"""
    p = tmp_path / "prompts" / "baseline.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(BASELINE_PROMPT, encoding="utf-8")
    return hashlib.sha256(BASELINE_PROMPT.encode("utf-8")).hexdigest()


def _write_baseline_meta(tmp_path, dev_avg=50.0):
    """寫入 baseline.meta.json。"""
    p = tmp_path / "prompts" / "baseline.meta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    meta = {"dev_avg": dev_avg}
    p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def _install_fake_run_opt(monkeypatch, always_success=False):
    """注入假的 run_opt 模組到 sys.modules，回傳呼叫記錄 list。"""
    calls = []

    def fake_run_opt_pass(**kwargs):
        calls.append(kwargs)
        return always_success

    fake_mod = types.ModuleType("run_opt")
    fake_mod.run_opt_pass = fake_run_opt_pass  # type: ignore[attr-defined]
    fake_mod.load_file = lambda path: ""  # type: ignore[attr-defined]
    fake_mod.load_json = lambda path: {}  # type: ignore[attr-defined]
    fake_mod.parse_parallel_args = lambda args: {  # type: ignore[attr-defined]
        "smoke_parallel": 24,
        "dev_parallel": 24,
        "holdout_parallel": 24,
    }
    monkeypatch.setitem(sys.modules, "run_opt", fake_mod)
    return calls


def _read_log(tmp_path):
    """讀取 evolution_log.jsonl 回傳 list of dict。"""
    log_path = tmp_path / "evolution_log.jsonl"
    if not log_path.exists():
        return []
    rows = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _baseline_hash(tmp_path):
    """計算當前 baseline.md 的 sha256。"""
    return hashlib.sha256(
        (tmp_path / "prompts" / "baseline.md").read_bytes()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Tests — retry → convergence
# ---------------------------------------------------------------------------

class TestNoImproveRetryThenConvergence:
    """連續 no-improve 觸發 retry → convergence 結論。"""

    def test_retry_entered_and_converged(self, tmp_path, monkeypatch):
        """驗證：no_improve_limit 代後進入 retry，retry 耗盡後寫入 convergence 結論。"""
        monkeypatch.chdir(tmp_path)
        original_hash = _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 2)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 2)

        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "15"])  # 足夠的世代數觸發 retry

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)
        events = [r.get("event") for r in log]

        assert "start" in events
        assert "stop" in events

        retry_events = [r for r in log if r.get("event") == "retry_mode_entered"]
        assert len(retry_events) >= 1, f"預期 >=1 retry_mode_entered，實際 {len(retry_events)}"

        conv_events = [r for r in log if r.get("event") == "converged_to_baseline"]
        assert len(conv_events) == 1, f"預期 1 converged_to_baseline，實際 {len(conv_events)}"
        assert conv_events[0]["conclusion"] == "已收斂於 baseline，重試仍無改善"

        stop = [r for r in log if r.get("event") == "stop"][-1]
        assert "重試" in stop["reason"]

        # baseline.md 雜湊不變
        assert _baseline_hash(tmp_path) == original_hash

    def test_retry_adjust_events_recorded(self, tmp_path, monkeypatch):
        """驗證：每次 retry 調整都有 retry_adjust 事件。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 2)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 3)

        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "20"])  # 足夠的世代數觸發多次 retry

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)

        # 第一次進入 retry → retry_mode_entered
        # 後續 retry → retry_adjust（2 次，因為 RETRY_AFTER_NO_IMPROVE=3 需要 3 輪 retry 才停）
        adjust_events = [r for r in log if r.get("event") == "retry_adjust"]
        assert len(adjust_events) >= 1, f"預期 >=1 retry_adjust，實際 {len(adjust_events)}"

        for adj in adjust_events:
            assert "retry_count" in adj
            assert "generation" in adj


# ---------------------------------------------------------------------------
# Tests — no retry mode
# ---------------------------------------------------------------------------

class TestNoImproveNoRetry:
    """RETRY_AFTER_NO_IMPROVE=0 時，直接因 no-improve 停止。"""

    def test_stops_without_retry(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        original_hash = _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 3)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)

        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "10"])

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)

        retry_events = [r for r in log if r.get("event") == "retry_mode_entered"]
        assert len(retry_events) == 0

        conv_events = [r for r in log if r.get("event") == "converged_to_baseline"]
        assert len(conv_events) == 0

        stop = [r for r in log if r.get("event") == "stop"][-1]
        assert "未晉升" in stop["reason"]
        assert "重試" not in stop["reason"]

        assert _baseline_hash(tmp_path) == original_hash


# ---------------------------------------------------------------------------
# Tests — generation event recording
# ---------------------------------------------------------------------------

class TestGenerationEventRecording:
    """每代 generation_complete 事件記錄 baseline 比較。"""

    def test_generation_events_contain_no_improve_fields(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 6)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)

        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "5"])

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)
        gen_events = [r for r in log if r.get("event") == "generation_complete"]

        assert len(gen_events) == 5
        for i, evt in enumerate(gen_events):
            assert evt["generation"] == i + 1
            assert "no_improve_count" in evt
            assert "success" in evt
            assert "promoted" in evt
            assert "before_baseline_dev" in evt
            assert "after_baseline_dev" in evt
            assert evt["promoted"] is False

    def test_no_improve_count_increments(self, tmp_path, monkeypatch):
        """no_improve_count 每代遞增（無晉升時）。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 10)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)

        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "4"])

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)
        gen_events = [r for r in log if r.get("event") == "generation_complete"]

        counts = [r["no_improve_count"] for r in gen_events]
        assert counts == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Tests — finite step completion
# ---------------------------------------------------------------------------

class TestFiniteStepCompletion:
    """演化在有限步數內結束。"""

    def test_terminates_within_max_generations(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 2)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 1)

        max_generations = 6
        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", str(max_generations)])

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)
        gen_events = [r for r in log if r.get("event") == "generation_complete"]

        assert len(gen_events) <= max_generations
        assert len(gen_events) >= 1
        assert any(r.get("event") == "stop" for r in log)

    def test_convergence_report_has_environment(self, tmp_path, monkeypatch):
        """convergence 結論包含環境資訊。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 2)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 2)

        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "10"])

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)
        conv = [r for r in log if r.get("event") == "converged_to_baseline"]
        assert len(conv) == 1
        c = conv[0]
        assert "timestamp" in c
        assert "generation" in c
        assert "reason" in c
        assert "successful_evolutions" in c
        assert "best_score" in c
        assert "conclusion" in c
        assert "environment" in c
        assert "python" in c["environment"]
        assert "platform" in c["environment"]
        assert "arch" in c["environment"]

    def test_stop_event_records_totals(self, tmp_path, monkeypatch):
        """stop 事件記錄累計統計。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, dev_avg=50.0)
        monkeypatch.setattr(
            auto_evolve.subprocess, "run", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        # Mock platform.platform() to avoid subprocess calls
        monkeypatch.setattr(auto_evolve.platform, "platform", lambda: "test-platform")
        monkeypatch.setattr(auto_evolve.platform, "machine", lambda: "test-arch")
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)

        # 修改 auto_evolve 的常數以加速測試
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 2)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 2)

        # 修改 sys.argv 來傳遞世代數
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "8"])

        rc = auto_evolve.main()

        assert rc == 0
        log = _read_log(tmp_path)
        stop = [r for r in log if r.get("event") == "stop"][-1]

        assert "successful_evolutions" in stop
        assert "best_score" in stop
        assert "elapsed_seconds" in stop
        assert "retry_mode" in stop
        assert "retry_count" in stop
        assert stop["successful_evolutions"] == 0
