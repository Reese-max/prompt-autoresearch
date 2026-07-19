import json
import os
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
    """每個測試使用隔離的 config 載入快取、環境變數與路徑。"""
    monkeypatch.setattr(config, "_CONFIG", None)
    monkeypatch.setattr(config, "_CONFIG_PATH", config._CONFIG_PATH)
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


def test_environment_variables_override_file_and_types(tmp_path, monkeypatch):
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
        monkeypatch.setenv(key, value)

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


def test_reload_after_cache_cleared_and_error_branch_for_invalid_json(tmp_path, monkeypatch):
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
    monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "33")

    fallback = config.get_all()
    assert fallback["parallel"]["dev"] == 33
    assert fallback["api"]["url"] == config._DEFAULTS["api"]["url"]
    assert isinstance(fallback["parallel"]["smoke"], int)


def test_get_branch_L109_L111_dict_key_shifted_to_default(tmp_path):
    """覆蓋 lib/config.py L109-111：key 為 dict/list 時移入 default，回傳 section 或 default。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"parallel": {"smoke": 5}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _set_config_path(config_file)
    config._load_config()

    # L108→L109: key={} (dict), default=None → 觸發 default = key
    # L111: section 存在 → 回傳 section_data（dict 被當作 default 的副作用不影響結果）
    result_existing = config.get("parallel", {})
    assert result_existing == {"smoke": 5, "dev": 24, "holdout": 24}, (
        "L109-111: dict key 移為 default 後，section 存在時仍回傳完整 section_data"
    )

    # L111: section 不存在 → section_data={} (falsy) → 回傳 default（即被移入的 dict）
    result_missing = config.get("nonexistent_section", {})
    assert result_missing == {}, (
        "L109-111: section 不存在時，dict key 成為 default 並被回傳"
    )

    # L109: key=[] (list)、default=42 → default 非 None → 不覆寫
    # L111: 回傳 section_data
    result_list = config.get("parallel", [], default=42)
    assert result_list == {"smoke": 5, "dev": 24, "holdout": 24}, (
        "L109-111: list key + 已有 default 時不覆寫，回傳 section_data"
    )


def test_get_branch_L114_non_dict_section_returns_default(tmp_path):
    """覆蓋 lib/config.py L114：section_data 非 dict 時直接回傳 default，無驗證。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": "not_a_dict"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _set_config_path(config_file)
    config._load_config()

    # L112: isinstance("not_a_dict", dict) → False
    # L114: 直接回傳 default，不嘗試呼叫 .get()
    result = config.get("api", "timeout", 180)
    assert result == 180, "L114: section_data 非 dict 時回傳 default"

    # L114: 未指定 default → 回傳 None
    result_none = config.get("api", "url")
    assert result_none is None, "L114: section_data 非 dict 且 default=None 時回傳 None"


def test_invalid_numeric_env_var_raises_and_falls_back_to_default(tmp_path, monkeypatch):
    """數值型環境變數格式異常時，raise ValueError 拒絕無效值，清理後回退至預設值。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_TIMEOUT"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
    cfg = config.get_all()
    assert cfg["api"]["timeout"] == 180
    assert isinstance(cfg["api"]["timeout"], int)


def test_invalid_parallel_env_var_raises_and_falls_back_to_default(tmp_path, monkeypatch):
    """無效 smoke_parallel 被驗證攔下，清理後回退至預設值且通過合法性檢查。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "abc")

    with pytest.raises(ValueError, match="AUTORESEARCH_SMOKE_PARALLEL"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_SMOKE_PARALLEL", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["parallel"]["smoke"] == config._DEFAULTS["parallel"]["smoke"]
    assert isinstance(cfg["parallel"]["smoke"], int)


def test_invalid_max_candidate_length_env_var_raises_and_falls_back_to_default(tmp_path, monkeypatch):
    """無效 max_candidate_length 被驗證攔下，清理後回退至預設值且通過合法性檢查。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "not-a-number")

    with pytest.raises(ValueError, match="AUTORESEARCH_MAX_CANDIDATE_LENGTH"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["thresholds"]["max_candidate_length"] == config._DEFAULTS["thresholds"]["max_candidate_length"]
    assert isinstance(cfg["thresholds"]["max_candidate_length"], int)


def test_valid_file_config_plus_invalid_env_var_raises_and_falls_back_to_file_value(tmp_path, monkeypatch):
    """config.json 有效覆蓋 timeout，env var 以無效值覆寫同 key → env 優先但驗證攔下，回退至檔案值。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"timeout": 300}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_TIMEOUT"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["api"]["timeout"] == 300
    assert isinstance(cfg["api"]["timeout"], int)


