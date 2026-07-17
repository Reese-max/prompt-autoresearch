# 測試完整性驗證報告

## 問題描述

先前狀態為「396 passed, 1 deselected」，其中 deselected 的測試無法證明目標要求的 failing test 曾存在或執行。

## 驗證日期

2026-07-18

## 驗證方法

1. 執行 `python -m pytest --tb=short -v` 完整測試套件
2. 檢查是否有 `@pytest.mark.skip`、`@pytest.mark.xfail`、`@pytest.mark.skipif` 等標記
3. 檢查 conftest.py 是否有 deselect 邏輯
4. 檢查 pytest.ini 是否有 deselect 設定

## 驗證結果

### 測試摘要

```
collected 398 items
398 passed in 16.26s
```

- **通過**: 398
- **失敗**: 0
- **跳過（skipped）**: 0
- **取消選擇（deselected）**: 0
- **xfail**: 0
- **xpass**: 0

### 覆蓋率摘要

```
TOTAL  1693 stmts  0 miss  100% coverage
```

所有模組（api/、lib/、scripts/）均達到 100% 覆蓋率。

### 標記檢查

- `@pytest.mark.skip` / `@pytest.mark.skipif`: 未發現
- `@pytest.mark.xfail`: 未發現
- conftest.py 中無 deselect 邏輯
- pytest.ini 中無 deselect 設定

## 結論

當前狀態已從「396 passed, 1 deselected」修正為「398 passed, 0 deselected」。所有398 條測試均正常執行且通過，無任何 skip、deselect 或 xfail 標記。先前 deselected 的 failing test 已透過以下修正重新納入測試套件：

1. `test_experiment_report_snapshot_rejects_semantically_wrong_output` — 修正 `run_app.py` 的 `build_experiment_report_snapshot()` 加入 `run_count` 驗證
2. `test_compare_pragmatic_rejects_risk_regression_below_baseline` — 修正 `compare_runs.py` 的 pragmatic 模式 c3 風險條件

完整的 red/green 證據紀錄請參閱 `docs/negative_test_failure_evidence.txt`。
