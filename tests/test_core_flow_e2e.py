# -*- coding: utf-8 -*-
"""核心流程端到端 runner 單元測試。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
