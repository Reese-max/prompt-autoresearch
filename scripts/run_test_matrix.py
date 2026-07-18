# -*- coding: utf-8 -*-
"""以目前 Python 解譯器執行跨平台／多版本測試矩陣。"""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PLATFORMS = ("Linux", "macOS", "Windows")
SUPPORTED_PYTHON_VERSIONS = ("3.10", "3.11", "3.12")
M1_TESTS = ("runtime", "pytest --version", "scripts/preflight.py --json")
PYTEST_SETS = (
    ("M2", ("tests/test_cross_platform.py",)),
    (
        "M3",
        (
            "tests/test_lib_io.py",
            "tests/test_lib_config.py",
            "tests/test_lib_config_regression.py",
            "tests/test_lib_config_cache_stability.py",
            "tests/test_config_semantic.py",
            "tests/test_config_integration.py",
            "tests/test_config_special_branch.py",
        ),
    ),
    (
        "M4",
        (
            "tests/test_gatekeeper.py",
            "tests/test_preflight.py",
            "tests/test_script_entrypoints.py",
        ),
    ),
    (
        "M5",
        (
            "tests/test_api_server.py",
            "tests/test_api_server_gaps.py",
            "tests/test_integration_server_feedback.py",
            "tests/test_lib_api.py",
            "tests/test_lib_api_error_contract.py",
            "tests/test_lib_api_external_failures.py",
            "tests/test_lib_api_http_status_codes.py",
            "tests/test_lib_api_line37_branch.py",
            "tests/test_lib_api_positive_verify.py",
            "tests/test_lib_api_rate_wait_branch.py",
        ),
    ),
    ("M6", ()),
)


def _runtime():
    system = platform.system()
    return (
        "macOS" if system == "Darwin" else system,
        platform.python_version(),
        f"{sys.version_info.major}.{sys.version_info.minor}",
    )


def _emit(platform_name, python_version, test_set, tests, exit_code):
    result = {
        "platform": platform_name,
        "python_version": python_version,
        "test_set": test_set,
        "tests": list(tests),
        "exit_code": exit_code,
    }
    print(f"MATRIX_RESULT {json.dumps(result, ensure_ascii=False)}", flush=True)


def _preflight_exit_code(result):
    if result.returncode == 0:
        return 0
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return result.returncode or 1

    errors = [error for error in payload.get("errors", ()) if error.get("name") != "MINIMAX_API_KEY"]
    python_check = next(
        (check for check in payload.get("checks", ()) if check.get("name") == "Python version"),
        {},
    )
    return 0 if python_check.get("passed") and not errors else result.returncode or 1


def _run_m1():
    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "--version"],
        cwd=PROJECT_ROOT,
        check=False,
    )
    preflight_result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "preflight.py"), "--json"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if preflight_result.stdout:
        print(preflight_result.stdout, end="" if preflight_result.stdout.endswith("\n") else "\n")
    if preflight_result.stderr:
        print(
            preflight_result.stderr,
            end="" if preflight_result.stderr.endswith("\n") else "\n",
            file=sys.stderr,
        )
    return pytest_result.returncode or _preflight_exit_code(preflight_result)


def _run_pytest(test_set, tests):
    command = [sys.executable, "-m", "pytest", *tests, "-q"]
    if test_set != "M6":
        command.append("--no-cov")
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def main(argv=None):
    actual_platform, actual_version, actual_minor = _runtime()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=SUPPORTED_PLATFORMS)
    parser.add_argument("--python-version", required=True, choices=SUPPORTED_PYTHON_VERSIONS)
    args = parser.parse_args(argv)

    if args.platform != actual_platform or args.python_version != actual_minor:
        _emit(actual_platform, actual_version, "M1", M1_TESTS, 2)
        _emit(actual_platform, actual_version, "ALL", ("M1",), 2)
        print(
            f"執行環境不符：指定 {args.platform}/Python {args.python_version}，"
            f"實際 {actual_platform}/Python {actual_version}",
            file=sys.stderr,
        )
        return 2

    results = []
    m1_code = _run_m1()
    results.append(m1_code)
    _emit(actual_platform, actual_version, "M1", M1_TESTS, m1_code)

    for test_set, tests in PYTEST_SETS:
        code = _run_pytest(test_set, tests)
        results.append(code)
        _emit(actual_platform, actual_version, test_set, tests or ("tests/",), code)

    overall = next((code for code in results if code), 0)
    _emit(actual_platform, actual_version, "ALL", ("M1", *(name for name, _ in PYTEST_SETS)), overall)
    return overall


if __name__ == "__main__":
    sys.exit(main())
