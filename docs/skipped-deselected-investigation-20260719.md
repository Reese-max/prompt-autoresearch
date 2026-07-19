# 2 skipped／1 deselected 驗收處理紀錄

日期：2026-07-19

## 結論

三個案例都不在核心 E2E 失敗鏈路：`scripts/run_core_flow_e2e.py` 的測試在
`tests/test_core_flow_e2e.py`，而下列案例分別是平台相容性與架構快照契約。

| 類型 | 測試 | 決策 | 可驗證理由 |
|---|---|---|---|
| deselected | `tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract` | 移除 L311 的 `--deselect` | 單獨執行通過，且無平台條件；保留排除只會讓專用驗收與預設套件不一致。 |
| skipped | `tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir` | 保留 Windows skip | 僅驗證非 Windows 程序的 `GIT_DIR`／`GIT_WORK_TREE` 注入；Linux 分支實跑通過。 |
| skipped | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror` | 保留 Windows skip | 僅驗證 POSIX 目錄 `chmod`；Windows 的同檔唯讀檔案例覆蓋可攜的 `OSError` 契約，Linux 分支實跑通過。 |

兩個保留的 skip 都不是核心 E2E 失敗分支，因此不強迫在 Windows 執行不適用的
平台語意；它們各自在適用的 Linux 路徑已被驗證。

## 可重現證據

```text
python -m pytest tests/ -q
678 passed, 2 skipped in 63.29s

python -m pytest tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract -q --no-cov
1 passed in 0.07s

python -m pytest tests/ -q --no-cov -rs --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
677 passed, 2 skipped, 1 deselected in 26.84s

wsl.exe --cd /mnt/d/Users/Administrator/Desktop/autodev-ng/data/prompt-autoresearch/worktrees/3adecb67 --exec python3 -m pytest tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror -q --no-cov -rs
2 passed in 1.77s
```

Windows skip 摘要由含 `--deselect` 的命令輸出確認：

```text
tests\\test_cross_platform_error_handling.py:274: Windows 對目錄 chmod 行為不一致，改由唯讀檔案例覆蓋
tests\\test_product_diff_audit.py:183: 此案例驗證非 Windows 程序啟動行為
```

L311 現在直接執行 `python -m pytest tests/ -q`，因此不再產生該 deselected
結果；九格矩陣的 M6 原本也以完整 `tests/` 套件執行。
