# 跨平台驗證測試說明

## 目的

確保 Prompt AutoResearch 的關鍵流程在 Windows（開發環境）與 Linux/macOS（CI 環境 `ubuntu-latest`）上以相同輸入產生一致的輸出、錯誤型別與退出碼，避免平台差異被隱性忽略。

## 測試檔

`tests/test_cross_platform.py` — 34 個測試案例，覆蓋 8 個驗證類別。

## 驗證類別

| # | 類別 | 覆蓋內容 | 平台風險點 |
|---|------|----------|------------|
| 1 | `TestNormalizePath` | `io.normalize_path` 反斜線轉正斜線 | Windows 路徑含 `\`，Linux 無此問題 |
| 2 | `TestFileIORoundTrip` | `load_file`/`write_file`/`load_json`/`write_json` Unicode round-trip | Windows 預設編碼非 UTF-8 |
| 3 | `TestJSONLRoundTrip` | `append_jsonl`/`read_jsonl` Unicode 行序與內容 | 行尾與編碼交互 |
| 4 | `TestProtectedFilePathHandling` | `_is_protected_product_file` 同時處理 `/` 與 `\` | git status 輸出路徑格式因平台而異 |
| 5 | `TestGatekeeperCrossPlatform` | gatekeeper CLI 退出碼與 JSON 輸出契約 | `os.chdir`、`sys.exit` 行為 |
| 6 | `TestConfigPathResolution` | `lib.config._CONFIG_PATH` 路徑解析 | `os.path.abspath` 跨平台一致性 |
| 7 | `TestLineEndingConsistency` | `\r\n` vs `\n` 讀取一致性 | Windows 換行符 |
| 8 | `TestEnsureDir` | `io.ensure_dir` 目錄建立 | 權限模型差異 |

## 設計原則

- **最小改動**：僅新增一個測試檔，不修改任何原始碼。
- **明確斷言**：每個測試包含平台標註的錯誤訊息，失敗時可立即定位平台差異。
- **與 CI 對齊**：CI 在 `ubuntu-latest` 執行，開發在 Windows；本測試確保兩邊行為一致。
- **無外部依賴**：僅使用 `pytest`、標準函式庫與專案自有 `lib.io`。

## 執行方式

```bash
# 單獨執行跨平台測試
pytest tests/test_cross_platform.py -v --no-cov

# 納入完整測試套件
pytest tests/ -v
```

## CI 整合

本測試自動被 `pytest.ini` 的 `testpaths = tests` 納入，CI 的 `ubuntu-latest` 環境會自動執行。
若任何跨平台斷言在 Linux 上失敗，CI 即會擋下，確保平台差異不會被隱性忽略。
