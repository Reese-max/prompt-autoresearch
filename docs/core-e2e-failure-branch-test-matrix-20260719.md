# 核心 E2E 失敗／例外分支與測試映射表

日期：2026-07-19

範圍：`api/server.py`、`api/continuous_optimizer.py`、`api/feedback.py`、`lib/api.py`

## 結論

核心鏈路為：

```text
POST /api/feedback
  -> feedback.jsonl
  -> api.feedback 摘要／弱點／建議
  -> continuous_optimizer 門檻／分析／run_opt.py
  -> optimization_log.jsonl
  -> GET /api/optimizer/status
```

`lib/api.py` 是 `run_opt.py` 使用的外部 MiniMax 呼叫邊界。

目前既有測試已直接覆蓋所有 `lib/api.py` 的錯誤轉譯分支，以及 server 的
HTTP 錯誤回傳和 optimizer 的正常／失敗／例外回傳；仍未形成測試契約的路徑
集中在檔案／目錄 I/O 失敗、feedback 寫入失敗、非預期匯入例外，以及
`serve_forever()` 發生非 `KeyboardInterrupt` 時的清理流程。

這份盤點不把「同一個 `except Exception` 已由另一種例外觸發」誤列為行級
branch 缺口；這類案例另外標為「部分覆蓋」。

## 覆蓋證據

目標模組測試與 branch coverage 指令：

```powershell
python -m pytest tests/test_api_server.py tests/test_api_server_gaps.py tests/test_integration_server_feedback.py tests/test_continuous_optimizer.py tests/test_api_feedback.py tests/test_lib_api.py tests/test_lib_api_external_failures.py tests/test_lib_api_error_contract.py tests/test_lib_api_http_status_codes.py tests/test_lib_api_rate_wait_branch.py tests/test_lib_api_line37_branch.py tests/test_lib_api_positive_verify.py -q -o addopts= --cov=api.server --cov=api.continuous_optimizer --cov=api.feedback --cov=lib.api --cov-branch --cov-report=term-missing
```

實測：`121 passed`。

```text
api\continuous_optimizer.py      82      0     16      0   100%
api\feedback.py                  85      2     36      2    97%   76->75, 197-198
api\server.py                   219      1     46      1    99%   396
lib\api.py                       63      0     20      1    99%   103->exit
```

其中 `api/feedback.py:76->75` 與 `lib/api.py:103->exit` 是由目前程式控制流
造成的結構性 partial branch，不是核心 E2E 的外部失敗缺口；
`api/server.py:396` 是模組入口 guard，並非 HTTP 錯誤路徑。

完整套件驗證：

```powershell
python -m pytest tests -q
```

結果：`636 passed, 2 skipped`。完整套件下四個指定模組均為 `100%` statement／
branch coverage；兩個 skipped 是既有測試的環境條件案例，沒有新增或修改。

## 未測／部分未測失敗路徑清單

狀態定義：

- **已覆蓋**：已有測試直接觸發該條件，並斷言回傳、例外或日誌結果。
- **部分覆蓋**：同一程式分支已被其他例外或輸入觸發，但此失敗形態或清理
  後置條件仍未驗證。
- **未測／未定義**：目前沒有對應測試；程式也沒有明確的錯誤回傳或清理契約。

### `api/server.py`

