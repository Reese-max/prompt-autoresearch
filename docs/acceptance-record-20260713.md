# 驗收紀錄（2026-07-13，取代先前矛盾輸出）

## 問題

先前一輪驗收輸出自相矛盾：頂部統計顯示 `passed=1`，但同一份輸出內嵌的
pytest 摘要為 `278 passed, 1 deselected`。原因是頂部的 `passed` 計數的是
「驗收項目數」（1 個驗收步驟通過），而非 pytest 測試數，兩個不同單位的
數字被並列呈現，造成矛盾且無法追溯。本紀錄以單一口徑（pytest 測試數）
重新實跑產生。

## 驗收摘要（單一口徑：pytest 測試數）

| 項目 | 值 |
|---|---|
| passed | 283 |
| deselected | 1 |
| failed | 0 |
| exit code | 0 |

（舊輸出的 278 為當時測試數；其後分支又新增測試，現為 283，以本次實跑為準。）

## 可追溯資訊

- 執行日期：2026-07-13
- 執行 commit：`f9bc42d3b84705801fba3e3416e4fcfda40352fe`（分支 `adng/f3c5d0c5` HEAD）
- Python：3.11.9
- 執行指令：

```
python -m pytest tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

- pytest 摘要原文（最後一行）：

```
283 passed, 1 deselected in 9.36s
```

- deselected 的 1 條為 `tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract`
  （快照契約測試，沿用 `docs/engine-end-to-end-selfcheck.md` 既有的驗收排除項）。
- coverage（lib/api/scripts 合計）：99%（1629 stmts / 23 miss），由 pytest.ini
  預設 `--cov` 產出。

任何人可在上述 commit 以同一指令重現本紀錄。
