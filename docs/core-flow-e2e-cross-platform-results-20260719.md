# 核心流程端到端跨平台可比對結果（2026-07-19）

## 任務範圍

在每個**可達目標平台**執行核心流程端到端測試，驗證**相同固定輸入**產生**一致且符合規格**的輸出，並提交可比對產物。

目標平台（見 [`version-platform-support.md`](version-platform-support.md)）：Linux / macOS / Windows × CPython 3.10–3.12。

本輪**本機實際執行**平台（可取得原生 runner）：

| 組合 | 作業系統 | Python | 執行環境 |
|---|---|---|---|
| W311 | Windows 10 | 3.11.9 | 本機 `win32` |
| L312 | Linux（WSL2 Ubuntu） | 3.12.3 | WSL2 |

macOS 與其他 Python 次要版本由 CI 矩陣（`.github/workflows/ci.yml` × `scripts/run_test_matrix.py` M2 含本 runner 測試）覆蓋定義；本報告不主張未實跑的 runner 已通過（對齊 L012 / L017）。

## 核心流程定義

固定輸入（與 `tests/test_cross_platform.py::TestCoreEvaluationFlow` 對齊）：

| 輸入 | 內容 |
|---|---|
| Prompt | `UNICODE_PROMPT`（含 CRLF 寫入） |
| 題庫 | 單題案例題 JSONL（含 CRLF） |
| LLM | mock：temperature 0.3 → 固定答案；0.1 → 固定評分 JSON |
| Gatekeeper | 同一 prompt 正例 + 短字串負例 |

規格期望（`EXPECTED`）：

| 欄位 | 期望值 |
|---|---|
| `prompt_hash` | `sha256(UNICODE_PROMPT)` |
| `average_score` | `79.0` |
| `total_score` | `79` |
| `failures` | `["F03"]` |
| `word_count_pass_rate` | `100.0` |
| `risk_perfect_rate` | `0.0` |
| `error_count` | `0` |
| gatekeeper 正例 | `passed=true` |
| gatekeeper 負例 | `passed=false` 且 reject ≥ 1 |
| 產物 | `details.jsonl` / `summary.json` / `summary.md` / `results.tsv` 無 BOM、UTF-8、含 `\t79.00\t` |
| 冪等 | 清 cache 後重跑 summary/results 契約欄位相同 |

## 執行命令

```text
# Windows (W311)
python scripts/run_core_flow_e2e.py --out docs/evidence/core-flow-e2e-Windows-3.11.json

# Linux WSL2 (L312)
python3 scripts/run_core_flow_e2e.py --out docs/evidence/core-flow-e2e-Linux-3.12.json
```

契約測試：

```text
python -m pytest tests/test_core_flow_e2e.py tests/test_cross_platform.py::TestCoreEvaluationFlow -q --no-cov
```

## 可比對結果摘要

| 欄位 | Windows 3.11.9 | Linux 3.12.3 | 一致？ |
|---|---|---|---|
| `spec_ok` | `true` | `true` | 是 |
| `exit_code` | `0` | `0` | 是 |
| `comparable_digest` | `1cb2551633b57a0440842185e5311842ff6ba4a1abeaa1591fd32d74092e84ab` | 同左 | **是** |
| `evaluation.canonical_digest` | `9947b3d8fbab4fcebfb974f8bd38425a6b68d871c2a0db335825b43aaf5b1baa` | 同左 | **是** |
| `average_score` | `79.0` | `79.0` | 是 |
| `gatekeeper.valid_prompt.passed` | `true` | `true` | 是 |
| `gatekeeper.short_prompt.passed` | `false` | `false` | 是 |

**結論**：相同固定輸入在 Windows 與 Linux 上產生**位元級一致**的 `comparable_digest`（已排除 runtime 指紋與暫存絕對路徑），且全部規格斷言通過。

## 執行環境指紋（來源證明）

### Windows

| 項目 | 值 |
|---|---|
| hostname | `HPZBOOKG10-` |
| platform | Windows / `win32` |
| Python | 3.11.9 |
| executable | `C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` |
| 時間 | 2026-07-19 07:30 +0800 |

### Linux（WSL2）

| 項目 | 值 |
|---|---|
| hostname | `HPZBOOKG10` |
| platform | Linux / `linux`（kernel `5.15.167.4-microsoft-standard-WSL2`） |
| Python | 3.12.3 |
| executable | `/usr/bin/python3` |
| 時間 | 2026-07-19 07:30 +0800 |

## 可比對產物清單

| 檔案 | 說明 |
|---|---|
| [`docs/evidence/core-flow-e2e-Windows-3.11.json`](evidence/core-flow-e2e-Windows-3.11.json) | Windows 完整結果（含 runtime + comparable） |
| [`docs/evidence/core-flow-e2e-Linux-3.12.json`](evidence/core-flow-e2e-Linux-3.12.json) | Linux 完整結果 |
| [`docs/evidence/core-flow-e2e-comparable-side-by-side.json`](evidence/core-flow-e2e-comparable-side-by-side.json) | 兩邊 `comparable` 並排 + `digests_equal` |
| [`docs/evidence/core-flow-e2e-Windows-3.11-console.txt`](evidence/core-flow-e2e-Windows-3.11-console.txt) | Windows 主控台原始輸出 |
| [`docs/evidence/core-flow-e2e-Linux-3.12-console.txt`](evidence/core-flow-e2e-Linux-3.12-console.txt) | Linux 主控台原始輸出 |

## 新增／變更的程式入口

| 路徑 | 角色 |
|---|---|
| `scripts/run_core_flow_e2e.py` | 固定輸入核心流程 E2E；輸出可比對 JSON |
| `tests/test_core_flow_e2e.py` | runner 規格與 CLI 寫檔測試 |
| `scripts/run_test_matrix.py`（M2） | 將 `tests/test_core_flow_e2e.py` 納入跨平台矩陣子集 |

## 可重現步驟

```powershell
# 1) Windows
python scripts/run_core_flow_e2e.py --out docs/evidence/core-flow-e2e-Windows-3.11.json --quiet

# 2) Linux (WSL2，同一 worktree)
wsl -e bash -lc 'cd /mnt/d/Users/Administrator/Desktop/autodev-ng/data/prompt-autoresearch/worktrees/f59a8744 && python3 scripts/run_core_flow_e2e.py --out docs/evidence/core-flow-e2e-Linux-3.12.json --quiet'

# 3) 比對 digest
python -c "import json; from pathlib import Path; w=json.loads(Path('docs/evidence/core-flow-e2e-Windows-3.11.json').read_text(encoding='utf-8')); l=json.loads(Path('docs/evidence/core-flow-e2e-Linux-3.12.json').read_text(encoding='utf-8')); print(w['comparable_digest']==l['comparable_digest'], w['comparable_digest'])"
```

預期：印出 `True` 與同一 64 字元 hex digest。

## 限制聲明

1. 本輪未在本機 macOS runner 或 CPython 3.10 上實跑；可比對證據限 W311 與 L312。
2. LLM 為 mock（固定回傳），驗證的是**核心管線契約與序列化一致性**，非真實 API 內容品質。
3. `comparable_digest` 刻意排除 `runtime` 指紋與暫存目錄絕對路徑，僅保留規格契約欄位。
