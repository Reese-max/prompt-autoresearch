# 跨平台測試佐證（2026-07-19）

## 佐證範圍

本報告對應提交前基準 `49afa3c`，並在同一個 worktree 實際執行 Windows 與 Linux 測試。macOS 與未安裝的 Python 次要版本只列出 CI 目標，不宣稱已於本輪通過。

| 證據層級 | 定義 |
|---|---|
| 本輪實跑 | 本報告記錄環境指紋、命令、退出碼與原始摘要 |
| CI 目標 | `.github/workflows/ci.yml` 已定義 runner 與命令，但本輪沒有 runner 結果 |
| 既有附件 | `docs/evidence/` 內已提交的 console、JSON 或 JUnit 原始產物 |

## 平台與版本

CI 支援矩陣共有九格；本輪可驗證的實跑格為 W311 與 L312。

| ID | 平台／runner | Python | 本輪狀態 | 結果 |
|---|---|---:|---|---|
| L310 | Linux／`ubuntu-latest` | 3.10 | CI 目標 | 未於本輪實跑 |
| L311 | Linux／`ubuntu-latest` | 3.11 | CI 目標 | 未於本輪實跑 |
| L312 | Linux／WSL2，kernel 5.15.167.4 | 3.12.3 | **本輪實跑** | 完整套件 638 passed，exit 0 |
| M310 | macOS／`macos-latest` | 3.10 | CI 目標 | 未於本輪實跑；實際 macOS 版本無本輪證據 |
| M311 | macOS／`macos-latest` | 3.11 | CI 目標 | 未於本輪實跑；實際 macOS 版本無本輪證據 |
| M312 | macOS／`macos-latest` | 3.12 | CI 目標 | 未於本輪實跑；實際 macOS 版本無本輪證據 |
| W310 | Windows／`windows-latest` | 3.10 | CI 目標 | 未於本輪實跑 |
| W311 | Windows，kernel build 10.0.26200 | 3.11.9 | **本輪實跑** | 完整套件 636 passed、2 skipped，exit 0 |
| W312 | Windows／`windows-latest` | 3.12 | CI 目標 | 未於本輪實跑 |

環境指紋：

```text
Windows: Windows-10-10.0.26200-SP0; CPython 3.11.9
Linux:   Linux-5.15.167.4-microsoft-standard-WSL2-x86_64-with-glibc2.39; CPython 3.12.3
```

WSL2 是本輪實際 Linux 執行環境，不等同 GitHub `ubuntu-latest` runner；CI 是否成功仍須以 GitHub Actions 的九格結果判定。

## 完整測試結果

兩邊皆從目前 repo 根目錄執行相同的 `tests/` 完整集合，`--no-cov` 只停用 coverage 報表，不會取消或挑選測試。

### Windows／CPython 3.11.9

```text
COMMAND=python -m pytest -q --no-cov
EXIT_CODE=0
636 passed, 2 skipped in 18.78s
```

### Linux WSL2／CPython 3.12.3

```text
COMMAND=wsl -e python3 -m pytest -q --no-cov
EXIT_CODE=0
638 passed in 81.28s (0:01:21)
```

兩平台各收集 638 個案例；Windows 的兩個平台條件案例為預期跳過，沒有 failed 或 error。

## 測試案例與核心輸入輸出

### 案例範圍

