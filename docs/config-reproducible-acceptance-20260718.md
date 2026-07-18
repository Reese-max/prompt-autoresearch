# 配置模組可重現驗收（乾淨環境）

## 目標

讓引擎可在全新環境中，重複執行配置相關測試並驗證「無效環境變數不會靜默吞掉、修正後可立即重載」的穩定性。

## 本次新增的回歸測試檔案

- `tests/test_lib_config_cache_stability.py`
  - 覆蓋項目：
    - 無效環境變數導致載入失敗後，不會卡住舊快取而跳過後續重試。
    - 檔案覆蓋 + 環境變數修正時，可再次載入並套用新值。

## 完整驗收指令（乾淨環境）

> 以下命令建議在 `python -m pytest` 路徑下執行，避免直接 `pytest` 在某些環境觸發 import path 差異。

1. 安裝依賴（首次或新環境）  

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

2. 先跑配置專用回歸（含新加的快取穩定案例）  

```bash
python -m pytest -q tests/test_lib_config.py tests/test_lib_config_regression.py tests/test_config_semantic.py tests/test_lib_config_cache_stability.py
```

3. 跑完整測試，確認整體未回歸  

```bash
python -m pytest -q
```

4. 可選：只看配置 coverage（便於 CI 監控）  

```bash
python -m pytest -q tests/test_lib_config.py -o addopts= --cov=lib --cov-report=term-missing
```

## 通過門檻

- 指令 2：無例外、退出碼 `0`。
- 指令 2：`python -m pytest ...` 至少需有 106+ 通過項目（目前環境實測：106 pass）。
- 指令 3：全量測試全部通過（目前環境實測：`python -m pytest -q` 全部通過）。

## 變更摘要（可追溯）

- `lib/config.py`：`_load_config()` 在 env 套用/驗證失敗時清除快取（避免失敗後快取停滯）。
- `tests/test_lib_config_cache_stability.py`：新增快取回穩定性回歸測試。
