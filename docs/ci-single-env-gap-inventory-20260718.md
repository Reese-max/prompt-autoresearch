# CI／pytest 單一環境缺口盤點（2026-07-18）

## 任務範圍

檢查現有 CI／workflow 設定與 pytest 入口，找出**目前仍只在單一環境（win32／Python 3.11.9）**執行或僅有該環境證據的工作，並對齊 `docs/version-platform-support.md` 的支援聲明，列出需補齊的 Linux、macOS 與受支援 Python 版本組合。

本文件為盤點報告；**不修改** `.github/workflows/ci.yml` 或測試程式。

## 來源對照

| 來源 | 路徑 | 角色 |
|---|---|---|
| 支援聲明 | `docs/version-platform-support.md` | 宣告 CPython 3.10–3.12 × Linux／macOS／Windows（9 組合） |
| CI workflow | `.github/workflows/ci.yml` | 唯一 workflow；`test` job 使用 matrix |
| 矩陣入口 | `scripts/run_test_matrix.py` | `SUPPORTED_PLATFORMS`／`SUPPORTED_PYTHON_VERSIONS`；M1–M6 |
| pytest 預設 | `pytest.ini` | `testpaths = tests`；預設 `addopts` 含 coverage |
| 本機實測環境（本報告撰寫時） | — | **Windows win32，CPython 3.11.9** |

## 1. 現況摘要

| 項目 | 現況 | 是否仍單一環境 |
|---|---|---|
| CI 測試矩陣定義 | 已列 9 組合（L310–W312） | 否（定義已多環境） |
| CI 覆蓋率閘門 | 僅 `matrix.id == 'L311'` | 是（刻意單格，非 win32） |
| CI coverage artifact | 僅 L311 上傳 | 是（同上） |
| 本機預設 `pytest`／`python -m pytest` | 綁定執行者當前解譯器 | **是（本機僅 win32／3.11.9）** |
| 本機 `scripts/run_test_matrix.py` 可實跑 | 僅當 `--platform`／`--python-version` 與主機一致 | **是（本機僅 W311）** |
| 可追溯本機通過證據 | `docs/ci-matrix-rerun-record.md`、`docs/cross-platform-python-test-matrix.md` 等 | **是（僅 W311／3.11.9）** |
| 過時盤點文件 | `docs/test-platform-portability-audit-20260718.md` 仍寫「CI 只有 ubuntu-latest」 | 與現況不符（見 §5） |

**結論（一句話）**：CI **定義**已對齊支援聲明的 9 組合；但**本機與歷史驗收證據**仍集中在 win32／Python 3.11.9，且 **coverage gate 僅 L311**。對「可宣稱全組合已驗證」而言，仍缺其餘 8 組合的可重跑通過證據（及若要將 coverage 視為跨平台閘門，則缺其他 8 格的 coverage 執行）。

## 2. CI／workflow 設定盤點

### 2.1 Job 結構

- Workflow 名稱：`CI`
- 觸發：`push`、`pull_request`
- 單一 job：`test`
- Job 名稱模板：`${{ matrix.id }} (${{ matrix.os }}, Python ${{ matrix.python_version }})`
- `strategy.fail-fast: false`（單一組合失敗仍跑完其餘組合）

### 2.2 已宣告 matrix 組合（與支援聲明一致）

| 組合 ID | `runs-on` | `platform` | `python_version` | 測試入口 | Coverage gate |
|---|---|---|---|---|---|
| L310 | `ubuntu-latest` | Linux | 3.10 | `run_test_matrix.py` | 否 |
| L311 | `ubuntu-latest` | Linux | 3.11 | `run_test_matrix.py` | **是**（≥80%，限 `scripts/`+`api/`） |
| L312 | `ubuntu-latest` | Linux | 3.12 | `run_test_matrix.py` | 否 |
| M310 | `macos-latest` | macOS | 3.10 | `run_test_matrix.py` | 否 |
| M311 | `macos-latest` | macOS | 3.11 | `run_test_matrix.py` | 否 |
| M312 | `macos-latest` | macOS | 3.12 | `run_test_matrix.py` | 否 |
| W310 | `windows-latest` | Windows | 3.10 | `run_test_matrix.py` | 否 |
| W311 | `windows-latest` | Windows | 3.11 | `run_test_matrix.py` | 否 |
| W312 | `windows-latest` | Windows | 3.12 | `run_test_matrix.py` | 否 |

### 2.3 各 step 與環境綁定