# ── 預設值回退路徑驗證：config.json 空值/錯誤型別覆蓋 defaults ──────────


def test_empty_config_json_falls_back_to_defaults(tmp_path):
    """config.json 為空物件 {} 時，所有值應使用 _DEFAULTS。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    _set_config_path(config_file)

    cfg = config.get_all()

    assert cfg["api"]["timeout"] == config._DEFAULTS["api"]["timeout"]
    assert cfg["api"]["retry"] == config._DEFAULTS["api"]["retry"]
    assert cfg["parallel"]["smoke"] == config._DEFAULTS["parallel"]["smoke"]
    assert cfg["parallel"]["dev"] == config._DEFAULTS["parallel"]["dev"]
    assert cfg["thresholds"]["max_candidate_length"] == config._DEFAULTS["thresholds"]["max_candidate_length"]
    assert cfg["archive"]["max_versions"] == config._DEFAULTS["archive"]["max_versions"]
    assert cfg["multi_candidate"]["enabled"] is config._DEFAULTS["multi_candidate"]["enabled"]


def test_config_json_empty_string_overrides_numeric_default_validated(tmp_path):
    """config.json 提供空字串覆蓋數值 defaults，validate_config() 必須拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"timeout": ""}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="api.timeout"):
        config.get_all()


def test_config_json_wrong_type_for_numeric_override_validated(tmp_path):
    """config.json 提供字串覆蓋整數 defaults，validate_config() 必須拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"parallel": {"smoke": "not-a-number"}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="parallel.smoke"):
        config.get_all()


def test_config_json_null_for_numeric_default_validated(tmp_path):
    """config.json 提供 null 覆蓋數值 defaults，validate_config() 必須拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"thresholds": {"max_candidate_length": None}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="thresholds.max_candidate_length"):
        config.get_all()


# ── 預設值回退路徑驗證：環境變數空值 ─────────────────────────────────────


def test_empty_numeric_env_var_raises_value_error(tmp_path, monkeypatch):
    """數值型環境變數為空字串時，_apply_env_overrides 必須拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "")

    with pytest.raises(ValueError, match="不可為空字串"):
        config.get_all()


def test_whitespace_numeric_env_var_raises_value_error(tmp_path, monkeypatch):
    """數值型環境變數為純空白時，_apply_env_overrides 必須拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "   ")

    with pytest.raises(ValueError, match="不可為空字串"):
        config.get_all()


def test_empty_smoke_parallel_env_var_raises_and_falls_back_to_default(tmp_path, monkeypatch):
    """空字串 smoke_parallel 被拒絕後，回退至預設值且不污染 cfg。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_SMOKE_PARALLEL"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_SMOKE_PARALLEL", raising=False)
    cfg = config.get_all()
    assert cfg["parallel"]["smoke"] == config._DEFAULTS["parallel"]["smoke"]
    assert isinstance(cfg["parallel"]["smoke"], int)


def test_empty_dev_parallel_env_var_raises_and_falls_back_to_default(tmp_path, monkeypatch):
    """空字串 dev_parallel 被驗證攔下，raise 前不污染其他數值設定，清理後回退至預設值。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_DEV_PARALLEL"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_DEV_PARALLEL", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["parallel"]["dev"] == config._DEFAULTS["parallel"]["dev"]
    assert isinstance(cfg["parallel"]["dev"], int)
    assert cfg["parallel"]["smoke"] == config._DEFAULTS["parallel"]["smoke"]
    assert cfg["parallel"]["holdout"] == config._DEFAULTS["parallel"]["holdout"]


