# config.py 預設值回退與驗證缺口審計

日期：2026-07-17

## 審計範圍

`lib/config.py` 中環境變數覆蓋（`_apply_env_overrides`）及 `get()` 函式的預設值回退路徑，
聚焦第 109-111、114 行，確認哪些情況會直接落到預設值且未再驗證。

---

## 1. `_apply_env_overrides` 三階 type coercion（L94-100）

```
int(val) → float(val) → 原始字串
```

### 涉及設定項與預期型別

| 環境變數 | section.key | 預期型別 |
|---|---|---|
| `AUTORESEARCH_API_TIMEOUT` | api.timeout | int |
| `AUTORESEARCH_SMOKE_PARALLEL` | parallel.smoke | int |
| `AUTORESEARCH_DEV_PARALLEL` | parallel.dev | int |
| `AUTORESEARCH_HOLDOUT_PARALLEL` | parallel.holdout | int |
| `AUTORESEARCH_MAX_CANDIDATE_LENGTH` | thresholds.max_candidate_length | int |

### 問題

當上述任一環境變數被設為非數字字串（如 `"abc"`、`""`、`"true"`）時：

1. `int(val)` 拋出 `ValueError` → 進入 except
2. `float(val)` 拋出 `ValueError` → 進入 except
3. **原始字串被直接寫入 cfg**（L100），無任何驗證
4. 下游程式碼以數值方式使用該值（如 `timeout` 送入 `requests.get(timeout=...)`），將在 runtime 拋出 `TypeError`

**這是一條從不可信輸入（環境變數）直通設定結構的路徑，且整段沒有任何驗證攔截。**

### 已有測試覆蓋

`test_environment_variables_override_file_and_types` 僅測試合法數字字串（`"75"`、`"18"`、`"777.7"`），
**未覆蓋非法值進入 fallback 的路徑**。

---

## 2. `get()` L109-111：section 回傳或 default

```python
if key is None or isinstance(key, (dict, list)):
    if key is not None and default is None:
        default = key
    return section_data if section_data else default  # L111
```

### 觸發條件

| 情境 | section_data | 回傳值 |
|---|---|---|
| section 存在且非空 | `{"smoke": 6, ...}` | section_data |
| section 存在但為空 dict | `{}`（falsy） | default |
| section 不存在 | `{}`（falsy） | default |

### 問題

- 當 section 為空 dict 時，回傳 `default` 而非空 dict。呼叫端若期望拿到 dict 卻拿到其他型別的 default，可能出錯。
- **default 值從呼叫端傳入，完全未經型別或範圍驗證。**

### 已有測試覆蓋

`test_get_branch_L109_L111_dict_key_shifted_to_default` 已覆蓋 dict/list key 的回退行為。

---

## 3. `get()` L112-114：section_data 非 dict 回退

```python
if isinstance(section_data, dict):
    return section_data.get(key, default)  # L113
return default                             # L114
```

### 觸發條件

當 `config.json` 中某 section 的值不是 dict（如 `"api": "not_a_dict"`），
`_deep_merge` 會用整個字串覆蓋原 dict → `section_data` 為字串 → L113 的 `isinstance` 判斷為 False → 走 L114。

### 問題

- 跳過 `.get(key)` 直接回傳 default，**呼叫端無法區分「key 不存在」與「整個 section 損壞」。**
- default 同樣未經驗證。

### 已有測試覆蓋

`test_get_branch_L114_non_dict_section_returns_default` 已覆蓋此路徑。

---

## 4. 整體缺口總結

| 路徑 | 輸入來源 | 是否驗證 | 風險 |
|---|---|---|---|
| `_apply_env_overrides` 三階 fallback | 環境變數 | ❌ 無 | **高**：非法值以正確型別之姿進入 cfg，runtime 才爆 |
| L111 section 空 → default | config 內部結構 | ❌ 無 | 中：default 值型別不受控 |
| L114 section 非 dict → default | config 內部結構 | ❌ 無 | 中：等同 section 損壞靜默吞掉 |
| L113 key 缺失 → default | config 內部結構 | ❌ 無 | 低：default 由呼叫端控制 |

**整個 `lib/config.py` 沒有 `validate_config()` 或類似的型別/範圍校驗函式**（grep 零命中）。
環境變數覆蓋是唯一接觸外部輸入的路徑，也是唯一缺少驗證的路徑。

---

## 5. 建議（供後續 task 參考）

1. **`_apply_env_overrides` 增加型別驗證**：int/float 轉換失敗時應 `raise ValueError` 而非靜默存字串。
2. **新增專屬測試**：覆蓋 `AUTORESEARCH_API_TIMEOUT=abc` 等非法值，斷言 raise 或被拒絕。
3. 考慮集中式 `validate_config()` 在 `_load_config()` 結束後呼叫，確保最終 cfg 的所有值符合預期型別與範圍。
