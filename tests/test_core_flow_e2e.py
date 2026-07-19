# -*- coding: utf-8 -*-
"""核心流程端到端 runner 單元測試。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("result_question", "summary_prompt", "summary_question"),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
        (True, True, True),
    ],
    ids=["149-to-151", "152-to-154", "154-to-156", "paths-present"],
)
def test_strip_volatile_optional_path_branches(
    result_question, summary_prompt, summary_question
):
    import scripts.run_core_flow_e2e as e2e

    summary = {"total_questions": 1}
    result = {"id": 1, "failures": ["F01"]}
    if result_question:
        result["question_file"] = "root/輸入 資料/題庫.jsonl"
    if summary_prompt:
        summary["prompt_file"] = "root/輸入 資料/提示詞.md"
    if summary_question:
        summary["question_file"] = "root/輸入 資料/題庫.jsonl"

    clean_summary, clean_results = e2e._strip_volatile(summary, [result])

    assert ("question_file" in clean_results[0]) is result_question
    assert ("prompt_file" in clean_summary) is summary_prompt
    assert ("question_file" in clean_summary) is summary_question


@pytest.mark.parametrize("cache_enabled", [True, False], ids=["cache-present", "202-to-206"])
def test_core_evaluation_cache_directory_branches(tmp_path, monkeypatch, cache_enabled):
    import scripts.run_core_flow_e2e as e2e

    monkeypatch.chdir(tmp_path)
    if not cache_enabled:
        monkeypatch.setattr(e2e.evaluate, "save_cached_result", lambda *_args: None)

    result = e2e._run_core_evaluation(tmp_path)

    assert result["repeat_identical"] is True
    assert (tmp_path / ".cache").exists() is cache_enabled


def test_run_core_flow_e2e_spec_ok_and_stable_digest():
    import scripts.run_core_flow_e2e as e2e

    first = e2e.run_e2e()
    second = e2e.run_e2e()

    assert first["spec_ok"] is True
    assert first["spec_failures"] == []
    assert first["exit_code"] == 0
    assert first["comparable_digest"] == second["comparable_digest"]
    assert (
        first["comparable"]["evaluation"]["summary"]["average_score"] == 79.0
    )
    assert first["comparable"]["gatekeeper"]["valid_prompt"]["passed"] is True
    assert first["comparable"]["gatekeeper"]["short_prompt"]["passed"] is False


def test_run_core_flow_e2e_cli_writes_out(tmp_path):
    out = tmp_path / "result.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "run_core_flow_e2e.py"),
            "--out",
            str(out),
            "--quiet",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["spec_ok"] is True
    assert payload["exit_code"] == 0
    assert len(payload["comparable_digest"]) == 64
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    assert summary["spec_ok"] is True
    assert summary["comparable_digest"] == payload["comparable_digest"]


def test_main_relative_out_creates_missing_parent(monkeypatch, tmp_path, capsys):
    import scripts.run_core_flow_e2e as e2e

    monkeypatch.setattr(e2e, "PROJECT_ROOT", tmp_path)
    relative_out = Path("evidence") / "core-flow.json"

    assert e2e.main(["--quiet", "--out", str(relative_out)]) == 0

    payload = json.loads((tmp_path / relative_out).read_text(encoding="utf-8"))
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["spec_ok"] is True
    assert summary["comparable_digest"] == payload["comparable_digest"]


def test_main_cleanup_ignores_created_parent_rmdir_error(monkeypatch, tmp_path):
    import scripts.run_core_flow_e2e as e2e

    monkeypatch.setattr(e2e, "PROJECT_ROOT", tmp_path)
    relative_out = Path("evidence") / "core-flow.json"
    out_path = tmp_path / relative_out
    original_write_text = e2e.Path.write_text
    original_rmdir = e2e.Path.rmdir

    def partial_write_then_fail(self, *args, **kwargs):
        original_write_text(self, *args, **kwargs)
        raise RuntimeError("核心步驟輸出寫入失敗")

    def fail_only_output_parent_rmdir(self):
        if self == out_path.parent:
            raise OSError("輸出目錄仍被使用")
        return original_rmdir(self)

    monkeypatch.setattr(e2e.Path, "write_text", partial_write_then_fail)
    monkeypatch.setattr(e2e.Path, "rmdir", fail_only_output_parent_rmdir)

    with pytest.raises(RuntimeError, match="核心步驟輸出寫入失敗"):
        e2e.main(["--quiet", "--out", str(relative_out)])

    assert not out_path.exists()
    assert out_path.parent.exists()
