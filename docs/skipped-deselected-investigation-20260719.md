# 驗收 1 skipped / 1 deselected 調查與處理（2026-07-19）

## 任務

調查並處理驗收結果中的 **1 skipped** 與 **1 deselected**，記錄測試名稱與原因；若為平台專屬行為，須在相關平台啟用並執行，否則提供可驗證的排除依據。

## 結論摘要

| 類型 | 測試名稱 | 原因 | 處理結果 |
|---|---|---|---|
| **deselected** | `tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract` | 僅由 **CLI `--deselect`** 排除（`pytest.ini` / `conftest` **無**固定 deselect）；常見於歷史驗收命令與 CI 的 L311 acceptance 步驟 | Windows 單獨執行 **PASSED**；完整套件（不加 `--deselect`）已納入並通過 |
| **skipped（Windows）** | `tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir` | `os.name == "nt"` 時 `pytest.skip`：案例驗證**非 Windows** 的 `GIT_DIR` / `GIT_WORK_TREE` 注入 | **Linux/WSL 已啟用並通過**（見下方證據） |
| **skipped（Windows，現行額外套件）** | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror` | `PLATFORM == "Windows"` 時 skip：Windows 對目錄 `chmod` 行為不一致；唯讀**檔**案例已覆蓋 | **Linux/WSL 已啟用並通過**（見下方證據） |

> 歷史驗收摘要「**1 skipped, 1 deselected**」（見 `docs/cross-platform-fix-evidence-20260719.md`）對應的 skip 為上表第一項 skipped；第二項 skipped 為後續新增的跨平台錯誤處理測試，故**今日**在 Windows 上完整套件為 **2 skipped**，非 1。

## 1. Deselected

### 名稱

`tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract`

### 為何會被 deselect

- **來源**：命令列參數，不是測試標記或設定檔。
- **證據**：`pytest.ini` 的 `addopts` 僅含 coverage，**無** `--deselect`。
- **典型命令**（歷史驗收／CI L311 acceptance）：

```text
python -m pytest tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

- **歷史排除依據**（可驗證、非產品缺陷）：先前部分驗收聚焦配置流程時以 CLI 暫時排除架構快照合約測試（見 `docs/deselected-test-investigation-20260718.md`）。該測試以 mock `subprocess.run` 驗證 `experiment_report` 快照契約，與配置解析路徑無關。

### 處理

1. 確認 repo 預設收集會包含此測試（不加 `--deselect` 即執行）。
2. 在本 worktree **啟用並執行**（Windows）：

```text
python -m pytest tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract -v --no-cov
```

結果：`1 passed in 0.03s`（exit=0）。

3. 完整套件（Windows，無 deselect）：`632 passed, 2 skipped`（見第 3 節）。
4. 完整套件（Linux/WSL，無 deselect）：`634 passed`（0 skipped、0 deselected）。  
   `634 - 632 = 2`，恰為 Windows 上兩則平台 skip 在 Linux 被實際執行並通過的差額。

**排除依據（僅當命令列刻意 `--deselect` 時）**：人為縮小驗收範圍，**非**測試失敗；預設完整套件已納入且通過，無需改產品碼或刪測試。

## 2. Skipped（平台專屬）

### 2.1 `test_git_status_kwargs_sets_env_for_windows_gitdir`

| 欄位 | 內容 |
|---|---|
| 檔案 | `tests/test_product_diff_audit.py:180-208` |
| Skip 條件 | `if os.name == "nt": pytest.skip("此案例驗證非 Windows 程序啟動行為")` |
| 目的 | 非 Windows 且 `.git` 指向 Windows `gitdir:` 時，應注入 `GIT_DIR` / `GIT_WORK_TREE` |
| Windows | **SKIPPED**（行為不適用於本機 nt） |
| Linux/WSL | **PASSED**（已啟用執行） |

### 2.2 `test_write_into_readonly_directory_raises_oserror`

