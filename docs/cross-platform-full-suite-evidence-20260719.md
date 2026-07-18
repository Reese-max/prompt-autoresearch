# 跨作業系統完整測試佐證（2026-07-19）

## 執行範圍

兩個平台皆執行 `tests/` 下的完整 pytest 套件，未使用 `--deselect`。命令中的 `-o addopts=` 僅覆寫 `pytest.ini` 的 coverage 報表選項，避免覆寫既有 coverage 產物，並不影響測試收集或執行。

## 結果

| 平台 | 版本 | Python／pytest | 執行命令 | exit code | 通過 | 失敗 | 跳過 |
|---|---|---|---|---:|---:|---:|---:|
| Windows | Microsoft Windows 11 專業版 10.0.26200 | Python 3.11.9／pytest 9.1.1 | `python -m pytest tests/ -q -o addopts= --junitxml=docs\\evidence\\full-suite-Windows-10-Python-3.11.9-20260719.junit.xml` | 0 | 613 | 0 | 1 |
| Ubuntu | Ubuntu 24.04.4 LTS（WSL2 Linux 5.15.167.4） | Python 3.12.3／pytest 9.0.3 | `python3 -m pytest tests/ -q -o addopts= --junitxml=docs/evidence/full-suite-Ubuntu-24.04-Python-3.12.3-20260719.junit.xml` | 0 | 614 | 0 | 0 |

「失敗」為 JUnit 的 `failures + errors`。兩平台各收集 614 個測試；Windows 的一個跳過案例已由 pytest 原始輸出與 JUnit `skipped="1"` 記錄。

## 完整佐證

| 平台 | 完整主控台日誌 | JUnit 測試結果 |
|---|---|---|
| Windows | [cross-platform-Windows-10-Python-3.11.9-20260719.log](evidence/cross-platform-Windows-10-Python-3.11.9-20260719.log) | [full-suite-Windows-10-Python-3.11.9-20260719.junit.xml](evidence/full-suite-Windows-10-Python-3.11.9-20260719.junit.xml) |
| Ubuntu | [cross-platform-Ubuntu-24.04-Python-3.12.3-20260719.log](evidence/cross-platform-Ubuntu-24.04-Python-3.12.3-20260719.log) | [full-suite-Ubuntu-24.04-Python-3.12.3-20260719.junit.xml](evidence/full-suite-Ubuntu-24.04-Python-3.12.3-20260719.junit.xml) |

每份原始日誌都包含平台資訊、Python／pytest 版本、完整測試命令、pytest 進度與摘要，以及 `EXIT_CODE=0`。JUnit 檔則保留每個測試案例與 `tests`、`failures`、`errors`、`skipped` 的可解析統計。
