# -*- coding: utf-8 -*-
"""不可變基準儲存機制測試。

驗證：
1. 內容雜湊與唯一版本 ID 由內容派生，相同內容 → 相同版本，不同內容 → 不同版本。
2. store_version 對既有版本一律拒絕覆寫（目標版本已存在 → 拒絕操作）。
3. 資料列以 append-only 累積，重複內容雜湊的資料列拒絕加入。
4. 旁路重評整合：重跑不會覆寫既有基準檔、資料列或版本。
5. 所有版本／資料列以內容雜湊與唯一版本 ID 可機械追溯。
"""
import hashlib
import json
from pathlib import Path

import scripts.bypass_reevaluate as bre
from lib import immutable_store as ims


# ---------------------------------------------------------------------------
# 內容雜湊與唯一版本 ID
# ---------------------------------------------------------------------------

def test_content_hash_is_deterministic_and_content_sensitive():
    payload = {"group": "candidate", "path": "prompts/candidates/a.md", "new_score": 80.5}
    ch1 = ims.content_hash(payload)
    ch2 = ims.content_hash({"path": "prompts/candidates/a.md", "group": "candidate", "new_score": 80.5})
    ch3 = ims.content_hash({"group": "candidate", "path": "prompts/candidates/a.md", "new_score": 80.6})
    assert ch1 == ch2, "相同內容（欄位順序不同）應有相同內容雜湊"
    assert ch1 != ch3, "不同內容應有不同內容雜湊"
    assert len(ch1) == 64, "內容雜湊應為 SHA-256 全長"


def test_derive_version_id_unique_per_content_hash():
    vid1 = ims.derive_version_id("a" * 64, namespace="bypass-reeval")
    vid2 = ims.derive_version_id("b" * 64, namespace="bypass-reeval")
    vid3 = ims.derive_version_id("a" * 64, namespace="bypass-reeval-report")
    assert vid1.startswith("bypass-reeval-")
    assert vid1 != vid2, "不同內容雜湊應有不同版本 ID"
    assert vid1 != vid3, "不同命名空間應有不同版本 ID"
    assert vid1 == ims.derive_version_id("a" * 64, namespace="bypass-reeval"), "同內容同命名空間應同版本 ID"


# ---------------------------------------------------------------------------
# store_version：既有版本拒絕覆寫
# ---------------------------------------------------------------------------

def test_store_version_creates_new_version_with_traceable_identity(tmp_path):
    payload = {"path": "prompts/candidates/a.md", "new_score": 81.0}
    outcome = ims.store_version(payload, tmp_path, namespace="bypass-reeval")
    assert outcome["stored"] is True
    assert outcome["rejected"] is False
    assert outcome["content_hash"] == ims.content_hash(payload)
    assert outcome["version_id"] == ims.derive_version_id(outcome["content_hash"], "bypass-reeval")
    assert Path(outcome["path"]).exists()
    stored = json.loads(Path(outcome["path"]).read_text(encoding="utf-8"))
    assert stored == payload, "版本內容應與原始 payload 一致"


def test_store_version_rejects_when_target_version_exists(tmp_path):
    payload = {"path": "prompts/candidates/a.md", "new_score": 81.0}
    first = ims.store_version(payload, tmp_path, namespace="bypass-reeval")
    second = ims.store_version(payload, tmp_path, namespace="bypass-reeval")
    assert first["stored"] is True
    assert second["stored"] is False
    assert second["rejected"] is True
    assert second["reason"] == "version_already_exists"
    assert second["version_id"] == first["version_id"]
    raw = Path(first["path"]).read_text(encoding="utf-8")
    assert json.loads(raw) == payload, "既有版本不應被覆寫"


def test_store_version_never_overwrites_existing_file(tmp_path):
    payload = {"new_score": 82.0}
    ims.store_version(payload, tmp_path, namespace="bypass-reeval")
    victim_path = ims.version_path(tmp_path, ims.derive_version_id(ims.content_hash(payload), "bypass-reeval"))
    victim_path.write_text("original content", encoding="utf-8")
    outcome = ims.store_version(payload, tmp_path, namespace="bypass-reeval")
    assert outcome["rejected"] is True
    assert victim_path.read_text(encoding="utf-8") == "original content", "既有檔案不得被覆寫"


