# -*- coding: utf-8 -*-
"""腳本與 API 模組 CLI entrypoint 覆蓋測試（__main__ 路徑）。"""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
import runpy
import subprocess
import sys
from types import SimpleNamespace
import warnings

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

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


@pytest.mark.parametrize(
    ("system_name", "full_version", "major", "minor", "expected"),
    [
        ("Darwin", "3.10.14", 3, 10, ("macOS", "3.10.14", "3.10")),
        ("Linux", "3.11.9", 3, 11, ("Linux", "3.11.9", "3.11")),
        ("macOS", "3.12.4", 3, 12, ("macOS", "3.12.4", "3.12")),
    ],
)
def test_test_matrix_runtime_normalizes_platform_and_version(
    monkeypatch, system_name, full_version, major, minor, expected
):
    import scripts.run_test_matrix as matrix

    monkeypatch.setattr(matrix.platform, "system", lambda: system_name)
    monkeypatch.setattr(matrix.platform, "python_version", lambda: full_version)
    monkeypatch.setattr(matrix.sys, "version_info", SimpleNamespace(major=major, minor=minor))

    assert matrix._runtime() == expected


@pytest.mark.parametrize(
    ("runtime_platform", "runtime_minor"),
    [
        (platform_name, python_minor)
        for platform_name in ("Linux", "macOS")
        for python_minor in ("3.10", "3.11", "3.12")
    ],
)
def test_test_matrix_runs_every_supported_combination_and_reports_runtime(
    monkeypatch, capsys, runtime_platform, runtime_minor
):
    import scripts.run_test_matrix as matrix

    calls = []
    full_version = f"{runtime_minor}.9"
    missing_key = {
        "errors": [{"name": "MINIMAX_API_KEY"}],
        "checks": [{"name": "Python version", "passed": True}],
    }

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[-1] == "--json":
            return subprocess.CompletedProcess(command, 1, json.dumps(missing_key), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(matrix, "_runtime", lambda: (runtime_platform, full_version, runtime_minor))
    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    assert matrix.main(["--platform", runtime_platform, "--python-version", runtime_minor]) == 0
    rows = _matrix_rows(capsys.readouterr().out)

    assert [row["test_set"] for row in rows] == ["M1", "M2", "M3", "M4", "M5", "M6", "ALL"]
    assert all(row["platform"] == runtime_platform for row in rows)
    assert all(row["python_version"] == full_version for row in rows)
    assert all(row["exit_code"] == 0 for row in rows)
    assert len(calls) == 7
    assert all(command[0] == sys.executable for command in calls)


def test_test_matrix_returns_first_failed_test_set_and_continues(monkeypatch, capsys):
    import scripts.run_test_matrix as matrix

    calls = []
    exit_codes = {"M3": 5, "M5": 8}

    def fake_run_pytest(test_set, tests):
        calls.append((test_set, tests))
        return exit_codes.get(test_set, 0)

    monkeypatch.setattr(matrix, "_runtime", lambda: ("Linux", "3.11.9", "3.11"))
    monkeypatch.setattr(matrix, "_run_m1", lambda: 0)
    monkeypatch.setattr(matrix, "_run_pytest", fake_run_pytest)

    assert matrix.main(["--platform", "Linux", "--python-version", "3.11"]) == 5
    rows = _matrix_rows(capsys.readouterr().out)
    assert [row["exit_code"] for row in rows] == [0, 0, 5, 0, 8, 0, 5]
    assert calls == list(matrix.PYTEST_SETS)


def test_test_matrix_rejects_runtime_version_mismatch(monkeypatch, capsys):
    import scripts.run_test_matrix as matrix

    monkeypatch.setattr(matrix, "_runtime", lambda: ("macOS", "3.11.9", "3.11"))
    monkeypatch.setattr(
        matrix.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不應執行測試")),
    )

    assert matrix.main(["--platform", "macOS", "--python-version", "3.12"]) == 2
    rows = _matrix_rows(capsys.readouterr().out)
    assert [(row["test_set"], row["exit_code"]) for row in rows] == [("M1", 2), ("ALL", 2)]


def test_test_matrix_rejects_invalid_python_version(monkeypatch, capsys):
    import scripts.run_test_matrix as matrix

    monkeypatch.setattr(matrix, "_runtime", lambda: ("macOS", "3.11.9", "3.11"))
    monkeypatch.setattr(
        matrix.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不應執行測試")),
    )

    with pytest.raises(SystemExit) as exc_info:
        matrix.main(["--platform", "macOS", "--python-version", "3.13"])

    assert exc_info.value.code == 2
    assert "invalid choice: '3.13'" in capsys.readouterr().err


def test_test_matrix_entrypoint_propagates_unsupported_runtime_combination():
    import scripts.run_test_matrix as matrix

    actual_platform, _, actual_minor = matrix._runtime()
    requested_platform = next(name for name in matrix.SUPPORTED_PLATFORMS if name != actual_platform)
    requested_minor = next(version for version in matrix.SUPPORTED_PYTHON_VERSIONS if version != actual_minor)

    output = run_module_capture_output(
        "scripts.run_test_matrix",
        ["--platform", requested_platform, "--python-version", requested_minor],
    )

    assert output["exit_code"] == 2
    assert [(row["test_set"], row["exit_code"]) for row in _matrix_rows(output["out"])] == [
        ("M1", 2),
        ("ALL", 2),
    ]
    assert "執行環境不符" in output["err"]


@pytest.mark.parametrize(("stdout", "returncode"), [(None, 7), ("not-json", 8)])
def test_test_matrix_preflight_invalid_output_propagates_failure(stdout, returncode):
    import scripts.run_test_matrix as matrix

    result = subprocess.CompletedProcess(["preflight"], returncode, stdout, "")

    assert matrix._preflight_exit_code(result) == returncode


def test_test_matrix_subprocess_start_error_becomes_failure(monkeypatch, capsys):
    import scripts.run_test_matrix as matrix

    monkeypatch.setattr(
        matrix.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("找不到執行檔")),
    )

    assert matrix._run_pytest("M2", ("tests/test_cross_platform.py",)) == 1
    assert "無法執行子程序：找不到執行檔" in capsys.readouterr().err