| 編號 | 程式位置／分支 | 失敗觸發 | 目前行為與風險 | 測試映射 | 狀態 |
|---|---|---|---|---|---|
| S-01 | `_get_feedback_module()`：`except ImportError` | 回饋模組無法匯入 | 降級為 `{}`；摘要端點回 `200` 與空摘要 | `tests/test_api_server_gaps.py::test_feedback_module_import_error_degrades_to_empty`；`tests/test_integration_server_feedback.py::test_lazy_import_wires_real_feedback_module` | 已覆蓋 |
| S-02 | `_get_feedback_module()`：匯入期間拋非 `ImportError` | 模組初始化拋 `RuntimeError`／其他例外 | 例外向外拋出，沒有 API 錯誤 JSON | 無 | 未測／未定義 |
| S-03 | `_get_current_prompt()`、`_get_baseline()`：`load_file()` 回空值 | 檔案不存在或讀取層回預設值 | `404` 錯誤 JSON | `test_current_prompt_missing_returns_404`；`test_baseline_missing_returns_404` | 已覆蓋 |
| S-04 | 同上：`load_file()` 直接拋例外 | 權限、開檔或檔案系統失敗 | 例外中止 handler，沒有 `500` 錯誤 JSON | 無 | 未測／未定義 |
| S-05 | `_get_prompt_meta()`、`_get_route()`：`load_json()` 回空值 | JSON 不存在或解析層回 `{}` | `404` 錯誤 JSON | `test_prompt_meta_missing_returns_404`；`test_route_missing_returns_404` | 已覆蓋 |
| S-06 | `_list_champions()`：目錄不存在 | champions 目錄不存在 | `200`，`{"champions": []}` | `test_list_champions_dir_missing` | 已覆蓋 |
| S-07 | `_get_champion()`：目標不存在後執行 `os.listdir(CHAMPIONS_DIR)` | slug 不存在且 champions 目錄也不存在 | `FileNotFoundError` 未捕捉；與 S-06 不同，沒有空清單降級 | 無 | 未測／未定義 |
| S-08 | `_get_champion()`：中文 metadata 命中／最終不存在 | 以 type name 查找或找不到題型 | 命中回 `200`；找不到回 `404` | `test_get_champion_by_chinese_type_name`；`test_get_champion_not_found` | 已覆蓋 |
| S-09 | `_post_feedback()`：`except (JSONDecodeError, UnicodeDecodeError)` | JSON 語法錯誤或 body 不是 UTF-8 | `400`，回傳「JSON 解析失敗」；目前只測語法錯誤 | `test_post_feedback_invalid_json_returns_400` | 部分覆蓋 |
| S-10 | `_post_feedback()`：`Content-Length` 解析失敗 | 缺失以外的非整數 header，例如 `abc` | `int()` 直接拋 `ValueError`，沒有錯誤 JSON | 無 | 未測／未定義 |
| S-11 | `_post_feedback()`：`append_jsonl()` 成功／失敗 | 回饋檔無法建立或追加 | 成功回 `200 accepted`；寫入 `OSError` 未捕捉，沒有明確錯誤回傳 | `test_post_feedback_success`；無寫入失敗測試 | 部分覆蓋 |
| S-12 | `_post_feedback()`：JSON 頂層不是 mapping | body 為 `null`、list 或純量 | 必要欄位檢查或取值可能拋 `TypeError`，沒有 `400` 契約 | 無 | 未測／未定義 |
| S-13 | `_get_feedback_summary()`、`_get_feedback_weak_areas()`、`_get_feedback_hints()`：分析函式拋例外 | feedback 內容損毀或分析依賴失敗 | `500`，回傳 `{"error": "分析失敗: ..."}` | `test_feedback_summary_analysis_error_returns_500`；`test_feedback_weak_areas_analysis_error_returns_500`；`test_feedback_hints_analysis_error_returns_500`；`test_malformed_feedback_row_maps_to_500` | 已覆蓋 |
| S-14 | `_get_optimizer_status()`：`read_jsonl()` 拋例外 | optimization／feedback JSONL 讀取或解析失敗 | 例外中止 handler，沒有 `500` 錯誤 JSON | 無 | 未測／未定義 |
| S-15 | `_health_check()`：讀檔函式拋例外 | health 依賴檔案 I/O 失敗 | 例外中止 handler；只有「回傳空值」的 degraded 狀態有測試 | `test_health_check_degraded` 只覆蓋空值，不覆蓋拋例外 | 未測／未定義 |
| S-16 | `main()`：`except KeyboardInterrupt` | 伺服器被正常中斷 | 印出停止訊息並呼叫 `server.server_close()` | `tests/test_api_server_gaps.py::test_main_default_args` | 已覆蓋 |
| S-17 | `main()`：`serve_forever()` 拋非 `KeyboardInterrupt` | socket／伺服器執行期例外 | 沒有 `finally`；例外離開前不保證 `server_close()` | 無 | 未測／清理未定義 |

### `api/continuous_optimizer.py`

