# CI 測試矩陣與跨平台執行結果（2026-07-19）

## 任務對齊

| 需求 | 落地 |
|---|---|
| 至少涵蓋 Windows 與 Linux（或 macOS）的 CI 測試矩陣 | `.github/workflows/ci.yml`：Linux × 3.10/3.11/3.12、macOS × 3.10/3.11/3.12、Windows × 3.10/3.11/3.12（共 9 格） |
| 分別保存平台名稱 | `platform` 欄位（JSONL／summary） |
| 分別保存執行指令 | `command` 欄位 |
| 分別保存退出碼 | `exit_code` 欄位 |
| 分別保存測試結果 | `test_set`／`summary`／M1–M6 明細 |

> 依 L012／L017／L019：本文件只記錄本輪可驗證的 Windows／Linux 實跑；其餘 CI 格以 workflow 設定為準，不冒充已在本機通過。

---

## 1. CI 測試矩陣（已提交）

來源：`.github/workflows/ci.yml`

| 組合 ID | 平台 | runs-on | Python | 執行指令 |
|---|---|---|---|---|
| L310 | Linux | ubuntu-latest | 3.10 | `python scripts/run_test_matrix.py --platform Linux --python-version 3.10` |
| L311 | Linux | ubuntu-latest | 3.11 | 同上（另含 coverage gate） |
| L312 | Linux | ubuntu-latest | 3.12 | 同上 |
| M310 | macOS | macos-latest | 3.10 | `python scripts/run_test_matrix.py --platform macOS --python-version 3.10` |
| M311 | macOS | macos-latest | 3.11 | 同上 |
| M312 | macOS | macos-latest | 3.12 | 同上 |
| W310 | Windows | windows-latest | 3.10 | `python scripts/run_test_matrix.py --platform Windows --python-version 3.10` |
| W311 | Windows | windows-latest | 3.11 | 同上 |
| W312 | Windows | windows-latest | 3.12 | 同上 |

每格 CI 步驟會輸出：

- `MATRIX_ENV`：`matrix_id` / `os` / `runner_os` / `python_*` / `test_command`
- `MATRIX_TARGET_RESULT`：上述欄位 + `exit_code` + `status`
- artifact：`ci-matrix-evidence-<platform>-<python>-<id>` → `matrix-<platform>-<python>.jsonl`

必要閘門 job：`test-matrix-required`（任一 matrix 格非 success 則失敗）。

---

## 2. 本輪本機／WSL 實跑紀錄

結構化彙總：[`docs/evidence/ci-matrix-summary.json`](evidence/ci-matrix-summary.json)

### 2.1 Windows（W311）

| 欄位 | 值 |
|---|---|
| **平台名稱** | Windows |
| **Runner** | HPZBOOKG10- / Windows 10 / AMD64 / Python 3.11.9 |
| **執行指令** | `python scripts/run_test_matrix.py --platform Windows --python-version 3.11` |
| **退出碼（ALL）** | **0** |
| **測試結果** | M1–M6 皆 0；M6：`632 passed, 2 skipped` |

明細 JSONL：[`docs/evidence/matrix-Windows-3.11-result.jsonl`](evidence/matrix-Windows-3.11-result.jsonl)  
主控台：[`docs/evidence/matrix-Windows-3.11-console.txt`](evidence/matrix-Windows-3.11-console.txt)

| test_set | exit_code | 結果摘要 |
|---|---:|---|
| M1 | 0 | runtime / pytest / preflight |
| M2 | 0 | 98 passed, 1 skipped |
| M3 | 0 | 128 passed |
| M4 | 0 | 89 passed |
| M5 | 0 | 96 passed |
| M6 | 0 | 632 passed, 2 skipped |
| **ALL** | **0** | PASS |

### 2.2 Linux（L312，WSL2）

| 欄位 | 值 |
|---|---|
| **平台名稱** | Linux |
| **Runner** | HPZBOOKG10 / Linux 5.15.167.4-microsoft-standard-WSL2 / x86_64 / Python 3.12.3 |
| **執行指令** | `python3 scripts/run_test_matrix.py --platform Linux --python-version 3.12` |
| **退出碼（ALL）** | **1**（僅 M1 preflight；pytest 全過） |
| **測試結果** | M2–M6 皆 0；M6：`634 passed`；M1=1（preflight baseline 路徑） |

明細 JSONL：[`docs/evidence/matrix-Linux-3.12-result.jsonl`](evidence/matrix-Linux-3.12-result.jsonl)  
主控台：[`docs/evidence/matrix-Linux-3.12-console.txt`](evidence/matrix-Linux-3.12-console.txt)

| test_set | exit_code | 結果摘要 |
|---|---:|---|
| M1 | 1 | preflight：`baseline dev run` 路徑為 Windows 反斜線；`MINIMAX_API_KEY` 缺失（矩陣會忽略 API key） |
| M2 | 0 | 99 passed |
| M3 | 0 | 128 passed |
| M4 | 0 | 89 passed |
| M5 | 0 | 96 passed |
| M6 | 0 | 634 passed |
| **ALL** | **1** | FAIL_M1_PREFLIGHT；**pytest 套件全過** |

---

## 3. 欄位契約（驗收對照）

每平台結果檔至少含：

| 需求欄位 | JSON 鍵 |
|---|---|
| 平台名稱 | `platform` |
| 執行指令 | `command` |
| 退出碼 | `exit_code` |
| 測試結果 | `test_set` + `tests` / `summary` / `status` |

---

## 4. 結論

1. **CI 矩陣已建立並涵蓋 Windows + Linux + macOS**（各 3 個 Python 小版本）。
2. **本輪可驗證實跑**：Windows ALL=`0`；Linux pytest（M2–M6）全過，M1 preflight 在 WSL 工作樹上因路徑分隔而 `exit_code=1`（已如實記錄，未偽造成功）。
3. 證據路徑見 §2 與 `docs/evidence/ci-matrix-summary.json`。
