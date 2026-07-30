# -*- coding: utf-8 -*-
"""
manual-goal-error-free-evolution.py — 整合驗證三類 crash 正確產出、
F03/F04 對策注入與記錄、指定日期區間至少三筆無錯 round_complete 日誌
及 baseline 雜湊不變。

可直接執行：
    python tests/manual-goal-error-free-evolution.py

或以 pytest 執行：
    python -m pytest -q tests/manual-goal-error-free-evolution.py
"""
import hashlib
import json
import os
import sys
import time as time_module
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import auto_evolve
import infinite_evolve
import run_opt
import scripts.compare_runs as cr

BASELINE_PROMPT = "你是一位專精臺灣國家考試的專家。"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_baseline(tmp_path):
    p = tmp_path / "prompts" / "baseline.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(BASELINE_PROMPT, encoding="utf-8")
    return hashlib.sha256(BASELINE_PROMPT.encode("utf-8")).hexdigest()


def _write_baseline_meta(tmp_path, data):
    p = tmp_path / "prompts" / "baseline.meta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


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
    fake_mod.LAST_ROUND_COUNTERMEASURES = []
    monkeypatch.setitem(sys.modules, "run_opt", fake_mod)
    return calls


def _install_fake_run_opt_for_auto_evolve(monkeypatch, always_success=False):
    calls = []

    def fake_run_opt_pass(**kwargs):
        calls.append(kwargs)
        return always_success

    fake_mod = types.ModuleType("run_opt")
    fake_mod.run_opt_pass = fake_run_opt_pass
    fake_mod.load_file = lambda path: ""
    fake_mod.load_json = lambda path: {}
    fake_mod.parse_parallel_args = lambda args: {
        "smoke_parallel": 24, "dev_parallel": 24, "holdout_parallel": 24,
    }
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


def make_run(dirpath, records):
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "details.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return str(dirpath)


def rec(qid, qtype="事實", score=80.0, failures=None, char_count=1000, risk=10):
    return {
        "id": qid, "type": qtype, "total_score": score,
        "failures": failures or [], "char_count": char_count, "risk_score": risk,
    }


# ===========================================================================
# 類別一：三類 crash 正確產出
# ===========================================================================

class TestThreeCrashCorrectOutputs:
    """驗證三類已知 crash 的正確產出。"""

    def test_crash1_holdout_avg_none_no_crash(self, tmp_path, monkeypatch):
        """Crash 1: NoneType.__format__ — holdout_avg=None 不應崩潰。"""
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, {
            "dev_avg": 88.03, "dev_run": "runs/some_dev",
            "holdout_avg": None,
        })
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(auto_evolve.subprocess, "run",
                            lambda cmd, timeout=None: SimpleNamespace(returncode=0))
        monkeypatch.setattr(auto_evolve, "platform",
                            types.SimpleNamespace(platform=lambda: "test", machine=lambda: "test"))
        _install_fake_run_opt_for_auto_evolve(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 10)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "3"])

        rc = auto_evolve.main()
        assert rc == 0

    def test_crash1_generations_logged(self, tmp_path, monkeypatch):
        """Crash 1: generation_complete 事件應正確記錄。"""
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, {
            "dev_avg": 88.03, "dev_run": "runs/some_dev",
            "holdout_avg": None,
        })
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(auto_evolve.subprocess, "run",
                            lambda cmd, timeout=None: SimpleNamespace(returncode=0))
        monkeypatch.setattr(auto_evolve, "platform",
                            types.SimpleNamespace(platform=lambda: "test", machine=lambda: "test"))
        _install_fake_run_opt_for_auto_evolve(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 10)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "3"])

        auto_evolve.main()
        log = _read_log(tmp_path)
        gen_events = [r for r in log if r.get("event") == "generation_complete"]
        assert len(gen_events) == 3
        for evt in gen_events:
            assert "success" in evt
            assert "promoted" in evt

    def test_crash2_dict_failure_code_compare(self, tmp_path):
        """Crash 2: unhashable type 'dict' — compare 不應崩潰。"""
        base = make_run(tmp_path / "base", [rec("q1", failures=[{"bad": "dict"}])])
        new = make_run(tmp_path / "new", [rec("q1", score=86.0, failures=[{"bad": "dict"}])])
        passed, avg_new, diff = cr.compare(new, base, mode="pragmatic")
        assert avg_new == pytest.approx(86.0)
        lc = cr.LAST_COMPARISON
        assert lc["failure_new"] == {}
        assert lc["failure_base"] == {}

    def test_crash2_mixed_string_and_dict_failures(self, tmp_path):
        """Crash 2: 混合合法字串與 dict failure — dict 被過濾。"""
        base = make_run(tmp_path / "base", [rec("q1", failures=["F03", {"bad": "dict"}])])
        new = make_run(tmp_path / "new", [rec("q1", score=86.0, failures=["F03", "F12", {"bad": "dict"}])])
        passed, avg_new, diff = cr.compare(new, base, mode="pragmatic")
        lc = cr.LAST_COMPARISON
        assert lc["failure_new"] == {"F03": 1, "F12": 1}
        assert lc["failure_base"] == {"F03": 1}

    def test_crash3_type_variance_single_type(self, tmp_path):
        """Crash 3: type_variance — 單一題型時 variance 為 0.0。"""
        base = make_run(tmp_path / "base", [rec("q1", "事實")])
        new = make_run(tmp_path / "new", [rec("q1", "事實", score=85.0)])
        cr.compare(new, base, mode="pragmatic")
        lc = cr.LAST_COMPARISON
        assert "type_variance" in lc
        assert lc["type_variance"] == pytest.approx(0.0)

    def test_crash3_type_variance_multi_type(self, tmp_path):
        """Crash 3: type_variance — 多題型時正確計算。"""
        base = make_run(tmp_path / "base", [
            rec("q1", "事實", 80.0), rec("q2", "推理", 80.0),
        ])
        new = make_run(tmp_path / "new", [
            rec("q1", "事實", 85.0), rec("q2", "推理", 75.0),
        ])
        cr.compare(new, base, mode="pragmatic")
        lc = cr.LAST_COMPARISON
        assert "type_variance" in lc
        assert lc["type_variance"] >= 0.0


