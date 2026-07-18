# CI 設定與平台矩陣執行紀錄佐證（2026-07-19）

## 任務對齊

**問題**：僅憑單次 `exit=0` 或覆蓋率輸出，無法證明 Linux／macOS／Windows × Python 3.10／3.11／3.12 已在流水線自動執行。

**本文件交付**：

1. **CI 設定佐證** — 完整 9 格 matrix 定義（對齊 `.github/workflows/ci.yml`）
2. **平台矩陣執行紀錄** — 本輪可驗證的本機 W311 實跑 `MATRIX_RESULT`（含 runner 身分）
3. **流水線證據契約** — 每個 matrix job 必須留下的日誌標記與 artifact，避免單點冒充全量

> 依 L012／L017／L019／L026／L027：本文件**不**以覆蓋率摘要或單一成功輸出宣稱九格皆已通過；未在本機實際執行的 OS／Python 組合，狀態標為「僅 CI 設定、待 runner 實跑紀錄」。

---

## 1. CI 設定佐證（流水線已宣告全矩陣）

來源：`.github/workflows/ci.yml`（workflow 名稱 `CI`）。  
結構化快照：`docs/evidence/ci-matrix-config-snapshot.json`。

| 組合 ID | `runs-on` | platform | Python | 測試入口 | Coverage gate | Job 顯示名模板 |
|---|---|---|---|---|---|---|
| L310 | `ubuntu-latest` | Linux | 3.10 | `scripts/run_test_matrix.py` | 否 | `L310 (ubuntu-latest, Python 3.10)` |
| L311 | `ubuntu-latest` | Linux | 3.11 | `scripts/run_test_matrix.py` | **是**（≥80%，`scripts/`+`api/`） | `L311 (ubuntu-latest, Python 3.11)` |
| L312 | `ubuntu-latest` | Linux | 3.12 | `scripts/run_test_matrix.py` | 否 | `L312 (ubuntu-latest, Python 3.12)` |
| M310 | `macos-latest` | macOS | 3.10 | `scripts/run_test_matrix.py` | 否 | `M310 (macos-latest, Python 3.10)` |
| M311 | `macos-latest` | macOS | 3.11 | `scripts/run_test_matrix.py` | 否 | `M311 (macos-latest, Python 3.11)` |
| M312 | `macos-latest` | macOS | 3.12 | `scripts/run_test_matrix.py` | 否 | `M312 (macos-latest, Python 3.12)` |
| W310 | `windows-latest` | Windows | 3.10 | `scripts/run_test_matrix.py` | 否 | `W310 (windows-latest, Python 3.10)` |
| W311 | `windows-latest` | Windows | 3.11 | `scripts/run_test_matrix.py` | 否 | `W311 (windows-latest, Python 3.11)` |
| W312 | `windows-latest` | Windows | 3.12 | `scripts/run_test_matrix.py` | 否 | `W312 (windows-latest, Python 3.12)` |

附加必要檢查 job：

| Job | 名稱 | 作用 |
|---|---|---|
| `test-matrix-required` | `test-matrix-required` | `needs: [test]`；任一 matrix 格非 `success` 則失敗，供 branch protection 設為 required check |

`strategy.fail-fast: false`：單一格失敗不中斷其餘格，便於一次取得全矩陣結果；彙總閘門仍由 `test-matrix-required` 阻擋合併。

### 每格強制產出的證據契約（不可省略）

| 步驟 | 標記／產物 | 必含欄位 |
|---|---|---|
| Record environment | `MATRIX_ENV` | `matrix_id`, `os`, `runner_os`, `python_requested`, `python_version`, `python_executable` |
| Run full automated test suite | 再印 `MATRIX_ENV`；結束印 `MATRIX_TARGET_RESULT`；失敗另印 `MATRIX_TARGET_FAIL` | 另含 `test_command`, `exit_code`, `status` |
| 測試本體 | `MATRIX_RESULT`（M1–M6 與 `ALL`） | `matrix_id`, `platform`, `python_version`, `test_set`, `exit_code` |
| Upload | artifact `ci-matrix-evidence-<id>` → 檔案 `matrix-<id>.jsonl` | 每格獨立上傳，`if: always()` |

**判定規則**：同一輪 CI 的 9 個 job **各自**必須有可識別的 `MATRIX_TARGET_RESULT`；**不得**以 W311 單點、單一 coverage 或單一 `exit=0` 代替其餘 8 格。

