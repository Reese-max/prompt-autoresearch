# 跨平台差異修正與雙平台驗證證據（2026-07-19）

## 任務範圍

若非 Windows 平台出現差異，**只**修正平台相依的路徑、編碼、暫存目錄或程序啟動行為，再重跑 Windows 與 Linux 驗證，直到兩邊穩定通過並留下可檢查證據。

## 發現的差異（Linux / WSL）

| 現象 | 根因 | 類型 |
|---|---|---|
| `test_product_diff_audit.py` 在 WSL 拋 `RuntimeError: 無法讀取 git 狀態：128` | worktree 的 `.git` 指標為 `gitdir: D:/...`；Linux git 將 `D:/...` 當相對路徑 | **路徑／程序啟動** |
| 路徑修好後同一測試誤報大量 `api/`、`lib/` 等「未授權修改」 | Windows worktree 在 WSL 下 `core.filemode`／CRLF 造成假陽性 | **程序啟動（git -c）** |

Windows 本機同一命令先前即通過；差異僅在非 Windows 存取同一 worktree 時顯現。

## 最小修正（僅 `tests/test_product_diff_audit.py`）

1. **路徑**：非 Windows 讀取 `.git` 的 `gitdir:`；若為 Windows 磁碟路徑且轉譯後的 `/mnt/<drive>/...` 存在，則設定 `GIT_DIR` + `GIT_WORK_TREE`。
2. **編碼**：`subprocess.run(..., encoding="utf-8", errors="replace")`，避免 locale 解碼失敗。
3. **程序啟動**：固定  
   `git -c core.filemode=false -c core.autocrlf=true status --porcelain -uno`  
   避免 filemode／CRLF 假修改。

未改產品碼（`api/`、`lib/`）、未動 `BACKLOG.md`、未改 CI 矩陣設定。

## 雙平台驗證命令

兩平台皆執行：

```text
python -m pytest tests/ -q --no-cov --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

（Linux 以 WSL2 內 `python3 -m pytest ...` 執行，cwd 為本 worktree 的 `/mnt/d/.../04f3777f`。）

## 可檢查結果

### Windows（W311 對齊）

| 欄位 | 值 |
|---|---|
| 時間 | 2026-07-19 06:19 +08:00 |
| hostname | `HPZBOOKG10-` |
| OS | Windows（`platform.system()=Windows`） |
| Python | 3.11.9 |
| executable | `C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` |
| 結果 | **612 passed, 1 skipped, 1 deselected in 21.21s**，`exit=0` |
| skip 原因 | `test_git_status_kwargs_sets_env_for_windows_gitdir` 僅驗證非 Windows 啟動行為 |

主控台摘錄見 [`docs/evidence/cross-platform-W311-console.txt`](evidence/cross-platform-W311-console.txt)。

### Linux（WSL2，L312 近似）

| 欄位 | 值 |
|---|---|
| 時間 | 2026-07-19 06:19 +08:00 |
| hostname | `HPZBOOKG10`（WSL） |
| OS | Linux（`uname`：`5.15.167.4-microsoft-standard-WSL2`） |
| Python | 3.12.3 |
| executable | `/usr/bin/python3` |
| 結果 | **613 passed, 1 deselected in 12.43s**，`exit=0` |

主控台摘錄見 [`docs/evidence/cross-platform-L312-wsl-console.txt`](evidence/cross-platform-L312-wsl-console.txt)。

### 對照

| 平台 | 修正前 | 修正後 |
|---|---|---|
| Windows | 611+ passed（既有） | 612 passed, 1 skipped, exit=0 |
| Linux WSL | 1 failed（gitdir 128 → 路徑修好後假陽性 protected files） | 613 passed, exit=0 |

> 依 L012／L017：本文件不宣稱 GitHub Actions 九格 runner 皆已實跑；本輪可驗證者為 **本機 Windows 3.11.9** 與 **WSL2 Linux 3.12.3** 全量 pytest。

## 可重現步驟

```powershell
# Windows
python -m pytest tests/ -q --no-cov --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract

# Linux (WSL2，同一 worktree)
wsl -e bash -lc 'cd "/mnt/d/Users/Administrator/Desktop/autodev-ng/data/prompt-autoresearch/worktrees/04f3777f" && python3 -m pytest tests/ -q --no-cov --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract'
```
