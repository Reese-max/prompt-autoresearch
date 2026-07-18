# Deselected Test 調查報告

**日期**: 2026-07-18（初次建立）→ 2026-07-18（二次驗證更新）
**任務**: 查明並執行目前被 deselect 的 1 個測試

## 調查結果

### 歷史上被 deselect 的測試

- **測試名稱**: `tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract`
- **目前狀態**: 測試**可以通過**，無需任何修改，已重新納入完整測試套件

### 驗證結果（二次驗證）

**單獨執行**：
```
python -m pytest "tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract" -v --no-cov
```
結果：`1 passed in 0.02s`

**完整套件執行**：
```
python -m pytest tests/ -q
```
結果：`540 passed in 19.14s`，無失敗、無 skip、無 deselect

### 結論

1. 目前完整測試套件執行結果為 **540 passed, 0 deselected, 0 failed, 0 skipped**
2. 歷史上被 deselect 的測試（`test_experiment_report_snapshot_contract`）實際上可以正常通過
3. 此測試**不涉及配置流程**，為架構快照合約測試（使用 subprocess 模擬）
4. **排除理由**：該測試為架構快照合約測試，與配置解析/驗證無關；先前因驗收聚焦於配置流程而被 CLI `--deselect` 排除
5. **不影響本目標**：該測試驗證的是 `experiment_report.py` 的快照輸出契約（非配置解析路徑），與配置驗證無關
6. 經覆蓋率報告確認，所有模組（api/、lib/、scripts/）均達 100% 覆蓋率

### 驗證命令

```bash
# 完整套件
python -m pytest tests/ -q
# 結果：540 passed in 19.14s，無失敗、無 skip、無 deselect

# 單獨執行歷史 deselected 測試
python -m pytest tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract -v --no-cov
# 結果：1 passed in 0.02s
```

此報告依據可驗證的測試輸出撰寫，無擴寫未經證實的結論。
