# 版本與平台支援清單

## 支援範圍

| 平台 | 最低 Python 版本 | 最高支援 Python 版本 | 說明 |
|---|---|---|---|
| Linux | 3.10 | 3.12 | CI 以 `ubuntu-latest` 測試 |
| macOS | 3.10 | 3.12 | CI 以 `macos-latest` 測試 |
| Windows | 3.10 | 3.12 | CI 以 `windows-latest` 測試 |

僅支援 CPython。PyPy、Jython、GraalPy 等不在支援範圍內。

## 支援組合與 CI 對應

| 組合 ID | 平台 | Python 版本 | CI matrix ID | 最低版本要求通過 | 最高版本要求通過 |
|---|---|---|---|---|---|
| L310 | Linux | 3.10 | `L310` | 是（=3.10） | 是（≤3.12） |
| L311 | Linux | 3.11 | `L311` | 是（≥3.10） | 是（≤3.12） |
| L312 | Linux | 3.12 | `L312` | 是（≥3.10） | 是（=3.12） |
| M310 | macOS | 3.10 | `M310` | 是（=3.10） | 是（≤3.12） |
| M311 | macOS | 3.11 | `M311` | 是（≥3.10） | 是（≤3.12） |
| M312 | macOS | 3.12 | `M312` | 是（≥3.10） | 是（=3.12） |
| W310 | Windows | 3.10 | `W310` | 是（=3.10） | 是（≤3.12） |
| W311 | Windows | 3.11 | `W311` | 是（≥3.10） | 是（≤3.12） |
| W312 | Windows | 3.12 | `W312` | 是（≥3.10） | 是（=3.12） |

共 9 個組合，對應 `.github/workflows/ci.yml` 的 9 個 matrix job。

## 排除組合

| 排除條件 | 原因 | 政策 |
|---|---|---|
| Python ≤ 3.9 | CPython 3.9 已於 2025-10 EOL，不再接收安全性修補 | 不支援，`scripts/preflight.py` 會攔截 |
| Python ≥ 3.13 | 尚未納入 CI 測試矩陣，相容性未驗證 | 待驗證後決定是否加入；加入前視為不支援 |
| PyPy / Jython / GraalPy | 非 CPython 解譯器，標準函式庫行為與 CPython 有差異 | 不支援 |
| 32-bit 解譯器 | CI 全部使用 64-bit runner | 不支援 |
| iOS / Android / WASI | 無 CI 覆蓋，stdlib 在這些平台有重大限制 | 不支援 |

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
