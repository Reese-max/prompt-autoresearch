# -*- coding: utf-8 -*-
"""
manual-goal-evolve-reignite.py — 手動驗證 infinite_evolve 演化流程的日誌、
評分記錄、archive/champion 產物、no-improve 出口、baseline 雜湊
及重現性證據是否完整寫入與正確。

可直接執行：
    python tests/manual-goal-evolve-reignite.py

或以 pytest 執行：
    python -m pytest -q tests/manual-goal-evolve-reignite.py
"""
import hashlib
import json
import os
import sys
import types
from types import SimpleNamespace

import pytest

import infinite_evolve

BASELINE_PROMPT = "你是一位專精臺灣國家考試的專家。"


def _write_baseline(tmp_path):
    p = tmp_path / "prompts" / "baseline.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(BASELINE_PROMPT, encoding="utf-8")
    return hashlib.sha256(BASELINE_PROMPT.encode("utf-8")).hexdigest()


def _install_fake_run_opt(monkeypatch, always_success=False):
    calls = []

    def fake_run_opt_pass(
        smoke_parallel=None,
        dev_parallel=None,
        holdout_parallel=None,
        force_direction=None,
        avoid_failures=None,
    ):
        calls.append({
            "smoke_parallel": smoke_parallel,
            "dev_parallel": dev_parallel,
            "holdout_parallel": holdout_parallel,
            "force_direction": force_direction,
            "avoid_failures": avoid_failures,
        })
        return always_success

    fake_mod = types.ModuleType("run_opt")
    fake_mod.run_opt_pass = fake_run_opt_pass
    monkeypatch.setitem(sys.modules, "run_opt", fake_mod)
    return calls


def _read_log(tmp_path):
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


def _read_metrics(tmp_path_or_root):
    import lib.io as io
    path = os.path.join(str(tmp_path_or_root), "metrics.jsonl")
    return io.read_jsonl(path)


def _baseline_hash(tmp_path):
    return hashlib.sha256(
        (tmp_path / "prompts" / "baseline.md").read_bytes()
    ).hexdigest()