def test_store_version_distinct_content_creates_distinct_versions(tmp_path):
    a = ims.store_version({"new_score": 80.0}, tmp_path, namespace="bypass-reeval")
    b = ims.store_version({"new_score": 90.0}, tmp_path, namespace="bypass-reeval")
    assert a["version_id"] != b["version_id"]
    assert a["stored"] is True and b["stored"] is True
    versions = ims.list_versions(tmp_path)
    assert a["version_id"] in versions
    assert b["version_id"] in versions


# ---------------------------------------------------------------------------
# append_row：資料列不可覆寫、不可重複
# ---------------------------------------------------------------------------

def test_append_row_accumulates_without_overwriting(tmp_path):
    rows_path = tmp_path / "rows.jsonl"
    r1 = ims.append_row(rows_path, {"path": "a.md", "new_score": 80.0})
    r2 = ims.append_row(rows_path, {"path": "b.md", "new_score": 85.0})
    assert r1["appended"] is True and r2["appended"] is True
    rows = ims.read_rows(rows_path)
    assert len(rows) == 2, "資料列應累積而非覆寫"
    assert rows[0]["content_hash"] != rows[1]["content_hash"]


def test_append_row_rejects_duplicate_content_hash(tmp_path):
    rows_path = tmp_path / "rows.jsonl"
    row = {"path": "a.md", "new_score": 80.0}
    first = ims.append_row(rows_path, row)
    second = ims.append_row(rows_path, row)
    assert first["appended"] is True
    assert second["appended"] is False
    assert second["rejected"] is True
    assert len(ims.read_rows(rows_path)) == 1, "重複內容雜湊資料列不得加入"


# ---------------------------------------------------------------------------
# 旁路重評整合：重跑不覆寫既有基準檔、資料列或版本
# ---------------------------------------------------------------------------

def test_bypass_rerun_does_not_overwrite_existing_versions(tmp_path):
    store_dir = tmp_path / "versions"
    rows_path = tmp_path / "rows.jsonl"

    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)

    first = bre.persist_immutable_results(results, store_dir=store_dir, rows_path=rows_path)
    assert all(r["stored"] for r in first), "首次應全部建立新版本"

    second = bre.persist_immutable_results(results, store_dir=store_dir, rows_path=rows_path)
    assert all(r["rejected"] for r in second), "相同結果重跑應全部拒絕覆寫"
    assert all(r["stored"] is False for r in second)

    versions = ims.list_versions(store_dir)
    assert len(versions) == len(first), "重跑不得新增或覆寫版本"
    rows = ims.read_rows(rows_path)
    assert len(rows) == len(first), "重跑不得新增重複資料列"


def test_bypass_report_version_rejects_on_identical_rerun(tmp_path):
    report = {
        "meta": {"timestamp": "2026-08-05 00:00:00", "cache_namespace": ".cache/bypass_eval/"},
        "per_item": [{"path": "a.md", "old_score": 80.0, "new_score": 81.0}],
        "conclusion": {"overall_pass": True},
    }
    first = bre.persist_immutable_report(report, store_dir=tmp_path)
    second = bre.persist_immutable_report(report, store_dir=tmp_path)
    assert first["stored"] is True
    assert second["stored"] is False
    assert second["rejected"] is True
    assert second["version_id"] == first["version_id"]
    assert Path(first["path"]).exists()
    assert json.loads(Path(first["path"]).read_text(encoding="utf-8")) == report


def baseline_bytes():
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "prompts" / "baseline.md").read_bytes()


def meta_bytes():
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "prompts" / "baseline.meta.json").read_text(encoding="utf-8")


def test_persist_results_preserves_baseline_file(tmp_path):
    store_dir = tmp_path / "versions"
    rows_path = tmp_path / "rows.jsonl"

    baseline_hash_before = hashlib.sha256(baseline_bytes()).hexdigest()
    meta_raw_before = meta_bytes()

    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    bre.persist_immutable_results(results, store_dir=store_dir,
                                  rows_path=rows_path)
    bre.persist_immutable_report(
        bre.generate_report(results, 3.0), store_dir=store_dir,
    )

    assert hashlib.sha256(baseline_bytes()).hexdigest() == baseline_hash_before
    assert meta_bytes() == meta_raw_before, "基準 meta 不應被改動"
