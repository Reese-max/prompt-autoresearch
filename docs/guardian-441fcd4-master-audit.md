# guardian `441fcd4` 與目前 `master` 稽核

## 結論

`441fcd4` 已是目前 `master`（`616306d`）的祖先。其核心修復沒有缺少：

- 評測摘要寫入 `dataset`、`metric`、`evaluator_version`、`measurement_settings`。
- `auto_evolve._rank_candidate_evaluations` 以 stage 與完整量測基準分組，禁止 smoke／dev 或不同評測器版本直接比較。
- 同分不再以候選路徑決勝，證據不足時只回報比較群組最佳，不宣稱全域最佳。

`441fcd4` 原本另寫入 `runs/controlled_closed_loop_ranking.json`；後續 `755bfaa` 以 `evolution_log.jsonl` 的 `controlled_closed_loop_ranking` 事件取代，並非遺失選優證據。

本次補上的必要修復是報告層的基準追溯：`scripts/best_version_report.py` 以前在 scorecard 沒有顯式 `stage_evaluations` 時只使用 baseline 分數，沒有讀取 stage run 的 `summary.json`。現在會優先從 `dev`、`smoke`、`holdout` run 摘要取得完整評測基準，舊 scorecard 仍保留 baseline fallback。

## 實際選優呼叫鏈

```text
auto_evolve.main
  -> run_controlled_closed_loop
     -> scan_candidate_evaluations
     -> _rank_candidate_evaluations（既有候選）
     -> run_opt.run_opt_pass
        -> gatekeeper：全部候選
        -> smoke：全部候選
        -> 取 smoke 最高者進 dev，再依接受條件進 holdout
        -> 更新 candidate scorecard
     -> scan_candidate_evaluations
     -> _rank_candidate_evaluations（既有 + 本輪）
     -> evolution_log.jsonl

scripts/best_version_report.py
  -> load_candidate_scorecards
  -> _basis_from_card
     -> 顯式 basis／stage_evaluations
     -> stage run summary.json（本次修復）
     -> 舊資料 baseline_scores fallback
  -> verify_evidence_integrity
```

沒有重做 `run_controlled_closed_loop` 的 smoke／dev 隔離；本次只修正其下游報告讀取證據的缺口。

## 現有測試覆蓋

- `tests/test_controlled_closed_loop_ranking.py`：同 stage／跨 stage、同分、缺少比較基準、評測器版本不一致，以及受控閉環報告持久化。
- `tests/test_best_version_report.py`：報告完整性閘門、不同顯式基準、缺欄位、同分與本次新增的 run summary 基準追溯。
- `tests/test_best_version_report_e2e.py`：以隔離工作區實際執行多候選閉環與最佳版本報告驗收。

修復前新增回歸測試失敗：報告錯誤回傳 `valid`，未拒絕 `evaluate-v1` 與 `evaluate-v2` 的不同基準。修復後該測試通過，報告回傳 `INCOMPLETE_EVIDENCE`。

## 驗證

```text
python -m pytest -q tests/test_controlled_closed_loop_ranking.py tests/test_best_version_report.py tests/test_best_version_report_e2e.py
79 passed

python -m pytest -q
1129 passed, 2 skipped in 99.11s
總覆蓋率：76%
```
