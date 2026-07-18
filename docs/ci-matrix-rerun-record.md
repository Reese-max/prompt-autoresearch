# CI 矩陣可重跑紀錄（2026-07-18）

## 變更目的

- 在 CI 執行中，讓每個 `matrix` 工作可輸出**可識別目標**的環境資訊與測試結果。
- 每個目標（作業系統 × Python 版本）必須留下 **OS、Python 版本、測試命令、退出碼**，並在失敗時印出明確 `MATRIX_TARGET_FAIL`，避免單一成功紀錄冒充全量驗證。
- 每個目標產出可下載的 evidence artifact，支援獨立辨識與重跑。

## 變更內容

1. `.github/workflows/ci.yml`
   - Job 名稱模板：`${{ matrix.id }} (${{ matrix.os }}, Python ${{ matrix.python_version }})`。
   - `Record environment`：輸出 `MATRIX_ENV`（`matrix_id` / `os` / `runner_os` / `python_requested` / `python_version` / `python_executable`）。
   - `Run acceptance test suite`：
     - 執行前再印 `MATRIX_ENV` 與 `TEST_*` 欄位。
     - 以子程序執行驗收命令並**一定**輸出：
       - `MATRIX_TARGET_RESULT`：含 `os`、`python_version`、`test_command`、`exit_code`、`status`
       - 失敗時另印 `MATRIX_TARGET_FAIL`（同上欄位）
     - 寫入 `matrix-${{ matrix.id }}.jsonl`
   - `Upload CI matrix evidence`（`always()`）上傳 `ci-matrix-evidence-<id>`。
   - L311 coverage gate 同樣輸出 `MATRIX_ENV` / `MATRIX_TARGET_RESULT` / `MATRIX_TARGET_FAIL`。

2. 驗收命令（九格矩陣共用）

```bash
python -m pytest tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

## 日誌標記約定

| 標記 | 時機 | 必要欄位 |
|------|------|----------|
| `MATRIX_ENV` | 環境記錄／測試前 | `matrix_id`, `os`, `python_version`（或 `python_requested`）, `test_command`（測試步驟） |
| `MATRIX_TARGET_RESULT` | 測試結束（成功或失敗） | `matrix_id`, `os`, `python_version`, `test_command`, `exit_code`, `status` |
| `MATRIX_TARGET_FAIL` | `exit_code != 0` | 同上，便於 log 搜尋失敗目標 |

`status`：`PASS`（`exit_code=0`）或 `FAIL`（非零）。

## 可重跑方式

本機對齊單一矩陣目標（以 W311 為例）：

```bash
python -m pytest tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

在 CI 日誌中以 `matrix_id`（如 `L310`、`M311`、`W312`）過濾，或下載 artifact
`ci-matrix-evidence-<id>` 內的 `matrix-<id>.jsonl` 核對 `exit_code`。

## 完成判定

- 同一輪 CI 的 9 個 matrix job **各自**留下可識別的 `MATRIX_TARGET_RESULT`。
- 不得以單一 job 成功代替其餘 8 格；任一目標 `exit_code != 0` 即阻擋合併（workflow 失敗）。
- 失敗 job 必須出現 `MATRIX_TARGET_FAIL`，並含 OS、Python 版本、測試命令、退出碼。