@pytest.mark.parametrize("path_type", (PurePosixPath, PureWindowsPath))
def test_test_matrix_writes_report_with_platform_path_parts(
    monkeypatch, tmp_path, capsys, path_type
):
    import scripts.run_test_matrix as matrix

    relative = path_type("矩陣 結果") / "nested" / "matrix.jsonl"
    report_path = tmp_path.joinpath(*relative.parts)
    monkeypatch.setenv("CI_MATRIX_ID", "W311")
    monkeypatch.setenv("CI_MATRIX_REPORT_PATH", str(report_path))

    matrix._emit("Windows", "3.11.9", "M2", ("tests/test_cross_platform.py",), 0)

    row = json.loads(report_path.read_text(encoding="utf-8"))
    assert row == _matrix_rows(capsys.readouterr().out)[0]
    assert row["matrix_id"] == "W311"


@pytest.mark.parametrize(
    ("stdout", "stderr", "expected_stdout", "expected_stderr"),
    [
        ("", "preflight warning", "", "preflight warning\n"),
        ("{}\n", "preflight warning\n", "{}\n", "preflight warning\n"),
    ],
)
def test_test_matrix_m1_forwards_preflight_output_once(
    monkeypatch, capsys, stdout, stderr, expected_stdout, expected_stderr
):
    import scripts.run_test_matrix as matrix

    results = iter(
        [
            subprocess.CompletedProcess(["pytest"], 0, "", ""),
            subprocess.CompletedProcess(["preflight"], 0, stdout, stderr),
        ]
    )
    monkeypatch.setattr(matrix.subprocess, "run", lambda *args, **kwargs: next(results))

    assert matrix._run_m1() == 0
    captured = capsys.readouterr()
    assert captured.out == expected_stdout
    assert captured.err == expected_stderr


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

    monkeypatch.setattr(matrix, "_runtime", lambda: ("macOS", "3.11.9", "3.11"))
    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    assert matrix.main(["--platform", "macOS", "--python-version", "3.11"]) == 1
    rows = _matrix_rows(capsys.readouterr().out)
    assert rows[0]["test_set"] == "M1" and rows[0]["exit_code"] == 1
    assert rows[-1]["test_set"] == "ALL" and rows[-1]["exit_code"] == 1
    assert len(calls) == 7
