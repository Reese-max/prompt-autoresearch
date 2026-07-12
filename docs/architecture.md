# Prompt AutoResearch v3 架構總覽

## 目標

Prompt AutoResearch 是一個本機優先的提示詞演化實驗室，用來優化 `prompts/current.md` 的臺灣國考申論題提示詞。系統的正確性來自固定題庫、固定 rubric、固定評估腳本與可回溯的 `runs/*/decision.md`，而不是修改評分器或題庫來換分數。

## 模組地圖

| 模組 | 主要檔案 | 職責 |
|---|---|---|
| Frontend | `index.html`、`app.js`、`styles.css` | 提供工作區、三層優化器、題庫、rubric、A/B arena、設定與架構總覽 UI。 |
| Local UI Server | `run_app.py` | 服務靜態前端、提供本機 JSON API、讀取題庫與 runs、啟動演化/驗收 subprocess、限制 CORS proxy 目的地。 |
| Optimization Engine | `run_opt.py`、`auto_evolve.py`、`route_loop.py`、`route_evolve.py` | 產生候選、跑多階段評估、比較 baseline、處理 route subset 與 champion 決策。 |
| Evaluation Scripts | `scripts/gatekeeper.py`、`scripts/evaluate.py`、`scripts/compare_runs.py`、`scripts/evaluate_routed.py` | 固定評估資產的一部分，負責硬性規則、題庫評分、回歸比較與 routed prompt 評估。 |
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
- `/api/questions/<group>`：讀取 `questions/smoke.jsonl`、`dev.jsonl`、`holdout.jsonl`、`final.jsonl`。
- `/api/latest-summary`、`/api/latest-decision`：讀取 `runs/latest/` 的審計輸出。
- `/api/experiment-report`：即時計算歷史 runs 的實驗治理報告，彙整字數合格率、風險滿分率、F-code 與題型弱點，不寫入檔案。
- `/api/results`：讀取 `results.tsv`。
- `/api/baseline-meta`：讀取 `prompts/baseline.meta.json`。

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
