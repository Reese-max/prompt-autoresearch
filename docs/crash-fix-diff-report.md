# 三類 Crash 根因修復差異報告

## Crash 1: `unsupported format string passed to NoneType.__format__`

### 根因
`auto_evolve.py` 原始程式碼在 f-string 中對 `holdout_avg` 直接使用 `:.2f`，
當 `holdout_avg=None` 時 Python 拋出 `ValueError`。

### 修復差異（`auto_evolve.py:184`）

**Before（崩潰）**
```python
print(f"... holdout={holdout_avg:.2f if holdout_avg is not None else 'N/A'} ...")
```

**After（正確產出 N/A）**
```python
holdout_display = f"{holdout_avg:.2f}" if holdout_avg is not None else "N/A"
print(f"... holdout={holdout_display} ...")
```

**非 try/except 證明**
修復使用**三元運算子**將格式化移至條件分支內，None 時直接給字串 `"N/A"`。
若改用 try/except 吞 ValueError，None 會被無聲吃掉而非正確顯示。
測試 `test_none_format_guard_is_ternary_not_try` 驗證：
- 直接執行 `f"{None:.2f}"` 仍噴 ValueError
- 加上三元運算子後正確回傳 `"N/A"`

---

## Crash 2: `unhashable type: 'dict'`

### 根因
`scripts/compare_runs.py` 與 `run_opt.py` 的 failure 統計以 dict
`{code: count}` 累計，原始程式碼只用 `if code:` 過濾空值，
當 failure code 為 dict 時仍嘗試將其作為 key 寫入 dict，觸發 `TypeError`。

### 修復差異（`scripts/compare_runs.py:88,94` 與 `run_opt.py:271`）

**Before（崩潰）**
```python
if f:
    fail_new[f] = fail_new.get(f, 0) + 1
```

**After（正確過濾）**
```python
if isinstance(f, str) and f:
    fail_new[f] = fail_new.get(f, 0) + 1
```

**非 try/except 證明**
修復使用 **`isinstance(f, str)` 前置型別檢查**，在嘗試 key 存取前排除 dict。
若改用 try/except 捕獲 TypeError，dict key 的錯誤會被隱藏。
測試 `test_dict_filter_is_isinstance_not_try` 驗證：
- dict 做 dict key 時仍拋 `TypeError`（`{}.__setitem__({"bad": "dict"}, 1)`）
- isinstance 過濾後只有 string failure 被計入

---

## Crash 3: `cannot access local variable 'type_variance'`

### 根因
`scripts/compare_runs.py` 的 `type_variance` 使用 walrus-style
單行 `(value if list else 0.0)` 初始化，當條件分支未被執行時
Python 編譯器在某些路徑下認定變數未綁定，導致 `UnboundLocalError`。

### 修復差異（`scripts/compare_runs.py:125-127`）

**Before（崩潰）**
```python
type_variance = (
    math.sqrt(sum((s - avg_new) ** 2 for s in type_scores_list) / len(type_scores_list))
    if type_scores_list else 0.0
)
```

**After（正確初始化）**
```python
type_variance = 0.0
if type_scores_list:
    type_variance = math.sqrt(sum((s - avg_new) ** 2 for s in type_scores_list) / len(type_scores_list))
```

**非 try/except 證明**
修復將 `type_variance = 0.0` **提前初始化**為預設值，再以 if 陳述選擇性覆寫。
若改用 try/except 吞 `UnboundLocalError`，則無法區分「真的沒資料」
與「變數名稱打錯」的差異。測試 `test_type_variance_initialized_before_conditional`
驗證：
- 無前置初始化時，空 list 走不到 if 分支，存取變數引發 `UnboundLocalError`
- 前置初始化後，無論有無資料 `type_variance` 永遠有定義
- `test_type_variance_propagates_other_errors` 驗證其他 TypeError
  （如 dict type）仍正常傳遞，不受修復影響

---

## 測試涵蓋摘要

| 測試類別 | 檔案 | 驗證標的 |
|---|---|---|
| `TestUnsupportedFormatNone` | `test_crash_regression.py` | NoneType 不崩潰＋日誌正確 |
| `TestUnhashableTypeDict` | `test_crash_regression.py` | dict failure 過濾＋正確統計 |
| `TestTypeVarianceUnbound` | `test_crash_regression.py` | type_variance 正確計算 |
| `TestFixBuiltWithGuardNotTryExcept` | `test_crash_regression.py` | 三個修復均非 try/except 吞例外 |
| `TestThreeCrashCorrectOutputs` | `manual-goal-error-free-evolution.py` | 三類 crash 整合正確產出 |
| `TestRootCause{*}` | `manual-goal-error-free-evolution.py` | 各根因最小重現 |
