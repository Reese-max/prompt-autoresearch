# 驗收證據報告：新增測試可追溯性

## 摘要

本報告將近期新增的測試與其驗證的目標行為一一對應，提供可追溯的驗收輸出。每筆測試皆附上：
- 測試名稱與所在檔案
- 驗證的目標行為描述
- 涉及的被測模組/函式
- 預期斷言與實際結果

**驗收時間**: 2026-08-06  
**測試環境**: Windows 32, Python 3.11.9, pytest 9.1.1  
**全量測試結果**: 1293 passed, 2 skipped (0 failed)  
**整體覆蓋率**: 80% (6108 stmts, 1119 miss)

---

## 1. test_completion_evidence_manifest.py (5 tests)

### 1.1 test_completion_persists_relative_size_hash_and_verification
- **驗證行為**: `completion_disposition()` 正常產出時，evidence_manifest 包含相對路徑、正確 size、SHA-256 與 verified=True
- **被測函式**: `lib.completion_gate.completion_disposition()`
- **斷言**: status=completed, evidence_errors=[], manifest 內容與實際檔案 SHA-256 一致
- **實際結果**: PASSED

### 1.2 test_invalid_file_evidence_is_rejected[-empty]
- **驗證行為**: 空檔案證據被拒絕，evidence_manifest 為空，錯誤訊息含 "empty"
- **被測函式**: `lib.completion_gate.completion_disposition()`
- **斷言**: status=failed, evidence_manifest=[], evidence_errors[0] 含 "empty"
- **實際結果**: PASSED

### 1.3 test_invalid_file_evidence_is_rejected[None-outside]
- **驗證行為**: 工作區外的檔案證據被拒絕，evidence_manifest 為空，錯誤訊息含 "outside"
- **被測函式**: `lib.completion_gate.completion_disposition()`
- **斷言**: status=failed, evidence_manifest=[], evidence_errors[0] 含 "outside"
- **實際結果**: PASSED

### 1.4 test_unreadable_file_evidence_is_rejected
- **驗證行為**: 不可讀的檔案證據被拒絕，錯誤訊息含 "unreadable"
- **被測函式**: `lib.completion_gate.completion_disposition()`
- **斷言**: status=failed, evidence_errors[0] 含 "unreadable"
- **實際結果**: PASSED

### 1.5 test_saved_summary_contains_verified_evidence_manifest
- **驗證行為**: `evaluate.save_run_results()` 儲存的 summary.json 包含 evidence_manifest，且所有項目 verified=True
- **被測函式**: `scripts.evaluate.save_run_results()`
- **斷言**: saved["evidence_manifest"] 非空，所有項目 size>0 且 verified=True
- **實際結果**: PASSED

---

## 2. test_persisted_run_evidence.py (43 tests)

### 2.1 TestPersistedRunEvidenceSuccess (3 tests)

#### 2.1.1 test_valid_run_returns_completed
- **驗證行為**: 正常 run 目錄 → status=completed, reason_code=''
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=completed, completion_status=completed, reason_code='', rejection_reasons=[], evidence_manifest 非空
- **實際結果**: PASSED

#### 2.1.2 test_valid_run_has_verified_manifest
- **驗證行為**: 正常 run → evidence_manifest 全部 verified=True, size>0, sha256 非空
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: 所有 manifest 項目 verified=True, size>0, sha256!=""
- **實際結果**: PASSED

#### 2.1.3 test_valid_run_manifest_matches_files
- **驗證行為**: 正常 run → evidence_manifest 指向實際存在的檔案
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: manifest 每個 path 對應的檔案存在
- **實際結果**: PASSED

### 2.2 TestPersistedRunEvidenceMissing (5 tests)

#### 2.2.1 test_missing_run_dir_returns_failed
- **驗證行為**: run 目錄不存在 → status=failed, reason_code=NO_VALID_OUTPUT
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, completion_status=failed, reason_code=NO_VALID_OUTPUT
- **實際結果**: PASSED

#### 2.2.2 test_none_run_dir_returns_failed
- **驗證行為**: run_dir=None → status=failed, reason_code=NO_VALID_OUTPUT
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=NO_VALID_OUTPUT
- **實際結果**: PASSED

