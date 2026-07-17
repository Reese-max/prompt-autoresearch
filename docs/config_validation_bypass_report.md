# config.py 環境變數與預設值回退驗證繞過分析報告

> 檢視範圍：`lib/config.py` 第 109-111、114 行及整體 `_apply_env_overrides` / `_load_config` 邏輯。
> 日期：2026-07-17

---

## 1. 有驗證的路徑（環境變數覆蓋）

`_apply_env_overrides` 中，凡列入 `_NUMERIC_ENV_KEYS` 的環境變數會經過數值解析驗證：

| 環境變數 | 目標欄位 | 驗證方式 |
|---|---|---|
| `AUTORESEARCH_API_TIMEOUT` | `api.timeout` | int → float → raise ValueError |
| `AUTORESEARCH_SMOKE_PARALLEL` | `parallel.smoke` | int → float → raise ValueError |
| `AUTORESEARCH_DEV_PARALLEL` | `parallel.dev` | int → float → raise ValueError |
| `AUTORESEARCH_HOLDOUT_PARALLEL` | `parallel.holdout` | int → float → raise ValueError |
| `AUTORESEARCH_MAX_CANDIDATE_LENGTH` | `thresholds.max_candidate_length` | int → float → raise ValueError |

此外，所有數值型環境變數均額外檢查空字串（第 104-107 行），空白字串同樣被拒絕。

**結論：環境變數覆蓋路徑不會靜默接受格式異常值。**

---

## 2. 繞過驗證的路徑

### 2.1 非數值型環境變數（無驗證）

以下環境變數不在 `_NUMERIC_ENV_KEYS` 中，直接寫入 cfg 不經任何驗證：

| 環境變數 | 目標欄位 | 預設型別 | 風險 |
|---|---|---|---|
| `MINIMAX_API_KEY` | `api.api_key` | str | 低（字串無型別問題） |
| `AUTORESEARCH_API_URL` | `api.url` | str | 低 |
| `AUTORESEARCH_API_MODEL` | `api.model` | str | 低 |

> 上述三個欄位均為字串型態，環境變數繞過驗證的實質風險較低。

### 2.2 config.json 覆蓋（完全無驗證）— 主要風險

`_load_config` 中 `json.load` 後直接 `_deep_merge`，**沒有任何型別或值域驗證**。以下設定欄位可被 config.json 以空字串、null、錯誤型別覆蓋，靜默生效：

| config.json 路徑 | 預設值與型別 | 可被覆蓋為 | 結果 |
|---|---|---|---|
| `api.timeout` | `180` (int) | `""`, `null`, `"abc"` | 靜默接受，下游取用時型別不符 |
| `api.retry` | `4` (int) | `""`, `null`, `"abc"` | 同上 |
| `api.rate_limit.max_concurrent` | `8` (int) | `""`, `null` | 同上 |
| `api.rate_limit.min_interval_ms` | `100` (int) | `""`, `null` | 同上 |
| `parallel.smoke` | `6` (int) | `""`, `null`, `"abc"` | 同上 |
| `parallel.dev` | `24` (int) | `""`, `null` | 同上 |
| `parallel.holdout` | `24` (int) | `""`, `null` | 同上 |
| `thresholds.max_candidate_length` | `550` (int) | `""`, `null` | 同上 |
| `thresholds.smoke_allowed_drop` | `2.0` (float) | `""`, `null`, `"abc"` | 同上 |
| `thresholds.smoke_min_score` | `75.0` (float) | `""`, `null` | 同上 |
| `thresholds.dev_min_improvement` | `2.0` (float) | `""`, `null` | 同上 |
| `thresholds.holdout_max_drop` | `1.0` (float) | `""`, `null` | 同上 |
| `thresholds.type_max_regression` | `3.0` (float) | `""`, `null` | 同上 |
| `thresholds.word_rate_min` | `85.0` (float) | `""`, `null` | 同上 |
| `archive.max_versions` | `20` (int) | `""`, `null` | 同上 |
| `multi_candidate.enabled` | `True` (bool) | `""`, `null`, `0` | 語義翻轉 |
| `multi_candidate.count` | `3` (int) | `""`, `null` | 同上 |
| `multi_candidate.temperatures` | `[0.5, 0.7, 0.9]` (list) | `null`, `"abc"` | 結構損壞 |

---

## 3. 總結

| 覆蓋來源 | 有驗證的欄位 | 繞過驗證的欄位 |
|---|---|---|
| 環境變數（數值型） | `api.timeout`, `parallel.smoke/dev/holdout`, `thresholds.max_candidate_length` | — |
| 環境變數（字串型） | — | `api.url`, `api.model`, `api.api_key`（低風險） |
| config.json | — | **全部設定欄位**（所有數值、布林、列表型態） |

**核心結論**：`config.json` 覆蓋路徑完全繞過驗證。數值型環境變數經 int→float→raise 三重檢查不會繞過；非數值型環境變數直接寫入但型別風險低。最大風險在於 config.json 可將任何數值欄位覆蓋為空字串、null 或字串型態，下游使用時才爆型別錯誤。

---

## 4. 已有測試覆蓋確認

以下既有測試已驗證環境變數繞過行為：
- `test_invalid_numeric_env_var_raises_and_does_not_pollute_cfg` — 無效數值 env 被拒絕
- `test_invalid_parallel_env_var_raises` — 無效 smoke_parallel 被拒絕
- `test_invalid_max_candidate_length_env_var_raises` — 無效 max_candidate_length 被拒絕
- `test_empty_numeric_env_var_raises_value_error` — 空字串數值 env 被拒絕
- `test_whitespace_numeric_env_var_raises_value_error` — 空白數值 env 被拒絕

以下既有測試已驗證 config.json 繞過行為：
- `test_config_json_empty_string_overrides_numeric_default_not_validated` — 空字串覆蓋未驗證
- `test_config_json_wrong_type_for_numeric_override_not_validated` — 錯誤型別覆蓋未驗證
- `test_config_json_null_for_numeric_default_not_validated` — null 覆蓋未驗證
