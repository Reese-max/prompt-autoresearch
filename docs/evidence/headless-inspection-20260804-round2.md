# 2026-08-04 第 2 棒 headless 巡檢重開證據

## 執行範圍

- 工作目錄：`D:/adng-worktrees/prompt-autoresearch/7e7f8890`
- 執行前 HEAD：`aa09ebcdded9850bbf508bdfadef16ed2650b038`
- 執行前工作樹：乾淨
- pytest 範圍：僅指定檔案；本輪未擴跑其他 pytest 測試

## 指定測試實際輸出

命令：

```powershell
python -m pytest tests/f3a446d66daf7490-research-conclusion-delivery-surface.py -q
```

實際輸出（保留文字內容；`__EXIT_CODE__` 為同一 PowerShell 執行後讀取的退出碼）：

```text
no tests ran in 0.10s
__EXIT_CODE__=4
ERROR: file or directory not found: tests/f3a446d66daf7490-research-conclusion-delivery-surface.py
```

判定：指定測試檔不在目前 repo 的 HEAD，pytest 以 exit code 4 結束；本次沒有測試案例可執行，因此不能宣稱引擎通過，也不能把本次結果判為 timeout。

## Git 預檢正案例

前置條件：工作樹乾淨。

命令：

```powershell
python scripts/preflight.py --require-git
```

實際輸出：

```text
============================================================
  Prompt AutoResearch Preflight
============================================================
  [OK] Git workspace: Git metadata、repository root 與 HEAD 可解析
  [OK] MINIMAX_API_KEY: 環境變數已設定
  [OK] Python version: 3.11.9
  [OK] questions/smoke.jsonl: 題數 6 / 預期 6
  [OK] questions/dev.jsonl: 題數 48 / 預期 48
  [OK] questions/holdout.jsonl: 題數 18 / 預期 18
  [OK] questions/final.jsonl: 題數 12 / 預期 12
  [OK] prompts/baseline.md: 字數 438
  [OK] prompts/current.md: 字數 438
  [OK] baseline.meta hash: meta=004e4d46a58f baseline=004e4d46a58f
  [OK] baseline dev run: runs\20260602_184026
  [OK] baseline smoke run: runs\20260602_182243
  [OK] baseline holdout run: runs\20260602_184533
  [OK] runs/latest: runs/latest/summary.md
  [OK] parallel settings: smoke=6, dev=24, holdout=24
============================================================
  結果: PASS
__EXIT_CODE__=0
```

## Git 預檢負案例

在目前 repo 內暫時建立未追蹤探針檔，執行預檢後即移除；未修改其他 repo。

命令：

```powershell
python scripts/preflight.py --require-git
```

實際輸出：

```text
============================================================
  Prompt AutoResearch Preflight
============================================================
  [FAIL] Git workspace: dirty_worktree
  [OK] MINIMAX_API_KEY: 環境變數已設定
  [OK] Python version: 3.11.9
  [OK] questions/smoke.jsonl: 題數 6 / 預期 6
  [OK] questions/dev.jsonl: 題數 48 / 預期 48
  [OK] questions/holdout.jsonl: 題數 18 / 預期 18
  [OK] questions/final.jsonl: 題數 12 / 預期 12
  [OK] prompts/baseline.md: 字數 438
  [OK] prompts/current.md: 字數 438
  [OK] baseline.meta hash: meta=004e4d46a58f baseline=004e4d46a58f
  [OK] baseline dev run: runs\20260602_184026
  [OK] baseline smoke run: runs\20260602_182243
  [OK] baseline holdout run: runs\20260602_184533
  [OK] runs/latest: runs/latest/summary.md
  [OK] parallel settings: smoke=6, dev=24, holdout=24
============================================================
  結果: FAIL
__EXIT_CODE__=1
```

## 結論

`INCOMPLETE_EVIDENCE`：Git 預檢正反案例均可重現且退出碼符合預期；指定 pytest 無法啟動，原因是檔案缺失，不是 timeout。可重跑命令仍為：

```powershell
python -m pytest tests/f3a446d66daf7490-research-conclusion-delivery-surface.py -q
```