#### 2.2.3 test_empty_string_run_dir_returns_failed
- **驗證行為**: run_dir='' → status=failed, reason_code=NO_VALID_OUTPUT
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=NO_VALID_OUTPUT
- **實際結果**: PASSED

#### 2.2.4 test_run_dir_without_summary_returns_failed
- **驗證行為**: run 目錄存在但缺少 summary.json → status=failed, MISSING_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=MISSING_EVIDENCE_MANIFEST, "summary" in rejection_reason
- **實際結果**: PASSED

#### 2.2.5 test_run_dir_with_corrupted_summary_returns_failed
- **驗證行為**: summary.json 內容損壞（非 JSON）→ status=failed, MISSING_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=MISSING_EVIDENCE_MANIFEST
- **實際結果**: PASSED

### 2.3 TestPersistedRunEvidenceUnreadable (3 tests)

#### 2.3.1 test_empty_summary_returns_failed
- **驗證行為**: summary.json 為空檔 → status=failed, MISSING_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=MISSING_EVIDENCE_MANIFEST
- **實際結果**: PASSED

#### 2.3.2 test_summary_without_manifest_returns_failed
- **驗證行為**: summary.json 無 evidence_manifest 欄位 → status=failed
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code in {MISSING_EVIDENCE_MANIFEST, INVALID_EVIDENCE_MANIFEST}
- **實際結果**: PASSED

#### 2.3.3 test_summary_with_empty_manifest_returns_failed
- **驗證行為**: summary.json 的 evidence_manifest 為空列表 → INVALID_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=INVALID_EVIDENCE_MANIFEST
- **實際結果**: PASSED

### 2.4 TestPersistedRunEvidenceVerificationFailed (8 tests)

#### 2.4.1 test_failed_completion_status_returns_failed
- **驗證行為**: summary.completion_status='failed' → status=failed, NON_COMPLETED_STATUS
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, completion_status=failed, reason_code=NON_COMPLETED_STATUS
- **實際結果**: PASSED

#### 2.4.2 test_incomplete_completion_status_returns_failed
- **驗證行為**: summary.completion_status='incomplete' → status=failed
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, completion_status=incomplete
- **實際結果**: PASSED

#### 2.4.3 test_summary_with_evidence_errors_returns_failed
- **驗證行為**: summary.evidence_errors 非空 → INVALID_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=INVALID_EVIDENCE_MANIFEST, rejection_reasons 含 "file missing"
- **實際結果**: PASSED

#### 2.4.4 test_manifest_sha256_mismatch_returns_failed
- **驗證行為**: evidence_manifest 的 sha256 與實際檔案不符 → INVALID_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=INVALID_EVIDENCE_MANIFEST, rejection_reasons 含 "sha256 mismatch"
- **實際結果**: PASSED

#### 2.4.5 test_manifest_size_mismatch_returns_failed
- **驗證行為**: evidence_manifest 的 size 與實際檔案不符 → INVALID_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=INVALID_EVIDENCE_MANIFEST, rejection_reasons 含 "size mismatch"
- **實際結果**: PASSED

#### 2.4.6 test_manifest_points_to_deleted_file_returns_failed
- **驗證行為**: evidence_manifest 指向已刪除的檔案 → INVALID_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=INVALID_EVIDENCE_MANIFEST
- **實際結果**: PASSED

#### 2.4.7 test_no_meaningful_results_returns_failed
- **驗證行為**: details.jsonl 全部為空或 errored → NO_VALID_OUTPUT
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code=NO_VALID_OUTPUT, "no meaningful result" in rejection_reason
- **實際結果**: PASSED

#### 2.4.8 test_empty_details_returns_failed
- **驗證行為**: details.jsonl 為空 → NO_VALID_OUTPUT 或 INVALID_EVIDENCE_MANIFEST
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=failed, reason_code in {NO_VALID_OUTPUT, INVALID_EVIDENCE_MANIFEST}
- **實際結果**: PASSED

### 2.5 TestPersistRunFailure (7 tests)

