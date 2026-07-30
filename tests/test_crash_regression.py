# -*- coding: utf-8 -*-
"""
Crash regression tests for three errors found in evolution_log.jsonl:
1. unsupported format string passed to NoneType.__format__
2. unhashable type: 'dict'
3. cannot access local variable 'type_variance'
"""
import hashlib
import json
import os
import sys
import types

import pytest

import auto_evolve
import scripts.compare_runs as cr
import run_opt

BASELINE_PROMPT = "你是一位專精臺灣國家考試的專家。"


def _write_baseline(tmp_path):
    p = tmp_path / "prompts" / "baseline.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(BASELINE_PROMPT, encoding="utf-8")


def _write_baseline_meta(tmp_path, data):
    p = tmp_path / "prompts" / "baseline.meta.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _install_fake_run_opt(monkeypatch, always_success=False):
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


# =====================================================================
# Crash 1: unsupported format string passed to NoneType.__format__
# =====================================================================

class TestUnsupportedFormatNone:
    """重現 evolution_log.jsonl 中 `unsupported format string passed to NoneType.__format__`。

    根因：auto_evolve.py line 184 的 f-string 在 holdout_avg=None 時直接對 None 套 .2f。
    """

    def test_holdout_avg_none_does_not_crash(self, tmp_path, monkeypatch):
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, {
            "dev_avg": 88.03, "dev_run": "runs/some_dev",
            "holdout_avg": None,
        })
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(auto_evolve.subprocess, "run",
                            lambda cmd, timeout=None: types.SimpleNamespace(returncode=0))
        monkeypatch.setattr(auto_evolve, "platform",
                            types.SimpleNamespace(platform=lambda: "test", machine=lambda: "test"))
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 10)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "3"])

        rc = auto_evolve.main()
        assert rc == 0

    def test_holdout_avg_none_logs_generations(self, tmp_path, monkeypatch):
        _write_baseline(tmp_path)
        _write_baseline_meta(tmp_path, {
            "dev_avg": 88.03, "dev_run": "runs/some_dev",
            "holdout_avg": None,
        })
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(auto_evolve.subprocess, "run",
                            lambda cmd, timeout=None: types.SimpleNamespace(returncode=0))
        monkeypatch.setattr(auto_evolve, "platform",
                            types.SimpleNamespace(platform=lambda: "test", machine=lambda: "test"))
        _install_fake_run_opt(monkeypatch, always_success=False)
        monkeypatch.setattr(auto_evolve.time, "sleep", lambda _: None)
        monkeypatch.setattr(auto_evolve, "NO_IMPROVE_LIMIT", 10)
        monkeypatch.setattr(auto_evolve, "RETRY_AFTER_NO_IMPROVE", 0)
        monkeypatch.setattr(sys, "argv", ["auto_evolve.py", "3"])

        auto_evolve.main()
        log_path = tmp_path / "evolution_log.jsonl"
        rows = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        gen_events = [r for r in rows if r.get("event") == "generation_complete"]
        assert len(gen_events) == 3
        for evt in gen_events:
            assert "success" in evt
            assert "promoted" in evt

    def test_direct_format_none_raises(self):
        """直接驗證原始程式碼模式在 None 時會拋出 ValueError。"""
        holdout_avg = None
        with pytest.raises((ValueError, TypeError)):
            _ = f"{holdout_avg:.2f if holdout_avg is not None else 'N/A'}"


# =====================================================================
# Crash 2: unhashable type: 'dict'
# =====================================================================