def test_empty_max_candidate_length_env_var_raises_and_falls_back_to_default(tmp_path, monkeypatch):
    """空字串 max_candidate_length 被驗證攔下，清理後回退至預設值且通過合法性檢查。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_MAX_CANDIDATE_LENGTH"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["thresholds"]["max_candidate_length"] == config._DEFAULTS["thresholds"]["max_candidate_length"]
    assert isinstance(cfg["thresholds"]["max_candidate_length"], int)


def test_empty_holdout_parallel_env_var_raises_and_falls_back_to_default(tmp_path, monkeypatch):
    """空字串 holdout_parallel 被驗證攔下，清理後回退至預設值且通過合法性檢查。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_HOLDOUT_PARALLEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_HOLDOUT_PARALLEL"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_HOLDOUT_PARALLEL", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["parallel"]["holdout"] == config._DEFAULTS["parallel"]["holdout"]
    assert isinstance(cfg["parallel"]["holdout"], int)


# ── L131 路徑覆蓋：正常 dict section + string key 的 get() 查詢 ─────────


def test_get_normal_dict_section_string_key_returns_value(tmp_path):
    """覆蓋 L131：section_data 為 dict 時，以 string key 查詢回傳對應值。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    _set_config_path(config_file)
    config._load_config()

    # L130: isinstance(section_data, dict) → True
    # L131: section_data.get("timeout", default) → 180
    result = config.get("api", "timeout")
    assert result == 180, "L131: dict section + string key 回傳對應值"
    assert isinstance(result, int)


def test_get_normal_dict_section_missing_key_returns_default(tmp_path):
    """覆蓋 L131：section_data 為 dict 時，key 不存在回傳 default。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({}), encoding="utf-8")
    _set_config_path(config_file)
    config._load_config()

    # L131: section_data.get("nonexistent_key", 42) → 42
    result = config.get("api", "nonexistent_key", 42)
    assert result == 42, "L131: 缺失 key 回傳 default"


def test_env_override_section_created_when_missing_from_cfg(monkeypatch):
    """覆蓋 L101-102：env_map 對應的 section 不在 cfg 時，自動建立空 dict 後寫入。"""
    # 直接呼叫 _apply_env_overrides，手動提供缺少 parallel section 的 cfg
    test_cfg = {"api": {"timeout": 180}}
    monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "99")

    config._apply_env_overrides(test_cfg)

    # L101: "parallel" not in test_cfg → True
    # L102: test_cfg["parallel"] = {} 後 test_cfg["parallel"]["dev"] = 99
    assert "parallel" in test_cfg, "L101-102: 缺失的 section 被自動建立"
    assert test_cfg["parallel"]["dev"] == 99, "L102: 建立後 env 值正確寫入"


# ── 環境變數格式錯誤驗證：nan / inf / 負數 / 零 / 空白 ────────────────


@pytest.mark.parametrize(
    "bad_value,description",
    [
        ("nan", "浮點非數"),
        ("inf", "無限大"),
        ("-1", "負數"),
        ("0", "零"),
        ("", "空字串"),
        ("   ", "純空白"),
    ],
    ids=["nan", "inf", "negative", "zero", "empty-string", "whitespace"],
)
def test_invalid_api_timeout_env_var_raises_value_error(monkeypatch, bad_value, description):
    """設定 AUTORESEARCH_API_TIMEOUT 為各種格式錯誤值後重置 _CONFIG，
    呼叫 get('api','timeout') 必須全部拋出 ValueError。"""
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", bad_value)

    config._CONFIG = None

    with pytest.raises(ValueError):
        config.get("api", "timeout")


# ── 字串設定驗證：AUTORESEARCH_API_URL / AUTORESEARCH_API_MODEL ──────────