#### 2.5.1 test_persists_failure_to_summary
- **驗證行為**: 正常 run 目錄 → persist_run_failure 寫入 failed 狀態到 summary.json
- **被測函式**: `lib.completion_gate.persist_run_failure()`
- **斷言**: success=True, summary.json 含 completion_status=failed, reason_code=INVALID_EVIDENCE_MANIFEST
- **實際結果**: PASSED

#### 2.5.2 test_returns_false_for_empty_run_dir
- **驗證行為**: run_dir 為空 → 回傳 False
- **被測函式**: `lib.completion_gate.persist_run_failure()`
- **斷言**: result=False
- **實際結果**: PASSED

#### 2.5.3 test_returns_false_for_none_run_dir
- **驗證行為**: run_dir=None → 回傳 False
- **被測函式**: `lib.completion_gate.persist_run_failure()`
- **斷言**: result=False
- **實際結果**: PASSED

#### 2.5.4 test_returns_false_for_missing_summary
- **驗證行為**: summary.json 不存在 → 回傳 False
- **被測函式**: `lib.completion_gate.persist_run_failure()`
- **斷言**: result=False
- **實際結果**: PASSED

#### 2.5.5 test_returns_false_for_corrupted_summary
- **驗證行為**: summary.json 損壞 → 回傳 False
- **被測函式**: `lib.completion_gate.persist_run_failure()`
- **斷言**: result=False
- **實際結果**: PASSED

#### 2.5.6 test_overwrites_existing_completed_status
- **驗證行為**: persist_run_failure 覆蓋原本的 completed 狀態
- **被測函式**: `lib.completion_gate.persist_run_failure()`
- **斷言**: summary.json 含 completion_status=failed, reason_code=LATE_FAILURE
- **實際結果**: PASSED

#### 2.5.7 test_persists_rejection_reasons_list
- **驗證行為**: persist_run_failure 正確儲存 rejection_reasons 列表
- **被測函式**: `lib.completion_gate.persist_run_failure()`
- **斷言**: summary.json 含 rejection_reasons 與原始列表一致
- **實際結果**: PASSED

### 2.6 TestLoadRunEvidence (7 tests)

#### 2.6.1 test_valid_run_returns_artifacts_results_summary
- **驗證行為**: 正常 run 目錄 → 回傳完整 artifacts/results/summary
- **被測函式**: `lib.completion_gate.load_run_evidence()`
- **斷言**: "details.jsonl" in artifacts, results[0]["total_score"]=80.0, summary["average_score"]=80.0
- **實際結果**: PASSED

#### 2.6.2 test_missing_run_dir_returns_empty
- **驗證行為**: run 目錄不存在 → 回傳空結構
- **被測函式**: `lib.completion_gate.load_run_evidence()`
- **斷言**: artifacts={}, results=[], summary={}
- **實際結果**: PASSED

#### 2.6.3 test_none_run_dir_returns_empty
- **驗證行為**: run_dir=None → 回傳空結構
- **被測函式**: `lib.completion_gate.load_run_evidence()`
- **斷言**: artifacts={}, results=[], summary={}
- **實際結果**: PASSED

#### 2.6.4 test_empty_string_run_dir_returns_empty
- **驗證行為**: run_dir='' → 回傳空結構
- **被測函式**: `lib.completion_gate.load_run_evidence()`
- **斷言**: artifacts={}, results=[], summary={}
- **實際結果**: PASSED

#### 2.6.5 test_missing_summary_json_returns_empty_summary
- **驗證行為**: 缺少 summary.json → summary 為空
- **被測函式**: `lib.completion_gate.load_run_evidence()`
- **斷言**: "summary.json" not in artifacts, summary={}
- **實際結果**: PASSED

#### 2.6.6 test_missing_details_jsonl_returns_empty_results
- **驗證行為**: 缺少 details.jsonl → results 為空
- **被測函式**: `lib.completion_gate.load_run_evidence()`
- **斷言**: "details.jsonl" not in artifacts, results=[]
- **實際結果**: PASSED

#### 2.6.7 test_corrupted_details_returns_empty_results
- **驗證行為**: details.jsonl 損壞 → results 為空
- **被測函式**: `lib.completion_gate.load_run_evidence()`
- **斷言**: results=[]
- **實際結果**: PASSED