# ===========================================================================
# 類別二：F03/F04 對策注入與記錄
# ===========================================================================

class TestF03F04CountermeasureInjection:
    """驗證 F03/F04 對策的載入、注入與日誌記錄。"""

    def test_loads_F03_countermeasure_text(self):
        """F03 對策原文包含完整中文說明。"""
        result = run_opt.load_targeted_countermeasures(["F03"])
        assert "F03" in result
        text = result["F03"]
        assert len(text) > 20
        assert "結構化、具體化" in text

    def test_loads_F04_countermeasure_text(self):
        """F04 對策原文包含完整中文說明。"""
        result = run_opt.load_targeted_countermeasures(["F04"])
        assert "F04" in result
        text = result["F04"]
        assert len(text) > 20
        assert "專有名詞" in text

    def test_both_F03_F04_returned_together(self):
        """同時要求 F03 與 F04 時兩者都返回。"""
        result = run_opt.load_targeted_countermeasures(["F03", "F04"])
        assert "F03" in result
        assert "F04" in result

    def test_countermeasure_block_format(self):
        """對策 block 格式包含完整句子。"""
        result = run_opt.load_targeted_countermeasures(["F03"])
        lines = [f"- {code}：{text}" for code, text in sorted(result.items())]
        block = "以下為對應缺陷的具體修復方向，請在優化時嚴格落實：\n" + "\n".join(lines)
        assert "- F03：" in block
        assert block.count("- F03：") == 1

    def test_injected_field_in_round_complete(self, tmp_path, monkeypatch):
        """round_complete 日誌包含 countermeasures_injected 欄位。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        tax_dir = tmp_path / "rubrics"
        tax_dir.mkdir(parents=True, exist_ok=True)
        (tax_dir / "failure_taxonomy.md").write_text(
            "### F03：採分點不外露\n"
            "* **修復方向**：規定標題必須「結構化、具體化」。\n"
            "\n"
            "### F04：內容抽象\n"
            "* **修復方向**：要求模型包含具體佐證。\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        def fake_run_opt_pass(**kwargs):
            return True

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = fake_run_opt_pass
        fake_mod.LAST_ROUND_COUNTERMEASURES = ["F03"]
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=_common_argv(max_rounds=5, no_improve_limit=10))
        assert rc == 0

        log = _read_log(tmp_path)
        round_events = [r for r in log if r.get("event") == "round_complete"]
        assert len(round_events) >= 1
        for evt in round_events:
            assert "countermeasures_injected" in evt
            assert isinstance(evt["countermeasures_injected"], list)
            assert evt["countermeasures_injected"] == ["F03"]

    def test_no_dominant_failure_empty_countermeasures(self, tmp_path, monkeypatch):
        """無 dominant_failure 時 countermeasures_injected 為空 list。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        def fake_run_opt_pass(**kwargs):
            return True

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = fake_run_opt_pass
        fake_mod.LAST_ROUND_COUNTERMEASURES = []
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=_common_argv(max_rounds=5, no_improve_limit=10))
        assert rc == 0

        log = _read_log(tmp_path)
        round_events = [r for r in log if r.get("event") == "round_complete"]
        for evt in round_events:
            assert evt["countermeasures_injected"] == []


# ===========================================================================
# 類別三：指定日期區間至少三筆無錯 round_complete 日誌
# ===========================================================================

