"""Real child-process controls for the physical matrix reporter's ownership.

This prevents accidental mock receipts in a parent's report, not hostile child
filesystem access. All temporary reports belong to these tests.
"""

import json
import os
import subprocess

import pytest

import scripts.run_test_matrix as matrix


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_real_mocked_matrix_tests_cannot_append_to_outer_physical_report(monkeypatch, tmp_path):
    report = tmp_path / "physical matrix 中文.jsonl"
    monkeypatch.setenv("CI_MATRIX_REPORT_PATH", str(report))
    monkeypatch.setenv("CI_MATRIX_ID", "owned-physical-probe")
    actual_platform, actual_version, _ = matrix._runtime()
    matrix._emit(actual_platform, actual_version, "M1", matrix.M1_TESTS, 0)

    # Existing tests exercise all nine mocked OS/Python combinations and failure
    # paths. They must still run, but must not become physical host receipts.
    tests = ("tests/test_script_entrypoints.py",)
    exit_code = matrix._run_pytest("M4", tests)
    matrix._emit(actual_platform, actual_version, "M4", tests, exit_code)

    assert exit_code == 0
    rows = read_rows(report)
    assert [row["test_set"] for row in rows] == ["M1", "M4"]
    assert all(row["platform"] == actual_platform and row["python_version"] == actual_version for row in rows)
    assert all(row["matrix_id"] == "owned-physical-probe" and row["exit_code"] == 0 for row in rows)
    assert os.environ["CI_MATRIX_REPORT_PATH"] == str(report)


def test_real_child_failure_still_reaches_parent_receipt(monkeypatch, tmp_path):
    report = tmp_path / "failed-physical.jsonl"
    child = tmp_path / "test_owned_child_failure.py"
    child.write_text("def test_intentional_failure():\n    assert False, 'owned negative control'\n", encoding="utf-8")
    monkeypatch.setenv("CI_MATRIX_REPORT_PATH", str(report))
    actual_platform, actual_version, _ = matrix._runtime()

    exit_code = matrix._run_pytest("M4", (str(child),))
    matrix._emit(actual_platform, actual_version, "M4", (str(child),), exit_code)
    matrix._emit(actual_platform, actual_version, "ALL", ("M4",), exit_code)

    assert exit_code == 1
    rows = read_rows(report)
    assert [(row["test_set"], row["exit_code"]) for row in rows] == [("M4", 1), ("ALL", 1)]
    assert all(row["platform"] == actual_platform for row in rows)


@pytest.mark.parametrize("report_key", ["CI_MATRIX_REPORT_PATH", "ci_matrix_report_path"])
def test_all_spawn_paths_strip_report_only_and_keep_parent_environment(monkeypatch, tmp_path, report_key):
    report_path = str(tmp_path / "outer.jsonl")
    monkeypatch.setenv(report_key, report_path)
    monkeypatch.setenv("MATRIX_TEST_UNRELATED", "preserve-this-setting")
    original = dict(os.environ)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "{}", "")

    monkeypatch.setattr(matrix.subprocess, "run", run)
    assert matrix._run_m1() == 0
    assert matrix._run_pytest("M2", ("tests/test_cross_platform.py",)) == 0
    assert matrix._run_pytest("M6", ()) == 0
    assert len(calls) == 4  # pytest --version, preflight, subset, complete suite.
    for _, kwargs in calls:
        assert not any(key.upper() == "CI_MATRIX_REPORT_PATH" for key in kwargs["env"])
        assert kwargs["env"]["MATRIX_TEST_UNRELATED"] == "preserve-this-setting"
        assert kwargs["cwd"] == matrix.PROJECT_ROOT
        assert kwargs["check"] is False
    assert calls[2][0][-1] == "--no-cov"
    assert calls[3][0][-1] == "-q" and "--no-cov" not in calls[3][0]
    assert dict(os.environ) == original


@pytest.mark.parametrize("explicit", [True, False, "bytes"])
def test_explicit_child_environment_is_copied_not_expanded(monkeypatch, explicit):
    source = {"CI_MATRIX_REPORT_PATH": "outer-only", "CHILD_SETTING": "keep"} if explicit else {}
    expected = {"CHILD_SETTING": "keep"} if explicit else {}
    if explicit == "bytes":
        source = {b"CI_MATRIX_REPORT_PATH": b"outer-only", b"CHILD_SETTING": b"keep"}
        expected = {b"CHILD_SETTING": b"keep"}
    before = dict(source)
    observed = []

    def run(command, **kwargs):
        observed.append(kwargs["env"])
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setenv("MATRIX_PARENT_ONLY", "not-an-explicit-child-setting")
    monkeypatch.setattr(matrix.subprocess, "run", run)
    assert matrix._run_command(["owned-command"], env=source).returncode == 7
    assert observed == [expected]
    assert source == before
