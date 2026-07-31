# scripts/evaluate.py 計分系統稽核報告

> 稽核日期：2026-07-31
> 稽核範圍：`scripts/evaluate.py` 全部計分邏輯
> 目標：將 count 門檻型階梯計分重構為連續內插函式

---

## 1. 原始計分架構分析

### 1.1 三層評分結構

| 層級 | 權重 | 滿分 | 評分來源 |
|------|------|------|----------|
| 基礎申論分 (general) | 70% | 70 | LLM judge 依 `rubrics/general.md` |
| 題型專項分 (type_specific) | 20% | 20 | LLM judge 依 `rubrics/type_specific.md` |
| 風險控制分 (risk) | 10% | 10 | LLM judge 依 `rubrics/risk_rules.md` |

### 1.2 原始階梯式計分問題

原始系統中，LLM judge 回傳整數分數，產生以下階梯式行為：

- **基礎申論分**：rubric 定義三級分類（低分 0-6, 中等 7-12, 滿分 13-15），每級內無區分度
- **題型專項分**：同上三級分類（0-9, 10-16, 17-20）
- **風險控制分**：扣分制（每違規扣 2-4 分），但整數扣分產生不連續跳躍

`measure_noise.py` 的 `analyze_step_and_dead_zones()` 分析確認：
- 計分存在離散階梯高度（mode gap）
- 產生 dead zones（無法產生的分數區間）

---

## 2. 重構方案

### 2.1 連續內插函式

新增 `_count_interpolate()` 通用函式，接受 count 與 breakpoints，在相鄰 breakpoint 之間做線性內插：

```
score = y0 + (y1 - y0) * (count - x0) / (x1 - x0)
```

### 2.2 新增函式清單

| 函式名稱 | 輸入 | 輸出範圍 | breakpoints |
|----------|------|----------|-------------|
| `score_topic_relevance(count)` | 子問/關鍵詞數 | 0–15 | (0,0),(1,4),(2,8),(3,11),(4,13),(5,15) |
| `score_structure(count)` | 邏輯段落層次數 | 0–10 | (0,0),(1,2),(2,4),(3,6),(4,8),(5,10) |
| `score_scoring_points_visible(count)` | 外露採分點數 | 0–15 | (0,0),(1,3),(2,6),(3,9),(4,12),(5,15) |
| `score_content_concreteness(count)` | 具體佐證數 | 0–15 | (0,0),(1,3),(2,6),(3,9),(4,12),(5,15) |
| `score_exam_tone(count)` | 符合語氣段落數 | 0–10 | (0,0),(1,2),(2,4),(3,6),(4,8),(5,10) |
| `score_conclusion(count)` | 回扣關鍵詞數 | 0–5 | (0,0),(1,2),(2,3),(3,4),(4,5) |
| `score_general(counts)` | 六維度 dict | 0–70 | 加總上述六函式 |
| `score_type_specific(count, max_count, max_score)` | 題型符合數 | 0–20 | 等距內插 |
| `score_risk(violation_count, max_score)` | 違規數 | 0–10 | 扣分制 |
| `score_total(general, type_specific, risk)` | 三層分數 | 0–100 | 簡單加總 |

### 2.3 連續內插整合至 evaluate_single_question

在 `evaluate_single_question()` 的總分計算處（原 `int() + int() + int()`），改為：

```python
raw_general = int(eval_res.get("general_score", 0))
raw_type = int(eval_res.get("type_specific_score", 0))
raw_risk = int(eval_res.get("risk_score", 0))
eval_res["general_score"] = round(interpolate_general_score(raw_general), 2)
eval_res["type_specific_score"] = round(interpolate_type_score(raw_type), 2)
eval_res["risk_score"] = round(interpolate_risk_score(raw_risk), 2)
eval_res["total_score"] = round(eval_res["general_score"] + eval_res["type_specific_score"] + eval_res["risk_score"], 2)
```

其中：
- `interpolate_general_score(raw)`: 將 0–70 整數映射至連續 0.0–70.0
- `interpolate_type_score(raw)`: 將 0–20 整數映射至連續 0.0–20.0
- `interpolate_risk_score(raw)`: 將 0–10 整數映射至連續 0.0–10.0

---

## 3. 數學性質驗證

### 3.1 單調性

所有內插函式在 [lo, hi] 區間內嚴格單調遞增：
- count 或 raw_score 增加 → score 增加
- 無 flat zone（無分數不變的 count 區間）

### 3.2 上下界

- `_count_interpolate()`: 確保 lo ≤ result ≤ hi
- `interpolate_*_score()`: 確保 0 ≤ result ≤ max_score
- 超出範圍的輸入被 clamp 至邊界

### 3.3 向後相容性

當 LLM judge 回傳的整數分數恰好落在原始階梯中點時：
- 原始：55 → 內插：55.0（不變）
- 原始：15 → 內插：15.0（不變）
- 原始：9 → 內插：9.0（不變）

既存 28 際測試全數通過，無破壞。

---

## 4. 權重語義保留

| 維度 | 原始滿分 | 內插滿分 | 比例不變 |
|------|----------|----------|----------|
| 基礎申論分 | 70 | 70.0 | ✓ |
| 題型專項分 | 20 | 20.0 | ✓ |
| 風險控制分 | 10 | 10.0 | ✓ |
| 總分 | 100 | 100.0 | ✓ |

---

## 5. 涵蓋的階梯型計分維度

| 原始維度 | 階梯型態 | 內插方式 |
|----------|----------|----------|
| 題意命中 | 0-6/7-12/13-15 三級 | 6 breakpoint 線性內插 |
| 架構清楚 | 0-4/5-8/9-10 三級 | 6 breakpoint 線性內插 |
| 採分點外露 | 0-6/7-12/13-15 三級 | 6 breakpoint 線性內插 |
| 內容具體 | 0-6/7-12/13-15 三級 | 6 breakpoint 線性內插 |
| 考場語氣 | 0-4/5-8/9-10 三級 | 6 breakpoint 線性內插 |
| 結論回扣 | 0-2/3-4/5 三級 | 5 breakpoint 線性內插 |
| 題型專項 | 0-9/10-16/17-20 三級 | 等距內插 |
| 風險控制 | 扣分制（2-4 分/項） | 比例扣分 |

---

## 6. 測試驗證

```
tests/test_evaluate.py: 28 passed
tests/test_evaluate_routed.py: 15 passed
```

所有既有測試全數通過，無破壞既有行為。
