# tests/ skip / deselect 稽核清單（2026-07-19）

## 掃描方式
- 指令：`rg -n "pytest\.skip\(" tests`
- 目標：統計 `tests/` 內所有 `skip` 標記，確認是否存在 `deselect`（`--deselect`、`pytest.mark.deselect`、`deselect` 關鍵字）

## 可執行清單（按測試案例）

| 編號 | 測試案例 | skip 來源/原因 | `lib.config` 驗證鏈 | 平台限定 | 可能掩蓋設定回歸 |
|---:|---|---|---|---|---|
| 1 | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_to_readonly_file_raises_oserror` | `pytest.skip("Running as root (uid 0) bypasses permission checks")`，`IS_ROOT` 分支直接跳過 | 否 | 是（Root UID） | 否（非設定解析路徑） |
| 2 | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror` | `pytest.skip("Running as root (uid 0) bypasses permission checks")` 以及 `pytest.skip("Windows 對目錄 chmod 行為不一致，改由唯讀檔案例覆蓋")` | 否 | 是（Root / Windows） | 否（非設定解析路徑） |
| 3 | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_permission_error_type_is_stable_across_path_forms` | `pytest.skip("Running as root (uid 0) bypasses permission checks")` | 否 | 是（Root UID） | 否（非設定解析路徑） |
| 4 | `tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir` | `pytest.skip("此案例驗證非 Windows 程序啟動行為")` | 否 | 是（非 Windows） | 否（非設定解析路徑） |

## 決策對照表

| 類型 | 測試案例 | 決策 | 理由 | 驗證命令 |
|---|---|---|---|---|
| skip | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_to_readonly_file_raises_oserror` | 保留 | Root UID 會繞過權限檢查；案例不在設定解析路徑，無設定回歸風險。 | `python -m pytest tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_to_readonly_file_raises_oserror -q --no-cov -rs` |
| skip | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror` | 保留 | Root 與 Windows 的目錄 `chmod` 語意不一致；可攜的唯讀檔案例已覆蓋 `OSError` 契約。 | `python -m pytest tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_write_into_readonly_directory_raises_oserror -q --no-cov -rs` |
| skip | `tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_permission_error_type_is_stable_across_path_forms` | 保留 | Root UID 會繞過權限檢查；案例只驗證含空白／非 ASCII 路徑的錯誤型別，不涉及設定驗證。 | `python -m pytest tests/test_cross_platform_error_handling.py::TestPermissionErrors::test_permission_error_type_is_stable_across_path_forms -q --no-cov -rs` |
| skip | `tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir` | 保留 | 案例只驗證非 Windows 程序的 `GIT_DIR`／`GIT_WORK_TREE` 注入，Windows 上不適用。 | `python -m pytest tests/test_product_diff_audit.py::test_git_status_kwargs_sets_env_for_windows_gitdir -q --no-cov -rs` |
| deselect（歷史命令列排除） | `tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract` | 移除 | 無平台條件且單獨執行通過；保留 `--deselect` 只會讓專用驗收與完整套件不一致。 | `python -m pytest tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract -q --no-cov -rs`；全量確認：`python -m pytest tests/ -q --no-cov -rs` |

本次沒有需要改寫的案例；四個 skip 都是平台／環境條件，且目前 `tests/` 與 `pytest.ini` 沒有永久 `deselect` 設定。

## `deselect` 盤點
- 在 `tests/` 目錄中未發現任何 `deselect` 標記。
- 目前僅有上述 4 個 `skip` 案例，已為「依平台/環境條件跳過」而非驗證鏈條件。

## 可直接執行核對清單
- `python -m pytest tests/test_cross_platform_error_handling.py -k permission -q`
- `python -m pytest tests/test_product_diff_audit.py -k windows_gitdir -q`
- `python -m pytest tests/ -q --maxfail=1`
