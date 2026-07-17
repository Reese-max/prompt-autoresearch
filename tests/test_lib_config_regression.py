"""回歸測試：環境變數缺失/格式錯誤/最終驗證的三條路徑。

覆蓋：
  1. 環境變數缺失時走預設值。
  2. 環境變數格式錯誤時觸發回退（raise ValueError）。
  3. 回退後最終生效值必須通過同一套合法性檢查，拒絕不合法設定。
  4. 預設值為非法值（非正數）時，validate_config 必須攔截並拋出 ValueError。
"""
import copy
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
def _clean_config(tmp_path, monkeypatch):
    """每個測試使用隔離的 config 狀態與環境變數。"""
    monkeypatch.setattr(config, "_CONFIG", None)
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "_CONFIG_PATH", str(tmp_path / "config.json"))
    yield
    monkeypatch.setattr(config, "_CONFIG", None)


def test_missing_env_var_falls_back_to_default():
    """場景 1：環境變數缺失時，使用預設值。"""
    cfg = config.get_all()

    assert cfg["api"]["timeout"] == config._DEFAULTS["api"]["timeout"]
    assert cfg["parallel"]["smoke"] == config._DEFAULTS["parallel"]["smoke"]
    assert cfg["parallel"]["dev"] == config._DEFAULTS["parallel"]["dev"]
    assert cfg["parallel"]["holdout"] == config._DEFAULTS["parallel"]["holdout"]
    assert cfg["thresholds"]["max_candidate_length"] == config._DEFAULTS["thresholds"]["max_candidate_length"]


def test_invalid_env_var_raises_and_falls_back_to_default(monkeypatch):
    """場景 2：環境變數格式錯誤時被驗證攔下，清理後回退至預設值且通過合法性檢查。"""
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_TIMEOUT"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["api"]["timeout"] == config._DEFAULTS["api"]["timeout"]
    assert isinstance(cfg["api"]["timeout"], int)


def test_fallback_final_value_must_pass_validation(monkeypatch):
    """場景 3：回退後最終生效值必須通過合法性檢查，拒絕不合法設定。"""
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")

    with pytest.raises(ValueError):
        config.get_all()

    # 清理後重新載入，確認無污染且最終值合法。
    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)

    cfg = config.get_all()

    assert isinstance(cfg["api"]["timeout"], (int, float))
    assert isinstance(cfg["parallel"]["smoke"], (int, float))
    assert isinstance(cfg["parallel"]["dev"], (int, float))
    assert isinstance(cfg["parallel"]["holdout"], (int, float))
    assert isinstance(cfg["thresholds"]["max_candidate_length"], (int, float))
    assert isinstance(cfg["api"]["retry"], (int, float))
    assert isinstance(cfg["archive"]["max_versions"], (int, float))
    assert isinstance(cfg["multi_candidate"]["count"], (int, float))
    assert isinstance(cfg["api"]["rate_limit"]["max_concurrent"], (int, float))
    assert isinstance(cfg["api"]["rate_limit"]["min_interval_ms"], (int, float))
    assert isinstance(cfg["thresholds"]["smoke_allowed_drop"], (int, float))
    assert isinstance(cfg["thresholds"]["smoke_min_score"], (int, float))
    assert isinstance(cfg["thresholds"]["dev_min_improvement"], (int, float))
    assert isinstance(cfg["thresholds"]["holdout_max_drop"], (int, float))
    assert isinstance(cfg["thresholds"]["type_max_regression"], (int, float))
    assert isinstance(cfg["thresholds"]["word_rate_min"], (int, float))


def test_file_valid_override_plus_env_invalid_same_key_rejected(tmp_path, monkeypatch):
    """場景 4：config.json 有效覆蓋 timeout，env var 無效覆寫同 key → 驗證攔下，清理後回歸 defaults。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"timeout": 300}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_CONFIG_PATH", str(config_file))
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_TIMEOUT"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["api"]["timeout"] == 300
    assert isinstance(cfg["api"]["timeout"], int)


# ── 場景 5：monkeypatch _DEFAULTS 為非法值，缺失環境變數回退預設後仍被驗證攔截 ──


def test_invalid_default_api_timeout_zero_raises(monkeypatch):
    """monkeypatch _DEFAULTS 設 api.timeout=0，無環境變數覆蓋時 get() 必須驗證攔截。"""
    modified = copy.deepcopy(config._DEFAULTS)
    modified["api"]["timeout"] = 0
    monkeypatch.setattr(config, "_DEFAULTS", modified)

    with pytest.raises(ValueError, match="api.timeout"):
        config.get_all()


def test_invalid_default_parallel_smoke_negative_raises(monkeypatch):
    """monkeypatch _DEFAULTS 設 parallel.smoke=-1，無環境變數覆蓋時 get() 必須驗證攔截。"""
    modified = copy.deepcopy(config._DEFAULTS)
    modified["parallel"]["smoke"] = -1
    monkeypatch.setattr(config, "_DEFAULTS", modified)

    with pytest.raises(ValueError, match="parallel.smoke"):
        config.get_all()


def test_invalid_default_max_candidate_length_zero_raises(monkeypatch):
    """monkeypatch _DEFAULTS 設 thresholds.max_candidate_length=0，無環境變數覆蓋時 get() 必須驗證攔截。"""
    modified = copy.deepcopy(config._DEFAULTS)
    modified["thresholds"]["max_candidate_length"] = 0
    monkeypatch.setattr(config, "_DEFAULTS", modified)

    with pytest.raises(ValueError, match="thresholds.max_candidate_length"):
        config.get_all()


# ── L166 路徑覆蓋：_STRING_SCHEMA 值為非字串型別時必須拒絕 ──────────────


@pytest.mark.parametrize(
    "bad_value",
    [123, True, [1, 2], {"k": "v"}],
    ids=["int", "bool", "list", "dict"],
)
def test_string_schema_rejects_non_string_type(tmp_path, bad_value):
    """覆蓋 lib/config.py L166：_STRING_SCHEMA 欄位收到非字串型別時 raise ValueError。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"url": bad_value}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"api\.url=.*型別不符，期望 str"):
        config.get_all()