---

## 2. 本輪平台矩陣執行紀錄（可驗證）

### 2.1 Runner 身分（避免「未標示來源」）

| 欄位 | 值 |
|---|---|
| 記錄時間 | 2026-07-19 |
| hostname | `HPZBOOKG10-` |
| OS | Windows 10（`platform.system()=Windows`） |
| machine | AMD64 |
| Python | 3.11.9 |
| `sys.platform` | `win32` |
| executable | `C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` |
| matrix_id | `W311`（本機對齊 CI 組合 ID） |
| 命令 | `python scripts/run_test_matrix.py --platform Windows --python-version 3.11` |
| 原始 jsonl | [`docs/evidence/matrix-W311-local.jsonl`](evidence/matrix-W311-local.jsonl) |
| 主控台摘要 | [`docs/evidence/matrix-W311-local-console.txt`](evidence/matrix-W311-local-console.txt) |

### 2.2 W311 `MATRIX_RESULT`（本輪實跑）

| test_set | exit_code | 摘要 |
|---|---|---|
| M1 | 0 | runtime / pytest / preflight |
| M2 | 0 | `tests/test_cross_platform.py`（79 passed） |
| M3 | 0 | config／io 相關（128 passed） |
| M4 | 0 | gatekeeper／preflight／entrypoints（89 passed） |
| M5 | 0 | API 相關（96 passed） |
| M6 | 0 | 全量 `tests/`（612 passed；本機 coverage 總計 99%，**僅代表 win32／3.11.9**） |
| **ALL** | **0** | M1–M6 皆 0 |

原始 JSONL（七行，僅含本輪 W311；不含其他 OS／版本冒充紀錄）：

```jsonl
{"matrix_id": "W311", "platform": "Windows", "python_version": "3.11.9", "test_set": "M1", "tests": ["runtime", "pytest --version", "scripts/preflight.py --json"], "exit_code": 0}
{"matrix_id": "W311", "platform": "Windows", "python_version": "3.11.9", "test_set": "M2", "tests": ["tests/test_cross_platform.py"], "exit_code": 0}
{"matrix_id": "W311", "platform": "Windows", "python_version": "3.11.9", "test_set": "M3", "tests": ["tests/test_lib_io.py", "tests/test_lib_config.py", "tests/test_lib_config_regression.py", "tests/test_lib_config_cache_stability.py", "tests/test_config_semantic.py", "tests/test_config_integration.py", "tests/test_config_special_branch.py"], "exit_code": 0}
{"matrix_id": "W311", "platform": "Windows", "python_version": "3.11.9", "test_set": "M4", "tests": ["tests/test_gatekeeper.py", "tests/test_preflight.py", "tests/test_script_entrypoints.py"], "exit_code": 0}
{"matrix_id": "W311", "platform": "Windows", "python_version": "3.11.9", "test_set": "M5", "tests": ["tests/test_api_server.py", "tests/test_api_server_gaps.py", "tests/test_integration_server_feedback.py", "tests/test_lib_api.py", "tests/test_lib_api_error_contract.py", "tests/test_lib_api_external_failures.py", "tests/test_lib_api_http_status_codes.py", "tests/test_lib_api_line37_branch.py", "tests/test_lib_api_positive_verify.py", "tests/test_lib_api_rate_wait_branch.py"], "exit_code": 0}
{"matrix_id": "W311", "platform": "Windows", "python_version": "3.11.9", "test_set": "M6", "tests": ["tests/"], "exit_code": 0}
{"matrix_id": "W311", "platform": "Windows", "python_version": "3.11.9", "test_set": "ALL", "tests": ["M1", "M2", "M3", "M4", "M5", "M6"], "exit_code": 0}
```

### 2.3 九格狀態表（設定 vs 本輪可驗證執行）

