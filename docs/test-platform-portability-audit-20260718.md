# `tests/` 與 CI 跨平台依賴盤點

## 結論

目前未發現固定 `C:\\`／磁碟機路徑、`/tmp`／`%TEMP%`、Windows 專用程式啟動旗標，或只在 Windows 才成立的測試路徑。直接的外部程式依賴只有 `git status`；CI 目前只驗證 Linux，沒有 macOS 工作流程，因此 macOS 回歸仍未被自動捕捉。

## 盤點結果

| 類別 | 位置 | Linux／macOS 失敗條件與判定 |
| --- | --- | --- |
| 外部程式 | `tests/test_product_diff_audit.py:17-25` | 直接執行 `git status --porcelain -uno`。若執行環境沒有 `git`、`cwd` 不是有效 checkout，測試會直接拋出 `RuntimeError`。`text=True` 未指定編碼；若變更路徑含非 ASCII 且本機 locale 無法解碼 Git 輸出，也可能失敗。這是指定 pytest 命令中最直接的跨平台風險。 |
| 被 mock 的程式 | `tests/test_architecture_surface.py:21-34,67-80,121-136` | 三段 `subprocess.run` 都在 `patch("subprocess.run")` 內，沒有真的啟動子程式；`sys.executable`、`-c`、`Path` 與 UTF-8 參數本身可跨 Linux／macOS 使用。不是實際的程式啟動風險。 |
| 被 stub 的程式 | `tests/test_integration_server_feedback.py:186-282` | `optimizer.subprocess.run` 全部以 stub 取代，只驗證命令列與回傳值；沒有依賴 Windows 的 `.exe`、shell 或啟動方式。 |
| 行程內入口 | `tests/test_script_entrypoints.py:16-46`、`tests/test_gatekeeper.py`、`tests/test_preflight.py` | 使用 `runpy`、`os.chdir`、`sys.path`，並在 `finally` 還原狀態；實際檔案路徑由 `Path(__file__).resolve()` 或 `tmp_path` 組成。這些是標準跨平台 API，未見 Linux／macOS 特有失敗點；若未來新增未還原的全域工作目錄，才會造成後續測試連鎖失敗。 |
| 路徑分隔符 | `tests/test_analyze_runs.py:70,100`、`tests/test_evaluate.py:80` | 反斜線只出現在「輸入 Windows 風格路徑後正規化」的測試資料，或 `replace("\\", "/")` 的可攜性處理；實際暫存檔案使用 `pathlib`／`os.path`。不是主機路徑硬編碼。 |
| 換行 | `tests/test_api_server.py:40-41` | `\r\n` 是 HTTP wire format 的必要分隔符，不是 Windows 文字檔換行假設；JSONL 與文字測試使用 `\n`、`splitlines()`，沒有原始位元組換行比對。 |
| 編碼 | `tests/` 直接 `open`、`read_text`、`write_text` 的檔案操作均明確使用 UTF-8；中文輸出由 `capsys`／`StringIO` 擷取。唯一未明確指定 subprocess 編碼的是上列 `git status`，風險已併入外部程式項目。 |
| 暫存目錄 | 全部 `tmp_path` 測試，以及 `tests/test_architecture_surface.py:173-182` 的 `tempfile.TemporaryDirectory` | 沒有固定暫存根目錄；皆由 pytest／Python 標準函式庫提供。只有執行帳號無法建立暫存目錄、容量不足或權限受限時會失敗，這不是 Windows／Linux／macOS 的路徑差異。 |
| CI 執行器 | `.github/workflows/ci.yml:9` | 只有 `ubuntu-latest`，可驗證 Linux，不能驗證 macOS。這是 macOS 失敗不會被 CI 發現的高風險覆蓋缺口。 |
| CI 執行入口 | `.github/workflows/ci.yml:17-27`、`pytest.ini:5-7` | CI 使用裸 `pip`／`pytest`，在 GitHub Ubuntu runner 可由 `setup-python` 正常提供；若日後加入 macOS matrix，應改用同一 Python 的 `python -m pip`／`python -m pytest`，避免 PATH 指向錯誤環境。現有設定沒有 Windows shell 語法。 |

## 最可能影響指定 pytest 命令的高風險案例

1. **高：`tests/test_product_diff_audit.py::test_product_code_should_not_be_edited_for_coverage_tuning`**。這是唯一真的啟動外部程式的測試；`git` 不在 PATH、checkout 不完整，或 Git 輸出受 locale／非 ASCII 路徑影響時會中止整個測試集。
2. **高（CI 覆蓋缺口）：`.github/workflows/ci.yml` 的 `runs-on: ubuntu-latest`**。目前指定命令在 Linux 會被驗證，但 macOS 的執行環境 PATH、locale 與檔案系統差異完全沒有 CI 證據；這不會改變本機命令的結果，卻是最可能漏掉 macOS 回歸的設定。
3. **中：`tests/test_api_server.py::run_handler` 的 CRLF 解析**。若未來替換 HTTP handler 或改成非標準輸出，`\r\n\r\n` 假設會讓 API 測試群組失敗；目前 CPython `http.server` 使用標準 HTTP CRLF，因此不是現階段的 OS 風險。

## 驗證

在目前工作區執行：

```text
python -m pytest tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

結果：`454 passed, 1 deselected in 13.74s`。本次結果來自 Windows／Python 3.11.9，只證明目前 Windows 執行成功，不宣稱 macOS 已通過。
