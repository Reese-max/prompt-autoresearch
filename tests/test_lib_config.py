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
def clean_config_state(monkeypatch):
    """每個測試使用隔離的 config 載入快取與環境變數。"""
    monkeypatch.setattr(config, "_CONFIG", None)
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    monkeypatch.setattr(config, "_CONFIG", None)


def _set_config_path(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    config._CONFIG_PATH = str(path)


def test_load_defaults_when_config_file_missing(tmp_path):
    _set_config_path(tmp_path / "not-exist.json")

    cfg = config.get_all()
    defaults = config._DEFAULTS

    assert cfg == defaults
    assert cfg["api"]["timeout"] == 180
    assert cfg["parallel"]["smoke"] == 6
    assert cfg["thresholds"]["dev_min_improvement"] == 2.0


def test_load_config_file_merge_overrides_defaults(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "api": {
                    "url": "https://override.example/v1",
                    "rate_limit": {
                        "max_concurrent": 2,
                    },
                },
                "parallel": {
                    "smoke": 2,
                },
                "extra": {
                    "enabled": True,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    cfg = config.get_all()

    assert cfg["api"]["url"] == "https://override.example/v1"
    assert cfg["api"]["rate_limit"]["max_concurrent"] == 2
    assert cfg["api"]["rate_limit"]["min_interval_ms"] == 100
    assert cfg["parallel"]["smoke"] == 2
    assert cfg["extra"]["enabled"] is True


def test_environment_variables_override_file_and_types(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "parallel": {
                    "smoke": 1,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    # env variables should have higher priority and keep type conversion behavior
    for key, value in {
        "MINIMAX_API_KEY": "secret-key",
        "AUTORESEARCH_API_URL": "https://env.example/v2",
        "AUTORESEARCH_API_MODEL": "MiniMax-M2.9",
        "AUTORESEARCH_API_TIMEOUT": "75",
        "AUTORESEARCH_SMOKE_PARALLEL": "18",
        "AUTORESEARCH_MAX_CANDIDATE_LENGTH": "777.7",
    }.items():
        config.os.environ[key] = value

    cfg = config.get_all()

    assert cfg["api"]["url"] == "https://env.example/v2"
    assert cfg["api"]["model"] == "MiniMax-M2.9"
    assert cfg["api"]["api_key"] == "secret-key"
    assert cfg["api"]["timeout"] == 75
    assert isinstance(cfg["api"]["timeout"], int)
    assert cfg["parallel"]["smoke"] == 18
    assert isinstance(cfg["parallel"]["smoke"], int)
    assert cfg["thresholds"]["max_candidate_length"] == 777.7
    assert isinstance(cfg["thresholds"]["max_candidate_length"], float)


def test_get_section_and_cache_hit_without_reload(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "parallel": {
                    "smoke": 3,
                    "dev": 12,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    section = config.get_section("parallel")
    assert section == {"smoke": 3, "dev": 12, "holdout": 24}

    first = config._load_config()
    config_file.write_text(
        json.dumps(
            {
                "parallel": {
                    "smoke": 8,
                    "dev": 99,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    second = config._load_config()

    # 快取命中：修改來源檔不應影響已快取設定
    assert first is second
    assert first["parallel"]["smoke"] == 3


def test_reload_after_cache_cleared_and_error_branch_for_invalid_json(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "parallel": {
                    "dev": 9,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    initial = config._load_config()
    assert initial["parallel"]["dev"] == 9

    # 先清掉快取，且設定檔改為不合法 JSON，確認重載走 fallback。
    config_file.write_text("{invalid-json", encoding="utf-8")
    config._CONFIG = None
    config.os.environ["AUTORESEARCH_DEV_PARALLEL"] = "33"

    fallback = config.get_all()
    assert fallback["parallel"]["dev"] == 33
    assert fallback["api"]["url"] == config._DEFAULTS["api"]["url"]
    assert isinstance(fallback["parallel"]["smoke"], int)