### 2.7 TestValidateEvidenceManifest (7 tests)

#### 2.7.1 test_valid_manifest_passes
- **驗證行為**: 有效 manifest → 回傳 verified 列表，無 errors
- **被測函式**: `lib.completion_gate.validate_evidence_manifest()`
- **斷言**: errors=[], len(verified)=1, verified[0]["verified"]=True
- **實際結果**: PASSED

#### 2.7.2 test_empty_manifest_returns_errors
- **驗證行為**: 空 manifest → 回傳 errors
- **被測函式**: `lib.completion_gate.validate_evidence_manifest()`
- **斷言**: errors 非空, "empty" in errors[0]
- **實際結果**: PASSED

#### 2.7.3 test_none_manifest_returns_errors
- **驗證行為**: manifest=None → 回傳 errors
- **被測函式**: `lib.completion_gate.validate_evidence_manifest()`
- **斷言**: errors 非空
- **實際結果**: PASSED

#### 2.7.4 test_manifest_with_non_dict_entry_returns_error
- **驗證行為**: manifest 含非 dict 項目 → 回傳 error
- **被測函式**: `lib.completion_gate.validate_evidence_manifest()`
- **斷言**: errors 非空, "not an object" in errors[0]
- **實際結果**: PASSED

#### 2.7.5 test_manifest_with_unverified_entry_returns_error
- **驗證行為**: manifest 含 verified=False 的項目 → 回傳 error
- **被測函式**: `lib.completion_gate.validate_evidence_manifest()`
- **斷言**: errors 非空, "not marked verified" in errors[0]
- **實際結果**: PASSED

#### 2.7.6 test_manifest_with_wrong_sha256_returns_error
- **驗證行為**: manifest sha256 與實際不符 → 回傳 sha256 mismatch error
- **被測函式**: `lib.completion_gate.validate_evidence_manifest()`
- **斷言**: errors 非空, "sha256 mismatch" in errors[0]
- **實際結果**: PASSED

#### 2.7.7 test_manifest_with_wrong_size_returns_error
- **驗證行為**: manifest size 與實際不符 → 回傳 size mismatch error
- **被測函式**: `lib.completion_gate.validate_evidence_manifest()`
- **斷言**: errors 非空, "size mismatch" in errors[0]
- **實際結果**: PASSED

### 2.8 TestEndToEndPersistedEvidence (3 tests)

#### 2.8.1 test_success_flow_validates_and_declares_completed
- **驗證行為**: 完整成功流程：建立有效 run → 驗證通過 → status=completed
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: status=completed, evidence_manifest 非空
- **實際結果**: PASSED

