# 配置流程特殊／例外分支與測試對照表

日期：2026-07-18

## 範圍與流程

本表以共用設定載入器 `lib/config.py` 為範圍，涵蓋 `_DEFAULTS`、`config.json`、環境變數覆寫，以及 `get()`、`get_section()`、`get_all()` 的回傳分支。流程順序如下：

```text
_DEFAULTS 的深複製
  → 若 config.json 存在則深層合併
  → 套用環境變數覆寫
  → validate_config() 驗證最終設定
  → 快取並提供 get / get_section / get_all
```

來源優先序是：環境變數 > `config.json` > `_DEFAULTS`。但「優先」不代表錯誤值會回退：檔案讀取／解析失敗會保留預設值；環境變數或已解析的檔案值不合法時，會在載入當次拋出 `ValueError`。

## 特殊／例外分支清單

| 編號 | 程式位置與條件 | 輸入情境 | 預期輸出／例外 |
|---|---|---|---|
| C01 | `lib/config.py:57-58` 快取命中 | `_CONFIG` 已載入後再次讀取 | 回傳同一份快取；來源檔案後續變更不會立即生效 |
| C02 | `lib/config.py:60` 檔案不存在 | `config.json` 缺值 | 使用 `_DEFAULTS`，不拋例外 |
| C03 | `lib/config.py:61-64` 合法 JSON 深層合併 | 檔案只覆寫部分欄位、包含巢狀 `dict` 或新增欄位 | 已指定值覆寫；未指定的預設欄位保留；未知欄位保留 |
| C04 | `lib/config.py:65-66` 檔案讀取／解析例外 | JSON 語法錯誤，或檔案開啟／合併期間發生例外 | 吞掉檔案例外，保留預設值；之後仍會套用環境變數並驗證 |
| C05 | `lib/config.py:67` 環境變數缺值 | `os.environ` 沒有對應鍵 | 不覆寫檔案／預設值 |
| C06 | `lib/config.py:193-195` section 缺值 | 直接呼叫 `_apply_env_overrides()`，目標 section 不存在 | 自動建立空 `dict`，再寫入覆寫值 |
| C07 | `lib/config.py:196-206` 數值轉型成功 | 整數字串如 `"12"`，或小數字串如 `"777.7"` | 依序得到 `int` 或 `float`，再進入最終驗證 |
| C08 | `lib/config.py:197-200` 數值環境變數空值 | `""` 或純空白 | 拋出 `ValueError`，訊息包含環境變數名稱與「不可為空字串」 |
| C09 | `lib/config.py:201-209` 數值環境變數無法解析 | `"abc"`、`"not-a-number"` | `int()`、`float()` 均失敗後拋出 `ValueError`，不接受原始字串 |
| C10 | `lib/config.py:146-149` 非有限數值 | `"nan"`、`"inf"` 轉成 `float` 後進入驗證 | 拋出 `ValueError`，訊息指出不允許 `NaN` 或 `inf` |
| C11 | `lib/config.py:150-153` 正數邊界 | 正數欄位收到 `0`、負數或負小數 | 拋出 `ValueError`，訊息指出必須為正數；正數值可通過 |
| C12 | `lib/config.py:210-216` 字串環境變數 | URL／model 有非空值 | 寫入設定；URL 還要通過 `http://` 或 `https://` 前綴驗證 |
| C13 | `lib/config.py:211-215` 字串環境變數空值 | `AUTORESEARCH_API_URL` 或 `AUTORESEARCH_API_MODEL` 為空字串／純空白 | 在覆寫階段拋出 `ValueError` |
| C14 | `lib/config.py:165-177` 字串設定不合法 | `api.url` 非字串、空白、非 HTTP(S)；`api.model` 非字串或空白 | 拋出 `ValueError`，訊息指出欄位與型別／格式問題 |
| C15 | `lib/config.py:142-145` 數值設定型別不符 | `config.json` 將數值欄位設為字串、空字串或 `null` | 最終驗證拋出 `ValueError`，不靜默接受檔案值 |
| C16 | `lib/config.py:64` 與 `lib/config.py:67` 同鍵衝突 | `config.json` 有合法值，環境變數同鍵覆寫為合法值 | 環境變數值勝出；例如 `api.timeout` 取 env 的整數 |
| C17 | 同鍵衝突但環境變數非法 | 檔案值合法，環境變數同鍵為 `"not-a-number"` | 環境變數優先並被拒絕，拋出 `ValueError`；不自動退回檔案值 |
| C18 | `lib/config.py:219-230` `get()` 取值分支 | section／key 缺值、key 誤傳 `dict`／`list`、section 非 `dict` | 依呼叫端 default 回傳；非 `dict` section 不呼叫 `.get()` |
| C19 | `lib/config.py:233-235` 取 section | section 存在或不存在 | 回傳 section 的淺複製；不存在時回傳空 `dict` |
| C20 | `lib/config.py:238-239` 取全部設定 | 呼叫端修改 `get_all()` 結果 | 回傳深複製；外部修改不污染快取 |
| C21 | `lib/config.py:112-123` 預設值自身不合法 | 測試替換 `_DEFAULTS` 為零或負數 | 缺少環境變數時仍會在最終驗證拋出 `ValueError`，不把壞預設當成合法回退值 |