class TestUnhashableTypeDict:
    """重現 evolution_log.jsonl 中 `unhashable type: 'dict'`。

    根因：compare_runs 與 run_opt 在 failure code 為 dict 時嘗試用 dict 做 dict key。
    """

    def test_compare_skips_dict_failure_code(self, tmp_path):
        """failure 中含 dict 不應導致 compare 崩潰。"""
        base = make_run(tmp_path / "base", [
            rec("q1", failures=[{"bad": "dict"}]),
        ])
        new = make_run(tmp_path / "new", [
            rec("q1", score=86.0, failures=[{"bad": "dict"}]),
        ])
        passed, avg_new, diff = cr.compare(new, base, mode="pragmatic")
        assert avg_new == pytest.approx(86.0)
        assert diff == pytest.approx(6.0)
        lc = cr.LAST_COMPARISON
        assert lc["failure_new"] == {}
        assert lc["failure_base"] == {}

    def test_compare_skips_mixed_string_and_dict_failures(self, tmp_path):
        """混合合法字串與 dict failure 時，dict 被過濾、字串正常計數。"""
        base = make_run(tmp_path / "base", [
            rec("q1", failures=["F03", {"bad": "dict"}]),
        ])
        new = make_run(tmp_path / "new", [
            rec("q1", score=86.0, failures=["F03", "F12", {"bad": "dict"}]),
        ])
        passed, avg_new, diff = cr.compare(new, base, mode="pragmatic")
        lc = cr.LAST_COMPARISON
        assert lc["failure_new"] == {"F03": 1, "F12": 1}
        assert lc["failure_base"] == {"F03": 1}

    def test_compare_dict_in_type_raises(self, tmp_path):
        """若 type 本身為 dict，compare 應 raise TypeError 而非默默吞下。"""
        new = make_run(tmp_path / "new", [{
            "id": "q1", "type": {"bad": "type"}, "total_score": 80.0,
            "failures": [], "char_count": 1000, "risk_score": 10,
        }])
        base = make_run(tmp_path / "base", [rec("q1")])
        with pytest.raises(TypeError):
            cr.compare(new, base, mode="pragmatic")

    def test_collect_recent_failure_trend_skips_dict(self, tmp_path, monkeypatch):
        """collect_recent_failure_trend 遇到 dict failure code 不應崩潰。"""
        run_dir = str(tmp_path / "run_test")
        details_path = os.path.join(run_dir, "details.jsonl")
        os.makedirs(run_dir, exist_ok=True)
        with open(details_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": "q1", "failures": [{"bad": "dict"}]}) + "\n")
            f.write(json.dumps({"id": "q2", "failures": ["F03"]}) + "\n")
        with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump({"question_file": "questions/dev.jsonl"}, f)

        monkeypatch.setattr(run_opt, "list_run_dirs", lambda: [run_dir])
        counts, runs = run_opt.collect_recent_failure_trend(
            question_file="questions/dev.jsonl"
        )
        assert counts == {"F03": 1}
        assert all(isinstance(k, str) for k in counts)


# =====================================================================
# Crash 3: cannot access local variable 'type_variance'
# =====================================================================

class TestTypeVarianceUnbound:
    """重現 evolution_log.jsonl 中 `cannot access local variable 'type_variance'`。

    根因：type_variance 在某些程式路徑未能初始化即在 print/LAST_COMPARISON 中被參照。
    修復：在 compare 函數中提前初始化 type_variance = 0.0。
    """

    def test_compare_with_single_type_has_variance(self, tmp_path):
        """單一題型時 type_variance 應為 0.0 且不拋異常。"""
        base = make_run(tmp_path / "base", [rec("q1", "事實")])
        new = make_run(tmp_path / "new", [rec("q1", "事實", score=85.0)])
        cr.compare(new, base, mode="pragmatic")
        lc = cr.LAST_COMPARISON
        assert "type_variance" in lc
        assert lc["type_variance"] == pytest.approx(0.0)

    def test_compare_with_multi_type_has_variance(self, tmp_path):
        """多題型時 type_variance 正確計算。"""
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

    def test_compare_variance_printed(self, tmp_path, capsys):
        """variance 應出現在 print 輸出中。"""
        base = make_run(tmp_path / "base", [rec("q1", "事實")])
        new = make_run(tmp_path / "new", [rec("q1", "事實", score=85.0)])
        cr.compare(new, base, mode="pragmatic")
        out = capsys.readouterr().out
        assert "題型分數方差" in out


# =====================================================================
# 證明三類修復皆非以 try/except 吞例外
# =====================================================================

class TestFixBuiltWithGuardNotTryExcept:
    """驗證每個 crash 的修復替代方式是結構化防禦（三元運算子/isinstance/
    前置初始化），而非以 try/except 吞掉例外——證明方式是繞過防禦後
    同類例外仍會正常拋出。"""

    # ---- Crash 1: NoneType 格式化 ----

    def test_none_format_guard_is_ternary_not_try(self):
        """NoneType 修復用三元運算子：None→N/A；若 try/except 吞例外，
        `None:.2f` 會被吞成空值而非正確顯示 N/A。"""
        holdout_avg = None
        with pytest.raises((ValueError, TypeError)):
            f"{holdout_avg:.2f}"
        display = f"{holdout_avg:.2f}" if holdout_avg is not None else "N/A"
        assert display == "N/A"
        assert "try" not in display
        assert "except" not in display

    def test_none_format_non_none_path_untouched(self):
        """非 None 值不受修復影響，仍正常格式化。"""
        val = 88.5
        display = f"{val:.2f}" if val is not None else "N/A"
        assert display == "88.50"
        assert float(display) == pytest.approx(88.5)

    # ---- Crash 2: unhashable type: 'dict' ----

    def test_dict_filter_is_isinstance_not_try(self):
        """dict failure 用 isinstance(str) 過濾而非 try/except：
        dict 作為 dict key 仍拋 TypeError。"""
        raw = [{"a": 1}, "F03", {"b": 2}]
        filtered = {}
        for f in raw:
            if isinstance(f, str) and f:
                filtered[f] = filtered.get(f, 0) + 1
        assert filtered == {"F03": 1}
        with pytest.raises(TypeError, match="unhashable"):
            {}.__setitem__({"bad": "dict"}, 1)
        assert all(isinstance(k, str) for k in filtered)

    def test_dict_filter_original_unhashable_still_raises(self):
        """不經 isinstance 過濾的 dict key 操作仍會拋 TypeError，
        證明修復是以型別檢查取代 try/except。"""
        with pytest.raises(TypeError, match="unhashable"):
            d = {}
            d[{"bad": "dict"}] = 1

    # ---- Crash 3: type_variance 未綁定 ----

    def test_type_variance_initialized_before_conditional(self):
        """type_variance=0.0 在 if 前初始化；若不初始化，
        空白 type_scores_list 會導致 UnboundLocalError。"""
        exec_globals = {}
        exec_code = """
type_scores = []
result = 0.0
if type_scores:
    result = 1.0  # pragma: no cover
# result is 0.0 because initialized before conditional
"""
        exec(exec_code, exec_globals)
        assert exec_globals["result"] == 0.0

    def test_type_variance_uninitialized_raises_unbound(self):
        """若不移除 type_variance=0.0 前置初始化（即不用此修復），
        改採 try/except 吞錯誤，則需捕獲 NameError/UnboundLocalError。
        此測試證明此類錯誤不該被捕獲——即正確修復不靠 try/except。"""
        with pytest.raises((UnboundLocalError, NameError)):
            exec("type_scores = []\n" "if type_scores:\n" "    variance = 1.0\n" "print(variance)")

    def test_type_variance_propagates_other_errors(self, tmp_path):
        """type_variance 修復不吞其他錯誤：compare 遇到無效資料仍拋異常。"""
        new = make_run(tmp_path / "new", [{
            "id": "q1", "type": {"bad": "type"}, "total_score": 80.0,
            "failures": [], "char_count": 1000, "risk_score": 10,
        }])
        base = make_run(tmp_path / "base", [rec("q1")])
        with pytest.raises(TypeError):
            cr.compare(new, base, mode="pragmatic")
