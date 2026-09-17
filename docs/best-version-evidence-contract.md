# 最佳版本證據契約（Best-Version Evidence Contract）

> 本檔記錄 `scripts/best_version_report.py` 產生之證據報告的唯一權威契約，
> 以及讓報告判定為 `VALID`／可採用所需的最小完整證據集合。

## Canonical schema

- 契約檔：`schemas/best_version_evidence_report.schema.json`
- 報告欄位 `schema_version` 目前為 `1.0.0`，`report_type` 固定為
  `best_version_evidence`。
- producer 產生的結構化報告必須通過該 schema 驗證；`--validate-schema`
  會在驗證失敗時讓 CLI 以非零結束。
- `load_report_schema()` 內嵌的後備契約僅在 schema 檔缺席時使用，
  其頂層 `required` 必須與 canonical schema 檔保持一致。

## 最小完整證據夾具

回歸測試 `tests/test_best_version_evidence_contract.py` 內的
`build_minimal_complete_evidence()` 即為此契約的文件化範例。完整性閘門
（`verify_evidence_integrity`）要求的關鍵證據：

| 證據 | 位置 | 必要內容 |
|---|---|---|
| winner 提示詞 | `prompts/baseline.md` | 可讀且非空 |
| baseline 元資料 | `prompts/baseline.meta.json` | `prompt_hash`、有限的 `dev_avg`／`holdout_avg` |
| 候選比較 | `prompts/candidates/*.scorecard.json` + 對應 `.md` | `candidate_path`、`candidate_hash`、`final_decision`、dev／holdout 分數 |
| 重現設定 | `config.yaml` | 巢狀 YAML，`thresholds` 須為非空 dict |
| 執行紀錄 | `evolution_log.jsonl` | 至少一個完整 session（`start` + `stop`） |

缺任一項 → `decision.status = "inconclusive"`、`code = INCOMPLETE_EVIDENCE`，
報告不得宣稱任何版本為最佳。

## Fail-closed 規則

- `config.yaml` 為真正的巢狀 YAML；`PyYAML` 為已宣告的執行期相依
  （`requirements.txt`／`requirements.lock`）。無 PyYAML 時退回扁平
  最佳努力解析，巢狀區段缺漏由閘門兜住，不會產生錯誤的 VALID。
- 證據檔缺失、不可讀（`PermissionError`）、語法錯誤或型別不符，
  一律回傳型別化 `INCOMPLETE_EVIDENCE`，不得逸出未捕捉例外。

## 漂移偵測

`schema_validation_errors()` 的診斷會點名缺失或不相容的欄位路徑
（例如 `$.decision.status`）。回歸測試會逐一移除 canonical schema
頂層 `required` 欄位並要求診斷點名該欄位，確保 producer／consumer
漂移可被定位而非靜默通過。
