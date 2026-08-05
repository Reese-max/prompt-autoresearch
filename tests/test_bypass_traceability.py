# -*- coding: utf-8 -*-
"""旁路重評追溯鏈中繼資料測試。

驗證：
1. 報告 meta 包含所有必要追溯中繼資料欄位。
2. 產物路徑完整且可追溯。
3. 新版本 ID 與不可變儲存一致。
4. 追溯鏈驗證通過。
5. 缺少任何欄位時驗證失敗。
"""
import hashlib
import json
from pathlib import Path

import scripts.bypass_reevaluate as bre
from lib import immutable_store as ims
from lib.version import (
    get_program_version,
    compute_input_settings_hash,
    get_baseline_info,
)


# ---------------------------------------------------------------------------
# lib.version 基礎測試
# ---------------------------------------------------------------------------

def test_get_program_version_returns_string():
    v = get_program_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_compute_input_settings_hash_deterministic():
    h1 = compute_input_settings_hash(cli_args={"seed_old": 42, "seed_new": 99})
    h2 = compute_input_settings_hash(cli_args={"seed_old": 42, "seed_new": 99})
    assert h1 == h2
    assert len(h1) == 64


def test_compute_input_settings_hash_sensitive_to_args():
    h1 = compute_input_settings_hash(cli_args={"seed_old": 42})
    h2 = compute_input_settings_hash(cli_args={"seed_old": 99})
    assert h1 != h2


def test_get_baseline_info_returns_required_fields(tmp_path):
    md = tmp_path / "baseline.md"
    md.write_text("test baseline content", encoding="utf-8")
    meta = tmp_path / "baseline.meta.json"
    meta.write_text(json.dumps({
        "prompt_hash": "abc123def456",
        "updated_at": "2026-08-05 00:00:00",
    }), encoding="utf-8")
    info = get_baseline_info(baseline_md_path=md, baseline_meta_path=meta)
    assert "baseline_version" in info
    assert "baseline_hash" in info
    assert info["baseline_version"] == "abc123def456"
    assert info["baseline_hash"] == hashlib.sha256("test baseline content".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 報告追溯中繼資料完整性
# ---------------------------------------------------------------------------

def test_report_meta_contains_all_traceability_fields(tmp_path):
    """報告 meta 包含所有必要追溯中繼資料欄位（new_version_id 在持久化前為 None）。"""
    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    report = bre.generate_report(results, 3.0, 5)

    meta = report["meta"]
    for field in bre.REQUIRED_TRACEABILITY_FIELDS:
        assert field in meta, f"meta 缺少追溯欄位: {field}"

    assert isinstance(meta["source_baseline_version"], str)
    assert isinstance(meta["source_baseline_hash"], str)
    assert isinstance(meta["input_settings_hash"], str)
    assert isinstance(meta["program_version"], str)
    assert isinstance(meta["timestamp"], str)
    assert isinstance(meta["artifact_locations"], dict)


def test_report_artifact_locations_complete(tmp_path):
    """報告 artifact_locations 包含所有必要產物路徑。"""
    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    report = bre.generate_report(results, 3.0, 5)

    artifacts = report["meta"]["artifact_locations"]
    for key in ["report_json", "report_md", "immutable_store", "immutable_rows"]:
        assert key in artifacts, f"artifact_locations 缺少: {key}"
        assert artifacts[key], f"artifact_locations[{key}] 為空"


# ---------------------------------------------------------------------------
# enrich_report_version_id
# ---------------------------------------------------------------------------

def test_enrich_report_version_id_populates_fields(tmp_path):
    """enrich_report_version_id 正確回填版本 ID 與產物路徑。"""
    store_dir = tmp_path / "versions"
    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    report = bre.generate_report(results, 3.0, 5)

    assert report["meta"]["new_version_id"] is None

    outcome = bre.persist_immutable_report(report, store_dir=store_dir)
    bre.enrich_report_version_id(report, outcome)

    assert report["meta"]["new_version_id"] == outcome["version_id"]
    assert report["meta"]["artifact_locations"]["immutable_report"] == outcome["path"]
    assert report["meta"]["artifact_locations"]["immutable_report_content_hash"] == outcome["content_hash"]


# ---------------------------------------------------------------------------
# verify_traceability_chain 完整追溯鏈
# ---------------------------------------------------------------------------

def test_verify_traceability_chain_passes_on_complete_report(tmp_path):
    """完整報告的追溯鏈驗證通過。"""
    store_dir = tmp_path / "versions"
    rows_path = tmp_path / "rows.jsonl"

    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    report = bre.generate_report(results, 3.0, 5)

    outcome = bre.persist_immutable_report(report, store_dir=store_dir)
    bre.enrich_report_version_id(report, outcome)

    chain = bre.verify_traceability_chain(report, store_dir=store_dir)
    assert chain["valid"] is True, f"追溯鏈驗證失敗: {chain['errors']}"
    assert chain["errors"] == []


# ---------------------------------------------------------------------------
# verify_traceability_chain 驗證缺失欄位
# ---------------------------------------------------------------------------

def test_verify_traceability_chain_fails_when_field_missing(tmp_path):
    """缺少追溯欄位時驗證失敗。"""
    store_dir = tmp_path / "versions"
    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    report = bre.generate_report(results, 3.0, 5)

    outcome = bre.persist_immutable_report(report, store_dir=store_dir)
    bre.enrich_report_version_id(report, outcome)

    for field in bre.REQUIRED_TRACEABILITY_FIELDS:
        modified = json.loads(json.dumps(report))
        modified["meta"][field] = None
        chain = bre.verify_traceability_chain(modified, store_dir=store_dir)
        assert chain["valid"] is False, f"移除 {field} 後應驗證失敗"
        assert any(f"missing_field:{field}" in e for e in chain["errors"])


def test_verify_traceability_chain_fails_when_artifact_missing(tmp_path):
    """缺少產物路徑時驗證失敗。"""
    store_dir = tmp_path / "versions"
    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    report = bre.generate_report(results, 3.0, 5)

    outcome = bre.persist_immutable_report(report, store_dir=store_dir)
    bre.enrich_report_version_id(report, outcome)

    for key in bre.REQUIRED_ARTIFACT_KEYS:
        modified = json.loads(json.dumps(report))
        modified["meta"]["artifact_locations"][key] = ""
        chain = bre.verify_traceability_chain(modified, store_dir=store_dir)
        assert chain["valid"] is False, f"移除 artifact {key} 後應驗證失敗"
        assert any(f"missing_artifact:{key}" in e for e in chain["errors"])


def test_verify_traceability_chain_fails_when_version_not_found(tmp_path):
    """版本 ID 指向不存在的版本時驗證失敗。"""
    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, 42, 99, 5)
    report = bre.generate_report(results, 3.0, 5)

    report["meta"]["new_version_id"] = "bypass-reeval-report-nonexistent000000"
    report["meta"]["artifact_locations"]["immutable_report"] = "nonexistent.json"
    report["meta"]["artifact_locations"]["immutable_report_content_hash"] = "a" * 64

    chain = bre.verify_traceability_chain(report, store_dir=tmp_path / "nonexistent")
    assert chain["valid"] is False
    assert any("version_not_found" in e for e in chain["errors"])


