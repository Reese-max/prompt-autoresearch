# Round 3 Stall 診斷報告 — no_improve_count=3 / dominant_failure=F04

## 範圍

盤點 `infinite_evolve.py` 控制流、`run_opt.py` 晉升邏輯、`evolution_log.jsonl`
實際歷史，還原第一 run（2026-05-25 03:26:15）在 round 3 停止的完整路徑。

---

## 1. 觸發情境（實際歷史）

**啟動參數**: `max_rounds=3, no_improve_limit=3, same_failure_limit=3`

| Round | promoted | no_improve_count | dominant_failure | same_failure_count |
|-------|----------|-------------------|------------------|---------------------|
| 1     | false    | 1                 | ""               | 0                   |
| 2     | false    | 2                 | ""               | 0                   |
| 3     | false    | 3                 | "F04"            | 1                   |

**停止原因**: `"連續 3 輪未晉升"`（`infinite_evolve.py:353-354`）

---

## 2. 停止控制流還原

### 2.1 每輪循環 (`infinite_evolve.py:257-376`)

```
for round_no in range(1, args.max_rounds + 1):
    1) 執行 run_opt_pass() → 回傳 success(bool)
    2) collect_new_runs() / 計算 dev_score
    3) promoted = after_baseline > before_baseline
    4) if promoted: no_improve_count = 0
       else: no_improve_count += 1
    5) 計算 dominant_failure + same_failure_count
    6) 選擇性 maybe_run_route()
    7) 檢查停止條件（依序）:
       a) no_improve_count >= no_improve_limit  → STOP
       b) same_failure_count >= same_failure_limit → STOP
       c) budget exceeded → STOP
```

### 2.2 Round 1 → 2 → 3 逐輪狀態變遷

**初始化** (line 236-243):
- `no_improve_count = 0`
- `same_failure_count = 0`
- `last_dominant_failure = ""`
- `best_score = baseline_dev_score()` → 88.03

**Round 1** (`run_opt_pass` returns False, no promotion):
- `promoted = False` → `no_improve_count = 1`
- `failure_code = dominant_failure(dev_summary)` → `""`（round_complete event 無 dominant_failure）
- `last_dominant_failure` stays `""`, `same_failure_count` stays `0`
- Stop check: `no_improve_count(1) < 3` → continue

**Round 2** (identical pattern):
- `promoted = False` → `no_improve_count = 2`
- `dominant_failure = ""`
- Stop check: `no_improve_count(2) < 3` → continue

**Round 3**:
- `promoted = False` → `no_improve_count = 3`
- `dev_summary` 有值，`dominant_failure` → `"F04"`
- `failure_code("F04") != last_dominant_failure("")` → `same_failure_count = 1`
- Stop check: `no_improve_count(3) >= no_improve_limit(3)` → **STOP**
- 停止原因選中 no-improve，**跳過 same-failure 檢查**

### 2.3 關鍵：為什麼 same_failure 沒先觸發

`dominant_failure` 在 round 1 與 2 都為空字串，因為根本没產生有意義的 dev run。
round 3 才有 dev_run，dominant_failure=F04 第一次出現。
此時 `same_failure_count=1`，遠低於 limit=3。

→ **`no_improve` 總是先打到上限，mask 掉 `same_failure`。**

---

## 3. 停擺根因分析

### Root Cause 1：`run_opt_pass()` 從未成功（systemic stagnation）

全部 6 個 runs（3+8+3+10+5+5 輪）中，`promoted` 始終為 False。
下列原因導致無任何候選晉升：

- **Dev 接受門檻過高**：`compare_runs.compare()` 要求全面改善，但單次小幅突變
  很難讓所有題型同時進步（`run_opt.py:764-767`）。
- **Governance 門檻**：`risk_perfect_rate < 100%` 或 `word_count_pass_rate < 85%`
  即直接否決（`run_opt.py:768-769`），即使有局部題型突破。
- **Holdout 門檻**：dev 通過後還需 holdout drop ≤ 1.0（`run_opt.py:829`）。

### Root Cause 2：停止條件階層設計問題

`infinite_evolve.py:352-358` 的三個停止條件用 `if/elif/elif` 階層判斷：
- `no_improve` 永遠優先觸發
- `same_failure` 和 `budget` 只在 no-improve 未達到時才會檢查
- 導致系統在 **3 輪無晉升** 就停，來不及讓 `same_failure` 累積到能觸發閾值

### Root Cause 3：`dominant_failure` 基準不一致

當 round 1-2 無 dev_run（dev_run=""）時，`dominant_failure()` 回傳空字串。
但 round 3 有了 dev_run 後才看到 F04。這造成 `same_failure_count` 的重置。
改善措施：缺少 dev_run 的 round 不該歸零 failure 追蹤，應沿用上輪紀錄或
視同 failure 狀態不變。

### Root Cause 4：champion / elite 局部保留未回饋到停止判斷

