# Prompt AutoResearch overview

本專案是本機優先的臺灣國考申論題提示詞自動演化實驗室。前端由 `index.html`、`app.js`、`styles.css` 組成；預設本機伺服器是 `run_app.py`，會服務靜態檔、讀取本機題庫/runs/prompts、啟動演化與驗收 subprocess，並提供受 allowlist 限制的 CORS proxy。

核心資料：`prompts/current.md`、`prompts/baseline.md`、`prompts/candidates/`、`prompts/champions/`、`questions/*.jsonl`、`rubrics/`、`runs/`、`results.tsv`。

核心引擎：`run_opt.py`、`auto_evolve.py`、`infinite_evolve.py`、`route_loop.py`、`route_evolve.py`。固定評估腳本在 `scripts/`，包含 `gatekeeper.py`、`evaluate.py`、`compare_runs.py`、`evaluate_routed.py`。