def test_empty_api_url_env_var_raises_value_error(tmp_path, monkeypatch):
    """空字串 AUTORESEARCH_API_URL 必須被 _apply_env_overrides 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_URL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_URL.*不可為空字串"):
        config.get_all()


def test_whitespace_api_url_env_var_raises_value_error(tmp_path, monkeypatch):
    """純空白 AUTORESEARCH_API_URL 必須被 _apply_env_overrides 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_URL", "   ")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_URL.*不可為空字串"):
        config.get_all()


def test_empty_api_model_env_var_raises_value_error(tmp_path, monkeypatch):
    """空字串 AUTORESEARCH_API_MODEL 必須被 _apply_env_overrides 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_MODEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_MODEL.*不可為空字串"):
        config.get_all()


def test_whitespace_api_model_env_var_raises_value_error(tmp_path, monkeypatch):
    """純空白 AUTORESEARCH_API_MODEL 必須被 _apply_env_overrides 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_MODEL", "   ")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_MODEL.*不可為空字串"):
        config.get_all()


def test_invalid_api_url_format_env_var_raises_value_error(tmp_path, monkeypatch):
    """非 http/https 格式的 AUTORESEARCH_API_URL 必須被 validate_config 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_URL", "ftp://example.com/api")

    with pytest.raises(ValueError, match="api.url.*http://.*https://"):
        config.get_all()


def test_invalid_api_url_no_protocol_env_var_raises_value_error(tmp_path, monkeypatch):
    """無協議前綴的 AUTORESEARCH_API_URL 必須被 validate_config 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_URL", "example.com/api")

    with pytest.raises(ValueError, match="api.url.*http://.*https://"):
        config.get_all()


def test_empty_api_url_in_config_json_raises_value_error(tmp_path):
    """config.json 中 api.url 為空字串時，validate_config 必須拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"url": ""}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="api.url.*不可為空字串或純空白"):
        config.get_all()


def test_invalid_api_url_format_in_config_json_raises_value_error(tmp_path):
    """config.json 中 api.url 為非 http/https 格式時，validate_config 必須拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"url": "ftp://invalid.example"}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="api.url.*http://.*https://"):
        config.get_all()


def test_empty_api_model_in_config_json_raises_value_error(tmp_path):
    """config.json 中 api.model 為空字串時，validate_config 必須拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"model": ""}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="api.model.*不可為空字串或純空白"):
        config.get_all()


def test_empty_api_url_env_var_fallback_to_default(tmp_path, monkeypatch):
    """空字串 AUTORESEARCH_API_URL 被拒絕後，回退至預設值且通過合法性檢查。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_URL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_URL"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_URL", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["api"]["url"] == config._DEFAULTS["api"]["url"]


def test_empty_api_model_env_var_fallback_to_default(tmp_path, monkeypatch):
    """空字串 AUTORESEARCH_API_MODEL 被拒絕後，回退至預設值且通過合法性檢查。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_MODEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_MODEL"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_MODEL", raising=False)
    cfg = config.get_all()
    config.validate_config(cfg)
    assert cfg["api"]["model"] == config._DEFAULTS["api"]["model"]


def test_valid_api_url_env_var_accepted(tmp_path, monkeypatch):
    """合法 http/https URL 的 AUTORESEARCH_API_URL 必須被接受。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_URL", "https://valid.example/v1/api")

    cfg = config.get_all()
    assert cfg["api"]["url"] == "https://valid.example/v1/api"


def test_valid_http_api_url_env_var_accepted(tmp_path, monkeypatch):
    """合法 http:// URL 的 AUTORESEARCH_API_URL 必須被接受。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_URL", "http://localhost:8080/api")

    cfg = config.get_all()
    assert cfg["api"]["url"] == "http://localhost:8080/api"


def test_valid_api_model_env_var_accepted(tmp_path, monkeypatch):
    """非空的 AUTORESEARCH_API_MODEL 必須被接受。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_MODEL", "gpt-5.4-mini")

    cfg = config.get_all()
    assert cfg["api"]["model"] == "gpt-5.4-mini"


