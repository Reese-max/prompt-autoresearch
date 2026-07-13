# lib/api.py 錯誤/例外轉譯分支覆蓋稽核

日期：2026-07-14
範圍：`lib/api.py`（47 stmts）
證據：`python -m pytest tests/test_lib_api.py --cov=lib.api --cov-branch --cov-report=term-missing -q`

```
lib\api.py    47      8     10      2    79%   26->29, 34-40, 88
9 passed in 1.48s
```

## 一、核心結論

`lib/api.py` **沒有任何錯誤「轉譯」層**。`call_minimax()` 的唯一例外處理是
`except Exception as e`（api.py:84）：非最後一次 attempt 就 `time.sleep(2**attempt)` 重試，
最後一次 attempt 則 `raise e` **原樣重拋**。呼叫端拿到的是底層原生例外，
不是自訂錯誤型別，也沒有統一的狀態碼/訊息包裝。

## 二、各錯誤情境：實際回傳的型別 / 訊息 / 狀態碼 / 覆蓋狀態

| # | 情境 | 觸發點 | 實際拋出型別 | 訊息 | 狀態碼 | 覆蓋 |
|---|------|--------|--------------|------|--------|------|
| 1 | 缺少 `MINIMAX_API_KEY` | api.py:49-50 | `RuntimeError` | 「缺少 MINIMAX_API_KEY 環境變數，無法呼叫 MiniMax API。」 | 無（不發請求） | ✅ `test_call_minimax_missing_api_key` |
| 2 | 外部 API 回非 2xx | api.py:80 → 84-86 | `urllib.error.HTTPError` 原樣重拋 | `str(e)` 為 `HTTP Error <code>: <msg>`（server 給什麼就是什麼） | 存在於 `e.code`（如 500），模組不讀取、不轉譯 | ✅ `test_call_minimax_non_200_raises_http_error` |
| 3 | read 階段 timeout | api.py:80-81 → 84-86 | `socket.timeout`（= `TimeoutError`）原樣重拋 | 原生訊息 | 無 | ✅ `test_call_minimax_timeout_raises` |
| 4 | 連線階段 timeout（urllib 包裝形態） | api.py:80 → 84-86 | `urllib.error.URLError`，`reason` 為 `socket.timeout` | `<urlopen error ...>` | 無 | ❌ **未覆蓋**（僅測裸 `socket.timeout`，未測 `URLError(reason=timeout)` 包裝形態） |
| 5 | 回應非合法 JSON | api.py:82 → 84-86 | `json.JSONDecodeError` 原樣重拋 | 原生解析訊息 | 無（HTTP 已是 2xx） | ✅ `test_call_minimax_invalid_json_raises` |
| 6 | 回應缺 `choices` | api.py:83 → 84-86 | `KeyError` 原樣重拋 | `'choices'` | 無 | ✅ `test_call_minimax_missing_choices_field_raises_key_error` |
| 7 | 一般 exception | api.py:84-86 | 原型別原樣重拋 | 原訊息 | 無 | ✅ `test_call_minimax_exception_is_propagated`（`RuntimeError("boom")`） |
| 8 | 重試後成功（非最後 attempt 進 sleep 分支） | api.py:87 | 不拋出，回傳內容 | — | — | ✅ `test_call_minimax_retry_gt_1_once_then_success`（僅以 `RuntimeError` 觸發重試；HTTPError/timeout 觸發重試的形態未另測，但為同一行同一分支） |
| 9 | `retry <= 0` 靜默回空字串 | api.py:88（branch 76→88） | 不拋出，`return ""` | — | — | ❌ **未覆蓋**。這是唯一「吞錯」分支：config `retry=0` 時迴圈完全不進入，**不呼叫 API、不報錯、靜默回 `""`** |

## 三、未覆蓋行明細（coverage 實測 Missing: `26->29, 34-40, 88`）

屬於錯誤/例外處理的未覆蓋項：

- **api.py:88 `return ""`**（branch 76→88）：`max_retry <= 0` 的靜默空字串 fallback，見上表 #9。是本次稽核唯一真正未覆蓋的錯誤處理分支。
- **情境 #4（URLError 包裝的 timeout）**：行覆蓋上與 #2/#3 走同一 except（84-86 行已覆蓋），故 coverage 數字看不出來；屬「例外形態」缺口而非行缺口。呼叫端若只 catch `socket.timeout` 會漏接這形態。

與錯誤轉譯無關的未覆蓋項（僅列出，不屬本稽核缺口）：

- **api.py:34-40**：`_rate_wait()` 本體 — 測試 fixture 以 `monkeypatch.setattr(api, "_rate_wait", lambda: None)` 繞過，屬 rate limiting 邏輯。
- **api.py:26->29**：`_get_semaphore()` 的「semaphore 已初始化」partial branch。

## 四、對呼叫端的實務含意

1. 呼叫端要判斷 HTTP 狀態碼只能自行 catch `urllib.error.HTTPError` 讀 `e.code`；`lib/api.py` 不提供結構化錯誤。
2. timeout 有兩種形態（`socket.timeout` 與 `URLError(reason=timeout)`），只 catch 其一會漏。
3. `retry=0` 設定錯誤不會炸，會拿到空字串 —— 與「API 回了空內容」無法區分。
