# Prompt AutoResearch v3 架構總覽

> 建議先閱讀 [架構總覽（新進版）](./architecture-overview.md)，再回來接上完整模組與資料流細節。  
> 如需文件入口總覽，請先看 [docs 文件索引](./README.md)。

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

## api / lib / scripts 責任邊界與資料流

這一段補足三個模組的「輸入→處理→輸出」與跨模組接點，避免把運行邏輯與對外服務邊界混淆。

### 一、`api/`：跨系統介面與回饋回路

| 檔案 | 輸入（Input） | 處理 | 輸出（Output） |
|---|---|---|---|
| `api/server.py` | `prompts/current.md`、`prompts/baseline.md`、`prompts/baseline.meta.json`、`prompts/champions/*.md`、`prompts/routes/type_champions.json`、`feedback.jsonl`、`optimization_log.jsonl`、`runs/latest/*` | 依照路由做只讀查詢或 `POST /api/feedback` 寫入；每個路由將欄位轉為可供外部消費的 JSON 結構 | 對外 REST 回應：prompt hash/長度、`route`、champion 清單、feedback 摘要、health、回饋建立結果；不直接觸發 `run_opt.py` |
| `api/feedback.py` | `feedback.jsonl`、`prompts/baseline.meta.json` | 依 `prompt_hash` 匯總 `scores`，計算平均分、弱點維度、弱點題型，輸出優化建議草案 | `summary`、`weak_areas`、`hints` 三類結果供 `api/server.py` 的 GET 回應使用 |
| `api/continuous_optimizer.py` | `feedback.jsonl`、lib 共用函式、外部可用 CLI（`run_opt.py`） | 檢查回饋數量門檻；可選擇只分析不優化；有建議時組裝參數後啟動 `run_opt.py` | `optimization_log.jsonl` 中寫入 `analysis`/`optimization`/`optimization_error`，並在命令列輸出輪次結果 |

### 二、`lib/`：共用核心工具（所有主流程共同依賴）

| 檔案 | 輸入（Input） | 處理 | 輸出（Output） | 注意事項 |
|---|---|---|---|---|
| `lib/config.py` | `config.json`、環境變數（`AUTORESEARCH_*`） | 先載入預設值、再覆寫 config.json、最後套用 env 轉型規則 | 統一的設定字典；`get()` / `get_section()` / `get_all()` | 不要直接改 `config.json` 作為 run 時策略，除非你要改治理邊界 |
| `lib/api.py` | system prompt、user prompt、`lib.config` 內的 `api.*` 參數、`MINIMAX_API_KEY` | 建立 HTTP 請求；依序受限流（semaphore）與最小間隔，最多重試 `retry` 次，超時 `timeout` 後回傳錯誤 | LLM 回應文字；上層可直接當作答案或 rubric 驗證輸入 | 失敗會直接拋例外由上層處理，適合放在 `run_opt.py` / `scripts/evaluate.py` 的 call site |
| `lib/io.py` | 路徑、JSON/JSONL payload、字串內容 | 提供 `load_file`、`load_json`、`read_jsonl`、`write_file`、`write_json`、`append_jsonl`、`normalize_path` | 統一檔案 I/O 行為，包含不存在時預設值與目錄自動建立 | 這是**所有模組共用**的基礎 I/O 抽象，不保證 schema 驗證 |
| `lib/metrics.py` | 事件欄位（round / event / error / score...） | 將事件拼成結構化 dict 並追加到 `metrics.jsonl` | `metrics.jsonl` 的時間戳事件列：`record_round`、`record_event` | `run_opt.py` 是主要寫入者 |

### 三、`scripts/`：固定評估與治理腳本（不改核心評分器）

#### 核心 Pipeline 腳本

