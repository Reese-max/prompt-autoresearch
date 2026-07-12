# Prompt AutoResearch v3 架構總覽

## 目標

Prompt AutoResearch 是一個本機優先的提示詞演化實驗室，用來優化 `prompts/current.md` 的臺灣國考申論題提示詞。系統的正確性來自固定題庫、固定 rubric、固定評估腳本與可回溯的 `runs/*/decision.md`，而不是修改評分器或題庫來換分數。

## 模組地圖

| 模組 | 主要檔案 | 職責 |
|---|---|---|
| Frontend | `index.html`、`app.js`、`styles.css` | 提供工作區、三層優化器、題庫、rubric、A/B arena、設定與架構總覽 UI。 |
| Local UI Server | `run_app.py` | 服務靜態前端、提供本機 JSON API、讀取題庫與 runs、啟動演化/驗收 subprocess、限制 CORS proxy 目的地。 |
| External API Service | `api/server.py`、`api/feedback.py` | 對外提供提示詞與回饋服務，包含 current/baseline/champion 讀取、路由查詢、回饋送入與回饋彙整。 |
| Optimization Engine | `run_opt.py`、`auto_evolve.py`、`route_loop.py`、`route_evolve.py` | 產生候選、跑多階段評估、比較 baseline、處理 route subset 與 champion 決策。 |
| Evaluation Scripts | `scripts/gatekeeper.py`、`scripts/evaluate.py`、`scripts/compare_runs.py`、`scripts/evaluate_routed.py` | 固定評估資產的一部分，負責硬性規則、題庫評分、回歸比較與 routed prompt 評估。 |
| Shared Library | `lib/api.py`、`lib/io.py`、`lib/config.py`、`lib/metrics.py` | 提供 LLM 呼叫封裝、I/O 工具、設定載入與指標紀錄，給 `scripts`、`api`、`optimization` 共用。 |
| Prompt Store | `prompts/` | 保存 `current.md`、`baseline.md`、候選、champions、routes 與 metadata。 |
| Champion Store | `prompts/champions/`、`prompts/routes/` | 保存題型 champion prompt、active type route、type champion decision 與 route-loop promotion 決策狀態。 |
| Historical Runs | `runs/` | 保存每輪 `details.jsonl`、`summary.md`、`decision.md`、route source 與最新結果 symlink/copy。 |

## 前端資訊架構

v3 前端分頁順序：

1. **工作區 & 編輯器**：編修 `current.md`，即時檢查長度、persona、反問、造假風險。
2. **三層閉環優化器**：控制 smoke/dev/holdout 演化流程與本機 subprocess。
3. **架構總覽**：讀取 `/api/architecture`，呈現目前模組、資料集、管線、路由與關鍵檔案狀態。
   - 同頁會讀取 `/api/experiment-report` 顯示實驗治理紅燈，包含字數合格率、風險滿分率、F-code 與題型弱點。
4. **分組國考題庫**：瀏覽 smoke/dev/holdout/final 題庫。
5. **評分規準 & 失敗碼**：整理 triple rubric 與 F-code taxonomy。
6. **A/B 評測競技場**：比較 baseline 與演化後提示詞。
7. **API 金鑰 & 設定**：管理 provider/model/temperature 與本機儲存金鑰。

## 本機 API

`run_app.py` 是前端預設入口。主要 GET 路由：

- `/api/architecture`：回傳 v3 架構快照，供架構總覽分頁渲染；其中 `champions` 會列出 `prompts/champions/*.md` 與對應 metadata，`route_status` 會整理 active route、type champion route decision、route loop decision 與目前 best route candidate。
- `/api/get-current-prompt`：讀取 `prompts/current.md`。
- `/api/get-baseline-prompt`：讀取 `prompts/baseline.md`。
- `/api/baseline-meta`：讀取 `prompts/baseline.meta.json`。
- `/api/questions/<group>`：讀取 `questions/smoke.jsonl`、`dev.jsonl`、`holdout.jsonl`、`final.jsonl`。
- `/api/latest-summary`、`/api/latest-decision`：讀取 `runs/latest/` 的審計輸出。
- `/api/experiment-report`：即時計算歷史 runs 的實驗治理報告，彙整字數合格率、風險滿分率、F-code 與題型弱點，不寫入檔案。
- `/api/results`：讀取 `results.tsv`。
- `/api/evolution-log`：列出 `optimization_log.jsonl`。

此外，`/api/architecture`、`/api/get-current-prompt`、`/api/get-baseline-prompt`、`/api/questions/<group>`、`/api/latest-summary`、`/api/latest-decision`、`/api/experiment-report` 等屬於**本機 UI 入口**（run_app）。

`api/server.py` 對外服務則為獨立入口（預設埠 `5001`）：