# ---------------------------------------------------------------------------
# 端到端：從收集到驗證的完整追溯鏈
# ---------------------------------------------------------------------------

def test_e2e_traceability_chain_from_collection_to_verification(tmp_path):
    """端到端測試：收集 prompt → 重評 → 持久化 → 回填 → 驗證追溯鏈。"""
    store_dir = tmp_path / "versions"
    rows_path = tmp_path / "rows.jsonl"

    items = bre.collect_prompts()
    assert len(items) > 0, "應至少收集到一個 prompt"

    results = bre.run_bypass_reeval(items, 42, 99, 5)
    assert len(results) == len(items)

    report = bre.generate_report(results, 3.0, 5)
    meta = report["meta"]

    assert meta["source_baseline_version"] != "unknown" or meta["source_baseline_hash"]
    assert len(meta["input_settings_hash"]) == 64
    assert len(meta["program_version"]) > 0

    result_records = bre.persist_immutable_results(results, store_dir=store_dir, rows_path=rows_path)
    assert all(r["stored"] for r in result_records)

    report_outcome = bre.persist_immutable_report(report, store_dir=store_dir)
    assert report_outcome["stored"] is True

    bre.enrich_report_version_id(report, report_outcome)
    assert report["meta"]["new_version_id"] == report_outcome["version_id"]

    chain = bre.verify_traceability_chain(report, store_dir=store_dir)
    assert chain["valid"] is True, f"端到端追溯鏈驗證失敗: {chain['errors']}"
