# -*- coding: utf-8 -*-
"""
演化流程可觀察行為測試：連續 no-improve 情境下的 retry / convergence 行為驗證。

覆蓋需求：
- 構造連續 no-improve 情境，斷言引擎產生 retry 或 convergence 結論
- 記錄失敗模式與 baseline 比較
- 在有限步數內結束
- 斷言 prompts/baseline.md 的內容雜湊全程不變
"""
import hashlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import infinite_evolve


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


def _install_fake_run_opt(monkeypatch, always_success=False):
    """注入假的 run_opt 模組到 sys.modules，回傳呼叫記錄 list。"""
    calls = []

    def fake_run_opt_pass(
        smoke_parallel=None,
        dev_parallel=None,
        holdout_parallel=None,
        force_direction=None,
        avoid_failures=None,
        dominant_failure=None,
    ):
        calls.append(
            {
                "smoke_parallel": smoke_parallel,
                "dev_parallel": dev_parallel,
                "holdout_parallel": holdout_parallel,
                "force_direction": force_direction,
                "avoid_failures": avoid_failures,
                "dominant_failure": dominant_failure,
            }
        )
        return always_success

    fake_mod = types.ModuleType("run_opt")
    fake_mod.run_opt_pass = fake_run_opt_pass  # type: ignore[attr-defined]
    fake_mod.LAST_ROUND_COUNTERMEASURES = []  # type: ignore[attr-defined]
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


def _common_argv(**overrides):
    """產生測試用 argv，預設關閉 sleep / route / 大超時。"""
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


def test_dry_run_forwards_offline_preflight_and_skips_evolution(tmp_path, monkeypatch):
    """dry-run 必須略過 provider key 並在任何演化 round 前結束。"""
    monkeypatch.chdir(tmp_path)
    calls = []

    def fake_run_cmd(cmd, timeout=None):
        calls.append((cmd, timeout))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(infinite_evolve, "run_cmd", fake_run_cmd)
    rc = infinite_evolve.main(argv=_common_argv(max_rounds=1) + ["--dry-run"])

    assert rc == 0
    assert len(calls) == 1
    assert calls[0][0][-1] == "--offline"
    assert not (tmp_path / "evolution_log.jsonl").exists()


def test_budget_requires_cost_estimate_before_preflight(tmp_path, monkeypatch):
    """指定預算卻沒有單次成本估計時，不得開始任何 subprocess。"""
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(
        infinite_evolve,
        "run_cmd",
        lambda cmd, timeout=None: calls.append((cmd, timeout)),
    )

    rc = infinite_evolve.main(
        argv=_common_argv(max_rounds=1) + ["--budget-usd", "1"]
    )

    assert rc == 2
    assert calls == []


# ---------------------------------------------------------------------------
# Tests — retry → convergence
# ---------------------------------------------------------------------------

class TestNoImproveRetryThenConvergence:
    """連續 no-improve 觸發 retry → convergence 結論。"""

    def test_retry_entered_and_converged(self, tmp_path, monkeypatch):
        """驗證：no_improve_limit 輪後進入 retry，retry 耗盡後寫入 convergence 結論。"""
        monkeypatch.chdir(tmp_path)
        original_hash = _write_baseline(tmp_path)
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
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=15,
            no_improve_limit=2,
            retry_after_no_improve=3,
        ))

        assert rc == 0
        log = _read_log(tmp_path)

        # 第一次進入 retry → retry_mode_entered
        # 後續 retry → retry_adjust（2 次，因為 retry_after_no_improve=3 需要 3 輪 retry 才停）
        adjust_events = [r for r in log if r.get("event") == "retry_adjust"]
        assert len(adjust_events) >= 1, f"預期 >=1 retry_adjust，實際 {len(adjust_events)}"

        for adj in adjust_events:
            assert "retry_count" in adj
            assert "dominant_failure" in adj


# ---------------------------------------------------------------------------
# Tests — no retry mode
# ---------------------------------------------------------------------------

