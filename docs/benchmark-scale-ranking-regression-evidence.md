# Benchmark 排名回歸紅綠證據

## 缺陷

`auto_evolve._rank_candidate_evaluations` 不能把不同 benchmark 的 raw score 放在同一條量尺上比較。具名 benchmark 也必須各自保留最佳版本；例如 `fractional` 的 `0.94` 與 `percentage` 的 `88` 不應互相淘汰。

## 可定位的程式碼差異

- 修復提交：`adec5e7f63cd0e03814dfd26d47aa3f21849a444`（`fix: 依 benchmark 識別碼分組選出最佳版本`）。
- 修復前基準：`c272de61339db949553efa20ebd4ecc8ab859d42`。
- 目前實作位置：`auto_evolve.py:47` 的 benchmark 欄位、`auto_evolve.py:81-127` 的比較／群組鍵、`auto_evolve.py:240-275` 的評測正規化，以及 `auto_evolve.py:299-466` 的分組排名與 `best_versions_by_benchmark` 證據。
- 回歸測試位置：`tests/test_benchmark_scale_ranking_regression.py:79-112`。

## 相同回歸測試的 red → green

### RED：修復前

以 `git show adec5e7^:auto_evolve.py` 載入修復前實作，執行同一個具名 benchmark case；失敗為 `KeyError: 'fractional'`，exit code `1`。

原始輸出：[benchmark-scale-ranking-red.txt](evidence/benchmark-scale-ranking-red.txt)

### GREEN：修復後

在目前工作樹執行同一回歸測試檔的 5 個案例，exit code `0`，結果為 `5 passed`。

原始輸出：[benchmark-scale-ranking-green.txt](evidence/benchmark-scale-ranking-green.txt)

## 整套驗證

命令：`python -m pytest --color=no --tb=short`；exit code `0`。

關鍵輸出：`1140 passed, 2 skipped in 96.78s`；coverage `TOTAL 4556 Stmts, 1048 Miss, 76%`。

## 結論

紅燈直接重現修復前缺少 benchmark 分組的錯誤；綠燈確認 fractional、percentage、具名 benchmark 與極端分數隔離案例均通過。整套測試亦在同一工作樹完成，沒有因定向證據新增回歸。
