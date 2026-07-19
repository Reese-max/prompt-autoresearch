# 布林值驗證 紅→綠 證據報告

**日期**: 2026-07-19  
**目標規則**: `multi_candidate.enabled` 必須為 `bool` 型別

## 背景

`validate_config` 已覆蓋數值型別、正數、NaN/inf、字串型別、空字串與 URL 格式，
但對預設值中的布林欄位 `multi_candidate.enabled` 完全無型別檢查。
任何人可透過 `config.json` 寫入 `1`、`"yes"`、`null` 等非布林值而不被攔截。

## 紅→綠流程

### RED 階段 — 測試先於實作

1. 新增 `tests/test_config_boolean_validation.py`：5 個測試（3 拒絕 + 2 接受）
2. 在**未修改**的 `lib/config.py` 上執行 → **3 FAILED / 5 total**

**失敗輸出**: `docs/evidence/red-boolean-validation.txt`

```
FAILED test_boolean_schema_rejects_non_bool_int      — DID NOT RAISE ValueError
FAILED test_boolean_schema_rejects_non_bool_string   — DID NOT RAISE ValueError
FAILED test_boolean_schema_rejects_non_bool_none     — DID NOT RAISE ValueError
PASSED test_boolean_schema_accepts_true
PASSED test_boolean_schema_accepts_false
```

### GREEN 階段 — 完成實作後全部通過

1. `lib/config.py` 新增 `_BOOLEAN_SCHEMA` frozenset 與 `validate_config()` 中的布林檢查
2. 執行相同測試 → **5 PASSED / 5 total**

**通過輸出**: `docs/evidence/green-boolean-validation.txt`

### 既有測試不受影響

- 原 277 個配置測試 + 43 個整合/回歸測試全數通過
- **總計: 320 passed**

## 證據檔案

| 階段 | 輸出檔案 | 測試結果 |
|------|----------|----------|
| RED  | `docs/evidence/red-boolean-validation.txt` | 3 failed, 2 passed |
| GREEN | `docs/evidence/green-boolean-validation.txt` | 5 passed |
| 全量驗證 | `test_config_boolean_validation.py` | 5 測試 |
| 實作 | `lib/config.py` | `_BOOLEAN_SCHEMA` + `validate_config` |

## 結論

本報告提供可重現的紅→綠證據：測試先於實作撰寫，未改動時失敗 3 案，
完成 `_BOOLEAN_SCHEMA` 驗證後全部通過，證明測試先行方法論已落實。
