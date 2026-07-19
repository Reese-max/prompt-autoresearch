# 核心 E2E 與分支覆蓋率驗收（2026-07-19）

## 測試案例

- `tests/test_core_flow_e2e.py::test_main_relative_out_creates_missing_parent`：
  相對 `--out` 路徑會以 `PROJECT_ROOT` 為基準，並建立原本不存在的父目錄。
- `tests/test_core_flow_e2e.py::test_main_cleanup_ignores_created_parent_rmdir_error`：
  寫檔失敗後會刪除半成品；若新建父目錄仍被使用而無法刪除，原始錯誤仍會正確傳遞。

## 可重跑驗收

```powershell
python -m pytest tests/test_core_flow_e2e.py tests/test_core_e2e_failure_paths.py -q -o addopts= --cov=scripts.run_core_flow_e2e --cov-branch --cov-report=term-missing
```

結果：`38 passed`。

| 檔案 | Statements | 缺失行 | Branches | 缺失分支 | Partial branches | Coverage |
|---|---:|---:|---:|---:|---:|---:|
| `scripts/run_core_flow_e2e.py` | 158 | 0 | 42 | 0 | 0 | 100% |

逐檔原始 coverage 報告：
[`docs/evidence/core-flow-e2e-coverage-20260719.json`](evidence/core-flow-e2e-coverage-20260719.json)。

## 核心 E2E 結果

```powershell
python scripts/run_core_flow_e2e.py --quiet --out docs/evidence/core-flow-e2e-Windows-3.11-20260719.json
```

- `spec_ok=true`
- `spec_failures=[]`
- `exit_code=0`
- `comparable_digest=1cb2551633b57a0440842185e5311842ff6ba4a1abeaa1591fd32d74092e84ab`

完整 E2E 輸出：
[`docs/evidence/core-flow-e2e-Windows-3.11-20260719.json`](evidence/core-flow-e2e-Windows-3.11-20260719.json)。
