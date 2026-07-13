# -*- coding: utf-8 -*-
"""腳本與 API 模組 CLI entrypoint 覆蓋測試（__main__ 路徑）。"""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
import runpy
import sys
import warnings

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_module_capture_output(module_name, argv=None, cwd=None):
    argv = argv or []
    old_argv = sys.argv[:]
    old_cwd = os.getcwd()
    old_paths = sys.path[:]

    out = StringIO()
    err = StringIO()
    sys.argv = [f"{module_name}.py", *argv]
    if cwd is not None:
        os.chdir(cwd)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    exit_code = 0
    try:
        with redirect_stdout(out), redirect_stderr(err):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                try:
                    runpy.run_module(module_name, run_name="__main__")
                except SystemExit as exc:
                    exit_code = exc.code
    finally:
        sys.path[:] = old_paths
        sys.argv = old_argv
        os.chdir(old_cwd)

    return {
        "exit_code": exit_code,
        "out": out.getvalue(),
        "err": err.getvalue(),
    }


def test_feedback_module_prints_summary():
    output = run_module_capture_output("api.feedback")
    assert output["exit_code"] == 0
    assert '"total_feedback"' in output["out"]


def test_server_module_help_prints_usage():
    output = run_module_capture_output("api.server", ["--help"])
    assert output["exit_code"] == 0
    assert "Prompt AutoResearch API" in output["out"]
    assert "--port PORT" in output["out"]


def test_analyze_runs_help_entrypoint():
    output = run_module_capture_output("scripts.analyze_runs", ["--help"])
    assert output["exit_code"] == 0
    assert "--question-file" in output["out"]


def test_backfill_candidate_scorecards_help_entrypoint():
    output = run_module_capture_output("scripts.backfill_candidate_scorecards", ["--help"])
    assert output["exit_code"] == 0
    assert "--force" in output["out"]


def test_evaluate_entrypoint_usage_error():
    output = run_module_capture_output("scripts.evaluate")
    assert output["exit_code"] == 1
    assert "用法:" in output["out"]


def test_experiment_report_help_entrypoint():
    output = run_module_capture_output("scripts.experiment_report", ["--help"])
    assert output["exit_code"] == 0
    assert "--out" in output["out"]


def test_generate_questions_entrypoint_writes_files(tmp_path):
    output = run_module_capture_output("scripts.generate_questions", cwd=tmp_path)
    assert output["exit_code"] == 0
    assert "Successfully wrote dev.jsonl" in output["out"]
    assert (tmp_path / "questions" / "dev.jsonl").exists()
    assert (tmp_path / "questions" / "holdout.jsonl").exists()
    assert (tmp_path / "questions" / "final.jsonl").exists()


def test_leaderboard_help_entrypoint():
    output = run_module_capture_output("scripts.leaderboard", ["--help"])
    assert output["exit_code"] == 0
    assert "--limit" in output["out"]