| 編號 | 程式位置／分支 | 失敗觸發 | 目前行為與風險 | 測試映射 | 狀態 |
|---|---|---|---|---|---|
| O-01 | `check_feedback_threshold()`：檔案不存在／數量不足／達門檻 | feedback JSONL 尚未建立或筆數不足 | 回傳 `(False, 0)` 或 `(False, count)`；達門檻回 `True` | `tests/test_integration_server_feedback.py::test_server_feedback_visible_to_optimizer_threshold` | 已覆蓋 |
| O-02 | `check_feedback_threshold()`：`read_jsonl()` 拋例外 | JSONL 損毀、開檔或權限失敗 | 例外直接離開 loop，沒有降級或錯誤日誌 | 無 | 未測／未定義 |
| O-03 | `analyze_and_suggest()`：摘要／建議分析失敗 | `get_feedback_summary()` 或 `generate_optimization_hints()` 拋例外 | 例外直接離開；不會寫 `analysis` 日誌 | `test_analyze_and_suggest_consistent_with_server_summary` 只測成功 | 未測／未定義 |
| O-04 | `analyze_and_suggest()`：`append_jsonl()` 失敗 | optimization log 無法寫入 | 分析結果尚未回傳即拋寫入例外 | 無 | 未測／未定義 |
| O-05 | `run_optimization_round()`：direction 有／無 | 有方向需加 `--force-direction`，無方向不可加 | 命令參數組裝正確 | `test_optimization_round_passes_direction_and_parallel`；`test_optimization_round_without_direction_omits_flag` | 已覆蓋 |
| O-06 | `run_optimization_round()`：子程序成功／非零退出 | `run_opt.py` 成功或未通過接受條件 | 寫 `optimization` 事件；回傳 `True`／`False` | `test_optimization_success_reflected_in_server_status`；`test_optimization_failure_logged_and_status_active` | 已覆蓋 |
| O-07 | `run_optimization_round()`：`subprocess.run()` 拋例外 | timeout、啟動失敗或其他子程序例外 | 寫 `optimization_error`；回傳 `False`；目前只用 timeout 形態觸發 | `test_optimization_exception_logged_as_error_status_idle` | 部分覆蓋 |
| O-08 | O-06／O-07 內的 `append_jsonl()` 失敗 | 成功、非零退出或例外日誌本身無法寫入 | 二次例外覆蓋原始結果；沒有 fallback 或標準錯誤回傳 | 無 | 未測／未定義 |
| O-09 | `run_continuous_loop()` 四種控制分支 | 回饋不足、無 hints、優化成功、優化失敗 | 分別等待／跳過／印成功／印失敗 | `tests/test_continuous_optimizer.py::test_loop_waits_when_feedback_insufficient`；`test_loop_skips_round_when_no_hints`；`test_loop_runs_optimization_success`；`test_loop_reports_optimization_failure` | 已覆蓋 |
| O-10 | `run_continuous_loop()` 依賴函式／sleep 拋例外 | threshold、analysis、round 或 sleep 中斷 | 沒有 `try/finally`，例外直接終止 loop；沒有中止日誌或清理契約 | 無 | 未測／清理未定義 |

### `api/feedback.py`

