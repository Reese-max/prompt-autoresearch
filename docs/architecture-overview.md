# 專案架構總覽（新進開發者版）

> 新進先看這篇；若要接著看完整 v3 架構與 API 詳細對位，請接著閱讀 [architecture.md](./architecture.md)。  
> 也可先回到 [docs 文件索引](./README.md) 了解全部文件入口。

## 一句話版

Prompt AutoResearch（本 repo）是一個本機優先的提示詞演化引擎：
使用固定題庫與評估規則，反覆產生提示詞候選、評估、比對，最後把可接受結果寫入 `prompts/current.md`。

## 專案目錄樹（重點）

```text
autodev-ng/prompt-autoresearch
├─ app.js
├─ run_app.py
├─ index.html
├─ styles.css
├─ run.sh / run.bat
├─ config.yaml / config.json
├─ auto_evolve.py / infinite_evolve.py
├─ run_opt.py / route_loop.py / route_evolve.py / route_loop_log.jsonl
├─ scripts/                 # 本地評估與治理腳本
│  ├─ gatekeeper.py
│  ├─ evaluate.py
│  ├─ evaluate_routed.py
│  ├─ compare_runs.py
│  ├─ experiment_report.py
│  ├─ analyze_runs.py
│  ├─ preflight.py
│  ├─ leaderboard.py
│  ├─ generate_questions.py
│  ├─ backfill_candidate_scorecards.py
│  └─ ...（更多輔助腳本）
├─ lib/                     # 共用核心工具
│  ├─ api.py
│  ├─ config.py
│  ├─ io.py
│  └─ metrics.py
├─ api/                     # 對外服務（與前端 API 分離）
│  ├─ server.py
│  ├─ feedback.py
│  └─ continuous_optimizer.py
├─ prompts/                 # 提示詞儲存區
│  ├─ baseline.md
│  ├─ current.md
│  ├─ candidates/
│  ├─ champions/
│  └─ routes/
├─ questions/               # 題庫
│  ├─ smoke.jsonl
│  ├─ dev.jsonl
│  ├─ holdout.jsonl
│  └─ final.jsonl
├─ rubrics/                 # 評分規格與規則
├─ runs/                    # 每次演化/驗證紀錄
├─ output/                  # 輸出快照（中介結果）
├─ docs/                    # 文件
└─ tests/                   # 測試
```

## 各模組角色（先看這段再看細節）

### 1) 介面層
- **`index.html` / `app.js` / `styles.css`**：前端工作台（手動編輯、演化按鈕、A/B 對照、架構檢視）
- **`run_app.py`**：本機 UI Server，提供本地 `/api/*`，負責把檔案、執行結果、流程狀態對前端可視化

### 2) 核心演化層
- **`run_opt.py`**：核心優化驅動入口，管理候選產生與評估流程
- **`auto_evolve.py` / `infinite_evolve.py`**：自動化演化工作流
- **`route_loop.py` / `route_evolve.py`**：路由（題型分流）優化、subset 搜尋、最佳路徑判定

### 3) 評估與治理層
- **`scripts/`**：固定評估邏輯與治理腳本，不應靠改這裡規則來「刷分」
  - `gatekeeper.py`：最小門檻校驗（長度、格式、危險字元等）
  - `evaluate.py` / `evaluate_routed.py`：題庫推進式打分
  - `compare_runs.py`：不同 runs 差異對比
  - `experiment_report.py` / `analyze_runs.py`：彙整歷史表現與異常

### 4) 共用函式庫
- **`lib/api.py`**：LLM 呼叫封裝、重試與逾時邏輯
- **`lib/config.py`**：設定載入與環境變數覆蓋規則
- **`lib/io.py`**：檔案/結果 I/O
- **`lib/metrics.py`**：計分、指標、可視化輸入資料

### 5) API 服務層
- **`api/server.py`**：外部 API 入口（本地 UI 以外的介面）
- **`api/feedback.py`**：feedback 收集與統計聚合
- **`api/continuous_optimizer.py`**：排程/連續演化（條件與狀態更新）

### 6) 資料層與資產
- **`prompts/*`**：所有提示詞與衍生結果
- **`questions/*`**：SMOKE/DEV/HOLDOUT/FINAL 題組
- **`rubrics/*`**：評分規則（固定資產）
- **`runs/*`**：每輪決策證據（決策摘要、分數、metadata）
- **`results.tsv` / `metrics.jsonl` / `evolution_log.jsonl`**：全域執行紀錄

## 新進開發者建議閱讀順序

> 目標：先建立系統心智模型，再看控制流程與資料邊界。

1. **先看這篇**：`docs/architecture-overview.md`（你現在閱讀的文件）
2. **理解入口**：
   - `run_app.py`（本機 UI）
   - `app.js` + `index.html`（操作入口）
3. **認識資料邊界**：
   - `prompts/`、`questions/`、`rubrics/`、`runs/`
   - 先看 `prompts/current.md`、`prompts/baseline.md`、`rubrics/*`
4. **看演化主流程**：
   - `run_opt.py`
   - `scripts/gatekeeper.py`
   - `scripts/evaluate.py`
5. **看路由/題型優化**：
   - `route_loop.py`
   - `route_evolve.py`
   - `prompts/routes/`
6. **看 API 與回饋**：
   - `api/server.py`
   - `api/feedback.py`
7. **看治理與回溯**：
   - `runs/*` 日誌
   - `scripts/experiment_report.py`
   - `scripts/analyze_runs.py`

## 新手常見踩雷（快速避坑）

- 不要把題庫、rubric、程式核心評估規則當成可為了過分數而隨意改動。
- 任何演化決策都應能追溯到 `runs/` 的紀錄與 `latest-*` 證據。
- 若要觀察系統健康，先看 `results.tsv`、`metrics.jsonl`、`evolution_log.jsonl`，再看 UI 狀態。
- `routes` 與 `champions` 的變更，務必對照路徑與 decision 檔判斷是否真的被啟用。
