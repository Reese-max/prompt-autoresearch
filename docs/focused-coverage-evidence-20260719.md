# 新失敗／清理測試精簡 pytest 與覆蓋率佐證（2026-07-19）

## 結論

三組新測試的精簡執行共 `29 passed`，失敗、例外、資源清理與 HTTP 回傳案例均實測通過。以同一組直接相關既有測試建立基線後加入新測試，目標模組未命中行由 `440` 降至 `422`，未命中分支由 `181` 降至 `176`。

## 執行環境與範圍

- Python `3.11.9`、pytest `9.1.1`、Coverage.py `7.14.1`、Windows `win32`。
- 目標模組：`api/server.py`、`api/feedback.py`、`api/continuous_optimizer.py`、`lib/api.py`、`run_opt.py`、`scripts/run_core_flow_e2e.py`。
- 新測試：`tests/test_core_e2e_failure_paths.py`、`tests/test_cleanup_regressions.py`，以及 `tests/test_integration_server_feedback.py::test_feedback_core_failures_reach_http_error_or_endpoint_fallback`。

## pytest 結果

| 輪次 | 測試結果 | 覆蓋率模式 |
|---|---:|---|
| 既有相關測試基線 | `127 passed, 3 deselected` | `--cov-branch` |
| 基線加上三組新測試 | `156 passed` | `--cov-branch` |
| 三組新測試單獨執行 | `29 passed` | `--cov-branch` |
| 全量 `python -m pytest -q` | `665 passed, 2 skipped` | pytest.ini 預設 coverage |

新測試的 29 個案例由下列參數化分支組成：核心負向測試 `21` 個、清理回歸 `5` 個、回饋 HTTP 失敗／回退 `3` 個。

## 覆蓋率比對

| 模組 | 未命中行（基線 → 增量） | 行覆蓋率 | 未命中分支（基線 → 增量） |
|---|---:|---:|---:|
| `api/continuous_optimizer.py` | `0 → 0` | `100% → 100%` | `0 → 0` |
| `api/feedback.py` | `14 → 14` | `83% → 83%` | `7 → 7` |
| `api/server.py` | `1 → 1` | `99% → 99%` | `1 → 1` |
| `lib/api.py` | `1 → 1` | `96% → 96%` | `2 → 2` |
| `run_opt.py` | `400 → 394` | `15% → 17%` | `155 → 153` |
| `scripts/run_core_flow_e2e.py` | `24 → 12` | `78% → 86%` | `16 → 13` |
| **合計** | **`440 → 422`** | **`56% → 57%`** | **`181 → 176`** |

新增命中的主要未執行區域：

- `run_opt.py:418-419, 421, 424-426`：封存清理迴圈與刪除失敗傳播。
- `scripts/run_core_flow_e2e.py:318, 370-371, 377, 382, 384-385, 394, 404, 415-416, 421`：規格失敗回傳、CLI 退出碼與失敗後流程清理。

Coverage 的 partial branch 計數由 `19` 變為 `22`；這是新增測試首次觸及部分條件後的非單調指標，未將其誤報為完整分支閉合。此次可驗證的改善以未命中行減少 `18`、未命中分支減少 `5` 為準。

## 可重跑命令

```powershell
$env:PYTHONPATH=(Get-Location).Path
$base = @(
  "tests/test_api_server.py",
  "tests/test_api_server_gaps.py",
  "tests/test_integration_server_feedback.py",
  "tests/test_continuous_optimizer.py",
  "tests/test_core_flow_e2e.py",
  "tests/test_lib_api.py",
  "tests/test_lib_api_error_contract.py",
  "tests/test_lib_api_external_failures.py",
  "tests/test_lib_api_rate_wait_branch.py",
  "tests/test_untested_entrypoints.py"
)
$cov = @(
  "--cov=api.server",
  "--cov=api.feedback",
  "--cov=api.continuous_optimizer",
  "--cov=lib.api",
  "--cov=scripts.run_core_flow_e2e",
  "--cov=run_opt",
  "--cov-branch",
  "--cov-report=term-missing"
)
python -m pytest $base -q -o addopts= --deselect tests/test_integration_server_feedback.py::test_feedback_core_failures_reach_http_error_or_endpoint_fallback $cov
python -m pytest ($base + @(
  "tests/test_core_e2e_failure_paths.py",
  "tests/test_cleanup_regressions.py"
)) -q -o addopts= $cov
python -m pytest tests/test_core_e2e_failure_paths.py tests/test_cleanup_regressions.py tests/test_integration_server_feedback.py::test_feedback_core_failures_reach_http_error_or_endpoint_fallback -q -o addopts= $cov
```
