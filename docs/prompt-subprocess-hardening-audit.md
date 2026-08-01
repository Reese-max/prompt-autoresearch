# 候選提示詞 subprocess／shell 邊界稽核報告

- 稽核日期：2026-08-02
- 稽核範圍：`auto_evolve.py`、`scripts/evaluate.py` 及其直接呼叫鏈
- 稽核目標：追蹤候選提示詞進入 subprocess／shell 的所有路徑；確認不存在以字串拼接、
  `shell=True`、`os.system` 或 `sh -c` 執行候選內容的實作，確保提示詞永遠只作為
  模型／評測器輸入資料。

## 1. 結論摘要

**直接呼叫鏈內沒有需要移除的違規實作。**

候選提示詞在 `auto_evolve.py`、`scripts/evaluate.py` 及其直接呼叫鏈中，只透過下列三種
受控方式流動，全程不經由任何 shell 解譯：

1. **受控檔案內容傳遞**：候選正文先以 `write_file()` 寫入 `prompts/current.md`，
   再以「檔案路徑」作為 argv 元素傳給 `scripts/evaluate.py`；子程序以 `load_file()` 讀取，
   該檔案內容從未被當作指令執行。
2. **模型 API 輸入資料**：提示詞作為 `system`/`user` role 的 `content` 欄位，放進
   HTTP JSON payload（`lib/api.call_minimax`）傳給 MiniMax API。
3. **in-process 函式參數**：Gatekeeper、compare、compress 等皆以純函式呼叫接收字串。

全部 subprocess 呼叫皆為**明確 argv list**，未使用 `shell=True`，且參數中不含有候選正文。

## 2. 直接呼叫鏈地圖

```
auto_evolve.py
├── subprocess.run(preflight_cmd) ────────────► scripts/preflight.py   (argv list，無候選內容)
├── run_opt.run_opt_pass(...)  (in-process)
│   ├── scripts.gatekeeper.run_gatekeeper(mutated)   (in-process，純字串檢查)
│   ├── lib.api.call_minimax(meta_prompt, ...)       (HTTP JSON → 模型輸入)
│   ├── write_file(PROMPT_PATH, mutated)             (候選寫入受控檔案)
│   ├── run_evaluate(PROMPT_PATH, question_file, ...)
│   │   └── subprocess.run([python, scripts/evaluate.py, <檔案路徑>, ...])  (argv list)
│   │       └── scripts/evaluate.py
│   │           ├── load_file(prompt_file)            (讀取受控檔案內容)
│   │           └── lib.api.call_minimax(system_prompt, ...)  (HTTP JSON → 模型輸入)
│   └── scripts.compare_runs.compare(...)          (in-process)
└── lib.io / lib.metrics / lib.completion_gate      (純 I/O 與驗證，無 subprocess)
```

## 3. subprocess 呼叫點逐一審查

| # | 位置 | 呼叫形式 | 候選正文是否進入 | 判定 |
|---|---|---|---|---|
| 1 | `auto_evolve.py:232-242`（preflight） | `subprocess.run(preflight_cmd)`，`preflight_cmd` 為 argv list，僅含 python 路徑、`scripts/preflight.py` 與平行數 | 否，無任何提示詞內容 | ✅ 明確 argv |
| 2 | `run_opt.py:574-583`（run_evaluate capture） | `subprocess.run(cmd, stdout=PIPE, stderr=PIPE, text=True, ...)`，`cmd` 為 argv list：`[PYTHON_BIN, "scripts/evaluate.py", prompt_path, question_file, "--parallel", str(parallel)]` | 僅傳 `prompts/current.md` 檔案路徑（候選正文已先寫入檔案） | ✅ 受控檔案內容 + 明確 argv |
| 3 | `run_opt.py:585`（run_evaluate 非 capture） | `subprocess.run(cmd)`，同上 argv list | 同上，僅檔案路徑 | ✅ 受控檔案內容 + 明確 argv |

> 附註：`run_opt.run_evaluate()` 在呼叫前一律先執行 `write_file(PROMPT_PATH, mutated)`
> （`run_opt.py:877` smoke、`:959` dev/holdout），候選正文只以檔案內容方式進入子程序，
> 不會以字串拼接方式出現在 argv 或任何 shell 指令中。

## 4. `scripts/evaluate.py` 內部審查

`scripts/evaluate.py` 本身**不包含任何 subprocess / os.system / shell 呼叫**：

| 位置 | 提示詞去向 |
|---|---|
| `scripts/evaluate.py:405` | `system_prompt = load_file(prompt_file)` — 由受控檔案讀取 |
| `scripts/evaluate.py:282` | `call_minimax(answer_system, answer_user, temperature=0.3)` — 模型輸入 |
| `scripts/evaluate.py:360` | `call_minimax(judge_system, judge_user_retry, temperature=0.1)` — 模型輸入 |

`lib/api.call_minimax()`（`lib/api.py:68-114`）只以 `urllib.request` 送出 HTTP JSON，
提示詞位於 `payload["messages"][*]["content"]`，為純資料，不會被本機執行。

## 5. 直接呼叫鏈內其他模組

| 模組 | subprocess/shell 使用 | 判定 |
|---|---|---|
| `scripts/preflight.py` | 無；僅讀檔與環境變數 | ✅ |
| `scripts/gatekeeper.py` | 無；純正規表達式檢查 | ✅ |
| `scripts/compare_runs.py` | 無；純資料比較 | ✅ |
| `lib/api.py` | 無；HTTP JSON | ✅ |
| `lib/io.py` / `lib/config.py` / `lib/metrics.py` / `lib/completion_gate.py` | 無 | ✅ |

## 6. 全域掃描證據

對整個 repo 執行下列掃描，皆**零命中**：

```text
rg "os\.system|shell\s*=\s*True|\bsh\b.*-c|check_output|os\.popen"  → 0 matches
```

repo 內所有 `subprocess.*` 呼叫點（含直接呼叫鏈外之獨立入口）均使用 argv list、未開 shell：

| 檔案 | 行號 | 形式 |
|---|---|---|
| `auto_evolve.py` | 242 | `subprocess.run(list)` |
| `run_opt.py` | 576, 585 | `subprocess.run(list)` |
| `infinite_evolve.py` | 120 | `subprocess.run(list)` |
| `route_evolve.py` | 141, 150 | `subprocess.run(list)` |
| `route_loop.py` | 242 | `subprocess.run(list)` |
| `run_app.py` | 457, 489 | `subprocess.Popen(list)` |
| `api/continuous_optimizer.py` | 126 | `subprocess.run(list)` |
| `scripts/collect_execution_evidence.py` | 40, 82, 128 | `subprocess.run(list)` |
| `scripts/run_test_matrix.py` | 117 | `subprocess.run(command, **kwargs)` |
| `scripts/verify_reproducibility.py` | 46, 101 | `subprocess.run(list)` |

## 7. 本次改動

- 直接呼叫鏈內**無違規實作可移除**，既有程式已符合「明確 argv、stdin 或受控檔案內容傳遞」。
- 本稽核結論以本檔落盤保存（調查／盤點類任務要求）。

## 8. 可重現驗證

```bash
# 直接呼叫鏈檔案的 subprocess 呼叫點（預期僅 3 處，皆為 argv list）
rg -n "subprocess" auto_evolve.py run_opt.py scripts/evaluate.py \
   scripts/preflight.py scripts/gatekeeper.py scripts/compare_runs.py lib/

# 危險模式掃描（預期零命中）
rg "os\.system|shell\s*=\s*True|sh -c|check_output|os\.popen" .
```