| Step | 環境範圍 | 說明 |
|---|---|---|
| `actions/checkout@v4` | 全 matrix | — |
| `actions/setup-python@v5` | 全 matrix | `python-version: ${{ matrix.python_version }}` |
| Install dependencies | 全 matrix | `python -m pip install -r requirements.txt -r requirements-dev.txt` |
| Record environment | 全 matrix | 印出 `platform.system()`／`python_version` |
| Run full automated test suite | 全 matrix | `python scripts/run_test_matrix.py --platform … --python-version …`；寫入 `matrix-${{ matrix.id }}.jsonl` |
| Upload CI matrix evidence | 全 matrix（`if: always()`） | artifact `ci-matrix-evidence-<id>` |
| Coverage gate | **僅 L311** | `pytest tests -o addopts= --cov=scripts --cov=api --cov-fail-under=80` |
| Upload coverage reports | **僅 L311** | `coverage.xml`、`htmlcov/` |

### 2.4 仍屬「單一環境」的 CI 工作

以下**不是** win32／3.11.9，但屬「只在一個 matrix 格執行」：

1. **Coverage gate**（`.github/workflows/ci.yml`，`if: matrix.id == 'L311'`）
2. **Coverage reports 上傳**（同上條件）

若支援聲明要求「跨平台完成判定」僅依賴 M1–M6 全綠，則 coverage 單格可接受（與 `docs/version-platform-support.md` L311 列一致）。若日後要把 coverage 也視為平台／版本相容性閘門，則需擴充（見 §4.2）。

## 3. pytest 入口盤點

| 入口 | 命令／設定 | 預設綁定環境 | 多環境能力 |
|---|---|---|---|
| 預設 pytest | `pytest`／`python -m pytest`（`pytest.ini`：`testpaths=tests`） | **當前解譯器**（本機 = win32 3.11.9） | 無矩陣；換 OS／版本需手動換環境 |
| 矩陣腳本 | `python scripts/run_test_matrix.py --platform <P> --python-version <V>` | 拒絕與實際 runtime 不符的 (P,V) | 支援 `Linux`／`macOS`／`Windows` × `3.10`／`3.11`／`3.12`，但**一次只能跑本機那一格** |
| CI 呼叫 | 同上腳本 + `CI_MATRIX_ID`／`CI_MATRIX_REPORT_PATH` | 由 runner 決定 | 9 格並行（GitHub Actions） |
| Coverage 本機慣例 | `pytest tests -o addopts= --cov=scripts --cov=api …`（多份 docs） | 紀錄多為 **win32 3.11.9** | 無強制矩陣 |
| 啟動器 | `run.bat`／`run.sh` | 本機伺服器，非 CI 測試矩陣 | 平台各一檔，非 pytest 矩陣 |

M1–M6 測試集合定義見 `scripts/run_test_matrix.py` 的 `M1_TESTS`／`PYTEST_SETS`（與 `docs/cross-platform-python-test-matrix.md` 一致）。

## 4. 對齊支援聲明：需新增／補齊的組合清單

支援聲明（`docs/version-platform-support.md`）：

- 平台：Linux、macOS、Windows  
- Python：CPython **3.10、3.11、3.12**  
- 共 **9** 組合；排除 3.9−、3.13+、非 CPython、32-bit

### 4.1 功能測試（M1–M6）— CI 定義已齊，本機證據缺口

| 組合 ID | 平台 | Python | CI matrix 是否已列 | 本工作區可追溯本機通過證據 | 需新增／補齊動作 |
|---|---|---|---|---|---|
| L310 | Linux | 3.10 | 已有 | 無 | **補齊 CI 成功紀錄或 Linux 本機實跑證據** |
| L311 | Linux | 3.11 | 已有 | 無（僅有「CI 已設定」敘述） | **補齊通過證據**（含 coverage gate） |
| L312 | Linux | 3.12 | 已有 | 無 | **補齊通過證據** |
| M310 | macOS | 3.10 | 已有 | 無 | **補齊通過證據** |
| M311 | macOS | 3.11 | 已有 | 無 | **補齊通過證據** |
| M312 | macOS | 3.12 | 已有 | 無 | **補齊通過證據** |
| W310 | Windows | 3.10 | 已有 | 無 | **補齊通過證據**（非 3.11.9） |
| W311 | Windows | 3.11 | 已有 | **有**（3.11.9，`matrix_id=local`） | 無需新增組合；可選對齊 CI runner 的 3.11.x patch |
| W312 | Windows | 3.12 | 已有 | 無 | **補齊通過證據** |

#### 若以「CI 尚未寫入 matrix」為判準（歷史任務用語）

目前 **不需再往 `ci.yml` 新增** 下列組合（已存在）：

- Linux × {3.10, 3.11, 3.12}
- macOS × {3.10, 3.11, 3.12}
- Windows × {3.10, 3.12}（3.11 亦已列）

#### 若以「相對 win32／3.11.9 本機單點，仍缺可驗證覆蓋」為判準（本任務主軸）

**必須補齊證據的 8 組合**（不得以 W311 單點冒充全量）：

