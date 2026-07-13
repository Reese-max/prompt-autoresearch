# lib/api 錯誤契約 TDD 週期驗證紀錄（2026-07-14）

驗證指令：

```
python -m pytest tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

## 結果

1. **修補前先失敗**：將 `lib/api.py` 暫時還原至 57836dd（修補 commit 6068275 之前），
   `tests/test_lib_api_error_contract.py` 5 個測試全數 FAILED（1.03s），
   確認 failing tests 確實鎖定修補前的行為落差。
2. **修補後通過**：還原至 HEAD 後，完整套件 **303 passed, 1 deselected**（7.64s），
   錯誤契約測試轉綠。
3. **無回歸**：其餘既有測試全數通過，覆蓋率 TOTAL 99%（1642 stmts / 13 miss），
   產品程式碼未在本輪變動（working tree 驗證後乾淨）。

對照稽核文件：`docs/lib-api-error-branch-audit.md`。
相關 commits：57836dd（failing tests）→ 6068275（例外轉譯層修補）。