| 編號 | 程式位置／分支 | 失敗觸發 | 目前行為與風險 | 測試映射 | 狀態 |
|---|---|---|---|---|---|
| F-01 | `load_feedback()` → `read_jsonl()` | 檔案不存在 | 回傳空 list，供摘要／弱點分析走空結果 | `tests/test_integration_server_feedback.py::test_summary_with_no_feedback_file`；`test_load_feedback_reads_feedback_path_with_limit` | 已覆蓋 |
| F-02 | `get_recent_feedback_trend()`：`except (ValueError, TypeError)` | timestamp 缺失、非字串或非法 ISO 格式 | 略過該筆，不污染趨勢結果 | `test_recent_trend_filters_old_invalid_and_missing_timestamps`；`test_recent_trend_skips_non_string_timestamp` | 已覆蓋 |
| F-03 | `analyze_feedback_by_hash()`：`scores.items()` 拋例外 | scores 為字串以外的非 mapping，或 JSONL row 形狀損毀 | 例外向上拋；經 server 摘要端點轉成 `500` | `tests/test_integration_server_feedback.py::test_malformed_feedback_row_maps_to_500` 只驗字串 scores | 部分覆蓋 |
| F-04 | `analyze_feedback_by_hash()`：hash／question type／total score 型別錯誤 | unhashable hash／題型，或 total score 無法相加 | 例外向上拋；沒有資料列驗證或模組層錯誤回傳 | 無 | 未測／未定義 |
| F-05 | `generate_optimization_hints()`／`get_feedback_summary()`：baseline JSON 不是 mapping | 合法 JSON 為 `null` 或 list | `get_feedback_summary()` 的 `.get()` 可能拋 `AttributeError`；server 可映射成 `500`，直接呼叫沒有契約 | `test_feedback_summary_empty_feedback_and_missing_baseline` 只測 `{}` | 未測／未定義 |
| F-06 | `get_weak_areas()`：弱點 dimension／type 的 true 與 false | 分數低於／等於門檻 | 低分列出並排序；等於門檻不列出 | `tests/test_integration_server_feedback.py::test_weak_dimension_boundary_15`；`test_weak_type_boundary_70`；`tests/test_api_feedback.py::test_weak_areas_thresholds_and_sorting` | 已覆蓋 |
| F-07 | `generate_optimization_hints()`：未知維度與 top-3 截斷 | dim_hints 找不到文案，或弱點超過三筆 | 未知維度略過；每類最多三筆 | `test_optimization_hints_maps_known_dimensions_and_skips_unknown`；`test_optimization_hints_caps_at_top_three_each` | 已覆蓋 |
| F-08 | `analyze_feedback_by_hash()`：`if tdata["count"] > 0` false 側 | 人工植入空 question-type bucket | 正常輸入不會形成此狀態，因建立 bucket 後同一輪立即加一 | coverage 顯示 `76->75` 未走到；既有 zero-count 測試只覆蓋 hash bucket | 結構性 partial，非 E2E 失敗缺口 |

### `lib/api.py`

| 編號 | 程式位置／分支 | 外部失敗／例外 | 目前錯誤回傳 | 測試映射 | 狀態 |
|---|---|---|---|---|---|
| A-01 | `call_minimax()` API key guard | 缺少 `MINIMAX_API_KEY` | `RuntimeError`，不發 request | `tests/test_lib_api.py::test_call_minimax_missing_api_key` | 已覆蓋 |
| A-02 | `_translate_error()` HTTPError | HTTP 4xx／5xx | `APIError`，保留 HTTP code 與 retry | `tests/test_lib_api_http_status_codes.py::test_non_2xx_status_code_raises_api_error_with_status_code`；`tests/test_lib_api_positive_verify.py::test_http_error_yields_api_error` | 已覆蓋 |
| A-03 | `_translate_error()` socket／TimeoutError | read 或直接 timeout | `APITimeoutError`，同時是 `TimeoutError` 與 `RuntimeError` | `test_call_minimax_timeout_raises`；`test_socket_timeout_yields_api_timeout_error`；`test_timeout_error_yields_api_timeout_error` | 已覆蓋 |
| A-04 | `_translate_error()` URLError timeout reason | connect timeout 被 urllib 包裝 | `APITimeoutError` | `tests/test_lib_api_error_contract.py::test_connect_timeout_urlerror_form_should_raise_same_type_as_read_timeout`；`tests/test_lib_api_positive_verify.py::test_urlerror_with_timeout_reason_yields_api_timeout_error` | 已覆蓋 |
| A-05 | `_translate_error()` URLError 非 timeout reason | DNS／拒絕連線等 | `APIError`，訊息含「連線失敗」 | `tests/test_lib_api_line37_branch.py::test_urlerror_non_timeout_should_raise_apierror_connection_failed`；`test_urlerror_with_non_timeout_reason_yields_api_error` | 已覆蓋 |
| A-06 | `_translate_error()` ConnectionError／generic Exception | 連線重置、OS 或未知例外 | `APIError`，以 `raise ... from e` 保留 cause | `test_connection_error_base_yields_api_error`；`test_connection_reset_error_yields_api_error`；`test_generic_exception_yields_api_error_with_type_name`；`test_os_error_yields_api_error_with_type_name` | 已覆蓋 |
| A-07 | `call_minimax()` response parse | 非法 JSON、缺 choices、空 choices | `APIError`，保留原始例外 cause | `test_call_minimax_invalid_json_raises`；`test_call_minimax_missing_choices_field_raises_api_error`；`test_200_empty_choices_list_raises_api_error` | 已覆蓋 |
| A-08 | retry 非最後一次／耗盡／`retry <= 0` | 暫時失敗後成功、最後一次仍失敗、零 retry | 分別 sleep 後重試、最後轉譯、至少 request 一次 | `test_call_minimax_retry_gt_1_once_then_success`；`test_retry_exhaustion_wraps_final_dependency_error`；`test_retry_zero_should_raise_instead_of_silent_empty_string` | 已覆蓋 |
| A-09 | `_rate_wait()` 正／反條件 | 連續呼叫需 sleep，首次呼叫不需 sleep | 限流等待後照常成功或轉譯錯誤 | `tests/test_lib_api_rate_wait_branch.py::test_rate_wait_sleeps_on_consecutive_calls`；`test_rate_wait_no_sleep_on_single_call`；其餘 rate-wait error tests | 已覆蓋 |
| A-10 | `with semaphore`、`with urlopen(...)` 清理後置條件 | response read／JSON parse／API request 例外 | 程式以 context manager 退出；現有測試只驗例外型別與 cause，沒有直接驗證 `__exit__` 或 semaphore permit 歸還 | `test_error_after_rate_wait_translated_to_api_error` 等失敗測試會進入例外路徑，但沒有 cleanup spy | 部分覆蓋 |
| A-11 | `for attempt in range(attempts)` 自然離開 | `attempts >= 1` 且每輪成功 return 或最後失敗 raise | `103->exit` 不可由目前控制流到達 | coverage 顯示 partial；不需新增失敗測試 | 結構性 partial，非 E2E 失敗缺口 |

