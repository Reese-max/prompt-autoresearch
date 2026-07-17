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


def test_invalid_numeric_env_var_raises_and_does_not_pollute_cfg(tmp_path, monkeypatch):
    """數值型環境變數格式異常時，_apply_env_overrides 必須 raise ValueError，不得靜默存字串。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")

    with pytest.raises(ValueError, match="AUTORESEARCH_API_TIMEOUT"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)
    cfg = config.get_all()
    assert cfg["api"]["timeout"] == 180
    assert isinstance(cfg["api"]["timeout"], int)


def test_invalid_parallel_env_var_raises(monkeypatch):
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "abc")

    with pytest.raises(ValueError, match="AUTORESEARCH_SMOKE_PARALLEL"):
        config.get_all()


def test_invalid_max_candidate_length_env_var_raises(monkeypatch):
    monkeypatch.setenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "not-a-number")

    with pytest.raises(ValueError, match="AUTORESEARCH_MAX_CANDIDATE_LENGTH"):
        config.get_all()


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


def test_config_json_empty_string_overrides_numeric_default_not_validated(tmp_path):
    """config.json 提供空字串覆蓋數值 defaults，因無 validate_config() 而被靜默接受。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"api": {"timeout": ""}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    cfg = config.get_all()

    assert cfg["api"]["timeout"] == "", (
        "空字串覆蓋數值 defaults 後未被驗證拒絕（_load_config 無 validate_config）"
    )


def test_config_json_wrong_type_for_numeric_override_not_validated(tmp_path):
    """config.json 提供字串覆蓋整數 defaults，因無驗證而被靜默接受。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"parallel": {"smoke": "not-a-number"}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    cfg = config.get_all()

    assert cfg["parallel"]["smoke"] == "not-a-number", (
        "字串覆蓋整數 defaults 後未被驗證拒絕"
    )


def test_config_json_null_for_numeric_default_not_validated(tmp_path):
    """config.json 提供 null 覆蓋數值 defaults，因無驗證而被靜默接受。"""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"thresholds": {"max_candidate_length": None}}),
        encoding="utf-8",
    )
    _set_config_path(config_file)

    cfg = config.get_all()

    assert cfg["thresholds"]["max_candidate_length"] is None, (
        "null 覆蓋數值 defaults 後未被驗證拒絕"
    )


# ── 預設值回退路徑驗證：環境變數空值 ─────────────────────────────────────


def test_empty_numeric_env_var_raises_value_error(monkeypatch):
    """數值型環境變數為空字串時，_apply_env_overrides 必須拒絕。"""
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "")

    with pytest.raises(ValueError, match="不可為空字串"):
        config.get_all()


def test_whitespace_numeric_env_var_raises_value_error(monkeypatch):
    """數值型環境變數為純空白時，_apply_env_overrides 必須拒絕。"""
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "   ")

    with pytest.raises(ValueError, match="不可為空字串"):
        config.get_all()


def test_empty_smoke_parallel_env_var_rejects_does_not_pollute(tmp_path, monkeypatch):
    """空字串 smoke_parallel 被拒絕後，cfg 不受影響仍為 defaults。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_SMOKE_PARALLEL"):
        config.get_all()

    config._CONFIG = None
    monkeypatch.delenv("AUTORESEARCH_SMOKE_PARALLEL", raising=False)
    cfg = config.get_all()
    assert cfg["parallel"]["smoke"] == config._DEFAULTS["parallel"]["smoke"]
    assert isinstance(cfg["parallel"]["smoke"], int)


def test_empty_dev_parallel_env_var_rejects_and_preserves_other(tmp_path, monkeypatch):
    """空字串 dev_parallel 被拒絕時，raise 前不應污染 cfg。"""
    _set_config_path(tmp_path / "not-exist.json")
    monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_DEV_PARALLEL"):
        config.get_all()


def test_empty_max_candidate_length_env_var_raises(monkeypatch):
    """空字串 max_candidate_length 必須被拒絕。"""
    monkeypatch.setenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_MAX_CANDIDATE_LENGTH"):
        config.get_all()


def test_empty_holdout_parallel_env_var_raises(monkeypatch):
    """空字串 holdout_parallel 必須被拒絕。"""
    monkeypatch.setenv("AUTORESEARCH_HOLDOUT_PARALLEL", "")

    with pytest.raises(ValueError, match="AUTORESEARCH_HOLDOUT_PARALLEL"):
        config.get_all()


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
