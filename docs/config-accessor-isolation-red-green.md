# 設定讀取 API 快取隔離：紅→綠證據

## 驗收範圍

`get()` 與 `get_section()` 不應把 `_CONFIG` 內的巢狀 `dict`／`list` 直接暴露給呼叫端；呼叫端修改回傳值後，再次讀取設定應維持原值。

- 紅燈基準 commit：`12f7ebc4f3018fd2a038cc4278ba4713c36be282`
- 新增測試檔 blob：`8c494030ffd6644fc6a4f099711016c2dca9a6d8`
- 紅燈執行前：`git diff --quiet -- lib/config.py` 回傳 `0`，確認實作未修改。

## 同一組測試

紅、綠兩階段均執行：

```powershell
python -m pytest --no-cov --color=no -q tests/test_config_accessor_isolation.py
```

| 階段 | 原始輸出 | exit code | 結果 |
|---|---|---:|---|
| RED：未修改實作 | `docs/evidence/config-accessor-isolation-red.txt` | 1 | `3 failed`；三個 accessor 都會污染快取 |
| GREEN：完成實作 | `docs/evidence/config-accessor-isolation-green.txt` | 0 | `3 passed` |

修正只對實際來自設定快取的回傳值使用既有 `copy.deepcopy()`；呼叫端傳入的 fallback 物件仍原樣回傳。

## 重播方式

在本提交的綠燈狀態，可用保存的最小實作 patch 重播相同紅→綠流程：

```powershell
git apply -R --unidiff-zero docs/evidence/config-accessor-isolation.patch
python -m pytest --no-cov --color=no -q tests/test_config_accessor_isolation.py
git apply --unidiff-zero docs/evidence/config-accessor-isolation.patch
python -m pytest --no-cov --color=no -q tests/test_config_accessor_isolation.py
```

第一輪預期 `3 failed`，第二輪預期 `3 passed`。第二個 `git apply` 亦會恢復綠燈實作。

## 完整回歸

```powershell
python -m pytest --color=no
```

結果：`902 passed, 2 skipped in 45.44s`。完整套件結果僅作回歸檢查；測試先於實作失敗的證明以上述 RED 原始輸出為準。
