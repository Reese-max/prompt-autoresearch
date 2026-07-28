# -*- coding: utf-8 -*-
"""tests/test_not_reproducible_acceptance.py — 驗收測試：明確斷言重複執行會產生差異 (NOT-REPRODUCIBLE)

現有一般測試與覆蓋率通過，無法證明目標「NOT-REPRODUCIBLE」。
本檔案新增驗收測試，明確斷言下列場景會被判定為 NOT-REPRODUCIBLE：
  1. 兩次執行 exit_code 不同（一次成功一次失敗）
  2. 兩次執行均成功但 compare_test_runs 偵測到覆蓋率差異
  3. verify_reproducibility.py 偵測到差異時以非零退出碼退出
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import scripts.collect_execution_evidence as cee
import scripts.verify_reproducibility as vr


# ─── helpers ───────────────────────────────────────────────────────────────────

def _make_run_info(exit_code=0, summary="10 passed", cmd=None):
    """建構 run_once 回傳的 info dict。"""
    return {
        "cmd": cmd or [sys.executable, "-m", "pytest"],
        "exit_code": exit_code,
        "run_dir": "/tmp/fake",
        "stdout_summary": summary,
        "stdout_full": f"stdout of run exit={exit_code}",
        "stderr_full": "",
        "coverage_xml": True,
    }


def _make_compare_result(exit_code=0, has_diff=False):
    """建構 compare() 回傳的 dict。"""
    return {
        "exit_code": exit_code,
        "report": {"has_differences": has_diff} if exit_code != 0 else None,
        "stdout": json.dumps({"has_differences": has_diff}),
        "stderr": "",
    }


# ─── collect_execution_evidence：NOT-REPRODUCIBLE 斷言 ────────────────────────

class TestCollectExecutionEvidenceNotReproducible:
    """驗收：collect_execution_evidence.main() 在差異場景應判定 NOT-REPRODUCIBLE。"""

    def test_different_exit_codes_produces_not_reproducible(self, tmp_path, capsys):
        """場景 1：兩次執行 exit_code 不同 → NOT-REPRODUCIBLE。"""
        r1 = _make_run_info(exit_code=0, summary="5 passed")
        r2 = _make_run_info(exit_code=1, summary="1 failed")
        cmp = _make_compare_result(exit_code=1, has_diff=True)

        with patch.object(cee, "run_once", side_effect=[(r1, tmp_path / "d1"), (r2, tmp_path / "d2")]):
            with patch.object(cee, "compare", return_value=cmp):
                with patch.object(cee, "collect_env", return_value={"python": "3.x", "executable": "py", "platform": "x", "arch": "x", "hashseed": "0", "commit": "abc", "time": "now"}):
                    with patch.object(cee, "collect_dep_hashes", return_value={}):
                        with patch.object(cee, "collect_src_hashes", return_value={}):
                            with patch.object(cee, "OUTPUT_DIR", tmp_path / "out"):
                                rc = cee.main()

        out = capsys.readouterr().out
        assert "NOT-REPRODUCIBLE" in out, (
            "exit_code 不同時應輸出 NOT-REPRODUCIBLE，"
            f"但實際輸出為：\n{out}"
        )
        assert rc == 0  # main() always returns 0; reproducibility is in the report

        # 驗證 JSON 報告確實紀錄 NOT-REPRODUCIBLE
        json_files = list((tmp_path / "out").glob("execution-evidence-*.json"))
        assert json_files, "應產生 execution-evidence JSON 檔"
        report = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert report["reproducibility"] == "NOT-REPRODUCIBLE", (
            f"JSON 報告中 reproducibility 欄位應為 NOT-REPRODUCIBLE，"
            f"實際為 {report['reproducibility']}"
        )

    def test_compare_difference_produces_not_reproducible(self, tmp_path, capsys):
        """場景 2：兩次執行均成功，但 compare 偵測到覆蓋率差異 → NOT-REPRODUCIBLE。"""
        r1 = _make_run_info(exit_code=0, summary="10 passed")
        r2 = _make_run_info(exit_code=0, summary="10 passed")
        cmp = _make_compare_result(exit_code=1, has_diff=True)  # compare exit=1 表示有差異

        with patch.object(cee, "run_once", side_effect=[(r1, tmp_path / "d1"), (r2, tmp_path / "d2")]):
            with patch.object(cee, "compare", return_value=cmp):
                with patch.object(cee, "collect_env", return_value={"python": "3.x", "executable": "py", "platform": "x", "arch": "x", "hashseed": "0", "commit": "abc", "time": "now"}):
                    with patch.object(cee, "collect_dep_hashes", return_value={}):
                        with patch.object(cee, "collect_src_hashes", return_value={}):
                            with patch.object(cee, "OUTPUT_DIR", tmp_path / "out"):
                                rc = cee.main()

        out = capsys.readouterr().out
        assert "NOT-REPRODUCIBLE" in out, (
            "compare exit=1 時應輸出 NOT-REPRODUCIBLE，"
            f"但實際輸出為：\n{out}"
        )

        json_files = list((tmp_path / "out").glob("execution-evidence-*.json"))
        report = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert report["reproducibility"] == "NOT-REPRODUCIBLE"

    def test_both_runs_fail_produces_not_reproducible(self, tmp_path, capsys):
        """場景 3：兩次執行皆失敗 → NOT-REPRODUCIBLE。"""
        r1 = _make_run_info(exit_code=2, summary="error")
        r2 = _make_run_info(exit_code=2, summary="error")
        cmp = _make_compare_result(exit_code=1, has_diff=False)

        with patch.object(cee, "run_once", side_effect=[(r1, tmp_path / "d1"), (r2, tmp_path / "d2")]):
            with patch.object(cee, "compare", return_value=cmp):
                with patch.object(cee, "collect_env", return_value={"python": "3.x", "executable": "py", "platform": "x", "arch": "x", "hashseed": "0", "commit": "abc", "time": "now"}):
                    with patch.object(cee, "collect_dep_hashes", return_value={}):
                        with patch.object(cee, "collect_src_hashes", return_value={}):
                            with patch.object(cee, "OUTPUT_DIR", tmp_path / "out"):
                                rc = cee.main()

        out = capsys.readouterr().out
        assert "NOT-REPRODUCIBLE" in out

        json_files = list((tmp_path / "out").glob("execution-evidence-*.json"))
        report = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert report["reproducibility"] == "NOT-REPRODUCIBLE"


# ─── collect_execution_evidence：REPRODUCIBLE 斷言 ────────────────────────────

class TestCollectExecutionEvidenceReproducible:
    """驗收：兩次執行完全相同 → REPRODUCIBLE（確保 NOT-REPRODUCIBLE 不會誤報）。"""

    def test_identical_runs_produces_reproducible(self, tmp_path, capsys):
        r1 = _make_run_info(exit_code=0, summary="10 passed")
        r2 = _make_run_info(exit_code=0, summary="10 passed")
        cmp = _make_compare_result(exit_code=0, has_diff=False)

        with patch.object(cee, "run_once", side_effect=[(r1, tmp_path / "d1"), (r2, tmp_path / "d2")]):
            with patch.object(cee, "compare", return_value=cmp):
                with patch.object(cee, "collect_env", return_value={"python": "3.x", "executable": "py", "platform": "x", "arch": "x", "hashseed": "0", "commit": "abc", "time": "now"}):
                    with patch.object(cee, "collect_dep_hashes", return_value={}):
                        with patch.object(cee, "collect_src_hashes", return_value={}):
                            with patch.object(cee, "OUTPUT_DIR", tmp_path / "out"):
                                rc = cee.main()

        out = capsys.readouterr().out
        assert "REPRODUCIBLE" in out
        assert "NOT-REPRODUCIBLE" not in out

        json_files = list((tmp_path / "out").glob("execution-evidence-*.json"))
        report = json.loads(json_files[0].read_text(encoding="utf-8"))
        assert report["reproducibility"] == "REPRODUCIBLE"


# ─── verify_reproducibility.py：差異場景退出碼斷言 ────────────────────────────

class TestVerifyReproducibilityNotReproducible:
    """驗收：verify_reproducibility.py 偵測到差異時，exit code 非零且輸出 NOT-REPRODUCIBLE。"""

    def test_returns_nonzero_on_difference(self, tmp_path, capsys, monkeypatch):
        """run_test 兩次都成功，但 compare_test_runs.main() 回傳 1（有差異）→ return 1。"""
        monkeypatch.setattr(sys, "argv", ["verify_reproducibility.py"])

        def fake_run_test(run_dir, pytest_args):
            run_dir.mkdir(parents=True, exist_ok=True)
            return True

        fake_compare_result = {
            "has_differences": True,
            "sections": {},
            "dir_a": str(tmp_path / "a"),
            "dir_b": str(tmp_path / "b"),
        }

        with patch.object(vr, "run_test", side_effect=fake_run_test):
            with patch("scripts.verify_reproducibility.subprocess.run") as mock_cmp:
                mock_cmp.return_value = subprocess.CompletedProcess(
                    args=[], returncode=1,
                    stdout=json.dumps(fake_compare_result),
                    stderr="",
                )
                with patch("scripts.verify_reproducibility.Path") as MockPath:
                    fake_script = tmp_path / "compare_test_runs.py"
                    fake_script.write_text("# fake", encoding="utf-8")
                    MockPath.return_value.parent.__truediv__ = lambda self, x: fake_script
                    MockPath.return_value.parent.__truediv__ = lambda self, x: fake_script

                    rc = vr.main()

        assert rc == 1, (
            "verify_reproducibility.py 偵測到差異時應 return 1，"
            f"但實際 return 為 {rc}"
        )

        captured = capsys.readouterr()
        assert "NOT-REPRODUCIBLE" in captured.err, (
            "輸出 stderr 中應包含 NOT-REPRODUCIBLE 字串"
        )

    def test_returns_zero_when_identical(self, tmp_path, capsys, monkeypatch):
        """run_test 兩次都成功且 compare exit=0 → return 0。"""
        monkeypatch.setattr(sys, "argv", ["verify_reproducibility.py"])

        def fake_run_test(run_dir, pytest_args):
            run_dir.mkdir(parents=True, exist_ok=True)
            return True

        fake_compare_result = {
            "has_differences": False,
            "sections": {},
            "dir_a": str(tmp_path / "a"),
            "dir_b": str(tmp_path / "b"),
        }

        with patch.object(vr, "run_test", side_effect=fake_run_test):
            with patch("scripts.verify_reproducibility.subprocess.run") as mock_cmp:
                mock_cmp.return_value = subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout=json.dumps(fake_compare_result),
                    stderr="",
                )
                with patch("scripts.verify_reproducibility.Path") as MockPath:
                    fake_script = tmp_path / "compare_test_runs.py"
                    fake_script.write_text("# fake", encoding="utf-8")
                    MockPath.return_value.parent.__truediv__ = lambda self, x: fake_script
                    MockPath.return_value.parent.__truediv__ = lambda self, x: fake_script

                    rc = vr.main()

        assert rc == 0
        captured = capsys.readouterr()
        assert "REPRODUCIBLE" in captured.out
        assert "NOT-REPRODUCIBLE" not in captured.out + captured.err

    def test_returns_nonzero_when_any_run_fails(self, tmp_path, capsys, monkeypatch):
        """第一次成功、第二次失敗 → NOT-REPRODUCIBLE。"""
        monkeypatch.setattr(sys, "argv", ["verify_reproducibility.py"])

        call_count = 0

        def fake_run_test(run_dir, pytest_args):
            nonlocal call_count
            run_dir.mkdir(parents=True, exist_ok=True)
            call_count += 1
            # 第二次失敗時需建立 stderr.txt 供錯誤訊息讀取
            if call_count == 2:
                (run_dir / "stderr.txt").write_text("simulated error", encoding="utf-8")
            return call_count == 1  # 第一次 True，第二次 False

        with patch.object(vr, "run_test", side_effect=fake_run_test):
            rc = vr.main()

        assert rc == 1
        captured = capsys.readouterr()
        # 執行失敗路徑印出「錯誤」而非「NOT-REPRODUCIBLE」（後者僅在 compare 失敗時印出）
        assert "錯誤" in captured.err or "NOT-REPRODUCIBLE" in captured.err


# ─── compare_test_runs.py：差異場景退出碼斷言 ──────────────────────────────────

class TestCompareTestRunsDiffersOnExecution:
    """驗收：compare_test_runs.py 在 coverage 差異時 exit=1，相同時 exit=0。"""

    def test_exit_code_1_when_coverage_differs(self, tmp_path):
        cov_a = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="1000" lines-valid="100" lines-covered="80" line-rate="0.8"
          branches-valid="40" branches-covered="30" branch-rate="0.75" complexity="0">
  <packages><package name="lib" line-rate="0.8" branch-rate="0.75" complexity="0">
    <classes><class name="a.py" filename="a.py" complexity="0" line-rate="0.8" branch-rate="0.75">
      <methods/><lines/></class></classes>
  </package></packages>
</coverage>"""
        cov_b = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="2000" lines-valid="100" lines-covered="90" line-rate="0.9"
          branches-valid="40" branches-covered="35" branch-rate="0.875" complexity="0">
  <packages><package name="lib" line-rate="0.9" branch-rate="0.875" complexity="0">
    <classes><class name="a.py" filename="a.py" complexity="0" line-rate="0.9" branch-rate="0.875">
      <methods/><lines/></class></classes>
  </package></packages>
