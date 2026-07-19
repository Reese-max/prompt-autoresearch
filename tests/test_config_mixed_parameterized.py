import json
import os
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
def clean_config_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "_CONFIG", None)
    monkeypatch.setattr(config, "_CONFIG_PATH", str(tmp_path / "config.json"))
    for key in CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    monkeypatch.setattr(config, "_CONFIG", None)


@pytest.mark.parametrize(
    ("config_data", "env_vars", "expected_err_msg", "expected_values"),
    [
        # 1. 非數值字串 (Non-numeric string for a numeric config option)
        (
            {"api": {"timeout": 300}},
            {"AUTORESEARCH_API_TIMEOUT": "not-a-number"},
            "無法解析為數值",
            None,
        ),
        # 2. 空白字串 / 空字串 - 數值變數 (Empty/blank string for numeric env key)
        (
            {"parallel": {"smoke": 10}},
            {"AUTORESEARCH_SMOKE_PARALLEL": ""},
            "不可為空字串",
            None,
        ),
        (
            {"parallel": {"smoke": 10}},
            {"AUTORESEARCH_SMOKE_PARALLEL": "   "},
            "不可為空字串",
            None,
        ),
        # 3. 空白字串 / 空字串 - 字串變數 (Empty/blank string for string env key)
        (
            {"api": {"url": "https://localhost"}},
            {"AUTORESEARCH_API_URL": ""},
            "不可為空字串",
            None,
        ),
        (
            {"api": {"url": "https://localhost"}},
            {"AUTORESEARCH_API_URL": "   "},
            "不可為空字串",
            None,
        ),
        # 4. 合法邊界值 (Valid boundary values)
        # 4a. Float values for timeout
        (
            {"api": {"timeout": 300}},
            {"AUTORESEARCH_API_TIMEOUT": "0.5"},
            None,
            {"api": {"timeout": 0.5}},
        ),
        # 4b. Positive integers
        (
            {"parallel": {"smoke": 10}},
            {"AUTORESEARCH_SMOKE_PARALLEL": "1"},
            None,
            {"parallel": {"smoke": 1}},
        ),
        # 4c. Valid URL
        (
            {"api": {"url": "https://original.com"}},
            {"AUTORESEARCH_API_URL": "https://localhost"},
            None,
            {"api": {"url": "https://localhost"}},
        ),
        # 5. 其他非數值邊界 (Illegal values like <= 0 on positive keys)
        (
            {"thresholds": {"max_candidate_length": 500}},
            {"AUTORESEARCH_MAX_CANDIDATE_LENGTH": "0"},
            "必須為正數",
            None,
        ),
        (
            {"thresholds": {"max_candidate_length": 500}},
            {"AUTORESEARCH_MAX_CANDIDATE_LENGTH": "-10"},
            "必須為正數",
            None,
        ),
        # 6. 極端非 HTTP/HTTPS URL
        (
            {"api": {"url": "https://original.com"}},
            {"AUTORESEARCH_API_URL": "ftp://localhost"},
            "必須為有效的 http:// 或 https:// URL",
            None,
        ),
        # 7. urlparse 丟出 ValueError 的無效 URL
        (
            {"api": {"url": "https://original.com"}},
            {"AUTORESEARCH_API_URL": "https://[invalid-ipv6]"},
            "必須為有效的 http:// 或 https:// URL",
            None,
        ),
    ]
)
def test_config_mixed_source_parameterized(tmp_path, monkeypatch, config_data, env_vars, expected_err_msg, expected_values):
    # 寫入 config.json
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps(config_data), encoding="utf-8")
    
    # 設定環境變數
    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)
        
    if expected_err_msg is not None:
        with pytest.raises(ValueError) as excinfo:
            config.get_all()
        assert expected_err_msg in str(excinfo.value)
    else:
        cfg = config.get_all()
        for section, keys in expected_values.items():
            for key, val in keys.items():
                assert cfg[section][key] == val
