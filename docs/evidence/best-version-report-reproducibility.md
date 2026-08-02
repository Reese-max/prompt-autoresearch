# 最佳版本證據報告：真實執行與重跑紀錄

## 執行範圍

目標介面為 `scripts/best_version_report.py`。`--help` 實際執行 exit 0，確認介面提供 `--out`、`--json-out`、`--json` 與 `--validate-schema`。

正式命令：

```powershell
python scripts\best_version_report.py --out docs/evidence/best-version-report-live.md --json-out docs/evidence/best-version-report-live.json --validate-schema
```

同一命令第二次執行時，僅將輸出檔名改為 `best-version-report-rerun.md` 與 `best-version-report-rerun.json`。

## 完整產物

- [第一次完整 Markdown 報告](best-version-report-live.md)
- [第一次完整結構化 JSON](best-version-report-live.json)
- [第二次完整 Markdown 報告](best-version-report-rerun.md)
- [第二次完整結構化 JSON](best-version-report-rerun.json)
- [第一次原始 stdout](best-version-report-live.stdout.txt)
- [第二次原始 stdout](best-version-report-rerun.stdout.txt)
- [第一次 stderr](best-version-report-live.stderr.txt)
- [第二次 stderr](best-version-report-rerun.stderr.txt)
- [完整測試輸出](best-version-full-suite.txt)

## 第一次真實執行

| 項目 | 結果 |
| --- | --- |
| exit code | `0` |
| 產生時間 | `2026-08-02 15:01:14` |
| 報告判定 | `inconclusive` |
| 判定碼 | `INCOMPLETE_EVIDENCE` |
| 候選數 | `254` |
| execution records | `132` |
| 證據檢查 | `518` 項：`304` 通過、`214` 未通過 |
| Schema | `valid=true`、`errors=0` |
| reproduction commands | `4` |
| Markdown 大小 | `1,686,512` bytes |
| JSON 大小 | `1,637,497` bytes |
| stderr | `0` bytes |

完整性閘門實際拒絕選優，因目前檔案與既有記錄的 hash 不一致；報告保留全部檢查結果，沒有宣稱任何版本為最佳。

## 第二次重跑

| 項目 | 結果 |
| --- | --- |
| exit code | `0` |
| 產生時間 | `2026-08-02 15:01:31` |
| 報告判定 | `inconclusive` |
| 判定碼 | `INCOMPLETE_EVIDENCE` |
| 候選數 | `254` |
| execution records | `132` |
| 證據檢查 | `518` 項：`304` 通過、`214` 未通過 |
| Schema | `valid=true`、`errors=0` |
| reproduction commands | `4` |
| Markdown 大小 | `1,686,512` bytes |
| JSON 大小 | `1,637,497` bytes |
| stderr | `0` bytes |

## 重現性比對

把唯一預期變動的 `generated_at` 正規化後，第一次與第二次的完整 Markdown 與 JSON 皆完全一致：

- 正規化 JSON：`True`
- 正規化 Markdown：`True`
- raw hash 不同僅因產生時間不同。

| 產物 | 第一次 SHA-256 | 第二次 SHA-256 |
| --- | --- | --- |
| Markdown | `804eb24f0289b1869160a758a667a9becabbcb45bd589bd4ae1efeca91683c36` | `7122534110f42f1c025b94db6e1c949319f17b1e5aa964e74c007fb9320f116b` |
| JSON | `03815d5498462c663e6c1a8d1cf7a128676e5b698409e94c464de9262c4e452a` | `bf30998f9184ed550db0482e5a609454a9250e5eb94cd62c045fd252d44b146c` |

## 測試重跑

`python -m pytest -q` 實際結果：`1120 passed, 2 skipped in 117.40s`，exit 0。完整輸出保存在 [best-version-full-suite.txt](best-version-full-suite.txt)。

結論：目標 CLI 存在、可產生完整 Markdown／JSON、Schema 驗證通過，且相同輸入重跑結果可重現；目前資料證據本身仍是 `INCONCLUSIVE`，不可據此宣稱有已驗證的最佳版本。
