# 執行佐證報告 (20260728-105855)

**可重複性判定: REPRODUCIBLE**

## 環境
- python: `3.11.9 (tags/v3.11.9:de54cf5, Apr  2 2024, 10:12:12) [MSC v.1938 64 bit (AMD64)]`
- platform: `Windows-10-10.0.26200-SP0`
- arch: `AMD64`
- hashseed: `0`
- commit: `2783c523994edbb4f2dccbca6274c25fd61cca0f`
- time: `2026-07-28T10:58:55.953001`

## 依賴鎖定檔
- `requirements.lock`: `63f160bd3d2be5fcef940ffc27965ab0aec374ebff6c52dcdb20cdeeb89922b2`

## 第一次執行
- 命令: `C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe -m pytest --cov=lib --cov=api --cov=scripts --cov-report=xml --cov-report=html --cov-fail-under=0`
- Exit: 0
- 摘要: ======================= 930 passed, 2 skipped in 49.31s =======================

## 第二次執行
- 命令: `C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe -m pytest --cov=lib --cov=api --cov=scripts --cov-report=xml --cov-report=html --cov-fail-under=0`
- Exit: 0
- 摘要: ======================= 930 passed, 2 skipped in 43.44s =======================

## 比較結果
- Compare exit: 0
- Has differences: False

## 原始碼雜湊 (前 10)
- `api/__init__.py`: `fbf845da479786c4...`
- `api/continuous_optimizer.py`: `b1810d0e98fb5c43...`
- `api/feedback.py`: `9973be5fd7fd5264...`
- `api/server.py`: `50d0705e6897c8f8...`
- `lib/__init__.py`: `d1846b937b63fc5b...`
- `lib/api.py`: `ded26788c7f64af8...`
- `lib/config.py`: `59ceef9517834fa4...`
- `lib/io.py`: `8ed3d35f61de99a0...`
- `lib/metrics.py`: `c1e9ee8a6652db61...`
- `scripts/__init__.py`: `e3b0c44298fc1c14...`
- ... (共 25 項)