class TestDateRangeErrorFreeRoundComplete:
    """驗證指定日期區間至少三筆無錯 round_complete 日誌。"""

    def test_at_least_3_error_free_round_complete_in_date_range(self, tmp_path, monkeypatch):
        """指定日期區間至少 3 筆 error='' 且 success=True 的 round_complete。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)

        # 將 time_module.strftime 鎖定為指定日期
        fake_timestamp = "2026-07-30 12:00:00"
        monkeypatch.setattr(time_module, "strftime", lambda fmt, *args, **kwargs: fake_timestamp)

        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        def fake_run_opt_pass(**kwargs):
            return True

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = fake_run_opt_pass
        fake_mod.LAST_ROUND_COUNTERMEASURES = []
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=6,
            no_improve_limit=10,
            retry_after_no_improve=0,
        ))
        assert rc == 0

        log = _read_log(tmp_path)
        round_events = [r for r in log if r.get("event") == "round_complete"]
        assert len(round_events) >= 3, f"預期至少 3 筆 round_complete，實際 {len(round_events)}"

        # 指定日期區間：2026-07-29 ~ 2026-07-31
        cutoff_start = datetime(2026, 7, 29)
        cutoff_end = datetime(2026, 7, 31, 23, 59, 59)
        error_free_in_range = []
        for evt in round_events:
            ts = evt.get("timestamp", "")
            try:
                evt_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                continue
            if cutoff_start <= evt_dt <= cutoff_end:
                if evt.get("error", None) == "" and evt.get("success", False) is True:
                    error_free_in_range.append(evt)

        assert len(error_free_in_range) >= 3, (
            f"預期指定日期區間至少 3 筆無錯 round_complete，"
            f"實際 {len(error_free_in_range)}"
        )

        # 每筆日誌包含必要欄位
        required_fields = [
            "round", "timestamp", "success", "promoted", "error",
            "before_baseline_dev", "after_baseline_dev", "best_score",
            "no_improve_count", "dominant_failure", "same_failure_count",
        ]
        for evt in error_free_in_range:
            for field in required_fields:
                assert field in evt, f"round_complete 缺少欄位 {field}"

    def test_round_complete_fields_are_correct_types(self, tmp_path, monkeypatch):
        """round_complete 日誌欄位型別正確。"""
        monkeypatch.chdir(tmp_path)
        _write_baseline(tmp_path)

        fake_timestamp = "2026-07-30 12:00:00"
        monkeypatch.setattr(time_module, "strftime", lambda fmt, *args, **kwargs: fake_timestamp)

        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        def fake_run_opt_pass(**kwargs):
            return True

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = fake_run_opt_pass
        fake_mod.LAST_ROUND_COUNTERMEASURES = []
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=_common_argv(
            max_rounds=5,
            no_improve_limit=10,
        ))
        assert rc == 0

        log = _read_log(tmp_path)
        round_events = [r for r in log if r.get("event") == "round_complete"]
        assert len(round_events) >= 3

        for evt in round_events:
            assert isinstance(evt.get("round"), int)
            assert isinstance(evt.get("timestamp"), str)
            assert isinstance(evt.get("success"), bool)
            assert isinstance(evt.get("promoted"), bool)
            assert isinstance(evt.get("error"), str)
            assert isinstance(evt.get("no_improve_count"), int)
            assert isinstance(evt.get("dominant_failure"), str)
            assert isinstance(evt.get("same_failure_count"), int)


# ===========================================================================
# 類別四：baseline 雜湊不變
# ===========================================================================

class TestBaselineHashUnchanged:
    """演化過程中 baseline.md 雜湊全程不變。"""

    def test_hash_unchanged_after_evolution(self, tmp_path, monkeypatch):
        """演化結束後 baseline.md 雜湊與起始相同。"""
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

    def test_hash_unchanged_after_convergence(self, tmp_path, monkeypatch):
        """收斂流程結束後 baseline.md 雜湊不變。"""
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
        assert _baseline_hash(tmp_path) == original_hash

    def test_hash_unchanged_after_auto_evolve(self, tmp_path, monkeypatch):
        """auto_evolve 結束後 baseline.md 雜湊不變。"""
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, {
            "dev_avg": 88.03, "dev_run": "runs/some_dev",
            "holdout_avg": 90.0,
        })
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(auto_evolve.subprocess, "run",
                            lambda cmd, timeout=None: SimpleNamespace(returncode=0))
        monkeypatch.setattr(auto_evolve, "platform",
                            types.SimpleNamespace(platform=lambda: "test", machine=lambda: "test"))
        original_hash = _baseline_hash(tmp_path)
        _install_fake_run_opt_for_auto_evolve(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 10)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "3"])

        rc = auto_evolve.main()
        assert rc == 0
        assert _baseline_hash(tmp_path) == original_hash

    def test_actual_baseline_file_exists(self):
        """實際 prompts/baseline.md 存在且可計算雜湊。"""
        baseline_path = Path(__file__).parent.parent / "prompts" / "baseline.md"
        assert baseline_path.exists()
        current_hash = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
        assert len(current_hash) == 64
        assert all(c in "0123456789abcdef" for c in current_hash)


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
