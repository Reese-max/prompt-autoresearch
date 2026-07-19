# 清單內 `lib.config.get()`／`validate_config()` 相關 skip／deselect 處置

日期：2026-07-19

## 來源清單

- [docs/skip_deselected_inventory_20260719.md](skip_deselected_inventory_20260719.md)

## 處置結論

| 清單編號 | 測試 | 是否直接相關 `get()`／`validate_config()` | 處置 |
|---:|---|---|---|
| 1 | `TestPermissionErrors::test_write_to_readonly_file_raises_oserror` | 否（權限／`OSError`） | 保留 skip；不屬設定驗證鏈 |
| 2 | `TestPermissionErrors::test_write_into_readonly_directory_raises_oserror` | 否（Root／Windows `chmod`） | 保留 skip；不屬設定驗證鏈 |
| 3 | `TestPermissionErrors::test_permission_error_type_is_stable_across_path_forms` | 否（Root UID） | 保留 skip；不屬設定驗證鏈 |
| 4 | `test_git_status_kwargs_sets_env_for_windows_gitdir` | 否（非 Windows `GIT_DIR` 行為） | 保留 skip；不屬設定驗證鏈 |

- `tests/` 內**無**任何 `@pytest.mark.skip`／`skipif`／`xfail`／`deselect` 標記落在 `lib.config` 測試檔。
- 清單中與 `lib.config.get()`／`validate_config()` **直接相關的 skipped／deselected 案例數：0**。
- 因此**無須移除跳過條件**；不存在「不合理 skip 掩蓋設定回歸」的可改動標的。

## 無效環境值／非法預設值已真正拋 `ValueError`（抽樣驗收）

既有測試已明確使用 `pytest.raises(ValueError, ...)`，覆蓋：

| 路徑 | 代表測試 | 斷言 |
|---|---|---|
| 無效數值 env | `tests/test_lib_config.py::test_invalid_numeric_env_vars_raise_value_error` | `config.get(section, key)` → `ValueError` |
| 空／空白 env | `tests/test_config_special_branch.py::test_empty_numeric_env_var_raises_value_error` 等 | 訊息含「不可為空字串」 |
| 非法 URL／model env | `tests/test_lib_config.py::test_invalid_api_url_format_env_var_raises_value_error` 等 | `ValueError` 且含欄位語意 |
| 非法預設回退 | `tests/test_lib_config_regression.py::test_get_rejects_invalid_default_fallback` | `config.get(...)` → `ValueError`（match dotted key） |
| 直接驗證 | `tests/test_lib_config.py::test_validate_config_rejects_invalid_positive_field` | `validate_config(cfg)` → `ValueError` |

### 可重現證據

```text
python -m pytest tests/test_lib_config.py tests/test_lib_config_regression.py tests/test_lib_config_cache_stability.py tests/test_config_special_branch.py tests/test_config_semantic.py -q --no-cov -k "invalid or reject or raise or ValueError or default or empty or nan or fallback"
233 passed, 28 deselected in 1.58s
```

（此處 `deselected` 為 `-k` 過濾未匹配案例，**不是**套件內永久 deselect 標記。）

```text
python -m pytest tests/ -q --no-cov -rs
835 passed, 2 skipped in 23.37s
```

目前僅剩平台條件 skip（Windows `chmod`／非 Windows `GIT_DIR`），與設定解析無關。

## 最小改動說明

- **程式／測試**：不需修改。清單內無可移除的 config 相關 skip，且負面案例已具備明確 `ValueError` 斷言。
- **本檔**：記錄對清單的篩選結果與驗收輸出，滿足「調查類必須落檔 commit」要求。
