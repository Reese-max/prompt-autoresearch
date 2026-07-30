# Baseline SHA-256 一致性與 Champion 晉升實跑證據

## 1. `prompts/baseline.md` SHA-256 記錄

| 項目 | 值 |
|---|---|
| 檔案 | `prompts/baseline.md` |
| 計算方式 | `sha256_text()` 等價：`hashlib.sha256(text.encode("utf-8")).hexdigest()`（strip 後） |
| 計算所得 SHA-256 | `004e4d46a58fd02d7a4c112948fe7749720bb3c529c2083ec203ae1f364bd08f` |
| `baseline.meta.json` 儲存值 | `004e4d46a58fd02d7a4c112948fe7749720bb3c529c2083ec203ae1f364bd08f` |
| **斷言結果** | ✅ 一致（MATCH） |
| `prompts/current.md` | 與 `baseline.md` 位元組一致（同 SHA-256） |

## 2. Champion 晉升實跑證據

以下三筆 champion 均經既有 `route_evolve.py`（champion evolution pipeline）完成晉升，
並在 `prompts/champions/` 留下永久紀錄。

### 2.1 `compare`（比較題）

| 欄位 | 值 |
|---|---|
| 晉升時間 | 2026-05-25 12:45:05 |
| 候選原始檔 | `prompts/candidates/compare_champion_candidate_1779684138.md` |
| 候選 hash | `cfb8f4adde69b5afa61fbc40260e09f4cda0fa2d733cf6519747e2a691cd88c0` |
| Champion 產物 | `prompts/champions/compare.md` + `compare.meta.json` |
| Dev run 目錄 | `runs/20260525_124336/`（存在 ✅） |
| Holdout run 目錄 | `runs/20260525_124505/`（存在 ✅） |
| Dev score diff | +2.5 |
| Holdout score diff | 0.0 |
| Evolution log event | `route_evolution_log.jsonl` → `champion_accept`（2 筆，含首次版本） |

### 2.2 `practical`（實務應用題）

| 欄位 | 值 |
|---|---|
| 晉升時間 | 2026-05-25 13:04:09 |
| 候選原始檔 | `prompts/candidates/practical_champion_candidate_1779685228.md` |
| 候選 hash | `bfb98e351d3fc5af28e7b235a7ebcb148f874283e69b134d746ca22c0961c656` |
| Champion 產物 | `prompts/champions/practical.md` + `practical.meta.json` |
| Dev run 目錄 | `runs/20260525_130222/`（存在 ✅） |
| Holdout run 目錄 | `runs/20260525_130409/`（存在 ✅） |
| Dev score diff | +6.67 |
| Holdout score diff | +4.67 |
| Evolution log event | `route_evolution_log.jsonl` → `champion_accept`（1 筆） |

### 2.3 `legal_case`（法律案例題）

| 欄位 | 值 |
|---|---|
| 晉升時間 | 2026-05-25 02:16:51 |
| 晉升路徑 | elite path（`run_opt.py` 單輪演化優化器） |
| 候選原始檔 | `prompts/candidates/candidate_1779646345.md` |
| 候選 hash | `48cadb1819d219d7889c50b252c594216986d77ac1f41ee864e627de30b35bf9` |
| Elite 備份 | `prompts/candidates/elite/legal_case_20260525_021651_48cadb18.md` |
| Champion 產物 | `prompts/champions/legal_case.md` + `legal_case.meta.json` |
| Dev run 目錄 | `runs/20260525_021650/`（存在 ✅） |
| Dev score diff | +9.5 |
| 決定 | `SPECIALTY_RETAINED`（保留特化 champion） |

## 3. Archive 流程證據（Baseline 備份）

`prompts/archive/baseline_20260602_184534_scoreold.md` 為前一代 baseline 的備份，
由 `run_opt.py` 晉升流程自動產生（`_cleanup_old_archives` 管理版本數量）。

| 欄位 | 值 |
|---|---|
| 歸檔檔名 | `baseline_20260602_184534_scoreold.md` |
| 檔案 SHA-256（strip） | `67b6f73a7372511dabadf5f2d4ab8ce557330836feb6c9299803361bed3424b9` |
| 當前 baseline SHA-256（strip） | `004e4d46a58fd02d7a4c112948fe7749720bb3c529c2083ec203ae1f364bd08f` |
| 兩者不同 ✅ | 確認歸檔確實為舊版 |

## 4. 流程架構摘要

```
run_opt.py                            route_evolve.py
  │                                      │
  ├─ 產生候選提示詞                       ├─ 產生題型特化候選
  ├─ Gatekeeper 檢查                     ├─ Gatekeeper 檢查
  ├─ Smoke / Dev / Holdout 評估          ├─ Dev 子題庫評估（vs baseline）
  ├─ 10 大接受條件判定                    ├─ Holdout 子題庫評估
  ├─ 備份舊 baseline → archive/          ├─ compare_runs 判定
  └─ 寫入新 baseline.md                  └─ save_champion() → champions/
          │                                      │
          └─ baseline.meta.json                   └─ <slug>.meta.json
```

## 5. 結論

- ✅ `baseline.md` SHA-256 與 `baseline.meta.json` 儲存值完全一致
- ✅ `prompts/current.md` 與 `baseline.md` 一致
- ✅ 三筆 champion（compare / practical / legal_case）均有完整晉升證據鏈：
  候選原始檔 → run 評估目錄 → champion 產物 → evolution log event → meta.json
- ✅ Archive 流程有實際產物（`prompts/archive/baseline_20260602_184534_scoreold.md`）
