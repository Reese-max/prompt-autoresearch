"""配置流程特殊分支測試。

逐項覆蓋缺值、非法值、衝突設定、fallback、空值及上下界。
每個案例明確斷言例外類型、錯誤訊息或最終配置輸出。
"""

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


def test_missing_config_file_falls_back_to_defaults(tmp_path, monkeypatch):
    """C02: 檔案不存在 → 使用 _DEFAULTS，不拋例外。"""
    missing = tmp_path / "no-such.json"
    monkeypatch.setattr(config, "_CONFIG_PATH", str(missing))
    cfg = config.get_all()
    assert cfg["api"]["timeout"] == 180
    assert cfg["parallel"]["smoke"] == 6


def test_missing_env_var_falls_back_to_default(monkeypatch):
    """C05: 環境變數缺值 → 不覆寫，保留預設值。"""
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    cfg = config.get_all()
    assert cfg["api"]["timeout"] == 180


def test_empty_numeric_env_var_raises_value_error(monkeypatch):
    """C08: 數值環境變數空值 → ValueError，訊息含「不可為空字串」。"""
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "不可為空字串" in str(exc.value)


def test_whitespace_numeric_env_var_raises_value_error(monkeypatch):
    """C08: 數值環境變數純空白 → ValueError。"""
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "   ")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "不可為空字串" in str(exc.value)


def test_invalid_numeric_env_var_raises_value_error(monkeypatch):
    """C09: 數值環境變數無法解析 → ValueError，訊息含 env 名稱。"""
    monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "not-a-number")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "無法解析為數值" in str(exc.value)


def test_nan_inf_env_var_raises_value_error(monkeypatch):
    """C10: 非有限數值 (nan/inf) → ValueError。"""
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "nan")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "不允許 NaN 或 inf" in str(exc.value)


def test_zero_or_negative_env_var_raises_value_error(monkeypatch):
    """C11: 正數邊界 (0/負數) → ValueError，訊息含「必須為正數」。"""
    monkeypatch.setenv("AUTORESEARCH_MAX_CANDIDATE_LENGTH", "0")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "必須為正數" in str(exc.value)


def test_empty_api_url_env_var_raises_value_error(monkeypatch):
    """C13: 字串環境變數空值 → ValueError。"""
    monkeypatch.setenv("AUTORESEARCH_API_URL", "")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "不可為空字串" in str(exc.value)


def test_invalid_api_url_format_env_var_raises_value_error(monkeypatch):
    """C14: URL 格式非法 (非 http/https) → ValueError。"""
    monkeypatch.setenv("AUTORESEARCH_API_URL", "ftp://example.com")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "必須為有效的 http:// 或 https:// URL" in str(exc.value)


def test_config_json_wrong_type_for_numeric_override_validated(tmp_path, monkeypatch):
    """C15: config.json 將數值欄位設為字串 → 最終驗證拋 ValueError。"""
    bad = tmp_path / "bad.json"
    bad.write_text('{"api": {"timeout": "not-a-number"}}', encoding="utf-8")
    monkeypatch.setattr(config, "_CONFIG_PATH", str(bad))
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "型別不符" in str(exc.value)


def test_valid_file_config_plus_invalid_env_var_raises(monkeypatch, tmp_path):
    """C17: 檔案值合法，環境變數同鍵非法 → 環境變數優先並被拒絕。"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text('{"api": {"timeout": 300}}', encoding="utf-8")
    monkeypatch.setattr(config, "_CONFIG_PATH", str(cfg_file))
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    assert "無法解析為數值" in str(exc.value)


def test_empty_env_var_validation_blocks_fallback(monkeypatch):
    """L002/L003: 空值應被驗證攔下，而非默默回退。"""
    monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "")
    with pytest.raises(ValueError) as exc:
        config.get_all()
    # 必須明確拋出 ValueError，不允許回退到預設值
    assert "不可為空字串" in str(exc.value)