| 檔案 | 輸入（Input） | 處理 | 輸出（Output） |
|---|---|---|---|
| `scripts/gatekeeper.py` | `prompts/*.md`（主要為 `current.md`） | 執行硬規則與語意驗證，回傳 pass/fail 與 violations | 退出碼（0/1）與可選 JSON 片段 |
| `scripts/evaluate.py` | `prompt_file`、`question_file`、`rubrics/*`、cache、`parallel` 參數 | 並行呼叫 LLM 審題、彙總題目分數/缺陷，建立 `summary` 統計 | `runs/<timestamp>/details.jsonl`、`runs/<timestamp>/summary.json`、`runs/<timestamp>/summary.md`，並同步複製到 `runs/latest/` |
| `scripts/evaluate_routed.py` | `route.json`、題庫、rubrics、`evaluate` 模組 | 按題型選擇 prompt，逐題評分 | 路由專用的 `details/summary`（走 `evaluate` 的輸出格式）與路由使用率報告 |
| `scripts/compare_runs.py` | 新 run 的 `details.jsonl`、基準 run 的 `details.jsonl`、`lib.config` 門檻 | 逐維度比較分數、缺陷與風險，回填接受條件 | CLI 報表列印 + 回傳 `passed/avg_new/score_diff` |

#### 輔助治理/回溯腳本

| 檔案 | 輸入（Input） | 處理 | 輸出（Output） |
|---|---|---|---|
| `scripts/preflight.py` | env、題庫、`prompts/baseline.md`、`prompts/current.md`、`prompts/baseline.meta.json` | 執行啟動前健康檢查，區分 `error/warn` | JSON 結果（或 CLI 文字）供 CI/手動判斷是否可跑 |
| `scripts/analyze_runs.py` | `runs/*/summary.json`、`runs/*/details.jsonl` | 依時間窗彙整失敗碼與題型均分趨勢 | 控制台報告/JSON |
| `scripts/leaderboard.py` | `runs/*/summary.json` | 根據 dev 資料整理分數/風險排行榜 | `limit` 限定的排行榜輸出 |
| `scripts/experiment_report.py` | `runs/*`、`prompts/baseline.meta.json`、`decision.md` | 匯總決策歷史、失敗碼熱點、題型弱勢 | Markdown 報告 `output/experiment_report.md`（預設列印） |
| `scripts/backfill_candidate_scorecards.py` | `prompts/candidates/*.md` 與 `.meta.*` | 補齊候選 scorecard JSON | `*.scorecard.json`（預設新建、`--force` 可覆蓋） |
| `scripts/generate_questions.py` | 內建模板與題目 schema | 生成 `questions/*.jsonl`（包含 dev/holdout/final） | 啟動題庫檔 |

### 四、跨模組資料流（端到端）

```text
prompts / questions / rubrics / config.json
   |
   ├─ run_opt.py / auto_evolve.py / route_loop.py
   │      ├─ lib.config 取得閾值與並行設定
   │      ├─ lib.api 呼叫 LLM 生成候選
   │      ├─ scripts.gatekeeper 做硬性規則
   │      ├─ scripts.evaluate 與 scripts.evaluate_routed 做 smoke/dev/holdout
   │      ├─ scripts.compare_runs 進行接受判斷
   │      └─ scripts.* 寫入 runs/*、results.tsv、prompts/baseline.meta.json（必要時）
   │
   ├─ run_app.py（本機 UI）
   │      ├─ 讀 runs/latest、questions、prompts、output 快照
   │      └─ 回傳前端資料（architecture/experiment-report/questions/summary）
   │
   ├─ api/server.py（外部服務）
   │      ├─ 提供 prompts/champions/routes 與 health
   │      ├─ 提供 feedback 入口 `/api/feedback`
   │      └─ 透過 api.feedback 回傳 summary/weak-areas/hints
   │
   └─ api.continuous_optimizer
          ├─ 讀 feedback.jsonl
          ├─ 分析弱點並決定方向
          └─ 觸發 run_opt.py（二次優化）
```

`run_app.py` 與 `api/server.py` 都可讀到同一批基礎資產，但責任邊界如下：

- `run_app.py`：本機 UI + 本地流程啟動器；只服務 `127.0.0.1` 前端控制需求，不承擔跨系統 API 的對外契約。
- `api/server.py`：外部整合點；關注 prompt/token、feedback 與優化狀態輸出，不負責啟動演化流程。

