# -*- coding: utf-8 -*-
"""腳本與 API 模組 CLI entrypoint 覆蓋測試（__main__ 路徑）。"""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
import runpy
import subprocess
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


def _matrix_rows(output):
    return [
        json.loads(line.removeprefix("MATRIX_RESULT "))
        for line in output.splitlines()
        if line.startswith("MATRIX_RESULT ")
    ]


def test_test_matrix_runs_every_set_and_reports_runtime(monkeypatch, capsys):
    import scripts.run_test_matrix as matrix

    calls = []
    missing_key = {
        "errors": [{"name": "MINIMAX_API_KEY"}],
        "checks": [{"name": "Python version", "passed": True}],
    }

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1] == "--json":
            return subprocess.CompletedProcess(command, 1, json.dumps(missing_key), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(matrix, "_runtime", lambda: ("Windows", "3.11.9", "3.11"))
    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    assert matrix.main(["--platform", "Windows", "--python-version", "3.11"]) == 0
    rows = _matrix_rows(capsys.readouterr().out)

    assert [row["test_set"] for row in rows] == ["M1", "M2", "M3", "M4", "M5", "M6", "ALL"]
    assert all(row["platform"] == "Windows" for row in rows)
    assert all(row["python_version"] == "3.11.9" for row in rows)
    assert all(row["exit_code"] == 0 for row in rows)
    assert len(calls) == 7
    assert all(command[0] == sys.executable for command in calls)


def test_test_matrix_rejects_runtime_mismatch(monkeypatch, capsys):
    import scripts.run_test_matrix as matrix

    monkeypatch.setattr(matrix, "_runtime", lambda: ("Windows", "3.11.9", "3.11"))
    monkeypatch.setattr(
        matrix.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不應執行測試")),
    )

    assert matrix.main(["--platform", "Linux", "--python-version", "3.11"]) == 2
    rows = _matrix_rows(capsys.readouterr().out)
    assert [(row["test_set"], row["exit_code"]) for row in rows] == [("M1", 2), ("ALL", 2)]


def test_test_matrix_does_not_hide_other_preflight_errors(monkeypatch, capsys):
    import scripts.run_test_matrix as matrix

    calls = []
    invalid_preflight = {
        "errors": [{"name": "baseline.meta hash"}],
        "checks": [{"name": "Python version", "passed": True}],
    }

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1] == "--json":
            return subprocess.CompletedProcess(command, 1, json.dumps(invalid_preflight), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(matrix, "_runtime", lambda: ("Windows", "3.11.9", "3.11"))
    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    assert matrix.main(["--platform", "Windows", "--python-version", "3.11"]) == 1
    rows = _matrix_rows(capsys.readouterr().out)
    assert rows[0]["test_set"] == "M1" and rows[0]["exit_code"] == 1
    assert rows[-1]["test_set"] == "ALL" and rows[-1]["exit_code"] == 1
    assert len(calls) == 7
