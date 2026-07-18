# 配置模組可重現驗收（2026-07-18）

## 目的與範圍

驗證設定來源的缺值、無效值、fallback、快取回復、來源優先序，以及設定值
實際傳入 `lib.api` HTTP 消費端的結果。設定專用驗收不依賴全庫 coverage，
每個例外案例都必須斷言 `ValueError`、錯誤訊息、fallback 值／型別或消費端
請求內容。

## 執行前提

在目前 repo 根目錄執行。首次建立環境時：

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

本次實測環境：Python 3.11.9。

## 完整驗收指令與結果

### 1. 設定專用合併驗收（不載入預設 coverage）

```bash
python -m pytest -q -o addopts= tests/test_lib_config.py tests/test_lib_config_regression.py tests/test_config_semantic.py tests/test_lib_config_cache_stability.py tests/test_config_special_branch.py tests/test_config_integration.py
```

結果：`121 passed`，退出碼 `0`。

### 2. 逐測試詳細輸出

以下命令會逐一列出每個測試案例的 `PASSED`／`FAILED` 狀態，不以總 coverage
百分比取代案例結果：

```bash
python -m pytest -v -o addopts= tests/test_lib_config.py tests/test_lib_config_regression.py tests/test_config_semantic.py tests/test_lib_config_cache_stability.py tests/test_config_special_branch.py tests/test_config_integration.py
```

結果：`121 passed`，每個列出的測試案例均為 `PASSED`，退出碼 `0`。

### 3. 設定測試逐檔結果

每列均可用下列形式單獨重跑：`python -m pytest -q -o addopts= <測試檔>`。

| 測試檔 | 通過 | 主要驗證內容 |
|---|---:|---|
| `tests/test_lib_config.py` | 53 | 檔案合併、快取、環境變數型別轉換、缺值與無效值回退、`get()` 分支 |
| `tests/test_lib_config_regression.py` | 16 | 無效 env 明確拋例外、清除錯誤來源後的預設／檔案值、最終 `validate_config()` |
| `tests/test_config_semantic.py` | 35 | 例外型別與訊息、fallback 精確值與型別、env > file > defaults 優先序 |
| `tests/test_lib_config_cache_stability.py` | 2 | 載入失敗清除快取，修正 env 後可立即重載 |
| `tests/test_config_special_branch.py` | 12 | 缺值、空值、純空白、非數字、`nan`、零／負數、URL 格式與檔案型別錯誤 |
| `tests/test_config_integration.py` | 3 | 無效設定不發 HTTP、env 覆寫實際請求、缺檔預設值傳入 HTTP 消費端 |
| **合計** | **121** | **全部退出碼為 0** |

### 4. 全庫回歸驗收

```bash
python -m pytest -q
```

結果：`543 passed in 24.94s`，退出碼 `0`；無 failed、skipped 或 deselected。
repo 預設 coverage 的補充輸出為 `1697 statements`、`574 branches`、`0`
missed、`100%`，但此數字不是設定例外情境的唯一驗收依據。

## 斷言內容佐證

- `test_config_special_branch.py` 與 `test_config_semantic.py` 對無效環境變數／檔案值使用 `pytest.raises(ValueError)`，並檢查錯誤訊息關鍵字、dotted key 或實際值。
- fallback 案例在清除錯誤來源並重置快取後，明確比較預設／檔案值及 `int` 型別，且再次呼叫 `validate_config()`。
- `test_lib_config_cache_stability.py` 驗證失敗載入後的快取確實可恢復，不會把失敗狀態留給下一次呼叫。
- `test_config_integration.py` 驗證無效設定時 `urlopen.assert_not_called()`，合法覆寫時則逐項檢查請求 URL、timeout、model；缺檔案例檢查預設值確實抵達 HTTP 消費端。

## 測試隔離修正

設定測試原先有直接寫入 `os.environ` 的案例，合併執行時會污染後續測試。現已改用 pytest `monkeypatch.setenv`，並讓 HTTP 整合 fixture 先清除所有設定相關環境變數，確保逐檔與合併命令結果一致。
