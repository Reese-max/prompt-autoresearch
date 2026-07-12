# Suggested commands

在 Windows PowerShell 下工作：

- 進入專案：`Set-Location -LiteralPath 'D:\Users\Administrator\Desktop\Prompt AutoResearch'`
- 啟動本機 UI：`python run_app.py --open`
- 跑架構/前端合約測試：`python -m unittest tests.test_architecture_surface -v`
- Python 語法檢查：`python -m py_compile run_app.py`
- JS 語法檢查：`node --check app.js`
- Gatekeeper：`python scripts\gatekeeper.py prompts\current.md`
- Smoke 評估：`python scripts\evaluate.py prompts\current.md questions\smoke.jsonl --parallel 6`
- Dev 評估：`python scripts\evaluate.py prompts\current.md questions\dev.jsonl --parallel 24`
- Holdout 評估：`python scripts\evaluate.py prompts\current.md questions\holdout.jsonl --parallel 24`

注意：目前資料夾沒有 `.git`，`git status` 會回 `fatal: not a git repository`。Port 8000 可能已有其他 Python process 佔用；若要測 API，可 import `run_app.LocalProxyHandler` 後綁定 ephemeral port。