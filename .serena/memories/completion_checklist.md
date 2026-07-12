# Completion checklist

完成前至少執行：

1. `python -m unittest tests.test_architecture_surface -v`
2. `python -m py_compile run_app.py`
3. `node --check app.js`
4. 若有 API 變更，使用 import 後的 ephemeral server 驗證對應 endpoint，避免被既有 8000 process 干擾。

如果變更涉及提示詞演化或評估流程，再依 scope 加跑 `scripts/gatekeeper.py`、`scripts/evaluate.py` smoke/dev/holdout。回報時明確列出有無改到固定評估資產。