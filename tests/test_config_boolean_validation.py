"""布林值驗證：multi_candidate.enabled 必須為 bool 型別。

覆蓋：
  1. multi_candidate.enabled 為非 bool 值時必須被 validate_config 拒絕。
  2. multi_candidate.enabled 為合法 bool 值時必須接受。
  3. env var MINIMAX_API_KEY 空字串（不在驗證範圍）的行為不受影響。
"""
import json

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
def _clean_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_CONFIG", None)
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "_CONFIG_PATH", str(tmp_path / "config.json"))
    yield
    monkeypatch.setattr(config, "_CONFIG", None)


def test_boolean_schema_rejects_non_bool_int(tmp_path):
    """multi_candidate.enabled 為整數 1 時必須被 validate_config 拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"multi_candidate": {"enabled": 1}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"multi_candidate\.enabled.*型別不符，期望 bool"):
        config.get_all()


def test_boolean_schema_rejects_non_bool_string(tmp_path):
    """multi_candidate.enabled 為字串 "yes" 時必須被 validate_config 拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"multi_candidate": {"enabled": "yes"}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"multi_candidate\.enabled.*型別不符，期望 bool"):
        config.get_all()


def test_boolean_schema_rejects_non_bool_none(tmp_path):
    """multi_candidate.enabled 為 null 時必須被 validate_config 拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"multi_candidate": {"enabled": None}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"multi_candidate\.enabled.*型別不符，期望 bool"):
        config.get_all()


def test_boolean_schema_accepts_true(tmp_path):
    """multi_candidate.enabled 為 True 時必須接受。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"multi_candidate": {"enabled": True}}),
        encoding="utf-8",
    )
    cfg = config.get_all()
    assert cfg["multi_candidate"]["enabled"] is True


def test_boolean_schema_accepts_false(tmp_path):
    """multi_candidate.enabled 為 False 時必須接受。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"multi_candidate": {"enabled": False}}),
        encoding="utf-8",
    )
    cfg = config.get_all()
    assert cfg["multi_candidate"]["enabled"] is False