| 組合 ID | CI 設定已提交 | 本輪可驗證執行紀錄 | 說明 |
|---|---|---|---|
| L310 | 是 | **無** | 需 GitHub `ubuntu-latest` runner；本工作區無 Linux 3.10 |
| L311 | 是 | **無** | 另含 coverage gate；不得以本機 win32 coverage 代替 |
| L312 | 是 | **無** | 同上 |
| M310 | 是 | **無** | 需 `macos-latest` |
| M311 | 是 | **無** | 需 `macos-latest` |
| M312 | 是 | **無** | 需 `macos-latest` |
| W310 | 是 | **無** | 本機僅有 3.11.9，腳本會拒絕 `--python-version 3.10` |
| W311 | 是 | **有**（§2.2，`ALL exit_code=0`） | 本機實跑；CI 上仍應產出獨立 `ci-matrix-evidence-W311` |
| W312 | 是 | **無** | 本機無 3.12 解譯器 |

本工作區 **無 git remote**，無法拉取 GitHub Actions run log／artifact；因此 **不能** 宣稱 L310–W312 的 runner 實跑已完成。可宣稱者僅：

1. CI **設定**已完整覆蓋 9 格，且每格有強制證據契約；
2. W311 本輪本機矩陣 **已** 留下可識別執行紀錄。

---

## 3. 為何「單次 exit=0／覆蓋率」不足（對齊 L026／L027）

| 證據類型 | 能證明什麼 | 不能證明什麼 |
|---|---|---|
| 本機一次 `pytest` exit=0 | 當前環境測試通過 | 其他 OS／Python 有跑 |
| `coverage.xml`／htmlcov | 該次執行的行／分支覆蓋 | 覆蓋率來源平台；九格各自通過 |
| 僅 `ci.yml` 有 matrix | 流水線**會**開 9 個 job | 該輪實際是否成功 |
| 每格 `MATRIX_TARGET_RESULT` + artifact | 指定 `(matrix_id, os, python)` 的實際退出碼 | —（此為完整證明） |

**正確證明路徑**：CI 同一 run 下載九份 `ci-matrix-evidence-<id>`，或於 log 以 `matrix_id` 過濾九筆 `MATRIX_TARGET_RESULT` 且 `status=PASS`，並確認 `test-matrix-required` 為 success。

---

## 4. 可重現命令

### 4.1 本機對齊單一格（僅當 OS／Python 相符）

```powershell
$env:CI_MATRIX_ID = "W311"
$env:CI_MATRIX_REPORT_PATH = "docs/evidence/matrix-W311-local.jsonl"
python scripts/run_test_matrix.py --platform Windows --python-version 3.11
```

與 runtime 不符時腳本 `exit_code=2` 拒絕，避免誤標通過。

### 4.2 CI 每格（已寫入 workflow）

```text
python scripts/run_test_matrix.py --platform <Linux|macOS|Windows> --python-version <3.10|3.11|3.12>
```

環境變數：`CI_MATRIX_ID`、`CI_MATRIX_PLATFORM`、`CI_MATRIX_PYTHON`、`CI_MATRIX_RUNNER_OS`、`CI_MATRIX_REPORT_PATH=matrix-<id>.jsonl`。

---

## 5. 交付清單（本 commit）

| 路徑 | 角色 |
|---|---|
| `.github/workflows/ci.yml` | CI 設定本體（既有；9 格 + 證據步驟 + required gate） |
| `docs/evidence/ci-matrix-config-snapshot.json` | CI 矩陣設定結構化快照 |
| `docs/evidence/matrix-W311-local.jsonl` | 本輪 W311 實跑 `MATRIX_RESULT` |
| `docs/evidence/matrix-W311-local-console.txt` | 本輪主控台輸出備份 |
| `docs/ci-matrix-pipeline-evidence-20260719.md` | 本佐證報告 |

---

## 6. 結論

| 主張 | 是否成立 | 依據 |
|---|---|---|
| CI 已設定 Linux／macOS／Windows × 3.10／3.11／3.12 共 9 格 | **是** | `ci.yml` + `ci-matrix-config-snapshot.json` |
| 每格在 CI 會留下可識別環境／結果／artifact | **是（契約）** | `MATRIX_*` 標記與 upload-artifact 步驟 |
| 本輪已取得 W311 本機全矩陣通過紀錄 | **是** | `matrix-W311-local.jsonl`（ALL=0） |
| 本輪已取得其餘 8 格 runner 實跑成功 | **否（誠實標示）** | 無對應 OS／Python 或無 GH Actions run |
| 僅用單次 exit=0 或 coverage 即可代表全矩陣 | **否** | §3；與任務／L026–L027 一致 |

*產製日期：2026-07-19。工作目錄：本 repo worktree；未使用其他 repo 路徑。*
