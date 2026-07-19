# `get_section` 非字典 section 的紅綠證據

## 變更目標
新增一筆回歸測試，覆蓋 `lib.config.get_section()` 當 section 資料不是 `dict` 時不該丟 `ValueError`，而是回傳 `dict`。

## 基準執行（實作未修改前）

### 指令
```powershell
python -m pytest -q tests/test_lib_config.py -k "get_section_with_non_dict_section_returns_empty_dict"
```

### 產出
- 來源檔：`docs/config-get-section-evidence-red.txt`
- 結果：`FAILED`（1 failed）
- 失敗重點：`get_section` 命中 `dict(cfg.get(section, {}))` 時，`section` 為字串導致 `ValueError`。

## 實作後執行（同一指令）

### 指令
```powershell
python -m pytest -q tests/test_lib_config.py -k "get_section_with_non_dict_section_returns_empty_dict"
```

### 產出
- 來源檔：`docs/config-get-section-evidence-green.txt`
- 結果：`1 passed`（同一指令，全部通過）

## 全域回歸
### 指令
```powershell
python -m pytest -q
```

### 結果
- `783 passed, 2 skipped`
