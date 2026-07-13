# scripts/ + api/ 覆蓋率驗收紀錄（2026-07-13）

## 驗收指令

CI（`.github/workflows/ci.yml`）明確執行：

```
pytest tests -o addopts= --cov=scripts --cov=api --cov-report=term-missing --cov-report=xml --cov-report=html --cov-fail-under=80
```

說明：`pytest.ini` 的 `addopts` 內含 `--cov=lib`，若不覆蓋，`lib/` 會被混入
TOTAL 拉高總覆蓋率（混算）。以 `-o addopts=` 清空後再明確指定
`--cov=scripts --cov=api`，閘門只以 scripts/ 與 api/ 的覆蓋率計算。

## 本機實跑結果（產生本次提交之 coverage.xml 與 htmlcov/）

- 平台：win32, Python 3.11.9
- 測試：`284 passed in 9.15s`
- 覆蓋率（僅 scripts + api）：`TOTAL 1469 stmts, 10 miss, 99%`
- 閘門：`Required test coverage of 80% reached. Total coverage: 99.32%`

各檔覆蓋率（term-missing 摘要）：

| 檔案 | Stmts | Miss | Cover |
|---|---|---|---|
| api/continuous_optimizer.py | 82 | 0 | 100% |
| api/feedback.py | 85 | 3 | 96% |
| api/server.py | 219 | 1 | 99% |
| scripts/analyze_runs.py | 92 | 1 | 99% |
| scripts/backfill_candidate_scorecards.py | 66 | 1 | 98% |
| scripts/compare_runs.py | 159 | 0 | 100% |
| scripts/evaluate.py | 250 | 1 | 99% |
| scripts/evaluate_routed.py | 110 | 0 | 100% |
| scripts/experiment_report.py | 167 | 1 | 99% |
| scripts/gatekeeper.py | 82 | 0 | 100% |
| scripts/generate_questions.py | 21 | 1 | 95% |
| scripts/leaderboard.py | 43 | 1 | 98% |
| scripts/preflight.py | 93 | 0 | 100% |

## 佐證檔案

- 測試檔：`tests/`（21 個測試檔、284 條測試，均已入版控）
- XML 報告：`coverage.xml`（僅含 scripts/ 與 api/ 兩個 package）
- HTML 報告：`htmlcov/index.html`
