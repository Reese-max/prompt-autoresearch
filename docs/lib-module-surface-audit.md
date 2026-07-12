# `lib/` 四模組公開行為盤點（config/io/metrics/api）

## 任務範圍
- 檔案：`lib/config.py`、`lib/io.py`、`lib/metrics.py`、`lib/api.py`
- 目的：盤點公開函式、主要分支、錯誤處理路徑，作為後續 e2e 測試覆蓋參考
- 約束：不修改 `app.js`、`index.html`、`lib/api/*.py` 以外的程式邏輯

---

## 1) `lib/config.py`

### 公開函式
- `get(section, key=None, default=None)`
- `get_section(section)`
- `get_all()`

### 分支與公開行為
- `_load_config()`：
  - 快取分支：`_CONFIG is not None` 時直接回傳快取值。
  - 首次載入分支：建立 `_CONFIG` 後，載入預設值。
  - 設定檔分支：若 `config.json` 存在則 `json.load`。
  - 無法讀取/解析：例外被 `except: pass`，保留預設值（加上既有已套用的覆蓋）。
  - 總是呼叫 `_apply_env_overrides()`。
- `_deep_merge(base, override)`：
  - 若 `base` 與 `override` 對應 key 都是 dict → 遞迴。
  - 否則覆蓋。
- `_apply_env_overrides(cfg)`：
  - 每個 env key 有「有/無」兩條路徑。
  - 有值：先嘗試 `int` 轉型；失敗改 `float`；仍失敗則原字串。

### `get` 邏輯
- `section` 不存在時回傳 `section_data`（空 dict）或 `default`。
- `key is None`：回傳整個 section。
- `key` 是 `dict` / `list`：被視為呼叫者誤用，回傳整個 section；若提供 `default` 且非 None 且 key 非空，會將 default 當回退值。
- 非 dict 的 section 與 key 查詢：回預設值。

### `get_section`
- 回傳 `dict(cfg.get(section, {}))` 的複本。

### `get_all`
- 回傳 `dict(_load_config())` 的快取快照。

### 錯誤處理重點
- `config.json` 讀檔/JSON 失敗：被吞掉（不拋錯）。
- 環境變數缺失：直接略過。
- 型別轉換失敗：不拋錯，保留原始字串。

---

## 2) `lib/io.py`

### 公開函式
- `load_file(path, default="")`
- `write_file(path, content)`
- `sha256_text(text)`
- `load_json(path, default=None)`
- `write_json(path, payload)`
- `read_jsonl(path, limit=None)`
- `append_jsonl(path, payload)`
- `normalize_path(path)`
- `ensure_dir(path)`

### 分支與公開行為
- `load_file`
  - 檔案不存在 → 回傳 `default`。
  - 存在 → 讀取內容並 `strip()`。
- `write_file`
  - 若目錄不存在，先 `os.makedirs(..., exist_ok=True)`。
  - 寫入文字。
- `load_json`
  - `default is None` 時使用 `{}`。
  - 檔案不存在 → 回傳 `default`。
  - 存在且成功解析 → 回傳 JSON。
  - `json.load` 失敗 → 回傳 `default`。
- `write_json`
  - 寫入前確保目錄存在。
- `read_jsonl`
  - 檔案不存在 → 回傳空 list。
  - 逐行讀：空行跳過。
  - 直到 `limit` 命中則停止（`if limit and len(rows) >= limit`）。
  - 單行 `json.loads` 不包 try/except，失敗會直接拋例外。
- `append_jsonl`
  - 寫前確保目錄存在。
  - 逐筆 append 一行 JSON。

### 錯誤處理重點
- `read_jsonl` 對壞 JSON 不具復原處理。
- 檔案開啟失敗、權限錯誤、編碼問題，依函式而異未捕捉，會外傳。
- `normalize_path` / `sha256_text` 幾乎無錯誤邊界。

---

## 3) `lib/metrics.py`

### 公開函式
- `record_event(event_type, data=None)`
- `record_round(...)`

### `record_event`
- 固定欄位：`event`, `timestamp`
- 若 `data` 為真值，`payload.update(data)`；`{}`、`[]`、`0`、`False`、`""` 不會 merge。

### `record_round`
- 參數預設：`round_no` 必填、`direction=""`、`target_failures=None`、`error=""`、`candidates_count=1`。
- 回傳值：傳回最後 payload。
- `target_failures or []`：避免 `None`。

### 錯誤處理重點
- timestamp 格式固定 `%Y-%m-%dT%H:%M:%S`。
- `append_jsonl` 失敗（IO 權限、路徑、硬碟）直接外傳。

---

## 4) `lib/api.py`

### 公開函式
- `call_minimax(system_prompt, user_content, temperature=0.7)`

### 關鍵流程分支
1. 讀取 `MINIMAX_API_KEY`
   - 無值：`raise RuntimeError("缺少 MINIMAX_API_KEY ...")`
2. 讀取 `api.url / model / timeout / retry`
3. 建立 request payload
4. 重試迴圈：`for attempt in range(max_retry)`
   - 每次嘗試都進入 `_get_semaphore()` 取得全域 semaphore
   - 先 `_rate_wait()`（保證全域最小間隔）
   - 成功回傳：`res_json["choices"][0]["message"]["content"].strip()`
   - 失敗：最後一次重試才 `raise e`，否則 `sleep(2**attempt)` 後重試

### 錯誤處理重點
- URL/網路錯誤、Timeout、JSON 解析錯誤、回應欄位缺失皆會被 `except Exception` 捕捉。
- 只有重試機制可攔截，最後一次仍失敗才向外拋錯。
- 回傳解析若欄位缺失，`KeyError` 屬於重試捕捉範圍。

---

## 可建議測試清單（只列測試維度）

### `lib/config.py`
- 無 `config.json` / 損壞 JSON / 有效 JSON。
- env 覆蓋 int、float、字串三種。
- `get(section, None)`、`get(section, {})`、`get(不存在 section, default)`、`get(非 dict section, key)`。

### `lib/io.py`
- `read_jsonl` 空行、`limit=None`、`limit=0`、`limit=2`。
- `read_jsonl` 遇到壞 JSON 是否直接 raise。
- `load_json` 解析失敗回 `default`。

### `lib/metrics.py`
- `record_event` 空 dict 不 merge。
- `record_round` 預設值與傳回 payload 驗證。

### `lib/api.py`
- 缺少金鑰快速失敗。
- `max_retry=1` 時只打一筆。
- timeout / retry / url / model 覆蓋。
- 回傳 JSON 欄位缺失導致異常是否重試。
