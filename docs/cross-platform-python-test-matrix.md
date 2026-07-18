# 跨平台／多版本測試矩陣

## 支援範圍

本 repo 宣告支援 CPython 3.10、3.11、3.12，涵蓋 Linux、macOS、Windows。`scripts/preflight.py` 已將 Python 3.10 設為最低版本；Python 3.9 以下不在支援範圍，Python 3.13 以上尚未納入本矩陣。

目前可追溯的執行證據如下：

- Linux／Python 3.11：`.github/workflows/ci.yml` 已設定 CI 工作。
- Windows／Python 3.11.9：本機完整測試已通過。
- 其餘組合：列為待驗證，不視為已通過。

## 本地單一驗證入口

先啟用已安裝 `requirements.txt` 與 `requirements-dev.txt` 的目標 Python 環境，再以一個命令執行該平台／版本的 `M1` 至 `M6`：

```bash
python scripts/run_test_matrix.py --platform Windows --python-version 3.11
```

`--platform` 可指定 `Linux`、`macOS` 或 `Windows`；`--python-version` 可指定 `3.10`、`3.11` 或 `3.12`。腳本會拒絕與目前主機或解譯器不符的指定值，並為每個集合輸出一行 `MATRIX_RESULT` JSON，包含實際平台、完整 Python 版本、測試集合與退出碼；最後一行 `ALL` 是整體退出碼。

## 可重現的本機矩陣

`requirements.lock` 鎖定測試所需的直接與傳遞相依套件；請從新的 virtual environment 安裝它，且使用 `--no-deps`，避免 pip 重新解析出未鎖定的版本。每次只執行與目前主機及解譯器版本相符的一列；要跑完整矩陣，就在對應平台各以 3.10、3.11、3.12 重複以下步驟。

所有命令均在 repo 根目錄執行，並直接呼叫 virtual environment 內的 Python，不需要啟用環境。`pip check` 必須成功後才執行矩陣。

### Linux（範例：CPython 3.11）

```bash
python3.11 -m venv .venv-3.11
.venv-3.11/bin/python -m pip install --no-deps -r requirements.lock
.venv-3.11/bin/python -m pip check
.venv-3.11/bin/python scripts/run_test_matrix.py --platform Linux --python-version 3.11
```

### macOS（範例：CPython 3.11）

```bash
python3.11 -m venv .venv-3.11
.venv-3.11/bin/python -m pip install --no-deps -r requirements.lock
.venv-3.11/bin/python -m pip check
.venv-3.11/bin/python scripts/run_test_matrix.py --platform macOS --python-version 3.11
```

### Windows PowerShell（範例：CPython 3.11）

```powershell
python -m venv .venv-3.11
& .\.venv-3.11\Scripts\python.exe -m pip install --no-deps -r requirements.lock
& .\.venv-3.11\Scripts\python.exe -m pip check
& .\.venv-3.11\Scripts\python.exe scripts\run_test_matrix.py --platform Windows --python-version 3.11
```

Windows 的 `python` 必須是目標 CPython 版本；若有 `py` launcher，可將第一行改成 `py -3.10 -m venv .venv-3.10` 或 `py -3.12 -m venv .venv-3.12` 來選擇版本。三個平台均將範例中的 `3.11` 同步替換為 `3.10` 或 `3.12`，並使用各自的 `.venv-<版本>` 目錄，即可完成該主機可執行的三個版本列。

驗證成功時，最後一行會是 `test_set` 為 `ALL` 且 `exit_code` 為 `0` 的 `MATRIX_RESULT`。`--platform` 或 `--python-version` 與實際環境不符時，腳本會以退出碼 `2` 拒絕執行，避免把非目標組合誤標為通過。

## 組合矩陣

每一列都必須執行 `M1` 至 `M6`。`M2` 至 `M5` 是核心功能分組，`M6` 是完整回歸門檻。

| 組合 ID | 平台 | Python | 需驗證的核心功能 | 預期結果 | 目前狀態 |
|---|---|---|---|---|---|
| L310 | Linux | 3.10 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 待驗證 |
| L311 | Linux | 3.11 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0；CI coverage gate ≥ 80% | CI 已設定，待本矩陣實跑 |
| L312 | Linux | 3.12 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 待驗證 |
| M310 | macOS | 3.10 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 待驗證 |
| M311 | macOS | 3.11 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 待驗證 |
| M312 | macOS | 3.12 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 待驗證 |
| W310 | Windows | 3.10 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 待驗證 |
| W311 | Windows | 3.11 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 已以 3.11.9 通過 |
| W312 | Windows | 3.12 | M1、M2、M3、M4、M5、M6 | 全部檢查退出碼為 0，無 failed／error | 待驗證 |

## 核心檢查清單

### M1：執行環境與相依套件