## 分支到具體測試案例對照

下表列出目前 repo 已存在的可直接重跑案例，以及其可觀察結果。測試名稱中的 `falls_back` 需依下方「回退語意」解讀：部分案例是在拋例外後清除錯誤來源並重置快取，才驗證下一次載入結果。

| 分支 | 具體測試案例 | 驗證的輸入／邊界 | 預期結果 |
|---|---|---|---|
| C01 | `tests/test_lib_config.py::test_get_section_and_cache_hit_without_reload` | 首次載入後修改來源檔，再次 `_load_config()` | `first is second`，仍保留第一次的值 |
| C02、C05 | `tests/test_lib_config.py::test_load_defaults_when_config_file_missing`；`tests/test_lib_config_regression.py::test_missing_env_var_falls_back_to_default` | 檔案不存在、環境變數缺值 | 回傳預設值，數值型別合法 |
| C03 | `tests/test_lib_config.py::test_load_config_file_merge_overrides_defaults` | 部分欄位、巢狀 `rate_limit`、未知 `extra` 欄位 | 覆寫值生效，未覆寫欄位與未知欄位均符合預期 |
| C04 | `tests/test_lib_config.py::test_reload_after_cache_cleared_and_error_branch_for_invalid_json` | 清除快取後載入 `{invalid-json`，另設 `AUTORESEARCH_DEV_PARALLEL=33` | JSON 例外被回退；`parallel.dev` 仍為 `33`，其他欄位取預設 |
| C06 | `tests/test_lib_config.py::test_env_override_section_created_when_missing_from_cfg` | `cfg` 沒有 `parallel`，env 設 `AUTORESEARCH_DEV_PARALLEL=99` | 建立 `parallel`，且 `dev == 99` |
| C07、C12 | `tests/test_lib_config.py::test_environment_variables_override_file_and_types`；`test_valid_*_env_var_accepted` 系列 | 整數、小數、HTTP／HTTPS URL、非空 model | 轉型後寫入，`int`／`float` 型別與字串內容正確 |
| C08 | `tests/test_lib_config.py::test_empty_numeric_env_var_raises_value_error`；`test_whitespace_numeric_env_var_raises_value_error`；`test_empty_*_parallel_env_var_raises_and_falls_back_to_default` | 數值 env 為 `""` 或 `"   "` | `ValueError`；清理來源並重載後回到預設值 |
| C09 | `tests/test_lib_config.py::test_invalid_numeric_env_var_raises_and_falls_back_to_default`；`test_invalid_parallel_env_var_raises_and_falls_back_to_default`；`test_invalid_max_candidate_length_env_var_raises_and_falls_back_to_default` | 非數字字串 | `ValueError` 且訊息含 env 名稱；清理後重新載入為預設值 |
| C10、C11 | `tests/test_lib_config.py::test_invalid_api_timeout_env_var_raises_value_error` | `nan`、`inf`、`-1`、`0`、空字串、純空白參數化案例 | 每個案例均拋出 `ValueError` |
| C13、C14 | `tests/test_lib_config.py::test_empty_api_url_env_var_raises_value_error`；`test_whitespace_api_model_env_var_raises_value_error`；`test_invalid_api_url_format_env_var_raises_value_error`；同檔案的 `config_json` URL／model 負向案例 | 空白、非字串、`ftp://`、缺少協議前綴 | `ValueError`，訊息對應 env 或 `api.url`／`api.model` |
| C15 | `tests/test_lib_config.py::test_config_json_empty_string_overrides_numeric_default_validated`；`test_config_json_wrong_type_for_numeric_override_validated`；`test_config_json_null_for_numeric_default_validated` | `""`、`"not-a-number"`、`null` 覆寫數值欄位 | `ValueError`，訊息含完整 dotted key |
| C16 | `tests/test_lib_config.py::test_environment_variables_override_file_and_types` | 檔案先設 `parallel.smoke=1`，env 設 `18` | 最終 `parallel.smoke == 18` 且為 `int` |
| C17 | `tests/test_lib_config.py::test_valid_file_config_plus_invalid_env_var_raises_and_falls_back_to_file_value`；`tests/test_lib_config_regression.py::test_file_valid_override_plus_env_invalid_same_key_rejected` | 檔案 `api.timeout=300`，env 同鍵為非數字 | 當次拋 `ValueError`；移除 env、重置快取後才回到檔案值 `300` |
| C18 | `tests/test_lib_config.py::test_get_branch_L109_L111_dict_key_shifted_to_default`；`test_get_branch_L114_non_dict_section_returns_default`；`test_get_normal_dict_section_string_key_returns_value`；`test_get_normal_dict_section_missing_key_returns_default` | `key=None`、`dict`、`list`、缺 key、非 `dict` section | 回傳 section、呼叫端 default 或 `None`，不拋取值例外 |
| C19 | `tests/test_lib_config.py::test_get_section_and_cache_hit_without_reload` | 取得 `parallel` section | 回傳合併後的 section 內容 |
| C20 | `tests/test_lib_config_regression.py::test_get_all_returns_isolated_mutable_views` | 修改第一次 `get_all()` 的巢狀 dict／list | 第二次取得的快取仍維持原值 |
| C21 | `tests/test_lib_config_regression.py::test_invalid_default_api_timeout_zero_raises`；`test_invalid_default_parallel_smoke_negative_raises`；`test_invalid_default_max_candidate_length_zero_raises` | 將 `_DEFAULTS` 正數欄位改為 `0` 或負數 | `ValueError`，訊息含對應 dotted key |

