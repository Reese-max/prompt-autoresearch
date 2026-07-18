"""語意斷言：驗證配置異常處理的例外型別與訊息、fallback 值、衝突優先序。

涵蓋三大面向：
  1. 例外型別與訊息：validate_config 和 _apply_env_overrides 的 ValueError
     訊息必須精確包含 dotted_key 與實際值，讓除錯可追蹤。
  2. Fallback 值：無效設定被攔截後，最終生效值必須等於預設值（或檔案覆蓋值），
     且所有欄位必須通過同一套合法性檢查。
  3. 衝突優先序：環境變數 > config.json > _DEFAULTS，三層覆寫時每層的值
     必須精確反映該層來源。
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
    monkeypatch.setattr(config, "_CONFIG", None)
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "_CONFIG_PATH", str(tmp_path / "config.json"))
    yield
    monkeypatch.setattr(config, "_CONFIG", None)


# ══════════════════════════════════════════════════════════════════════════
# 1. 例外型別與訊息精確驗證
# ══════════════════════════════════════════════════════════════════════════


class TestExceptionMessages:
    """validate_config 產生的 ValueError 訊息必須精確包含 dotted_key 與 repr(value)。"""

    def test_numeric_type_mismatch_message_includes_key_and_repr(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"timeout": "bad"}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.timeout=.+型別不符，期望 .+int"):
            config.get_all()

    def test_numeric_nan_message_includes_key(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"timeout": float("nan")}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.timeout=.+不允許 NaN 或 inf"):
            config.get_all()

    def test_numeric_inf_message_includes_key(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"timeout": float("inf")}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.timeout=.+不允許 NaN 或 inf"):
            config.get_all()

    def test_negative_value_message_includes_must_be_positive(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"retry": -1}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.retry=.+必須為正數"):
            config.get_all()

    def test_zero_positive_key_message_includes_must_be_positive(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"parallel": {"smoke": 0}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"parallel\.smoke=.+必須為正數"):
            config.get_all()

    def test_string_type_mismatch_message_for_url(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"url": 123}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.url=.+型別不符，期望 str"):
            config.get_all()

    def test_string_empty_message_for_url(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"url": ""}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.url.+不可為空字串或純空白"):
            config.get_all()

    def test_string_invalid_protocol_message_for_url(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"url": "ftp://bad"}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.url=.+必須為有效的 http:// 或 https:// URL"):
            config.get_all()

    def test_string_empty_message_for_model(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"model": ""}}), encoding="utf-8")
        with pytest.raises(ValueError, match=r"api\.model.+不可為空字串或純空白"):
            config.get_all()

    def test_env_numeric_unparseable_message_includes_env_key(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "abc")
        with pytest.raises(ValueError, match=r"AUTORESEARCH_API_TIMEOUT=.+無法解析為數值"):
            config.get_all()

    def test_env_empty_string_message_includes_env_key(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "")
        with pytest.raises(ValueError, match=r"AUTORESEARCH_API_TIMEOUT.+不可為空字串"):
            config.get_all()

    def test_env_empty_url_message_includes_env_key(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_API_URL", "")
        with pytest.raises(ValueError, match=r"AUTORESEARCH_API_URL.+不可為空字串"):
            config.get_all()

    def test_env_empty_model_message_includes_env_key(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_API_MODEL", "")
        with pytest.raises(ValueError, match=r"AUTORESEARCH_API_MODEL.+不可為空字串"):
            config.get_all()


# ══════════════════════════════════════════════════════════════════════════
# 2. Fallback 值精確驗證
# ══════════════════════════════════════════════════════════════════════════


class TestFallbackValues:
    """無效設定被攔截後，fallback 值必須精確等於預設值或先前有效值。"""

    def test_invalid_timeout_fallback_exact_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "xyz")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
        cfg = config.get_all()
        assert cfg["api"]["timeout"] == 180
        assert type(cfg["api"]["timeout"]) is int

    def test_invalid_smoke_parallel_fallback_exact_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "xyz")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_SMOKE_PARALLEL", raising=False)
        cfg = config.get_all()
        assert cfg["parallel"]["smoke"] == 6
        assert type(cfg["parallel"]["smoke"]) is int

    def test_invalid_dev_parallel_fallback_exact_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "xyz")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_DEV_PARALLEL", raising=False)
        cfg = config.get_all()
        assert cfg["parallel"]["dev"] == 24
        assert type(cfg["parallel"]["dev"]) is int

    def test_invalid_holdout_parallel_fallback_exact_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_HOLDOUT_PARALLEL", "xyz")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_HOLDOUT_PARALLEL", raising=False)
        cfg = config.get_all()
        assert cfg["parallel"]["holdout"] == 24
        assert type(cfg["parallel"]["holdout"]) is int

    def test_invalid_max_candidate_length_fallback_exact_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "xyz")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", raising=False)
        cfg = config.get_all()
        assert cfg["thresholds"]["max_candidate_length"] == 550
        assert type(cfg["thresholds"]["max_candidate_length"]) is int

    def test_invalid_url_fallback_exact_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_API_URL", "ftp://bad")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_API_URL", raising=False)
        cfg = config.get_all()
        assert cfg["api"]["url"] == config._DEFAULTS["api"]["url"]

    def test_invalid_model_fallback_exact_default(self, monkeypatch):
        monkeypatch.setenv("AUTORESEARCH_API_MODEL", "")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_API_MODEL", raising=False)
        cfg = config.get_all()
        assert cfg["api"]["model"] == config._DEFAULTS["api"]["model"]

    def test_invalid_env_fallback_does_not_pollute_other_fields(self, monkeypatch):
        """一個欄位無效被攔截後，其他欄位的 fallback 值不受影響。"""
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "bad")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
        cfg = config.get_all()
        assert cfg["parallel"]["smoke"] == 6
        assert cfg["parallel"]["dev"] == 24
        assert cfg["parallel"]["holdout"] == 24
        assert cfg["api"]["url"] == config._DEFAULTS["api"]["url"]
        assert cfg["api"]["model"] == config._DEFAULTS["api"]["model"]
        assert cfg["thresholds"]["max_candidate_length"] == 550

    def test_invalid_env_fallback_result_passes_validate_config(self, monkeypatch):
        """fallback 後的 cfg 必須通過 validate_config 檢查。"""
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")
        with pytest.raises(ValueError):
            config.get_all()
        config._CONFIG = None
        monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
        cfg = config.get_all()
        config.validate_config(cfg)

    def test_file_invalid_fallback_exact_default(self, tmp_path):
        """config.json 提供無效值（負數 retry），攔截後回退至預設值。"""
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": {"retry": -5}}), encoding="utf-8")
        config._CONFIG_PATH = str(f)
        with pytest.raises(ValueError):
            config.get_all()

    def test_file_invalid_fallback_preserves_valid_file_overrides(self, tmp_path):
        """config.json 同時有無效值和有效值時，無效值攔截但有效覆蓋仍保留。"""
        f = tmp_path / "config.json"
        f.write_text(
            json.dumps({"api": {"retry": -5, "timeout": 300}}),
            encoding="utf-8",
        )
        config._CONFIG_PATH = str(f)
        with pytest.raises(ValueError):
            config.get_all()


# ══════════════════════════════════════════════════════════════════════════
# 3. 衝突優先序驗證：環境變數 > config.json > _DEFAULTS
# ══════════════════════════════════════════════════════════════════════════


class TestConflictPriority:
    """三層覆寫：env > file > defaults。每層來源的值必須精確反映。"""

    def test_defaults_used_when_no_file_no_env(self):
        cfg = config.get_all()
        assert cfg["api"]["timeout"] == 180
        assert cfg["parallel"]["smoke"] == 6
        assert cfg["api"]["url"] == config._DEFAULTS["api"]["url"]

    def test_file_overrides_defaults(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(
            json.dumps({"api": {"timeout": 300}, "parallel": {"smoke": 10}}),
            encoding="utf-8",
        )
        config._CONFIG_PATH = str(f)
        cfg = config.get_all()
        assert cfg["api"]["timeout"] == 300
        assert cfg["parallel"]["smoke"] == 10
        assert cfg["parallel"]["dev"] == 24
        assert cfg["api"]["url"] == config._DEFAULTS["api"]["url"]

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        f = tmp_path / "config.json"
        f.write_text(
            json.dumps({"api": {"timeout": 300}}),
            encoding="utf-8",
        )
        config._CONFIG_PATH = str(f)
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "999")
        cfg = config.get_all()
        assert cfg["api"]["timeout"] == 999
        assert type(cfg["api"]["timeout"]) is int

    def test_env_overrides_file_overrides_defaults(self, tmp_path, monkeypatch):
        """三層同時存在時：env=50 > file=300 > default=180 → 最終 50。"""
        f = tmp_path / "config.json"
        f.write_text(
            json.dumps({"api": {"timeout": 300}}),
            encoding="utf-8",
        )
        config._CONFIG_PATH = str(f)
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "50")
        cfg = config.get_all()
        assert cfg["api"]["timeout"] == 50

    def test_file_overrides_defaults_for_smoke_parallel(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"parallel": {"smoke": 99}}), encoding="utf-8")
        config._CONFIG_PATH = str(f)
        cfg = config.get_all()
        assert cfg["parallel"]["smoke"] == 99

    def test_env_overrides_file_for_smoke_parallel(self, tmp_path, monkeypatch):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"parallel": {"smoke": 99}}), encoding="utf-8")
        config._CONFIG_PATH = str(f)
        monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "42")
        cfg = config.get_all()
        assert cfg["parallel"]["smoke"] == 42

    def test_file_overrides_defaults_for_url(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(
            json.dumps({"api": {"url": "https://file.example/v1"}}),
            encoding="utf-8",
        )
        config._CONFIG_PATH = str(f)
        cfg = config.get_all()
        assert cfg["api"]["url"] == "https://file.example/v1"

    def test_env_overrides_file_for_url(self, tmp_path, monkeypatch):
        f = tmp_path / "config.json"
        f.write_text(
            json.dumps({"api": {"url": "https://file.example/v1"}}),
            encoding="utf-8",
        )
        config._CONFIG_PATH = str(f)
        monkeypatch.setenv("AUTORESEARCH_API_URL", "https://env.example/v2")
        cfg = config.get_all()
        assert cfg["api"]["url"] == "https://env.example/v2"

    def test_file_partial_override_preserves_other_defaults(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text(
            json.dumps({"parallel": {"smoke": 3}}),
            encoding="utf-8",
        )
        config._CONFIG_PATH = str(f)
        cfg = config.get_all()
        assert cfg["parallel"]["smoke"] == 3
        assert cfg["parallel"]["dev"] == 24
        assert cfg["parallel"]["holdout"] == 24
        assert cfg["api"]["timeout"] == 180
        assert cfg["api"]["retry"] == 4

    def test_env_override_does_not_affect_unset_keys(self, tmp_path, monkeypatch):
        f = tmp_path / "config.json"
        f.write_text(json.dumps({}), encoding="utf-8")
        config._CONFIG_PATH = str(f)
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "55")
        cfg = config.get_all()
        assert cfg["api"]["timeout"] == 55
        assert cfg["api"]["retry"] == 4
        assert cfg["parallel"]["smoke"] == 6

    def test_non_dict_file_value_does_not_crash_and_uses_default(self, tmp_path):
        """config.json 中 api 為非 dict 時，get() 以 default 回傳，不崩潰。"""
        f = tmp_path / "config.json"
        f.write_text(json.dumps({"api": "not-a-dict"}), encoding="utf-8")
        config._CONFIG_PATH = str(f)
        result = config.get("api", "timeout", 42)
        assert result == 42