| 測試來源 | 主要案例 | 核心輸入 | 驗證結果 |
|---|---|---|---|
| `tests/test_cross_platform.py` | Windows／POSIX 分隔符、相對與絕對路徑、空白與非 ASCII 路徑 | `\`、`/`、`權限 目錄/locked file.txt` 等路徑 | 正規化、讀寫與例外型別契約通過 |
| `tests/test_cross_platform.py` | UTF-8、JSON、JSONL、LF／CRLF、BOM | 中文與 mixed English、混合行尾 | 內容 round-trip 一致，JSON 無 BOM |
| `tests/test_cross_platform.py` | Gatekeeper CLI | 有效 prompt、過短 prompt、缺檔、無參數 | 退出碼與 JSON／訊息契約通過 |
| `tests/test_cross_platform.py::TestCoreEvaluationFlow` | 核心評估流程 | 固定 prompt、單題題庫、mock LLM 評分 | Windows／Linux 產生相同規格輸出 |
| `tests/test_core_flow_e2e.py` | 核心流程重跑與 CLI 寫檔 | 同一固定輸入執行兩次 | digest 穩定、`spec_ok=true`、exit 0 |
| `tests/test_cross_platform_error_handling.py` | 無效輸入、缺檔、權限、外部行程與 API 失敗 | 格式錯誤環境變數、唯讀路徑、503、timeout 等 | Windows 20 passed／1 skipped；Linux 21 passed |
| 完整 `tests/` | 所有既有回歸案例 | repo 既有 fixtures 與 mock | Windows 636 passed／2 skipped；Linux 638 passed |

### 固定核心輸入

| 欄位 | 值 |
|---|---|
| Prompt | `UNICODE_PROMPT`，以 CRLF 寫入，含中文與英文 |
| Prompt SHA-256 | `c01e2ce7e27e3ac7a48ee6e651f4b3d83a9a4709f08dc327de6f79b8e099d78a` |
| 題庫 | 單題 JSONL：`請說明行政處分之要件。` |
| LLM 回答 | 固定中文／英文混合內容，共 960 字元 |
| LLM 評分 | 基礎 55、專項 15、風險 9 |
| Gatekeeper | 128 字元有效 prompt，以及 1 字元過短 prompt |

### 核心輸出比對

| 輸出 | Windows 3.11.9 | Linux 3.12.3 | 差異 |
|---|---|---|---|
| `exit_code` | 0 | 0 | 無 |
| `spec_ok` | true | true | 無 |
| `average_score` | 79.0 | 79.0 | 無 |
| `total_score` | 79 | 79 | 無 |
| `failures` | `["F03"]` | `["F03"]` | 無 |
| `error_count` | 0 | 0 | 無 |
| Gatekeeper 有效輸入 | passed=true | passed=true | 無 |
| Gatekeeper 過短輸入 | passed=false，reject=3 | passed=false，reject=3 | 無 |
| 評估 digest | `9947b3d8fbab4fcebfb974f8bd38425a6b68d871c2a0db335825b43aaf5b1baa` | 同左 | 無 |
| 可比對 digest | `1cb2551633b57a0440842185e5311842ff6ba4a1abeaa1591fd32d74092e84ab` | 同左 | **位元一致** |

本輪核心流程原始摘要：

```text
Windows: {"platform":"Windows","python_version":"3.11.9","comparable_digest":"1cb2551633b57a0440842185e5311842ff6ba4a1abeaa1591fd32d74092e84ab","spec_ok":true,"exit_code":0,"average_score":79.0,"gatekeeper_passed":true}
Linux:   {"platform":"Linux","python_version":"3.12.3","comparable_digest":"1cb2551633b57a0440842185e5311842ff6ba4a1abeaa1591fd32d74092e84ab","spec_ok":true,"exit_code":0,"average_score":79.0,"gatekeeper_passed":true}
```

## 錯誤處理結果

執行命令與結果：

```text
Windows: python -m pytest tests/test_cross_platform_error_handling.py -q --no-cov
         20 passed, 1 skipped in 3.81s; EXIT_CODE=0
Linux:   wsl -e python3 -m pytest tests/test_cross_platform_error_handling.py -q --no-cov
         21 passed in 1.58s; EXIT_CODE=0
