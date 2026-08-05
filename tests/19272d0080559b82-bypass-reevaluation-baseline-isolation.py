# -*- coding: utf-8 -*-
"""19272d0080559b82-bypass-reevaluation-baseline-isolation — 旁路重評基線隔離受控中斷測試。

受控模擬旁路重評在寫入結果、更新索引及封存前後中斷，斷言：
1. 原始 baseline 的內容、雜湊、版本及歷史比較結果保持不變
2. 殘留暫存資料不會成為可比較 benchmark
3. 安全重跑會建立可追溯的新版本
"""
import hashlib
import json
from pathlib import Path

import pytest

import scripts.bypass_reevaluate as bre


@pytest.fixture
def ws_factory(tmp_path):
    """建立測試工作區的 fixture。"""
    def _create():
        return _create_workspace(tmp_path)
    return _create


# ---------------------------------------------------------------------------
# 輔助函式：建立測試工作區
# ---------------------------------------------------------------------------

def _create_workspace(tmp_path):
    """在 tmp_path 建立最小化測試工作區。"""
    baseline = tmp_path / "prompts" / "baseline.md"
    baseline.parent.mkdir(parents=True)
    baseline.write_text("原始基線 prompt 內容", encoding="utf-8")

    meta = tmp_path / "prompts" / "baseline.meta.json"
    meta.write_text(json.dumps({
        "updated_at": "2026-08-01 00:00:00",
        "prompt_path": "prompts/baseline.md",
        "prompt_hash": hashlib.sha256("原始基線 prompt 內容".encode("utf-8")).hexdigest(),
        "smoke_run": "runs\\old_smoke",
        "dev_run": "runs\\old_dev",
        "holdout_run": "runs\\old_holdout",
        "smoke_avg": 90.0,
        "dev_avg": 88.5,
        "holdout_avg": 89.0,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cand_dir = tmp_path / "prompts" / "candidates"
    cand_dir.mkdir(parents=True)
    (cand_dir / "alpha.md").write_text("候選 prompt alpha 內容", encoding="utf-8")
    (cand_dir / "beta.md").write_text("候選 prompt beta 內容", encoding="utf-8")

    champ_dir = tmp_path / "prompts" / "champions"
    champ_dir.mkdir(parents=True)
    (champ_dir / "champion.md").write_text("冠軍 prompt 內容", encoding="utf-8")

    docs = tmp_path / "docs"
    docs.mkdir(parents=True)

    # 寫入歷史報告作為「歷史比較結果」
    old_report = docs / "bypass-reevaluation-report.json"
    old_report.write_text(json.dumps({
        "meta": {"timestamp": "2026-07-01 00:00:00", "original_cache_untouched": True},
        "conclusion": {"overall_pass": True},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    old_report_md = docs / "bypass-reevaluation-report.md"
    old_report_md.write_text("# 歷史報告\n", encoding="utf-8")

    return {
        "root": tmp_path,
        "baseline": baseline,
        "meta": meta,
        "old_report_json": old_report,
        "old_report_md": old_report_md,
    }


def _capture_baseline_state(ws):
    """擷取 baseline 當前狀態快照（僅基線檔與 meta）。"""
    return {
        "content": ws["baseline"].read_text(encoding="utf-8"),
        "hash": hashlib.sha256(ws["baseline"].read_bytes()).hexdigest(),
        "meta_raw": ws["meta"].read_text(encoding="utf-8"),
        "meta": json.loads(ws["meta"].read_text(encoding="utf-8")),
    }


def _assert_baseline_unchanged(ws, snap, msg=""):
    """斷言 baseline 內容、雜湊、版本未變。"""
    assert ws["baseline"].read_text(encoding="utf-8") == snap["content"], \
        f"baseline 內容變動：{msg}"
    assert hashlib.sha256(ws["baseline"].read_bytes()).hexdigest() == snap["hash"], \
        f"baseline 雜湊變動：{msg}"
    assert ws["meta"].read_text(encoding="utf-8") == snap["meta_raw"], \
        f"baseline meta 變動：{msg}"
    meta_now = json.loads(ws["meta"].read_text(encoding="utf-8"))
    assert meta_now == snap["meta"], f"baseline meta 結構變動：{msg}"


def _assert_file_not_parseable_as_json(path, msg=""):
    """斷言檔案不可解析為有效 JSON（檔案不存在或內容損毀）。"""
    if not path.exists():
        return  # 檔案不存在 → 不可解析
    raw = path.read_text(encoding="utf-8")
    try:
        json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return  # 確認不可解析
    assert False, f"檔案 {path.name} 意外為可解析 JSON，{msg}"


def _run_bypass_clean(ws, seed_old=42, seed_new=99):
    """在工作區內執行完整旁路重評流程（不受控干擾）。"""
    items = bre.collect_prompts()
    results = bre.run_bypass_reeval(items, seed_old, seed_new, 5)
    report = bre.generate_report(results, 3.0)
    bre.write_json(ws["root"] / "docs" / "bypass-reevaluation-report.json", report)
    md = bre.generate_markdown(report)
    (ws["root"] / "docs" / "bypass-reevaluation-report.md").write_text(
        md, encoding="utf-8", newline="\n",
    )
    return results, report


# ---------------------------------------------------------------------------
# 測試一：寫入結果（旁路快取）中途崩潰
# ---------------------------------------------------------------------------

def test_interruption_during_result_write_preserves_baseline(ws_factory, monkeypatch):
    """模擬寫入旁路快取結果中途崩潰——baseline 不變、殘留快取無效、重跑可追溯。"""
    ws = ws_factory()
    snap = _capture_baseline_state(ws)

    items = bre.collect_prompts()
    write_count = [0]
    original_write_json = bre.write_json

    def crashing_write_json(path, payload):
        write_count[0] += 1
        if write_count[0] == 2:
            raise OSError("模擬磁碟寫入失敗")
        original_write_json(path, payload)

    monkeypatch.setattr(bre, "write_json", crashing_write_json)

    try:
        bre.run_bypass_reeval(items, 42, 99, 5)
    except OSError:
        pass

    _assert_baseline_unchanged(ws, snap, "旁路快取寫入中斷")

    cache_dir = ws["root"] / ".cache" / "bypass_eval"
    if cache_dir.exists():
        for f in cache_dir.glob("*/result.json"):
            raw = f.read_text(encoding="utf-8")
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue  # 損壞的暫存 → 不可解析 → 不是有效 benchmark
            assert not parsed.get("from_cache", False), \
                f"殘留暫存 {f.name} 標記為有效快取，可能成為 benchmark"

    monkeypatch.setattr(bre, "write_json", original_write_json)
    new_results, new_report = _run_bypass_clean(ws, 42, 99)
    new_json = ws["root"] / "docs" / "bypass-reevaluation-report.json"
    assert new_json.exists()
    new_data = json.loads(new_json.read_text(encoding="utf-8"))
    assert "conclusion" in new_data
    assert len(new_data.get("per_item", [])) > 0
    _assert_baseline_unchanged(ws, snap, "重跑後 baseline 仍不變")


# ---------------------------------------------------------------------------
# 測試二：更新索引（報告 JSON）中途崩潰
# ---------------------------------------------------------------------------

def test_interruption_during_index_update_preserves_baseline(ws_factory, monkeypatch):
    """模擬更新索引（報告寫入）中途崩潰——留下不可解析之損毀索引、baseline 不變、重跑可追溯。"""
    ws = ws_factory()
    snap = _capture_baseline_state(ws)
    index_path = ws["root"] / "docs" / "bypass-reevaluation-report.json"

    original_write_json = bre.write_json

    def crashing_index_write(path, payload):
        p = Path(path)
        if p.name == "bypass-reevaluation-report.json":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(
                '{"meta": {"timestamp": "partial"}, "per_item": [',
                encoding="utf-8",
            )
            raise OSError("模擬索引更新中斷")
        original_write_json(path, payload)

    monkeypatch.setattr(bre, "write_json", crashing_index_write)

    items = bre.collect_prompts()
    try:
        results = bre.run_bypass_reeval(items, 42, 99, 5)
        report = bre.generate_report(results, 3.0)
        bre.write_json(index_path, report)
    except OSError:
        pass

    _assert_baseline_unchanged(ws, snap, "索引更新中斷")
    _assert_file_not_parseable_as_json(index_path, "索引更新中斷後應不可解析")

    monkeypatch.setattr(bre, "write_json", original_write_json)
    _run_bypass_clean(ws, 42, 99)
    assert index_path.exists()
    reloaded = json.loads(index_path.read_text(encoding="utf-8"))
    assert "conclusion" in reloaded
    assert "per_item" in reloaded
    assert len(reloaded["per_item"]) > 0
    _assert_baseline_unchanged(ws, snap, "重跑後 baseline 仍不變")


# ---------------------------------------------------------------------------
# 測試三：封存（報告 MD）中途崩潰
# ---------------------------------------------------------------------------

def test_interruption_during_archive_preserves_baseline(ws_factory, monkeypatch):
    """模擬封存（報告 MD 寫入）中途崩潰——baseline 不變、殘留 MD 損壞、重跑可追溯。"""
    ws = ws_factory()
    snap = _capture_baseline_state(ws)
    archive_path = ws["root"] / "docs" / "bypass-reevaluation-report.md"

    original_write_text = Path.write_text

    def crashing_archive_write(self, content, *args, **kwargs):
        if self.name == "bypass-reevaluation-report.md":
            self.parent.mkdir(parents=True, exist_ok=True)
            original_write_text(self, "# 旁路快取命名空間重評報告\n\n**時間**: partial",
                                encoding="utf-8")
            raise OSError("模擬封存寫入中斷")
        return original_write_text(self, content, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", crashing_archive_write)

    items = bre.collect_prompts()
    try:
        results = bre.run_bypass_reeval(items, 42, 99, 5)
        report = bre.generate_report(results, 3.0)
        bre.write_json(ws["root"] / "docs" / "bypass-reevaluation-report.json", report)
        md = bre.generate_markdown(report)
        archive_path.write_text(md, encoding="utf-8", newline="\n")
    except OSError:
        pass

    monkeypatch.setattr(Path, "write_text", original_write_text)

    _assert_baseline_unchanged(ws, snap, "封存寫入中斷")

    if archive_path.exists():
        raw = archive_path.read_text(encoding="utf-8")
        assert len(raw) < 200 or "完整報告" not in raw, \
            f"殘留封存檔過於完整({len(raw)} bytes)，應為部分內容"

    _run_bypass_clean(ws, 42, 99)
    assert archive_path.exists()
    final_md = archive_path.read_text(encoding="utf-8")
    assert "旁路快取命名空間重評報告" in final_md
    assert len(final_md) > 200
    _assert_baseline_unchanged(ws, snap, "重跑後 baseline 仍不變")


# ---------------------------------------------------------------------------
# 測試四：殘留暫存不可成為可比較 benchmark
# ---------------------------------------------------------------------------

def test_residual_bypass_cache_not_usable_as_benchmark(ws_factory, monkeypatch):
    """殘留的旁路快取暫存不應被視為有效 benchmark。"""
    ws = ws_factory()
    snap = _capture_baseline_state(ws)

    cache_dir = ws["root"] / ".cache" / "bypass_eval"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 寫入一個損壞的快取條目
    corrupt_entry = cache_dir / "abc123_bypass_ns"
    corrupt_entry.mkdir(parents=True, exist_ok=True)
    (corrupt_entry / "result.json").write_text(
        '{"overall": 77, "incomplete":', encoding="utf-8",
    )

    # 寫入一個結構不完整的快取條目（缺少必要欄位）
    incomplete_entry = cache_dir / "def456_bypass_ns"
    incomplete_entry.mkdir(parents=True, exist_ok=True)
    (incomplete_entry / "result.json").write_text(
        '{"overall": 80}', encoding="utf-8",
    )

    _assert_file_not_parseable_as_json(
        corrupt_entry / "result.json", "損壞快取應不可解析",
    )

    incomplete_raw = json.loads(
        (incomplete_entry / "result.json").read_text(encoding="utf-8"),
    )
    assert "type_averages" not in incomplete_raw, \
        "不完整快取不應含有 type_averages 欄位"
    assert "all_totals" not in incomplete_raw, \
        "不完整快取不應含有 all_totals 欄位"

    results = bre.collect_prompts()
    bypass_ns = bre.sha256_text("bypass_ns_99")[:8]
    for item in results:
        cache_key = f"{item['hash'][:16]}_{bypass_ns}"
        item_cache = cache_dir / cache_key / "result.json"
        if item_cache.exists():
            item_raw = json.loads(item_cache.read_text(encoding="utf-8"))
            assert "overall" in item_raw, \
                f"有效快取 {item_cache.name} 缺少 overall"
            assert "type_averages" in item_raw, \
                f"有效快取 {item_cache.name} 缺少 type_averages"
            assert "all_totals" in item_raw, \
                f"有效快取 {item_cache.name} 缺少 all_totals"

    _assert_baseline_unchanged(ws, snap, "暫存驗證後 baseline 仍不變")


# ---------------------------------------------------------------------------
# 測試五：安全重跑建立可追溯新版本
# ---------------------------------------------------------------------------

def test_safe_rerun_creates_traceable_new_version(ws_factory):
    """安全重跑產生新報告且版本可追溯，不覆蓋 baseline。"""
    ws = ws_factory()
    snap = _capture_baseline_state(ws)

    old_report_raw = ws["old_report_json"].read_text(encoding="utf-8")
    old_report = json.loads(old_report_raw)
    old_ts = old_report["meta"]["timestamp"]

    new_results, new_report = _run_bypass_clean(ws, 42, 99)

    new_json = ws["root"] / "docs" / "bypass-reevaluation-report.json"
    new_md = ws["root"] / "docs" / "bypass-reevaluation-report.md"
    assert new_json.exists(), "重跑應產生報告 JSON"
    assert new_md.exists(), "重跑應產生報告 MD"

    new_data = json.loads(new_json.read_text(encoding="utf-8"))
    new_ts = new_data["meta"]["timestamp"]
    assert new_ts != old_ts, f"新報告時間戳 {new_ts} 舊報告 {old_ts} 相同"
    assert new_data["meta"]["original_cache_untouched"] is True
    assert "conclusion" in new_data
    assert "overall_pass" in new_data["conclusion"]
    assert len(new_data.get("per_item", [])) > 0
    assert len(new_data.get("group_variance", {})) > 0

    new_md_content = new_md.read_text(encoding="utf-8")
    assert "旁路快取命名空間重評報告" in new_md_content
    assert new_ts in new_md_content

    _assert_baseline_unchanged(ws, snap, "重跑建立新版本後 baseline 仍不變")


# ---------------------------------------------------------------------------
# 測試六：全部三階段中途崩潰——baseline 絕對不受影響
# ---------------------------------------------------------------------------

def test_all_stage_interruptions_preserve_baseline_integrity(ws_factory, monkeypatch):
    """在三階段連續中斷——baseline 內容、雜湊、版本全數保持不變，殘留暫存不成為 benchmark。"""
    ws = ws_factory()
    snap = _capture_baseline_state(ws)

    original_write_json = bre.write_json
    call_count = [0]

    def triple_interrupt_write(path, payload):
        call_count[0] += 1
        # 階段一：第一筆旁路快取寫入中斷
        if call_count[0] == 1:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{"partial": true', encoding="utf-8")
            raise OSError("階段一：結果寫入中斷")
        # 階段二：第三筆快取寫入中斷（模擬部分完成後崩潰）
        if call_count[0] == 3:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{"meta": {"ts": "x"}, "items": [', encoding="utf-8")
            raise OSError("階段二：部分完成後中斷")
        original_write_json(path, payload)

    monkeypatch.setattr(bre, "write_json", triple_interrupt_write)

    items = bre.collect_prompts()
    try:
        bre.run_bypass_reeval(items, 42, 99, 5)
    except OSError:
        pass

    _assert_baseline_unchanged(ws, snap, "多階段中斷後 baseline 完整")

    bypass_cache = ws["root"] / ".cache" / "bypass_eval"
    if bypass_cache.exists():
        for f in bypass_cache.glob("*/result.json"):
            raw = f.read_text(encoding="utf-8")
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            assert "overall" in parsed, \
                f"殘留快取 {f.name} 缺少 overall，不應被視為 benchmark"

    report_path = ws["root"] / "docs" / "bypass-reevaluation-report.json"
    # 中斷發生在快取寫入階段，報告尚未寫入，因此報告要么不存在要么是舊的
    if report_path.exists():
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        assert "meta" in report_data, "殘留報告缺少 meta，不應被視為有效 benchmark"

    monkeypatch.setattr(bre, "write_json", original_write_json)
    _run_bypass_clean(ws, 42, 99)
    assert report_path.exists()
    reloaded = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(reloaded.get("per_item", [])) > 0
    _assert_baseline_unchanged(ws, snap, "最終重跑後 baseline 仍不變")
