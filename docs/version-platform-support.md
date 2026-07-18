# 版本與平台支援清單

## 支援範圍

| 平台 | 最低 Python 版本 | 最高支援 Python 版本 | 說明 |
|---|---|---|---|
| Linux | 3.10 | 3.12 | CI 以 `ubuntu-latest` 測試 |
| macOS | 3.10 | 3.12 | CI 以 `macos-latest` 測試 |
| Windows | 3.10 | 3.12 | CI 以 `windows-latest` 測試 |

僅支援 CPython。PyPy、Jython、GraalPy 等不在支援範圍內。

## 支援組合與完成判定

| 組合 ID | 作業系統 runner | Python 執行階段 | 該組合完成判定 |
|---|---|---|---|
| L310 | Linux（`ubuntu-latest`） | CPython 3.10 | `L310` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |
| L311 | Linux（`ubuntu-latest`） | CPython 3.11 | `L311` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0`，且 coverage gate ≥ 80% |
| L312 | Linux（`ubuntu-latest`） | CPython 3.12 | `L312` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |
| M310 | macOS（`macos-latest`） | CPython 3.10 | `M310` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |
| M311 | macOS（`macos-latest`） | CPython 3.11 | `M311` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |
| M312 | macOS（`macos-latest`） | CPython 3.12 | `M312` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |
| W310 | Windows（`windows-latest`） | CPython 3.10 | `W310` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |
| W311 | Windows（`windows-latest`） | CPython 3.11 | `W311` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |
| W312 | Windows（`windows-latest`） | CPython 3.12 | `W312` job 的 M1～M6 與 `ALL` 結果皆為 `exit_code = 0` |

共 9 個組合，對應 `.github/workflows/ci.yml` 的 9 個 matrix job。

## 排除組合

| 作業系統／架構 | 執行階段 | 排除判定 |
|---|---|---|
| Linux、macOS、Windows | CPython ≤ 3.9 | 低於最低版本；`scripts/preflight.py` 的 Python 版本檢查不通過 |
| Linux、macOS、Windows | CPython ≥ 3.13 | 不在 CI 與 `SUPPORTED_PYTHON_VERSIONS` 內，完成相容性驗證前不支援 |
| Linux、macOS、Windows | PyPy、Jython、GraalPy | 非 CPython，未納入 CI，不列為支援組合 |
| Linux、macOS、Windows（32-bit） | 任意 Python | CI 僅驗證 64-bit runner，不列為支援組合 |
| iOS、Android、WASI 或其他作業系統 | 任意 Python | 無 CI 覆蓋，不列為支援組合 |

## 整體完成判定標準

本文件所列相容性範圍僅在以下條件全部成立時判定完成：

1. `.github/workflows/ci.yml` 與 `scripts/run_test_matrix.py` 仍完整列出上述 9 個組合。
2. 同一輪 CI 的 9 個 matrix job 全部成功；每個 job 的 M1～M6 與 `ALL` 均回報 `exit_code = 0`。
3. `L311` 的 `scripts/` 與 `api/` coverage gate 達 80% 以上。
4. 完整測試無 `failed`、`error`、非預期的 `xfailed` 或 `skipped`。

排除組合不需要通過測試，但不得標示為支援。若要擴大支援範圍，必須先加入 CI 與測試矩陣、依上述標準通過，再同步更新本文件。

## 退役政策

### 版本退役

當 CPython 官方對某版本進入 EOL（End-of-Life）時，本專案於 **下一個主要版次** 棄用該版本：

1. **預警期**：Python 官方公布 EOL 日期後，在該版本被標記為 `deprecated`。
2. **正式退役**：下一個主要版次（如 1.0 → 2.0）不再將退役版本納入 CI 矩陣。
3. **移除期**：退役後第一個次要版次（如 2.1）可移除為退役版本所做的相容性代碼。

### 平台退役

當 CI runner（如 `ubuntu-latest`、`macos-latest`、`windows-latest`）升級導致某平台組合不再可測試時：

1. 於 CI 設定更新時同步更新本清單。
2. 若退役為非自願（如 GitHub 移除 runner），保留至少一個版次的過渡期。

### 新增版本

Python 新穩定版（如 3.13）發布後：

1. 先於本地驗證 `python -m pytest -q` 全數通過。
2. 將新版本加入 CI matrix，觀察至少一輪 CI 全綠。
3. 更新本清單的最高支援版本與 CI 對應表。

## 版本邊界驗證

`scripts/preflight.py` 檢查 `sys.version_info` 是否 ≥ 3.10。`scripts/run_test_matrix.py` 的 `SUPPORTED_PYTHON_VERSIONS` 為 `("3.10", "3.11", "3.12")`，不在清單中的版本會被拒絕執行。

兩者與本清單的最低（3.10）和最高（3.12）版本邊界一致。
