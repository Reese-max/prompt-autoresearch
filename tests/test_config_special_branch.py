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


@pytest.mark.parametrize(
    ("env_key", "key", "value"),
    [
        pytest.param("AUTORESEARCH_API_URL", "url", "", id="url-empty"),
        pytest.param("AUTORESEARCH_API_URL", "url", "   ", id="url-whitespace"),
        pytest.param("AUTORESEARCH_API_MODEL", "model", "", id="model-empty"),
        pytest.param("AUTORESEARCH_API_MODEL", "model", "   ", id="model-whitespace"),
    ],
)
def test_blank_api_string_env_vars_raise_value_error(monkeypatch, env_key, key, value):
    """C13: API URL／MODEL 為空字串或純空白 → ValueError。"""
    monkeypatch.setenv(env_key, value)
    config._CONFIG = None
    with pytest.raises(ValueError) as exc:
        config.get("api", key)
    assert env_key in str(exc.value)
    assert "不可為空字串" in str(exc.value)


@pytest.mark.parametrize(
    "bad_url",
    [
        pytest.param("ftp://example.com", id="ftp"),
        pytest.param("example.com/api", id="missing-protocol"),
        pytest.param("mailto:user@example.com", id="non-http-scheme"),
        pytest.param("http://", id="http-missing-host"),
        pytest.param("https://", id="https-missing-host"),
        pytest.param("http:///api", id="http-missing-host-with-path"),
        pytest.param("https:///api", id="https-missing-host-with-path"),
    ],
)
def test_invalid_api_url_format_env_var_raises_value_error(monkeypatch, bad_url):
    """C14: 非 HTTP(S) 或缺少主機的 URL → ValueError。"""
    monkeypatch.setenv("AUTORESEARCH_API_URL", bad_url)
    config._CONFIG = None
    with pytest.raises(ValueError) as exc:
        config.get("api", "url")
    assert "必須為有效的 http:// 或 https:// URL" in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("http://example.com/v1", id="http"),
        pytest.param("https://example.com/v1", id="https"),
    ],
)
def test_valid_http_api_url_env_var_is_accepted(monkeypatch, url):
    """合法 HTTP(S) URL 可透過 get() 讀取。"""
    monkeypatch.setenv("AUTORESEARCH_API_URL", url)
    config._CONFIG = None
    assert config.get("api", "url") == url


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