# ── 合法值通過：數值型 env var 接受有效數值並寫入 cfg ──────────────────


def test_valid_smoke_parallel_env_var_accepted(tmp_path, monkeypatch):
    """合法數值 AUTORESEARCH_SMOKE_PARALLEL 必須被接受並寫入 cfg。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "12")

    cfg = config.get_all()
    assert cfg["parallel"]["smoke"] == 12
    assert isinstance(cfg["parallel"]["smoke"], int)


def test_valid_dev_parallel_env_var_accepted(tmp_path, monkeypatch):
    """合法數值 AUTORESEARCH_DEV_PARALLEL 必須被接受並寫入 cfg。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "48")

    cfg = config.get_all()
    assert cfg["parallel"]["dev"] == 48
    assert isinstance(cfg["parallel"]["dev"], int)


def test_valid_holdout_parallel_env_var_accepted(tmp_path, monkeypatch):
    """合法數值 AUTORESEARCH_HOLDOUT_PARALLEL 必須被接受並寫入 cfg。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_HOLDOUT_PARALLEL", "36")

    cfg = config.get_all()
    assert cfg["parallel"]["holdout"] == 36
    assert isinstance(cfg["parallel"]["holdout"], int)


def test_valid_max_candidate_length_env_var_accepted(tmp_path, monkeypatch):
    """合法數值 AUTORESEARCH_MAX_CANDIDATE_LENGTH 必須被接受並寫入 cfg。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "400")

    cfg = config.get_all()
    assert cfg["thresholds"]["max_candidate_length"] == 400
    assert isinstance(cfg["thresholds"]["max_candidate_length"], int)


# ── 非法值被拒絕：MINIMAX_API_KEY 空字串/空白 ──────────────────────────


def test_empty_minimax_api_key_env_var_accepted_and_not_validated(tmp_path, monkeypatch):
    """MINIMAX_API_KEY 不在 _STRING_ENV_KEYS 中，空字串不會被 validate_config 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("MINIMAX_API_KEY", "")

    cfg = config.get_all()
    assert cfg["api"]["api_key"] == ""


def test_valid_minimax_api_key_env_var_accepted(tmp_path, monkeypatch):
    """合法 MINIMAX_API_KEY 必須被寫入 cfg。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-key-123")

    cfg = config.get_all()
    assert cfg["api"]["api_key"] == "sk-test-key-123"


# ── config.json 無效覆蓋的拒絕 + 回退驗證 ──────────────────────────────


def test_config_json_empty_string_timeout_rejected_and_falls_back_to_default(tmp_path):
    """config.json 以空字串覆蓋 api.timeout 必須被拒絕，回退至預設值。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"timeout": ""}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="api.timeout"):
        config.get_all()


def test_config_json_negative_retry_rejected_and_falls_back(tmp_path):
    """config.json 以負數覆蓋 api.retry 必須被 validate_config 拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"retry": -3}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="api.retry.*必須為正數"):
        config.get_all()