- [ ] `python --version` 顯示該列指定的 Python 版本。
- [ ] `python -m pip install -r requirements.txt -r requirements-dev.txt` 成功。
- [ ] `python scripts/preflight.py --json` 的 `Python version` 檢查為 `passed: true`。
- [ ] 若未設定 `MINIMAX_API_KEY`，只記錄該金鑰檢查失敗；不得把 Python 版本檢查誤判為失敗。

預期結果：使用該列的 Python 解譯器可載入專案與 pytest；Python 版本至少為 3.10。

### M2：路徑、編碼、檔案 I/O 與行尾

執行：

```bash
python -m pytest tests/test_cross_platform.py -q --no-cov
```

- [ ] `lib.io.normalize_path` 將 `/` 與 `\\` 輸入正規化為一致的 `/` 路徑。
- [ ] UTF-8 文字、JSON、JSONL 可完成 Unicode round-trip，且 JSON 不含 BOM。
- [ ] LF、CRLF 與混合行尾讀取結果一致。
- [ ] 暫存目錄可建立，`ensure_dir` 重複執行不失敗。

預期結果：`tests/test_cross_platform.py` 全數通過，Linux／macOS／Windows 的輸出、內容與退出碼一致。

### M3：設定載入與啟動前檢查

執行：

```bash
python -m pytest tests/test_lib_io.py tests/test_lib_config.py tests/test_lib_config_regression.py tests/test_lib_config_cache_stability.py tests/test_config_semantic.py tests/test_config_integration.py tests/test_config_special_branch.py -q --no-cov
```

- [ ] `config.json` 路徑解析為絕對路徑。
- [ ] 預設設定通過 `validate_config`。
- [ ] 有效環境變數覆寫正確生效。
- [ ] 空值、格式錯誤、型別錯誤與無效 URL 明確被拒絕，不靜默回退。

預期結果：設定讀取、覆寫與驗證在三個平台及三個 Python 版本上產生相同結果與 `ValueError` 契約。

### M4：Gatekeeper 與腳本入口

執行：

```bash
python -m pytest tests/test_gatekeeper.py tests/test_preflight.py tests/test_script_entrypoints.py -q --no-cov
```

- [ ] 有效 prompt 的 gatekeeper 退出碼為 `0`。
- [ ] 無效 prompt、缺少檔案與缺少參數的退出碼為 `1`。
- [ ] `--json` 輸出可解析，欄位與錯誤訊息契約不變。
- [ ] `api.*` 與 `scripts.*` 的 `__main__` 入口可顯示說明或回傳預期錯誤。

預期結果：CLI 不依賴作業系統路徑分隔符、shell 或目前工作目錄，退出碼與 JSON 結構一致。

### M5：API 與回饋流程

執行：

```bash
python -m pytest tests/test_api_server.py tests/test_api_server_gaps.py tests/test_integration_server_feedback.py tests/test_lib_api.py tests/test_lib_api_error_contract.py tests/test_lib_api_external_failures.py tests/test_lib_api_http_status_codes.py tests/test_lib_api_line37_branch.py tests/test_lib_api_positive_verify.py tests/test_lib_api_rate_wait_branch.py -q --no-cov
```

- [ ] API GET／POST handler 回傳預期 HTTP 狀態碼、標頭與 UTF-8 JSON。
- [ ] feedback summary、weak areas 與 hints 的資料契約維持一致。
- [ ] HTTP 狀態錯誤、連線失敗與逾時回傳既定例外。
- [ ] 測試使用的路徑、暫存檔與子行程參數不含平台硬編碼。

預期結果：API 與回饋流程的成功、失敗、逾時分支皆通過，且不因 Linux／macOS／Windows 差異改變契約。

### M6：完整回歸

執行：

```bash
python -m pytest -q
```

- [ ] pytest 退出碼為 `0`。
- [ ] `failed`、`error`、未預期的 `xfailed` 與 `skipped` 數量為 `0`。
- [ ] Linux／Python 3.11 額外執行 CI 的 coverage gate，結果至少為 80%。

預期結果：整套 `tests/` 通過，且不需要修改題庫、rubric、歷史 runs 或 `BACKLOG.md` 才能通過。

## 平台差異加驗

- [ ] Linux：確認 `run.sh` 可由 Bash 解析，並以 `python3` 啟動本機伺服器。
- [ ] macOS：除 Linux 清單外，確認 Bash、UTF-8 locale 與暫存目錄權限正常；目前沒有 macOS CI，必須保留實跑紀錄。
- [ ] Windows：確認 `run.bat` 可從 PATH 找到 `python3`、`python` 或 `py`，並確認 Windows 風格路徑與 CRLF 測試通過。

平台加驗只補充啟動器與主機環境差異；功能判定仍以 `M1` 至 `M6` 的 pytest 結果為準。