```

| 情境 | 輸入 | 預期且實際結果 | Windows | Linux |
|---|---|---|---|---|
| 過短 prompt | `太短` | exit 1；JSON `passed=false`；含 `R01_LENGTH_TOO_SHORT` | 通過 | 通過 |
| CLI 無參數 | Gatekeeper／Evaluate 無參數 | exit 1；stdout 含 `用法:` | 通過 | 通過 |
| 無效平台 | `--platform Plan9` | argparse exit 2；stderr 含 `invalid choice` | 通過 | 通過 |
| 無效環境變數 | `AUTORESEARCH_API_TIMEOUT=not-a-number` | 拋出 `ValueError`，訊息保留變數名稱；**不靜默回退** | 通過 | 通過 |
| API key 缺失 | 未設定 `MINIMAX_API_KEY` | 拋出 `RuntimeError`，訊息保留 key 名稱 | 通過 | 通過 |
| 輸入檔缺失 | 不存在的 prompt／題庫 | CLI exit 1；訊息指出缺檔 | 通過 | 通過 |
| 可安全回退的讀取 | 缺少文字／JSON／JSONL 或無效 JSON | 回傳明確傳入的 default／空陣列 | 通過 | 通過 |
| 父路徑其實是檔案 | `既存檔案/output.txt` | `FileExistsError`；`errno=EEXIST` | 通過 | 通過 |
| 唯讀檔 | 寫入唯讀檔 | 拋出 `OSError` 子類 | 通過 | 通過 |
| 唯讀目錄 | 寫入 chmod 0555 目錄 | 拋出 `OSError` 子類 | 預期跳過 | 通過 |
| 子行程無法啟動 | `OSError(2, ..., "fake-bin")` | 包裝為 `CompletedProcess`；returncode 1；stderr 保留原因 | 通過 | 通過 |
| pytest 子行程失敗 | mock returncode 7 | `_run_pytest` 原樣回傳 7 | 通過 | 通過 |
| 真子行程非零退出 | `sys.exit(3)` | returncode 為整數 3 | 通過 | 通過 |
| HTTP 503 | mock `HTTPError(503)` | `APIError`；訊息含 503／retry；保留 cause | 通過 | 通過 |
| API timeout | mock `TimeoutError` | `APITimeoutError`，同時符合 `TimeoutError`／`APIError` | 通過 | 通過 |

## 平台差異

1. Windows 完整套件的兩個預期 skip：
   - Windows 對目錄 `chmod` 的行為不一致，改由唯讀檔案例驗證權限錯誤。
   - `test_product_diff_audit.py` 的非 Windows gitdir 啟動分支只在 Linux 執行。
2. 暫存路徑分別為 Windows `%TEMP%` 與 Linux `/tmp`，路徑分隔符不同；核心輸出的兩個 digest 仍完全相同。
3. Windows 與 Linux 的 Python 次要版本不同（3.11.9／3.12.3），但本輪沒有觀察到功能、錯誤型別、退出碼、UTF-8 或行尾結果差異。
4. macOS 以及 Python 3.10、Windows 3.12 等其餘矩陣格沒有本輪實跑證據，只能確認 CI 設定存在。

## 可追溯附件

| 證據 | 路徑 |
|---|---|
| 九格 CI 矩陣與每格 artifact 規則 | `.github/workflows/ci.yml` |
| Windows／Linux 核心流程完整 JSON | `docs/evidence/core-flow-e2e-Windows-3.11.json`、`docs/evidence/core-flow-e2e-Linux-3.12.json` |
| 核心流程逐欄並排結果 | `docs/evidence/core-flow-e2e-comparable-side-by-side.json` |
| 既有 Windows／Ubuntu 完整 console | `docs/evidence/cross-platform-Windows-10-Python-3.11.9-20260719.log`、`docs/evidence/cross-platform-Ubuntu-24.04-Python-3.12.3-20260719.log` |
| 既有 Windows／Ubuntu JUnit | `docs/evidence/full-suite-Windows-10-Python-3.11.9-20260719.junit.xml`、`docs/evidence/full-suite-Ubuntu-24.04-Python-3.12.3-20260719.junit.xml` |
| 矩陣結構化摘要 | `docs/evidence/ci-matrix-summary.json` |

既有 console／JUnit 附件是同日較早提交的原始執行產物，案例數可能少於本輪 HEAD；本輪的最終數量與退出碼以本報告「完整測試結果」的實跑摘要為準。