#### 2.8.2 test_failure_flow_rejects_and_persists_reason
- **驗證行為**: 完整失敗流程：建立無效 run → 驗證失敗 → 拒絕成功 → 持久化拒絕原因
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`, `persist_run_failure()`
- **斷言**: 第一次 verify status=failed, persist 成功, 第二次 verify 仍為 failed
- **實際結果**: PASSED

#### 2.8.3 test_tampered_evidence_rejected_after_persist
- **驗證行為**: 竄改產物後重新驗證：hash/size 不符 → 拒絕成功
- **被測函式**: `lib.completion_gate.verify_persisted_run_evidence()`
- **斷言**: 初始 status=completed, 竄改後 status=failed, reason_code=INVALID_EVIDENCE_MANIFEST, sha256 mismatch
- **實際結果**: PASSED

---

## 3. test_invalid_candidate_output.py (8 tests)

### 3.1 test_empty_completion_has_machine_readable_rejection
- **驗證行為**: 空完成結果 → 機器可讀的拒絕原因 (status=failed, reason_code=NO_VALID_OUTPUT)
- **被測函式**: `run_opt.evaluation_completion()`
- **斷言**: status=failed, reason_code=NO_VALID_OUTPUT, missing_evidence_types 非空
- **實際結果**: PASSED

### 3.2 test_nonzero_empty_completion_keeps_missing_evidence_types
- **驗證行為**: 非零退出碼 + 空完成 → 保留缺失證據類型
- **被測函式**: `lib.completion_gate.completion_disposition()`
- **斷言**: status=failed, reason_code=NONZERO_EXIT_CODE, missing_evidence_types=["artifacts", "results", "summary"]
- **實際結果**: PASSED

### 3.3 test_failed_candidate_is_not_scanned_for_selection
- **驗證行為**: 失敗候選不被掃描為可選優候選
- **被測函式**: `run_opt.mark_candidate_evaluation_failed()`, `auto_evolve.scan_candidate_evaluations()`
- **斷言**: scorecard status=failed, scan_candidate_evaluations() == []
- **實際結果**: PASSED

### 3.4 test_rejected_candidate_with_stale_score_is_not_scanned_for_selection
- **驗證行為**: 已拒絕候選（帶舊分數）不被掃描為可選優候選
- **被測函式**: `auto_evolve.scan_candidate_evaluations()`
- **斷言**: scan_candidate_evaluations() == []
- **實際結果**: PASSED

### 3.5 test_empty_run_is_rejected_before_comparison
- **驗證行為**: 空 run 在比較前被拒絕
- **被測函式**: `scripts.compare_runs.compare()`
- **斷言**: passed=False, average=0.0, difference=0.0, completion_status=failed, reason_code=NO_VALID_OUTPUT
- **實際結果**: PASSED

### 3.6 test_tampered_completed_manifest_is_failed_and_excluded
- **驗證行為**: 竄改的已完成 manifest 被標記為 failed 並排除
- **被測函式**: `scripts.compare_runs.compare()`
- **斷言**: compare 回傳 (False, 0.0, 0.0), completion_status=failed, reason_code=INVALID_EVIDENCE_MANIFEST
- **實際結果**: PASSED

### 3.7 test_candidate_scan_rejects_tampered_completed_stage
- **驗證行為**: 竄改的已完成階段候選被掃描拒絕
- **被測函式**: `auto_evolve.scan_candidate_evaluations()`
- **斷言**: scan 回傳 [], scorecard status=failed, completion_status=failed
- **實際結果**: PASSED

### 3.8 test_champion_selection_rejects_failed_comparison
- **驗證行為**: 失敗比較結果的候選不被選為冠軍
- **被測函式**: `run_opt.save_elite_candidate()`
- **斷言**: save_elite_candidate 回傳 [], scorecard status=failed, reason_code=INVALID_EVIDENCE_MANIFEST
- **實際結果**: PASSED

---

## 4. test_delivery_consistency_gate.py (7 tests)

### 4.1 test_head_mismatch_is_unproven_and_has_rerun_commands
- **驗證行為**: HEAD commit 不符 → status=unproven, code=INCOMPLETE_EVIDENCE, 含重新執行指令
- **被測函式**: `scripts.best_version_report.verify_delivery_consistency()`
- **斷言**: status=unproven, code=INCOMPLETE_EVIDENCE, inconsistencies 含 "HEAD", rerun_commands 含 "best_version_report.py"
- **實際結果**: PASSED

### 4.2 test_preflight_head_mismatch_is_unproven
- **驗證行為**: 預檢 HEAD 不符 → status=unproven
- **被測函式**: `scripts.best_version_report.verify_delivery_consistency()`
- **斷言**: status=unproven, inconsistencies 含 "預檢 HEAD"
- **實際結果**: PASSED

### 4.3 test_undeclared_worktree_change_blocks_best_claim
- **驗證行為**: 未宣告的工作區變更阻擋最佳聲明
- **被測函式**: `scripts.best_version_report.verify_delivery_consistency()`
- **斷言**: valid=False, undeclared_changes 含 "unrelated.py"
- **實際結果**: PASSED

### 4.4 test_candidate_recorded_diff_mismatch_is_unproven
- **驗證行為**: 候選記錄的 diff 不符 → status=unproven
- **被測函式**: `scripts.best_version_report.verify_delivery_consistency()`
- **斷言**: valid=False, inconsistencies 含 "git_diff"
- **實際結果**: PASSED

### 4.5 test_git_provenance_marks_committed_files
- **驗證行為**: Git 來源標記已提交檔案
- **被測函式**: `scripts.best_version_report.verify_delivery_consistency()`
- **斷言**: provenance_map["prompts/baseline.md"] == "committed"
- **實際結果**: PASSED

### 4.6 test_git_provenance_marks_diff_tracked_files
- **驗證行為**: Git 來源標記 diff 追蹤檔案
- **被測函式**: `scripts.best_version_report.verify_delivery_consistency()`
- **斷言**: provenance_map["prompts/baseline.md"] == "diff_tracked"
- **實際結果**: PASSED

### 4.7 test_git_provenance_marks_undeclared_as_untracked
- **驗證行為**: Git 來源標記未宣告檔案為 untracked_worktree
- **被測函式**: `scripts.best_version_report.verify_delivery_consistency()`
- **斷言**: provenance_map.get("untracked_draft.md") == "untracked_worktree"
- **實際結果**: PASSED

---

## 5. test_product_diff_audit.py (5 tests, 1 skipped on Windows)

### 5.1 test_product_code_should_not_be_edited_for_coverage_tuning
- **驗證行為**: 受保護產品檔案未被未授權修改（防湊覆蓋率）
- **被測函式**: `tests/test_product_diff_audit._diff_paths()`, `_is_protected_product_file()`
- **斷言**: unexpected 為空列表
- **實際結果**: PASSED

### 5.2 test_diff_paths_handles_platform_paths_unicode_and_line_endings
- **驗證行為**: 跨平台路徑（POSIX/Windows）、Unicode、行尾符號正確處理
- **被測函式**: `tests/test_product_diff_audit._diff_paths()`
- **斷言**: 回傳路徑正確, 命令列參數正確
- **實際結果**: PASSED

### 5.3 test_windows_drive_path_to_posix_translation
- **驗證行為**: Windows 磁碟路徑正確轉譯為 WSL /mnt 形式
- **被測函式**: `tests/test_product_diff_audit._windows_drive_path_to_posix()`
- **斷言**: D:\... → /mnt/d/..., 非磁碟路徑 → None
- **實際結果**: PASSED

### 5.4 test_git_status_kwargs_sets_env_for_windows_gitdir (skipped on Windows)
- **驗證行為**: 非 Windows 環境下 GIT_DIR/GIT_WORK_TREE 正確注入
- **被測函式**: `tests/test_product_diff_audit._git_env_overrides()`, `_git_status_kwargs()`
- **斷言**: (此案例在 Windows 上被跳過)
- **實際結果**: SKIPPED

### 5.5 test_simulate_linux_macos_git_failure_and_success
- **驗證行為**: 模擬 Linux/macOS 環境下 git 失敗/成功輸出
- **被測函式**: `tests/test_product_diff_audit._diff_paths()`
- **斷言**: 失敗時拋出 RuntimeError, 成功時回傳正確路徑
- **實際結果**: PASSED

---

## 佐證檔清單

| 檔案 | 內容 |
|---|---|
| `docs/evidence/acceptance-test-output.txt` | 67 個驗收測試的完整詳細輸出（含 traceback） |
| `docs/evidence/full-test-output.txt` | 全量 1293 個測試的摘要輸出 |
| `docs/evidence/full-test-coverage.txt` | 全量測試覆蓋率報告（80% overall） |
| `docs/acceptance-evidence-report.md` | 本報告：每個測試對應的驗證行為 |

---

## 結論

共 68 個驗收測試（67 passed, 1 skipped），涵蓋以下核心行為：

1. **產物證據完整性** (5 tests): 檔案 SHA-256/size 驗證、工作區邊界檢查、不可讀拒絕
2. **持久化證據驗證** (43 tests): run 目錄存在性、summary 完整性、manifest 一致性、竄改偵測、拒絕原因持久化
3. **候選排除機制** (8 tests): 空完成拒絕、失敗候選排除、竄改 manifest 偵測、冠軍選優閘門
4. **交付一致性閘門** (7 tests): HEAD commit 比對、未宣告變更偵測、Git 來源追蹤
5. **產品差異審計** (5 tests): 受保護檔案防護、跨平台路徑處理、git 狀態解析

全量測試 1293 passed, 0 failed，覆蓋率 80%。所有測試皆可追溯至具體的目標行為與被測函式。
