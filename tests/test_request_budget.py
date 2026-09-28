"""Offline regressions for the shared provider-attempt budget."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError

import pytest

from lib import api
from lib.request_budget import BudgetExhausted, create_budget, read_budget, reserve_attempt


def test_attempt_cap_is_atomic_across_threads_and_processes(tmp_path):
    ledger = tmp_path / "requests.sqlite3"
    create_budget(str(ledger), 3)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: _try_reserve(str(ledger)), range(8)))
    assert results.count(True) == 3
    assert results.count(False) == 5
    assert read_budget(str(ledger)) == {"max_attempts": 3, "used_attempts": 3}

    child = subprocess.run(
        [sys.executable, "-c", "from lib.request_budget import reserve_attempt; "
         f"reserve_attempt({str(ledger)!r})"],
        capture_output=True, text=True, check=False,
    )
    assert child.returncode != 0
    assert "BudgetExhausted" in child.stderr
    assert read_budget(str(ledger))["used_attempts"] == 3


def _try_reserve(path):
    try:
        reserve_attempt(path)
        return True
    except BudgetExhausted:
        return False


def test_api_retries_consume_quota_before_each_network_attempt(tmp_path, monkeypatch):
    ledger = tmp_path / "requests.sqlite3"
    create_budget(str(ledger), 2)
    monkeypatch.setenv("AUTORESEARCH_REQUEST_BUDGET_DB", str(ledger))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-only-key")
    monkeypatch.setattr(api, "get", lambda *args, **kwargs: {
        "retry": 4, "timeout": 1, "url": "https://example.invalid/model",
        "model": "test", "rate_limit": {"min_interval_ms": 0, "max_concurrent": 1},
    }.get(args[1], kwargs.get("default")))
    monkeypatch.setattr(api, "_rate_wait", lambda: None)
    monkeypatch.setattr(api.time, "sleep", lambda _seconds: None)
    attempts = []

    def fail_offline(*_args, **_kwargs):
        attempts.append(1)
        raise URLError("offline test")

    monkeypatch.setattr(api.urllib.request, "urlopen", fail_offline)
    with pytest.raises(api.APIBudgetExceeded):
        api.call_minimax("system", "user")
    assert len(attempts) == 2
    assert read_budget(str(ledger))["used_attempts"] == 2


def test_exhausted_quota_blocks_request_before_network(tmp_path, monkeypatch):
    ledger = tmp_path / "requests.sqlite3"
    create_budget(str(ledger), 1)
    reserve_attempt(str(ledger))
    monkeypatch.setenv("AUTORESEARCH_REQUEST_BUDGET_DB", str(ledger))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-only-key")
    monkeypatch.setattr(api, "_rate_wait", lambda: None)
    monkeypatch.setattr(
        api.urllib.request, "urlopen",
        lambda *_args, **_kwargs: pytest.fail("network was attempted after cap"),
    )
    with pytest.raises(api.APIBudgetExceeded):
        api.call_minimax("system", "user")