```
L310  Linux  + CPython 3.10
L311  Linux  + CPython 3.11
L312  Linux  + CPython 3.12
M310  macOS  + CPython 3.10
M311  macOS  + CPython 3.11
M312  macOS  + CPython 3.12
W310  Windows + CPython 3.10
W312  Windows + CPython 3.12
```

建議每格可重現命令（在對應 OS 與 Python 上）：

```bash
python scripts/run_test_matrix.py --platform <Linux|macOS|Windows> --python-version <3.10|3.11|3.12>
```

成功判定：M1–M6 與 `ALL` 的 `MATRIX_RESULT.exit_code` 皆為 `0`（與支援聲明完成判定一致）。CI 上另以 artifact `ci-matrix-evidence-<id>` 留存。

### 4.2 Coverage 閘門 — 仍為單格

| 項目 | 目前 | 對齊支援聲明時的選項 |
|---|---|---|
| Coverage gate | 僅 L311 | **維持單格**（現有文件已寫明 L311 專責）**或**擴到全 9 格／每平台一格 |
| 本機 coverage 紀錄 | 多為 win32 3.11.9 | 與 CI 閘門平台不一致；宣稱「coverage 驗收」時應標明平台，避免與 L311 混用 |

**若要讓 coverage 也跨平台**：需新增執行的組合清單與 §4.1 相同 9 格（或至少 Linux／macOS／Windows 各一 × 受支援 Python）。**本盤點不建議在未改支援聲明前擅自擴 coverage**——現聲明僅要求 L311 ≥ 80%。

### 4.3 不應新增的組合（與支援聲明一致）

| 組合 | 原因 |
|---|---|
| 任一 OS × CPython ≤ 3.9 | 低於最低版本 |
| 任一 OS × CPython ≥ 3.13 | 尚未納入 `SUPPORTED_PYTHON_VERSIONS` |
| PyPy／Jython／GraalPy | 非 CPython |
| 32-bit 任一代理解譯器 | CI 僅 64-bit runner |
| iOS／Android／WASI 等 | 無支援聲明 |

## 5. 文件一致性備註（非本任務修改範圍）

下列文件敘述與**目前** `ci.yml` 9 格 matrix 不一致，後續維護時應更新，避免驗收誤判：

| 文件 | 過時敘述 |
|---|---|
| `docs/test-platform-portability-audit-20260718.md` | 「CI 只有 `ubuntu-latest`」「沒有 macOS 工作流程」 |
| `docs/cross-platform-validation.md` | 強調 CI 在 `ubuntu-latest`，未反映 macOS／Windows matrix |
| `docs/cross-platform-python-test-matrix.md` §平台差異加驗 | 「目前沒有 macOS CI」；組合表多列「待驗證」但 CI 定義已存在 |

本報告以 `ci.yml` 與 `version-platform-support.md` 為準。

## 6. 本機環境證據（撰寫時）

```text
Python 3.11.9
platform.system() / python_version / sys.platform → Windows / 3.11.9 / win32
```

抽樣測試（確認盤點期間測試入口可用，非全量 9 格證明）：

```text
python -m pytest tests/test_script_entrypoints.py -q --no-cov
→ 32 passed
```

## 7. 最終清單（交付）

### A. 仍只在單一環境執行／僅有單點證據的工作

1. **本機預設 pytest 與本機矩陣實跑** — win32／Python 3.11.9  
2. **歷史／本機驗收與 coverage 紀錄** — 多僅引用 win32／3.11.9  
3. **CI Coverage gate 與 coverage artifact** — 僅 L311（非 win32，但仍是單一 matrix 格）

### B. 對齊支援聲明後，相對單點環境「需要新增覆蓋」的組合

| # | 組合 ID | OS | Python |
|---|---|---|---|
| 1 | L310 | Linux | 3.10 |
| 2 | L311 | Linux | 3.11 |
| 3 | L312 | Linux | 3.12 |
| 4 | M310 | macOS | 3.10 |
| 5 | M311 | macOS | 3.11 |
| 6 | M312 | macOS | 3.12 |
| 7 | W310 | Windows | 3.10 |
| 8 | W312 | Windows | 3.12 |

（W311 已有本機 3.11.9 證據；CI 定義上九格皆已列入，**無需再改 workflow 才能「列出」上述組合**——缺的是**各格成功執行證據**。）

### C. CI workflow 是否還要加 matrix 列？

| 問題 | 答案 |
|---|---|
| `ci.yml` 是否缺少 Linux／macOS／多版本列？ | **否**，9 組合已齊 |
| 本任務是否要求實作新 job？ | **否**（僅盤點） |
| 後續實作任務應做什麼？ | 跑通並保存 §7.B 八格（或 CI 全綠 9 格）的 `MATRIX_RESULT`／artifact，並更新過時 docs |

---

*盤點日期：2026-07-18。證據來源：工作區內 `ci.yml`、`run_test_matrix.py`、`pytest.ini`、`version-platform-support.md` 與本機 `python --version`。*
