# `experiment_report` snapshot 回歸證據

日期：2026-08-02

## 定向測試紅→綠

紅（暫時移除既有 `run_count < 1` guard，模擬實作前；exit code：1）：

```text
F                                                                        [100%]
================================== FAILURES ===================================
_ ArchitectureSurfaceTests.test_experiment_report_snapshot_rejects_semantically_wrong_output _
tests\test_architecture_surface.py:184: in test_experiment_report_snapshot_rejects_semantically_wrong_output
    with self.assertRaises(ValueError):
E   AssertionError: ValueError not raised
=========================== short test summary info ============================
FAILED tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_rejects_semantically_wrong_output
1 failed in 6.46s
```

指令：

```text
python -m pytest tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_rejects_semantically_wrong_output -q --no-cov --tb=short
```

綠（還原 guard 後；exit code：0）：

```text
.                                                                        [100%]
1 passed in 0.08s
```

## 完整回歸

指令：

```text
python -m pytest tests/ -q --deselect tests/test_architecture_surface.py::ArchitectureSurfaceTests::test_experiment_report_snapshot_contract
```

實際尾段（exit code：0）：

```text
...................................................................      [100%]
--------------------------------------------------------------------------------------
TOTAL                                       4556   1048   1582     95    76%
1145 passed, 2 skipped, 1 deselected in 98.35s (0:01:38)
```

備註：首次執行完整指令於 124 秒逾時；提高等待上限後以相同指令重跑並取得上述通過結果。