| 欄位 | 內容 |
|---|---|
| 檔案 | `tests/test_cross_platform_error_handling.py:249-263` |
| Skip 條件 | `if PLATFORM == "Windows": pytest.skip("Windows 對目錄 chmod 行為不一致，改由唯讀檔案例覆蓋")` |
| 目的 | 目錄不可寫時 `io.write_file` 應拋 `OSError` |
| Windows 排除依據 | Windows 上 `os.chmod` 對目錄權限語意與 POSIX 不一致，無法穩定重現「目錄唯讀」；同檔 `test_write_to_readonly_file_raises_oserror` 已覆蓋權限錯誤路徑 |
| Linux/WSL | **PASSED**（`chmod 0o555` 後寫入子檔觸發 `OSError`） |

## 3. 可驗證執行證據

### 3.1 Windows（本機）

| 欄位 | 值 |
|---|---|
| 時間 | 2026-07-19 |
| host | `HPZBOOKG10-` |
| OS | Windows 10.0.26200 |
| Python | 3.11.9 |
| 完整套件命令 | `python -m pytest tests/ -q --no-cov -rs` |
| 結果 | **632 passed, 2 skipped**，exit=0 |
| skip 摘要 | 見上表 2.1、2.2 |

重現「1 deselected」（另含現行 2 skip）的驗收形命令：

```text
python -m pytest tests/ -q --no-cov --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract -rs
```

結果：**631 passed, 2 skipped, 1 deselected**，exit=0。

### 3.2 Linux（WSL2，相關平台啟用 skipped 案例）

| 欄位 | 值 |
|---|---|
| OS | Linux 5.15.167.4-microsoft-standard-WSL2 |
| Python | 3.12.3 |
| 工作目錄 | 同一 worktree（`/mnt/d/.../worktrees/31a35651`） |

**僅平台專屬測試：**

```text
python3 -m pytest \
  tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir \
  tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror \
  -v --no-cov -rs
```

結果：**2 passed** in 1.10s，exit=0。

**完整套件：**

```text
python3 -m pytest tests/ -q --no-cov -rs
```

結果：**634 passed** in 70.38s，**0 skipped、0 deselected**，exit=0。

## 4. 處理決策（最小改動）

| 項目 | 決策 | 理由 |
|---|---|---|
| deselected 測試 | **維持測試本體**；預設完整套件已執行並通過 | 非缺陷；CLI deselect 為歷史／局部驗收範圍選擇。CI 全矩陣「Run full automated test suite」未使用 `--deselect` |
| Windows skip ×2 | **維持平台 skip**；已在 Linux 啟用並通過 | 行為僅適用 POSIX 或非 Windows 啟動路徑；Windows 有對等覆蓋或不可穩定模擬 |
| 產品碼 / 測試邏輯 | **不修改** | 現有測試全數通過；改 skip 條件或強跑 Windows 會引入不穩定或誤報 |
| 本報告 | **新增本文件並 commit** | 調查類任務須落檔可檢查結論 |

## 5. 與「1 skipped / 1 deselected」的對齊說明

驗收文件 `docs/cross-platform-fix-evidence-20260719.md` 記載 Windows：`612 passed, 1 skipped, 1 deselected`。

| 當時 | 今日（本 worktree） |
|---|---|
| 1 skipped = `test_git_status_kwargs_sets_env_for_windows_gitdir` | 同上仍 skip，且多 1 則目錄 chmod skip |
| 1 deselected = `test_experiment_report_snapshot_contract`（CLI） | 同樣可被 CLI deselect；**不 deselect 時 PASSED** |

因此「1 skipped / 1 deselected」已完整對應並處理；現行 Windows 另有 1 則合理平台 skip，已一併在 Linux 驗證通過。

## 6. 限制聲明（依 L012）

- 本報告僅依本 worktree 內實跑輸出撰寫；未宣稱 GitHub Actions 九格矩陣皆已重跑。
- 已驗證平台：**Windows 3.11.9**、**WSL2 Linux 3.12.3**。
- 未改 `BACKLOG.md`，未新增任務。
