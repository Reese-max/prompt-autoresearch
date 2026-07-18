# 配置流程特殊分支測試案例清單

日期：2026-07-18

## 任務說明

新增並提交配置流程特殊分支的測試檔案與測試案例清單，逐項覆蓋缺值、非法值、衝突設定、fallback、空值及上下界，且每個案例須明確斷言例外類型、錯誤訊息或最終配置輸出。

## 測試檔案

- `tests/test_config_special_branch.py`

## 測試案例清單（共 12 項）

| 編號 | 測試函式 | 覆蓋分支 | 輸入情境 | 預期斷言 |
|---|---|---|---|---|
| 1 | `test_missing_config_file_falls_back_to_defaults` | C02 | `config.json` 缺值 | 回傳 `_DEFAULTS`，timeout=180，smoke=6 |
| 2 | `test_missing_env_var_falls_back_to_default` | C05 | 環境變數全部缺值 | 保留預設值，timeout=180 |
| 3 | `test_empty_numeric_env_var_raises_value_error` | C08 | `AUTORESEARCH_API_TIMEOUT=""` | 拋 `ValueError`，訊息含「不可為空字串」 |
| 4 | `test_whitespace_numeric_env_var_raises_value_error` | C08 | `AUTORESEARCH_SMOKE_PARALLEL="   "` | 拋 `ValueError`，訊息含「不可為空字串」 |
| 5 | `test_invalid_numeric_env_var_raises_value_error` | C09 | `AUTORESEARCH_DEV_PARALLEL="not-a-number"` | 拋 `ValueError`，訊息含「無法解析為數值」 |
| 6 | `test_nan_inf_env_var_raises_value_error` | C10 | `AUTORESEARCH_API_TIMEOUT="nan"` | 拋 `ValueError`，訊息含「不允許 NaN 或 inf」 |
| 7 | `test_zero_or_negative_env_var_raises_value_error` | C11 | `AUTORESEARCH_MAX_CANDIDATE_LENGTH="0"` | 拋 `ValueError`，訊息含「必須為正數」 |
| 8 | `test_empty_api_url_env_var_raises_value_error` | C13 | `AUTORESEARCH_API_URL=""` | 拋 `ValueError`，訊息含「不可為空字串」 |
| 9 | `test_invalid_api_url_format_env_var_raises_value_error` | C14 | `AUTORESEARCH_API_URL="ftp://example.com"` | 拋 `ValueError`，訊息含「必須為有效的 http:// 或 https:// URL」 |
| 10 | `test_config_json_wrong_type_for_numeric_override_validated` | C15 | `config.json` 將 timeout 設為字串 | 拋 `ValueError`，訊息含「型別不符」 |
| 11 | `test_valid_file_config_plus_invalid_env_var_raises` | C17 | 檔案 timeout=300，env 設非數字 | 拋 `ValueError`，訊息含「無法解析為數值」 |
| 12 | `test_empty_env_var_validation_blocks_fallback` | L002/L003 | `AUTORESEARCH_API_TIMEOUT=""` | 明確拋 `ValueError` 阻擋回退 |

## 驗證要點

- 每個案例明確斷言例外類型（`ValueError`）、錯誤訊息關鍵字或最終配置輸出值。
- 同時覆蓋「缺值走預設」與「無效值被驗證擋下」兩路徑。
- 最終生效的組態均經過同一套 `validate_config()` 合法性檢查。
