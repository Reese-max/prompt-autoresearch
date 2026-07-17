# Branch coverage 缺口優先序（2026-07-18）

## 執行結果

指定指令首次直接執行時，系統的 `pytest.exe`（Hermes venv）未把目前 repo 放入
頂層 `conftest.py` 的匯入路徑，收集階段即以
`ModuleNotFoundError: No module named 'lib.config'` 結束。僅對該測試行程設定目前
repo 為 `PYTHONPATH` 後，以相同 coverage 參數重跑：

```powershell
$env:PYTHONPATH = (Get-Location).Path
pytest --cov --cov-branch tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

結果為 `400 passed, 1 deselected`；產品程式共 `1693` statements、`0` missed，
branch 共 `574`，其中 `9` 個 partial branches，總覆蓋率顯示為 `99%`。

## Partial branch 明細

| 檔案與條件行 | True／迴圈本體側 | False／離開側 | 判定 |
|---|---|---|---|
| `lib/metrics.py:25`，`if data` | `25->26` 已覆蓋 | `25->27` **缺口** | **最高價值**：公開函式預設 `data=None`，正常可達 |
| `api/feedback.py:76`，`if tdata["count"] > 0` | `76->77` 已覆蓋 | `76->75` **缺口** | 正常輸入不可達；題型 bucket 建立後會在同一次迴圈立即加一 |
| `lib/api.py:103`，`for attempt in range(attempts)` | `103->104` 已覆蓋 | `103->exit` **缺口** | 結構性不可達；`attempts >= 1`，成功會 return，末次失敗會 raise |
| `scripts/compare_runs.py:12`，stdout 有 `reconfigure` | `12->13` 已覆蓋 | `12->14` **缺口** | 非標準 stdout 的相容性 guard |
| `scripts/compare_runs.py:14`，stderr 有 `reconfigure` | `14->15` 已覆蓋 | `14->18` **缺口** | 非標準 stderr 的相容性 guard |
| `scripts/evaluate_routed.py:24`，stdout 有 `reconfigure` | `24->25` 已覆蓋 | `24->26` **缺口** | 非標準 stdout 的相容性 guard |
| `scripts/evaluate_routed.py:26`，stderr 有 `reconfigure` | `26->27` 已覆蓋 | `26->29` **缺口** | 非標準 stderr 的相容性 guard |
| `scripts/preflight.py:12`，stdout 有 `reconfigure` | `12->13` 已覆蓋 | `12->14` **缺口** | 非標準 stdout 的相容性 guard |
| `scripts/preflight.py:14`，stderr 有 `reconfigure` | `14->15` 已覆蓋 | `14->17` **缺口** | 非標準 stderr 的相容性 guard |

## 鎖定結論

最高價值未覆蓋條件是 **`lib/metrics.py:25` 的 `if data`**：

- True 側已有 `tests/test_lib_metrics.py::test_record_event_append_payload_with_timestamp`
  覆蓋，會將額外欄位併入事件。
- False 側 `25->27` 未覆蓋；呼叫 `record_event(event_type)` 或傳入空 dict 時，
  應直接寫入只有事件名稱與時間戳記的合法紀錄。
- 此側是函式簽章明確提供的正常使用方式，不需偽造內部狀態或替換標準串流，
  因此優先價值高於其餘八個 partial branches。

## 完整測試驗證

`pytest -q`（同樣僅對該行程設定目前 repo 為 `PYTHONPATH`）結果為
`401 passed in 12.95s`，無失敗、skip 或 deselect。
