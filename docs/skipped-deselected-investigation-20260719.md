# 2 skipped／1 deselected 測試調查

日期：2026-07-19

## 結論

目前的 2 個 skipped 都是明確的平台條件，不是失敗；在同一份 worktree 的 Linux／WSL 執行後均通過。1 個 deselected 是命令列 `--deselect` 暫時排除，直接執行與完整套件執行都通過。沒有修改產品碼、測試碼或 skip 條件。

| 類型 | 測試 | 條件／來源 | 補跑結果 |
|---|---|---|---|
| skipped | `tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir` | `os.name == "nt"` 時跳過；案例驗證非 Windows 下的 `GIT_DIR`／`GIT_WORK_TREE` 注入 | Linux／Python 3.12.3：`PASSED` |
| skipped | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror` | `PLATFORM == "Windows"` 時跳過；目錄 `chmod` 語意在 Windows 不穩定，唯讀檔案例另行覆蓋 | Linux／Python 3.12.3：`PASSED` |
| deselected | `tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract` | 僅由 CLI `--deselect` 排除；`pytest.ini` 沒有固定 deselect 設定 | Windows／Python 3.11.9：`PASSED` |

## 可重現證據

### Windows／Python 3.11.9

完整套件（不排除測試）：

```text
python -m pytest tests/ -q --no-cov -rs
636 passed, 2 skipped in 13.54s
```

兩個 skip 的摘要為：

```text
SKIPPED [1] tests\test_cross_platform_error_handling.py:274
SKIPPED [1] tests\test_product_diff_audit.py:183
```

重現含 1 個 deselected 的歷史命令：

```text
python -m pytest tests/ -q --no-cov --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract -rs
635 passed, 2 skipped, 1 deselected in 20.63s
```

直接補跑 deselected 案例：

```text
python -m pytest tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract -v --no-cov
1 passed in 0.09s
```

### Linux／WSL／Python 3.12.3

直接補跑 Windows 上的兩個 skip 案例：

```text
wsl.exe --exec python3 -m pytest tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror -v --no-cov -rs
2 passed in 1.02s
```

同一份 worktree 的完整套件：

```text
wsl.exe --exec python3 -m pytest tests/ -q --no-cov -rs
638 passed in 55.52s
```

Linux 完整套件沒有 skipped 或 deselected；Windows 的 `636 passed + 2 skipped` 與 Linux 的 `638 passed` 差額正好是兩個平台條件案例，證明它們已由非 Windows 路徑實際覆蓋，而非跨平台測試缺口。

## 判定

- `test_git_status_kwargs_sets_env_for_windows_gitdir` 的非 Windows 分支已在 Linux 執行並通過；Windows 路徑不會錯誤執行不適用的 `GIT_DIR` 注入測試。
- `test_write_into_readonly_directory_raises_oserror` 的 POSIX 目錄權限分支已在 Linux 執行並通過；Windows 以同檔唯讀檔案例覆蓋可攜的 `OSError` 契約。
- `test_experiment_report_snapshot_contract` 不是平台專屬測試；Windows 直接執行通過，且 Linux 完整套件也納入收集並通過。
- `.github/workflows/ci.yml` 的 `Run full automated test suite` 矩陣入口沒有以 `--deselect` 執行；另有 L311 acceptance 步驟明確使用該 CLI 選項。本報告只宣稱本次本機 Windows／WSL 證據，未把它擴寫成九個遠端 runner 都已重跑。

本次調查只更新本報告；未修改 `BACKLOG.md`，也未新增任務。
