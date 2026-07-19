# API 字串環境變數驗證測試報告

本報告說明針對 API 相關的字串環境變數（`AUTORESEARCH_API_URL` 與 `AUTORESEARCH_API_MODEL`）所進行的驗證測試強化工作。

## 驗證規則與測試覆蓋範圍

根據需求，我們在 [test_lib_config.py](file:///mnt/d/Users/Administrator/Desktop/autodev-ng/data/prompt-autoresearch/worktrees/1026251b/tests/test_lib_config.py) 中新增了 `test_api_string_env_vars_validation_specific` 測試，以確保以下驗證邏輯被嚴格執行：

1. **空值與純空白驗證**：
   - 當 `AUTORESEARCH_API_URL` 或 `AUTORESEARCH_API_MODEL` 為空字串 `""` 或純空白 `"   "` 時，系統必須拋出 `ValueError`。
2. **URL 協議驗證**：
   - 當 `AUTORESEARCH_API_URL` 非 `http://` 或 `https://` 協定（例如：`ftp://example.com/api`）時，系統必須拒絕並拋出 `ValueError`。
3. **合法主機驗證**：
   - 當 `AUTORESEARCH_API_URL` 缺少合法主機 (hostname) 時，系統必須拒絕並拋出 `ValueError`（覆蓋案例包含：`http://`、`https:///path`、`https://[broken` 等）。
4. **合法 URL 驗證**：
   - 當為合法的 `http://` 或 `https://` 且包含主機的 URL 時，系統必須能成功接受並將其套用到組態中。

## 測試執行結果

- 測試檔案：[test_lib_config.py](file:///mnt/d/Users/Administrator/Desktop/autodev-ng/data/prompt-autoresearch/worktrees/1026251b/tests/test_lib_config.py)
- 測試狀態：**PASS**
- 分支覆蓋率 (Branch Coverage)：**100%**
