# Style and conventions

- 回覆與 UI 文案偏繁體中文、臺灣用語。
- Python 使用 stdlib 為主；目前 `requirements.txt` 宣告仍是 stdlib only。
- Windows entrypoint 應保留 UTF-8 編碼宣告與 `ensure_ascii=False` JSON 輸出。
- Subprocess 啟動應優先用 `sys.executable`，避免 Windows Python 路徑混亂。
- 前端是單檔大型原生 JS，無 bundler；以既有 `AppState`、`elements`、`hydrateFromLocalServer()`、`render*()` 函式風格延伸。
- 前端 CSS 使用既有 dark/glass design tokens，例如 `--cyan`、`--purple`、`--border-radius-md`、`--font-code`。
- 不要為了候選提示詞分數修改 `questions/`、`rubrics/`、`scripts/` 或歷史 `runs/`。