</coverage>"""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "coverage.xml").write_text(cov_a, encoding="utf-8")
        (dir_b / "coverage.xml").write_text(cov_b, encoding="utf-8")

        import scripts.compare_test_runs as ctr
        rc = ctr.main([str(dir_a), str(dir_b)])
        assert rc == 1, "coverage 不同時 compare_test_runs.main() 應回傳 1"

        report_json = ctr.compare_test_runs(str(dir_a), str(dir_b))
        assert report_json["has_differences"] is True, (
            "compare_test_runs() 回傳的 report 應標記 has_differences=True"
        )

    def test_exit_code_0_when_coverage_identical(self, tmp_path):
        cov = """<?xml version="1.0" ?>
<coverage version="7.14.1" timestamp="1000" lines-valid="100" lines-covered="80" line-rate="0.8"
          branches-valid="40" branches-covered="30" branch-rate="0.75" complexity="0">
  <packages><package name="lib" line-rate="0.8" branch-rate="0.75" complexity="0">
    <classes><class name="a.py" filename="a.py" complexity="0" line-rate="0.8" branch-rate="0.75">
      <methods/><lines/></class></classes>
  </package></packages>
</coverage>"""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        (dir_a / "coverage.xml").write_text(cov, encoding="utf-8")
        (dir_b / "coverage.xml").write_text(cov, encoding="utf-8")

        import scripts.compare_test_runs as ctr
        rc = ctr.main([str(dir_a), str(dir_b)])
        assert rc == 0, "coverage 相同時 compare_test_runs.main() 應回傳 0"

        report_json = ctr.compare_test_runs(str(dir_a), str(dir_b))
        assert report_json["has_differences"] is False