## 回退語意與目前缺口

### 已確認的回退

- 缺少 `config.json`、空物件 `{}`，或 JSON 讀取／解析例外：保留 `_DEFAULTS`，之後仍套用合法的環境變數。
- 缺少環境變數：沿用檔案值；若檔案也沒有該欄位，沿用預設值。
- 無效環境變數：不是回退成功，而是先拋 `ValueError`；現有測試在清除 env 並將 `_CONFIG` 設回 `None` 後，才驗證下一次載入的預設／檔案值。
- 檔案值與無效環境變數衝突：無效 env 不會靜默退回檔案值，必須由呼叫端處理例外並重新載入。

### 尚未由現有測試直接鎖定的特殊情境

以下是依目前程式碼可辨識、但不應誤列為「已驗證回退」的案例：

1. `_CONFIG` 在套用 env 或最終驗證前就已被指派。若呼叫端捕捉 `ValueError` 後不清除 `_CONFIG`，下一次呼叫會命中快取分支，可能取得前一次載入留下的失敗狀態；建議案例名稱：`test_failed_config_load_does_not_reuse_invalid_cache`。
2. `validate_config()` 遇到中途非 `dict` 的數值／字串路徑會略過該欄位；`get()` 則對非 `dict` section 回傳呼叫端 default。現有 `test_get_branch_L114_non_dict_section_returns_default` 覆蓋取值結果，但未把「結構損壞仍通過載入」獨立列為驗證契約。
3. Python 中 `bool` 是 `int` 的子類；目前數值 schema 對部分 `true`／`false` 輸入可能按數值處理。若產品契約禁止布林值，應另增明確拒絕案例，而不是把目前行為解讀為一般數值驗證已涵蓋。

## 驗證紀錄

設定相關測試已先獨立執行：

```text
python -m pytest tests\test_lib_config.py tests\test_lib_config_regression.py -q -o addopts=
69 passed in 0.61s
```

全量測試亦已執行：

```text
python -m pytest -q
491 passed in 19.29s
總覆蓋率：100%（1693 statements、574 branches）
```
