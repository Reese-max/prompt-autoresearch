# 跨 benchmark 極端分數排名紅→綠證據

## 目標

證明 `test_ranking_keeps_same_benchmark_best_version_over_extreme_other_benchmark` 曾在修復前失敗，並在修復後以相同測試通過。測試確認 `benchmark-b-extreme` 的極端分數不會取代 `benchmarks/a.jsonl` 比較群組的最佳候選，且勝者保留可稽核的 benchmark 群組證據。

## 基準與修復

- 修復前基準：`8bb84954d0a3af386a1509a26472eb92704769e6`。
- 修復提交：`d17a704963b89ada8cbcaaf7b45d89d954c3168c`，加入 benchmark 群組與 `selected_benchmark_group` 證據。
- 修復後目前提交：`49a578e82013610deadffef6c18f0d1db11f3a22`。

## 相同回歸測試

### RED：修復前

以 `git show 8bb8495:auto_evolve.py` 載入修復前實作，執行目前測試檔中的同一個 case。候選選擇與分數斷言先通過，但舊實作沒有 `selected_benchmark_group` 欄位，因此以 `KeyError` 失敗，exit code 為 `1`。

完整原始輸出：[controlled-closed-loop-extreme-benchmark-red.txt](evidence/controlled-closed-loop-extreme-benchmark-red.txt)

### GREEN：修復後

在目前 HEAD 執行完全相同的 pytest case，exit code 為 `0`，結果為 `1 passed`。

完整原始輸出：[controlled-closed-loop-extreme-benchmark-green.txt](evidence/controlled-closed-loop-extreme-benchmark-green.txt)

## 結論

紅燈輸出保留了修復前的具體 `KeyError`，綠燈輸出則是同一個測試的通過結果；因此可追溯證明目標證據欄位由缺失修復為可用。整體測試另於交付前執行，僅作回歸檢查。
