# 無效 API timeout 快取清理：紅→綠證據

## 驗收範圍

`test_api_timeout_invalid_env_values_raise_value_error_on_get` 由 commit
`d85feae6758b02c6648260b2409ec5762f4a3aa3` 強化；它逐項驗證 `nan`、`inf`、
`-inf`、負數、零、空字串及純空白，並斷言載入失敗後 `_CONFIG` 必須為
`None`，不能留下失敗前的部分快取。

## 同一條測試命令

紅、綠兩階段均在 Python 3.11.9、pytest 9.1.1 執行：

```powershell
python -m pytest --no-cov --color=no -q --tb=short tests/test_config_special_branch.py::test_api_timeout_invalid_env_values_raise_value_error_on_get
```

| 階段 | 實作狀態 | 原始輸出 | exit code | 結果 |
|---|---|---|---:|---|
| RED | 反向套用最小快取清理 patch | `docs/evidence/config-invalid-timeout-cache-red.txt` | 1 | 7 failed |
| GREEN | 恢復快取清理 patch | `docs/evidence/config-invalid-timeout-cache-green.txt` | 0 | 7 passed |

RED 的 7 個案例都已成功捕捉原本應拋出的 `ValueError`，失敗點一致位於新增的
`assert config._CONFIG is None`；因此失敗不是測試環境或例外類型造成，而是舊行為
確實留下 `_CONFIG`。

## 重播方式

從本提交的 green 狀態逐步執行：

```powershell
git apply -R docs/evidence/config-invalid-timeout-cache-reset.patch
python -m pytest --no-cov --color=no -q --tb=short tests/test_config_special_branch.py::test_api_timeout_invalid_env_values_raise_value_error_on_get
git apply docs/evidence/config-invalid-timeout-cache-reset.patch
python -m pytest --no-cov --color=no -q --tb=short tests/test_config_special_branch.py::test_api_timeout_invalid_env_values_raise_value_error_on_get
```

第一輪預期 exit code 1、`7 failed`；第二輪預期 exit code 0、`7 passed`。
保存的 patch 只切換 `_load_config()` 在驗證／覆寫失敗時是否清除 `_CONFIG`，
不改測試內容。

## 完整回歸

```powershell
python -m pytest --color=no
```

結果：exit code 0，`952 passed, 2 skipped in 58.60s`。