class TestNoImproveNoRetry:
    """retry_after_no_improve=0 時，直接因 no-improve 停止。"""

    def test_stops_without_retry(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        original_hash = _write_baseline(tmp_path)
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

        retry_events = [r for r in log if r.get("event") == "retry_mode_entered"]
        assert len(retry_events) == 0

        conv_events = [r for r in log if r.get("event") == "converged_to_baseline"]
        assert len(conv_events) == 0

        stop = [r for r in log if r.get("event") == "stop"][-1]
        assert "未晉升" in stop["reason"]
        assert "重試" not in stop["reason"]

        assert _baseline_hash(tmp_path) == original_hash


# ---------------------------------------------------------------------------
# Tests — failure pattern recording
# ---------------------------------------------------------------------------

class TestFailurePatternRecording:
    """每輪 round_complete 事件記錄 failure 模式與 baseline 比較。"""

    def test_round_events_contain_failure_fields(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=5,
            no_improve_limit=6,
            retry_after_no_improve=0,
        ))

        assert rc == 0
        log = _read_log(tmp_path)
        round_events = [r for r in log if r.get("event") == "round_complete"]

        assert len(round_events) == 5
        for i, evt in enumerate(round_events):
            assert evt["round"] == i + 1
            assert "no_improve_count" in evt
            assert "dominant_failure" in evt
            assert "same_failure_count" in evt
            assert "success" in evt
            assert "promoted" in evt
            assert "before_baseline_dev" in evt
            assert "after_baseline_dev" in evt
            assert evt["promoted"] is False

    def test_no_improve_count_increments(self, tmp_path, monkeypatch):
        """no_improve_count 每輪遞增（無晉升時）。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=4,
            no_improve_limit=10,
            retry_after_no_improve=0,
        ))

        assert rc == 0
        log = _read_log(tmp_path)
        round_events = [r for r in log if r.get("event") == "round_complete"]

        counts = [r["no_improve_count"] for r in round_events]
        assert counts == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Tests — baseline hash invariance
# ---------------------------------------------------------------------------

class TestBaselineHashInvariance:
    """演化過程中 baseline.md 內容雜湊全程不變。"""

    def test_hash_unchanged_throughout_evolution(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        original_hash = _write_baseline(tmp_path)
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
        assert _baseline_hash(tmp_path) == original_hash

    def test_baseline_file_not_modified_by_run_opt_pass(self, tmp_path, monkeypatch):
        """即使 run_opt_pass 被呼叫多次，baseline.md 不被修改。"""
        monkeypatch.chdir(tmp_path)
        original_hash = _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        calls = _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=6,
            no_improve_limit=3,
            retry_after_no_improve=0,
        ))

        assert rc == 0
        assert len(calls) >= 3  # run_opt_pass 至少被呼叫 3 次
        assert _baseline_hash(tmp_path) == original_hash

    def test_real_baseline_hash_invariance_during_evolution(self, tmp_path, monkeypatch):
        """使用真實 prompts/baseline.md 的內容驗證演化過程中雜湊不變。"""
        real_path = Path(__file__).resolve().parents[1] / "prompts" / "baseline.md"
        real_content = real_path.read_bytes()
        real_hash = hashlib.sha256(real_content).hexdigest()

        p = tmp_path / "prompts" / "baseline.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(real_content)

        monkeypatch.chdir(tmp_path)
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
        after_hash = hashlib.sha256(p.read_bytes()).hexdigest()
        assert after_hash == real_hash, (
            f"真實 baseline.md 內容在演化後雜湊改變："
            f"{real_hash[:16]} → {after_hash[:16]}"
        )


# ---------------------------------------------------------------------------
# Tests — finite step completion
# ---------------------------------------------------------------------------

class TestFiniteStepCompletion:
    """演化在有限步數內結束。"""

    def test_terminates_within_max_rounds(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        max_rounds = 6
        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=max_rounds,
            no_improve_limit=2,
            retry_after_no_improve=1,
        ))

        assert rc == 0
        log = _read_log(tmp_path)
        round_events = [r for r in log if r.get("event") == "round_complete"]

        assert len(round_events) <= max_rounds
        assert len(round_events) >= 1
        assert any(r.get("event") == "stop" for r in log)

    def test_convergence_report_has_environment(self, tmp_path, monkeypatch):
        """convergence 結論包含環境資訊。"""
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
        conv = [r for r in log if r.get("event") == "converged_to_baseline"]
        assert len(conv) == 1
        c = conv[0]
        assert "timestamp" in c
        assert "round" in c
        assert "reason" in c
        assert "successful_promotions" in c
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
        stop = [r for r in log if r.get("event") == "stop"][-1]

        assert "successful_promotions" in stop
        assert "best_score" in stop
        assert "estimated_api_calls_total" in stop
        assert "estimated_cost_total" in stop
        assert "elapsed_seconds" in stop
        assert "retry_mode" in stop
        assert "retry_count" in stop
        assert stop["successful_promotions"] == 0
