# Mutation Testing 報告：compare_runs.py c2 題型退步邊界

**日期**：2026-07-18
**目標**：證明 100% code coverage + 既有通過測試不足以保證 correctness

---

## Mutation 目標

| 項目 | 內容 |
|---|---|
| 被測檔案 | `scripts/compare_runs.py:164` |
| 原始邏輯 | `if b_val - n_val > 3.0:`（題型退步 **超過** 3.0 分才拒絕） |
| 變異邏輯 | `if b_val - n_val >= 3.0:`（題型退步 **達到** 3.0 分即拒絕） |
| Mutation 類型 | 比較邊界從 strict inequality `>` 改為 non-strict `>=` |

### 為何選此目標

`compare_runs.py` 的 `c2` 條件控制「單一題型退步上限」。既有的 `test_compare_type_regression_gate` 測試只驗證了 10 分退步（遠超閾值），未覆蓋恰好 3.0 分的邊界值，因此無法偵測到 `>` → `>=` 的變異。

---

## 實驗步驟與結果

### Step 1：原始程式碼（無 mutation）

- 398 passed, 0 failed, 100% coverage
- 新增的邊界測試 `test_compare_type_regression_exactly_3_points_still_accepted` **通過**

### Step 2：套用 mutation（`>` → `>=`）

- 398 passed（既有測試全數通過——mutation 存活）
- 100% coverage 不變
- 新增的邊界測試 **失敗**（AssertionError）

### Step 3：還原 mutation

- 399 passed（398 原有 + 1 新增），0 failed, 100% coverage

---

## 洩漏的變異證據

```
FAILED tests/test_compare_runs.py::test_compare_type_regression_exactly_3_points_still_accepted
E   AssertionError: 題型退步恰好 3.0 分應被接受（c2 門檻為 > 3.0），但實際判定為 REVERT——可能被變異為 >= 3.0
```

輸出對照：
| 指標 | 原始（`>`） | 變異（`>=`） |
|---|---|---|
| 事實題型退步 | 3.0 分 | 3.0 分 |
| c2 判定 | 通過 | **拒絕** |
| 最終判定 | ACCEPT | **REVERT** |

---

## 結論

1. **100% code coverage 不等於 correctness**：所有行都被執行，但邊界值（3.0 分）未被斷言，變異存活。
2. **既有通過測試不足以捕獲邊界退化**：398 個測試全部通過，但 `>` → `>=` 的語義差異未被發現。
3. **新增的邊界值測試成功捕獲變異**：`test_compare_type_regression_exactly_3_points_still_accepted` 在 mutation 下失敗，證明該測試提升了 correctness 保證。

---

## 修復

新增測試 `test_compare_type_regression_exactly_3_points_still_accepted`（`tests/test_compare_runs.py`），
覆蓋題型退步恰好 3.0 分的邊界情境，確認 `c2` 條件的 `>` 邏輯正確。
