# CI 矩陣可重跑紀錄（2026-07-18）

## 變更目的

- 在 CI 執行中，讓每個 `matrix` 工作可輸出**可識別目標**的測試結果。
- 讓每一個目標（作業系統 × Python 版本）都能留下可重播、可比對的輸出檔。

## 變更內容

1. `scripts/run_test_matrix.py`
   - `MATRIX_RESULT` 的 JSON 中新增 `matrix_id` 欄位（預設為 `local`）。
   - 新增 `CI_MATRIX_REPORT_PATH` 環境變數：若設定，會把每筆 `MATRIX_RESULT` 同步寫入 JSONL。
   - 由 CI 步驟設定 `CI_MATRIX_ID` 與 `CI_MATRIX_REPORT_PATH`。
2. `.github/workflows/ci.yml`
   - `Run full automated test suite` 步驟改為傳入：
     - `CI_MATRIX_ID: ${{ matrix.id }}`
     - `CI_MATRIX_REPORT_PATH: matrix-${{ matrix.id }}.jsonl`
   - 新增 `Upload CI matrix evidence`（`always()`）上傳 `matrix-${{ matrix.id }}.jsonl`。

## 可重跑與驗證方式

每個目標環境重跑命令（在該環境本機）如下：

```bash
python scripts/run_test_matrix.py --platform <Linux|macOS|Windows> --python-version 3.10|3.11|3.12
```

CI 每一個 job 會在成功或失敗後，輸出同一組 `MATRIX_RESULT`，
並附上以下欄位：

- `matrix_id`（如 `L310`, `M311`, `W312`）
- `platform`
- `python_version`
- `test_set`
- `tests`
- `exit_code`

每個矩陣目標會留下 `matrix-<id>.jsonl`，在 Actions 成果中以 artifact
`ci-matrix-evidence-<id>` 下載可查。

## 本次本機執行紀錄（已完成）

- 平台：Windows
- Python：3.11.9
- 輸入：`python scripts/run_test_matrix.py --platform Windows --python-version 3.11`
- 結果：
  - `M1`, `M2`, `M3`, `M4`, `M5`, `M6`, `ALL` 皆為 `exit_code=0`
  - `matrix_id=local`

> 備註：本機只能實際補上當前執行環境；若要完整覆蓋 9 組合，請以 CI 流程執行。