`save_elite_candidate()` 會保存局部題型突破到 champions/ 與 elite/，
**但這些成果完全不被停止條件納入考量**。
系統只看 `baseline.meta.json` 的 `dev_avg` 變化（`infinite_evolve.py:289`），
不看 champion pool 是否在累積突破。

---

## 4. 目前退出條件（`infinite_evolve.py:352-358`）

| 條件 | 變數 | 預設值 | 觸發方式 |
|------|------|--------|----------|
| 連續無晉升輪數 | `no_improve_count >= no_improve_limit` | 10 | `no_improve_count` 每輪未晉升 +1，晉升歸零 |
| 同失敗碼持續 | `same_failure_count >= same_failure_limit` | 5 | 該輪 dominant_failure 與上輪相同則 +1，不同歸零為 1 |
| 預算耗盡 | `estimated_cost_total >= budget_usd` | 0.0 (停用) | 累計估計 API 成本 |

缺陷：
1. `no_improve` 優先於 `same_failure`，低輪數下永遠先觸發
2. `same_failure` 計算受 `dev_run` 有無影響，無 dev_run 的 round 不計 failure
3. champion/elite 局部突破不影響停止決策

---

## 5. 修復設計建議

### P0（高優先 — 修復停止階層）：合併條件

將 `if/elif` 改為獨立檢查，或至少讓 `same_failure` 能與 `no_improve` 同時觸發：

```python
stop_reasons = []
if args.no_improve_limit and no_improve_count >= args.no_improve_limit:
    stop_reasons.append(f"連續 {no_improve_count} 輪未晉升")
if args.same_failure_limit and same_failure_count >= args.same_failure_limit:
    stop_reasons.append(f"主要失敗碼 {failure_code} 連續 {same_failure_count} 輪未解")
if args.budget_usd and estimated_cost_total >= args.budget_usd:
    stop_reasons.append(...)
if stop_reasons:
    stop_reason = "；".join(stop_reasons)
```

### P1（高優先）：failure 回溯填補

當 round 無 dev_run 時，應保留 `last_dominant_failure` 不變、`same_failure_count`
繼續累積，而非歸零：

```python
# 修改 infinite_evolve.py:303-308
if dev_run or latest_run:  # 只在有新 run 時才更新 failure
    failure_code = dominant_failure(dev_summary or latest_summary)
    if failure_code and failure_code == last_dominant_failure:
        same_failure_count += 1
    elif failure_code:
        same_failure_count = 1
        last_dominant_failure = failure_code
    # else: failure_code is empty → 保留 last_dominant_failure 不變
```

### P2（中優先）：champion/elite 局部突破納入停止加權

如果 champion pool 有新增（`save_elite_candidate` 回傳＞0），可視為
「部分進步」，減緩 `no_improve_count` 累積速度（例如：每保存 2 個 elite
抵消 1 個 no_improve）。

### P3（低優先）：調整 `no_improve_limit` 預設值

目前預設 10（`infinite_evolve.py:185`）。若 `same_failure_limit` 為 5，
且 `no_improve_limit` 建議 ≥ `same_failure_limit × 2`，讓 same-failure
有機會先觸發。但須注意本問題是階層設計導致，僅調值不夠。

---

## 6. 盤點流程圖摘要

```
infinite_evolve.py main()
  ├── parse_args() → no_improve_limit=3, same_failure_limit=3
  ├── preflight check
  ├── append_jsonl({"event":"start"})
  └── for round_no in 1..3:
        ├── run_opt_pass()
        │     ├── step 1: load baseline
        │     ├── step 2: LLM mutation → generates 3 candidates
        │     ├── step 3: Gatekeeper → filters
        │     ├── step 4: Smoke test → picks best
        │     ├── step 5: Dev test → compare vs baseline
        │     ├── step 6: compare → accept or reject
        │     │     ├── if NOT accept + type_breakthroughs → save_elite_candidate()
        │     │     └── if NOT accept + no breakthroughs → clean revert
        │     ├── step 7: Holdout (only if accept=True)
        │     └── return True/False
        ├── no_improve_count += (1 if not promoted else reset to 0)
        ├── dominant_failure update
        ├── maybe_run_route() (every route_every rounds)
        └── stop check: no_improve_count(3) >= no_improve_limit(3) → STOP
```

所有 3 輪 `run_opt_pass()` 回傳 False，原因：
- Round 1: Smoke 全滅（無 dev_run）
- Round 2: Smoke 全滅（無 dev_run）
- Round 3: Dev 有 run_dir 但 compare 不接受（diff=1.0, score=89.03 vs baseline 88.03 → 不通過）

---

## 7. 結論

Round 3 停止的真實根因是**停止條件階層設計缺陷**，而非 same_failure
機制有作用。`no_improve_limit=3` 在 low-round 設定下永遠優先於
`same_failure_limit` 觸發，且 round 1-2 無 dev_run 導致 failure 追蹤
無法累積。修復應先改條件判斷為獨立檢查，再補強 failure 追蹤的
round 回溯邏輯。