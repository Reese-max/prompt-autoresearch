# Branch coverage 驗收報告（2026-07-18）

## 執行指令

```powershell
python -m pytest tests -q -o addopts= --cov=lib --cov=api --cov=scripts --cov-branch --cov-report=term-missing --cov-report=xml --cov-report=html
```

此指令執行完整 `tests/`，未使用 `--deselect`、`-k` 或其他篩選選項。

## 結果

```text
Name                                       Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------------------------
TOTAL                                       1693      0    574      0   100%
455 passed in 20.42s
```

- Branch Missing：`0`（574 個 branch 全數覆蓋）
- BrPart：`0`
- 總 branch coverage：`100%`
- deselected：`0`（`455 tests collected` 與 `455 passed` 相等）

`coverage.xml` 亦記錄 `branches-valid="574"`、`branches-covered="574"`、`branch-rate="1"`；HTML 報表位於 `htmlcov/index.html`。