def test_config_json_wrong_type_for_url_rejected_and_falls_back(tmp_path):
    """config.json 以數字覆蓋 api.url 必須被 validate_config 拒絕。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"url": 12345}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    with pytest.raises(ValueError, match="api.url.*型別不符"):
        config.get_all()


# ── 參數化負面測試：所有 _POSITIVE_KEYS 欄位在 env var / config.json / _DEFAULTS 出現 nan/inf/0/負數必須拋 ValueError ──

_POSITIVE_FIELDS_WITH_ENV = [
    ("AUTORESEARCH_API_TIMEOUT", "api.timeout"),
    ("AUTORESEARCH_SMOKE_PARALLEL", "parallel.smoke"),
    ("AUTORESEARCH_DEV_PARALLEL", "parallel.dev"),
    ("AUTORESEARCH_HOLDOUT_PARALLEL", "parallel.holdout"),
    ("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "thresholds.max_candidate_length"),
]

_POSITIVE_FIELDS_NO_ENV = [
    ("api.retry", {"api": {"retry": None}}),
    ("api.rate_limit.max_concurrent", {"api": {"rate_limit": {"max_concurrent": None}}}),
    ("api.rate_limit.min_interval_ms", {"api": {"rate_limit": {"min_interval_ms": None}}}),
    ("archive.max_versions", {"archive": {"max_versions": None}}),
    ("multi_candidate.count", {"multi_candidate": {"count": None}}),
]

_INVALID_NUMERIC_VALUES = [
    ("nan", float("nan")),
    ("inf", float("inf")),
    ("-inf", float("-inf")),
    ("zero", 0),
    ("negative", -1),
]


@pytest.mark.parametrize("env_key,field", _POSITIVE_FIELDS_WITH_ENV)
@pytest.mark.parametrize("val_name,val", _INVALID_NUMERIC_VALUES)
def test_env_var_invalid_numeric_rejected(env_key, field, val_name, val, tmp_path, monkeypatch):
    """環境變數為 nan/inf/-inf/0/負數時，必須被 validate_config 拒絕。"""
    _set_config_path(tmp_path / "not-exist.json")
    config._CONFIG = None
    if isinstance(val, float) and (val != val or val in (float("inf"), float("-inf"))):
        env_val = {"nan": "nan", "inf": "inf", "-inf": "-inf"}[val_name]
    else:
        env_val = str(val)
    monkeypatch.setenv(env_key, env_val)

    with pytest.raises(ValueError):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv(env_key, raising=False)


@pytest.mark.parametrize("field,template", _POSITIVE_FIELDS_NO_ENV)
@pytest.mark.parametrize("val_name,val", [("zero", 0), ("negative", -1)])
def test_config_json_invalid_numeric_rejected(field, template, val_name, val, tmp_path):
    """config.json 為 0/負數時，必須被 validate_config 拒絕。"""
    config._CONFIG = None
    import copy
    cfg_data = copy.deepcopy(template)
    parts = field.split(".")
    d = cfg_data
    for p in parts[:-1]:
        d = d[p]
    d[parts[-1]] = val

    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(cfg_data), encoding="utf-8")
    _set_config_path(config_file)

    with pytest.raises(ValueError, match=field.replace(".", r"\.") + r".*必須為正數"):
        config.get_all()

    config._CONFIG = None


def test_validate_config_direct_nan_inf_rejected():
    """直接呼叫 validate_config 傳入 nan/inf/-inf 必須被拒絕（覆蓋無 env var 的欄位）。"""
    import copy
    import math
    for field, template in _POSITIVE_FIELDS_NO_ENV:
        for val_name, val in [("nan", float("nan")), ("inf", float("inf")), ("-inf", float("-inf"))]:
            cfg = copy.deepcopy(config._DEFAULTS)
            parts = field.split(".")
            d = cfg
            for p in parts[:-1]:
                d = d[p]
            d[parts[-1]] = val
            with pytest.raises(ValueError, match=field.replace(".", r"\.") + r".*不允許 NaN 或 inf"):
                config.validate_config(cfg)


def test_validate_config_direct_zero_negative_rejected():
    """直接呼叫 validate_config 傳入 0/負數必須被拒絕（覆蓋所有 _POSITIVE_KEYS）。"""
    import copy
    # Use field names (second element of tuples) for both lists
    field_names = [f for _, f in _POSITIVE_FIELDS_WITH_ENV] + [f for f, _ in _POSITIVE_FIELDS_NO_ENV]
    for field in field_names:
        for val in [0, -1, -100]:
            cfg = copy.deepcopy(config._DEFAULTS)
            parts = field.split(".")
            d = cfg
            for p in parts[:-1]:
                d = d[p]
            d[parts[-1]] = val
            with pytest.raises(ValueError, match=field.replace(".", r"\.") + r".*必須為正數"):
                config.validate_config(cfg)