def _common_argv(**overrides):
    defaults = {
        "max_rounds": 10,
        "no_improve_limit": 3,
        "retry_after_no_improve": 0,
        "sleep_seconds": 0,
        "route_every": 0,
        "round_timeout_seconds": 60,
    }
    defaults.update(overrides)
    argv = []
    for k, v in defaults.items():
        flag = "--" + k.replace("_", "-")
        argv.extend([flag, str(v)])
    return argv


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGoalEvolveReignite:

    def test_log_entry_count_and_fields(self, tmp_path, monkeypatch):
        """驗證日誌筆數與欄位完整性。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=6,
            no_improve_limit=2,
            retry_after_no_improve=0,
        ))
        assert rc == 0

        log = _read_log(tmp_path)
        assert len(log) >= 3, f"預期至少 3 筆日誌，實際 {len(log)}"

        events = [r.get("event") for r in log]
        assert "start" in events
        assert "stop" in events

        round_events = [r for r in log if r.get("event") == "round_complete"]
        assert len(round_events) >= 1, f"預期至少 1 筆 round_complete，實際 {len(round_events)}"

        required_fields = [
            "round", "timestamp", "success", "promoted", "error",
            "before_baseline_dev", "after_baseline_dev", "best_score",
            "no_improve_count", "dominant_failure", "same_failure_count",
            "round_estimated_api_calls", "estimated_api_calls_total",
            "estimated_cost_total", "elapsed_seconds",
        ]
        for evt in round_events:
            for field in required_fields:
                assert field in evt, f"round_complete 缺少欄位 {field}"

        start_event = [r for r in log if r.get("event") == "start"][0]
        assert "timestamp" in start_event
        assert "args" in start_event
        assert "baseline_dev_score" in start_event

    def test_no_improve_clear_exit(self, tmp_path, monkeypatch):
        """no-improve 達到上限時明確以「未晉升」停止。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=10,
            no_improve_limit=3,
            retry_after_no_improve=0,
        ))
        assert rc == 0

        log = _read_log(tmp_path)
        stop = [r for r in log if r.get("event") == "stop"]
        assert len(stop) >= 1, "缺少 stop 事件"
        assert "未晉升" in stop[-1]["reason"], (
            f"停止原因應包含「未晉升」，實際：{stop[-1]['reason']}"
        )
        assert "重試" not in stop[-1]["reason"], (
            "retry_after_no_improve=0 時原因不應包含「重試」"
        )

    def test_baseline_hash_unchanged(self, tmp_path, monkeypatch):
        """演化流程前後 baseline.md 雜湊不變。"""
        monkeypatch.chdir(tmp_path)
        original_hash = _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=8,
            no_improve_limit=2,
            retry_after_no_improve=0,
        ))
        assert rc == 0
        assert _baseline_hash(tmp_path) == original_hash

    def test_reproducibility_evidence_in_convergence(self, tmp_path, monkeypatch):
        """收斂結論包含重現性所需的環境資訊。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=12,
            no_improve_limit=2,
            retry_after_no_improve=2,
        ))
        assert rc == 0

        log = _read_log(tmp_path)
        conv = [r for r in log if r.get("event") == "converged_to_baseline"]
        assert len(conv) == 1, f"預期 1 筆 converged_to_baseline，實際 {len(conv)}"

        c = conv[0]
        assert "reason" in c
        assert "conclusion" in c
        assert "environment" in c
        env = c["environment"]
        assert "python" in env
        assert "platform" in env
        assert "arch" in env
        assert env.get("hashseed") is not None, "缺少 PYTHONHASHSEED"

        assert "successful_promotions" in c
        assert "best_score" in c
        assert "baseline_dev_score" in c
        assert "retry_count" in c

    def test_all_artifacts_written(self, tmp_path, monkeypatch):
        """確認 evolution_log.jsonl、metrics.jsonl 及收斂報告寫入。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=10,
            no_improve_limit=2,
            retry_after_no_improve=2,
        ))
        assert rc == 0

        log = _read_log(tmp_path)
        assert len(log) >= 1, "evolution_log.jsonl 應有內容"

        assert (tmp_path / "evolution_log.jsonl").exists(), "evolution_log.jsonl 不存在"

        conv_events = [r for r in log if r.get("event") == "converged_to_baseline"]
        if conv_events:
            doc_dir = tmp_path / "docs"
            conv_files = list(doc_dir.glob("convergence_report_*.json"))
            assert len(conv_files) >= 1, "收斂報告檔案未寫入 docs/"

            for cf in conv_files:
                with open(cf, "r", encoding="utf-8") as f:
                    report = json.load(f)
                assert "event" in report
                assert report["event"] == "converged_to_baseline"
                assert "conclusion" in report
                assert "environment" in report

    def test_stop_event_records_totals_and_mode(self, tmp_path, monkeypatch):
        """stop 事件包含累計統計與 retry 模式狀態。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=8,
            no_improve_limit=2,
            retry_after_no_improve=2,
        ))

        assert rc == 0
        log = _read_log(tmp_path)
        stop = [r for r in log if r.get("event") == "stop"]
        assert len(stop) >= 1

        s = stop[-1]
        assert "successful_promotions" in s
        assert "best_score" in s
        assert "estimated_api_calls_total" in s
        assert "estimated_cost_total" in s
        assert "elapsed_seconds" in s
        assert "retry_mode" in s
        assert "retry_count" in s

    def test_convergence_report_written_to_docs(self, tmp_path, monkeypatch):
        """收斂後 docs/convergence_report_*.json 確實寫入。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=10,
            no_improve_limit=2,
            retry_after_no_improve=2,
        ))
        assert rc == 0

        doc_dir = tmp_path / "docs"
        conv_files = list(doc_dir.glob("convergence_report_*.json"))
        assert len(conv_files) >= 1, "收斂報告未寫入 docs/ 目錄"

        with open(conv_files[0], "r", encoding="utf-8") as f:
            report = json.load(f)
        assert report.get("conclusion") == "已收斂於 baseline，重試仍無改善"
        assert "reason" in report
        assert "best_score" in report
        assert "no_improve_count" in report
        assert "retry_count" in report
        assert "environment" in report


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))