- `GET /api/current-prompt`：回傳 current 提示詞 hash 與長度。
- `GET /api/prompt-meta`：回傳 `prompts/baseline.meta.json`。
- `GET /api/baseline`：回傳 baseline 提示詞 hash 與長度。
- `GET /api/route`：回傳 `prompts/routes/type_champions.json`。
- `GET /api/champions`：列出已上線 champion（含 meta）。
- `GET /api/champion/<type>`：回傳指定題型 champion。
- `GET /api/feedback/summary`：回傳 feedback 匯總。
- `GET /api/feedback/weak-areas`：回傳弱點分析。
- `GET /api/feedback/hints`：回傳優化建議。
- `GET /api/optimizer/status`：回傳最近優化紀錄與狀態（含 `optimization_log.jsonl`）。
- `GET /api/health`：回傳健康檢查資訊。
- `POST /api/feedback`：寫入 `feedback.jsonl`。

主要 POST 路由：

- `/api/run-evolution`：以目前 Python 解譯器啟動 `auto_evolve.py`。
- `/api/run-final`：啟動 final 題庫驗收。
- `/api/proxy`：只允許轉發至 allowlist 內的 LLM API host。

## 評估管線

1. **gatekeeper**：`python scripts/gatekeeper.py prompts/current.md`
2. **smoke**：`python scripts/evaluate.py prompts/current.md questions/smoke.jsonl --parallel 6`
3. **dev**：`python scripts/evaluate.py prompts/current.md questions/dev.jsonl --parallel 24`
4. **holdout**：`python scripts/evaluate.py prompts/current.md questions/holdout.jsonl --parallel 24`

只有 dev 提升、題型不崩、風險分數合格且 holdout 不退步時，才應推進 baseline 或 route 決策。

## Champion 與 Route 狀態

架構頁現在會把 champion 與 route promotion 狀態整合到同一張快照：

- `champions.count`：目前 `prompts/champions/` 內可用題型 champion 數。
- `champions.items[]`：每個 champion 的題型、slug、prompt path、metadata path、dev/holdout score diff、risk rate、來源 candidate 與 decision。
- `route_status.active`：讀取 `prompts/routes/type_champions.json`，顯示 default prompt 與 `by_type` 分流表。
- `route_status.type_champion_decision`：讀取 `prompts/routes/type_champions.decision.json`，顯示 type champion route 是否被接受與 dev/holdout diff。
- `route_status.loop_decision`：讀取 `prompts/routes/route_loop.decision.json`，顯示 route subset search 的 candidate count、accepted count、總決策與 best route candidate。

目前這些資訊是狀態展示，不會直接修改 prompt 或 route；真正 promotion 仍須通過既有 gatekeeper、dev、holdout 與 decision 規則。

## 固定評估資產與寫入邊界

固定評估資產包含：

- `questions/`
- `rubrics/`
- `scripts/`
- `program.md`
- `results.tsv`
- 歷史 `runs/`

演化 agent 原則上只應修改 `prompts/current.md`，或產生 `prompts/candidates/*` 作為候選。前端/API 維護可以修改 `index.html`、`app.js`、`styles.css`、`run_app.py` 與測試，但不得把 evaluator、題庫或 rubric 改成配合候選提示詞。

## docs 文件缺口盤點（依目前 scan）

目前 `docs/` 內可用文件僅有：

- `architecture.md`（本文件）
- `codex-round-1.md`～`codex-round-5.md`（僅為回合標題，無架構職責內容）

### 已確認的缺口

1. **`api/` 套件責任未文件化**
   - `api/server.py`（外部 REST API）與 `run_app.py`（本機 UI 服務）的責任邊界未在文件中明確區隔。
   - `api/feedback.py` 的回饋分析流程（`feedback.jsonl` → summary/weak-areas/hints）未有獨立頁面。
   - `api/continuous_optimizer.py` 的連續優化迴圈啟發條件、日誌與錯誤模式未被覆蓋。

2. **`lib/` 套件職責未細拆**
   - `lib/api.py` 的重試、逾時、速率限制行為目前只在腳本層面零散可見。
   - `lib/config.py` 的預設值與環境變數覆蓋規則沒有文件。
   - `lib/io.py` / `lib/metrics.py` 的輸入輸出格式、欄位意義、錯誤回退機制無單頁說明。

3. **`scripts/` 只列舉部分腳本，缺少全域職責圖**
   - 除 `gatekeeper.py`、`evaluate.py`、`evaluate_routed.py` 以外，`analyze_runs.py`、`leaderboard.py`、`compare_runs.py`、`experiment_report.py`、`preflight.py`、`generate_questions.py`、`backfill_candidate_scorecards.py` 等未被逐一描述。
   - 缺少「輸入／輸出檔名」、「關鍵參數」與「誰在什麼流程呼叫」的對照表。

### 建議新增／補強頁面

| 類別 | 建議動作 | 優先順序 |
|---|---|---|
| `api/` | 新增 `docs/api.md`，補齊外部 API 與回饋分析責任、錯誤回傳、資料檔位。 | 高 |
| `lib/` | 新增 `docs/lib.md`，補齊設定載入鏈、`lib/api.py` 呼叫規範、`lib/metrics.py` 事件欄位。 | 高 |
| `scripts/` | 新增 `docs/scripts.md`，補齊腳本責任、輸入輸出與 CLI 參數對照。 | 高 |
| `architecture.md` | 補上 `api/`、`lib/`、`scripts/` 的責任邊界與相依關係區塊（`run_app` vs `api/server`）。 | 中 |
