# config.py 覆蓋率驗收紀錄（2026-07-17）

## 目標

確認 `lib/config.py` 的回退/環境變數路徑全部被測試覆蓋，且新增測試不是以既有
333+ passed 結果冒充完成。

## 新增測試前的缺口

執行 `pytest tests/test_lib_config.py --cov=lib/config.py --cov-report=term-missing`
後，`lib/config.py` 覆蓋率為 **97%**（58 stmts / 2 miss）：

| 缺失行 | 程式碼 | 說明 |
|---|---|---|
| L102 | `cfg[section] = {}` | `_apply_env_overrides` 中 `section not in cfg` 的防禦分支。因 `_DEFAULTS` 恆含所有 env_map 引用的 section，`_load_config()` 正常流程不可能觸發，屬不可達死碼。 |
| L131 | `return section_data.get(key, default)` | `get(section, key)` 的主要查詢路徑。既有測試僅透過 dict/list key 或非 dict section 觸發 L109-114 分支，從未以正常 string key 呼叫 `get()`。 |

## 新增的 3 條測試

| 測試函數 | 覆蓋目標 | 斷言要點 |
|---|---|---|
| `test_get_normal_dict_section_string_key_returns_value` | L131 | `config.get("api", "timeout")` 回傳 180（int），走 `section_data.get(key, default)` 路徑。 |
| `test_get_normal_dict_section_missing_key_returns_default` | L131 | `config.get("api", "nonexistent_key", 42)` 回傳 42，覆蓋 key 不存在時的 default 分支。 |
| `test_env_override_section_created_when_missing_from_cfg` | L101-102 | 手動構造缺少 `parallel` section 的 cfg，呼叫 `_apply_env_overrides`，驗證缺失 section 被自動建立且 env 值正確寫入。 |

## 新增測試後的結果

| 項目 | 值 |
|---|---|
| test_lib_config.py 測試數 | 23（原 20） |
| lib/config.py 覆蓋率 | **100%**（58 stmts / 0 miss） |
| 全域測試數 | 350 |
| 通過 | 350 |
| 失敗 | 0 |
| exit code | 0 |

## 可追溯資訊

- 執行日期：2026-07-17
- 分支：`adng/47b689d8`
- Python：3.11.9
- 執行指令：

```
python -m pytest tests/test_lib_config.py -v --cov=lib/config.py --cov-report=term-missing
```

- L101-102 不可達性的分析：`_apply_env_overrides` 的 `env_map` 引用的 section
  （api, parallel, thresholds）全部存在於 `_DEFAULTS`，而 `_load_config()` 恆以
  `deepcopy(_DEFAULTS)` 初始化 cfg，因此正常流程中 `section not in cfg` 永遠為
  False。新增測試透過直接呼叫 `_apply_env_overrides` 並手動構造殘缺 cfg 覆蓋此分支。