## 直接可執行的測試缺口索引

若後續要把本次盤點轉成最小測試增量，優先順序如下；本次任務只產出清單，
不在此輪新增測試或改變錯誤契約：

| 優先 | 建議測試案例 | 對應分支 | 必須斷言 |
|---|---|---|---|
| P0 | `test_post_feedback_append_failure_returns_defined_error` | S-11 | 先決定寫入失敗的 HTTP status／JSON 契約，並確認不回 `accepted` |
| P0 | `test_optimizer_status_read_failure_returns_defined_error` | S-14 | 先決定 JSONL 讀取失敗的 HTTP status／JSON 契約 |
| P0 | `test_server_closes_on_non_keyboardinterrupt` | S-17 | `serve_forever()` 任意例外時仍呼叫 `server_close()`，或明確記錄不保證清理 |
| P0 | `test_optimizer_analysis_dependency_failure_is_logged_or_propagated` | O-02～O-04 | 決定分析失敗是否寫 `optimization_error`，且不產生假成功結果 |
| P1 | `test_post_feedback_invalid_utf8_returns_400` | S-09 | `UnicodeDecodeError` 走同一 `400` 錯誤回傳 |
| P1 | `test_feedback_summary_non_mapping_baseline_is_defined` | F-05 | `null`／list baseline 的錯誤或降級契約 |
| P1 | `test_feedback_invalid_row_shapes_are_defined` | F-03～F-04 | scores、hash、題型、total score 的驗證或明確例外 |
| P1 | `test_api_context_managers_exit_on_failure` | A-10 | response context manager 已退出，semaphore 沒有 permit 洩漏 |
| P2 | `test_optimization_round_non_timeout_start_failure` | O-07 | `FileNotFoundError`／`OSError` 與 timeout 一樣寫 `optimization_error` 並回 `False` |

## 驗收界線

- 本文件只盤點四個指定模組及其在核心鏈路上的測試映射；沒有修改產品程式或
  既有測試。
- 「未測／未定義」不是宣稱目前一定會發生事故，而是表示目前沒有可重跑的
  測試證明其錯誤回傳、例外型別或清理後置條件。
- `lib/api.py` 的外部失敗轉譯目前已有直接測試；後續若只要求錯誤型別與訊息，
  不需重複新增同類 API failure case，真正剩餘的是 A-10 的 cleanup 後置條件。
