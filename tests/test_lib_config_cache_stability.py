"""鎖定設定載入失敗後的快取回復行為。"""

import json
from pathlib import Path

import pytest

import lib.config as config


CONFIG_ENV_KEYS = [
    "MINIMAX_API_KEY",
    "AUTORESEARCH_API_URL",
    "AUTORESEARCH_API_MODEL",
    "AUTORESEARCH_API_TIMEOUT",
    "AUTORESEARCH_SMOKE_PARALLEL",
    "AUTORESEARCH_DEV_PARALLEL",
    "AUTORESEARCH_HOLDOUT_PARALLEL",
    "AUTORESEARCH_MAX_CANDIDATE_LENGTH",
]


@pytest.fixture(autouse=True)
def _clean_config_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_CONFIG", None)
    monkeypatch.setattr(config, "_CONFIG_PATH", str(tmp_path / "config.json"))
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    monkeypatch.setattr(config, "_CONFIG", None)


def test_failed_config_load_cannot_stale_cache_when_env_fixed_later():
    """驗證載入失敗後，修正環境變數時可立即重載，不會卡在舊快取。"""
    env_key = "AUTORESEARCH_API_TIMEOUT"
    config.os.environ[env_key] = "bad-number"

    with pytest.raises(ValueError, match=env_key):
        config.get_all()

    config.os.environ[env_key] = "75"
    cfg = config.get_all()
    assert cfg["api"]["timeout"] == 75


def test_failed_config_load_with_valid_file_then_invalid_env_then_fixed_env_uses_file_and_env():
    """失敗時回補 `config.json` 有效值、再修正 env，最後應能重讀並套用 env。"""
    config_file = Path(config._CONFIG_PATH)
    config_file.write_text(
        json.dumps({"api": {"timeout": 420}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        config.os.environ["AUTORESEARCH_API_TIMEOUT"] = "not-a-number"
        config.get_all()

    config.os.environ["AUTORESEARCH_API_TIMEOUT"] = "99"
    cfg = config.get_all()
    assert cfg["api"]["timeout"] == 99
