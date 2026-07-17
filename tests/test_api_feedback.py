# -*- coding: utf-8 -*-
"""api/feedback.py 單元測試。

以 monkeypatch 替換 read_jsonl / load_json 隔離儲存層，
驗證回饋查詢、聚合（同 hash 累加）、弱點分析、優化建議與空值/非法輸入邊界。
"""
from datetime import datetime, timedelta
from collections import defaultdict

import api.feedback as feedback


def _item(prompt_hash="hash-a", total=80, scores=None, qtype="申論題", ts=None):
    item = {
        "prompt_hash": prompt_hash,
        "total_score": total,
        "scores": scores if scores is not None else {"issueHit": 16},
        "question_type": qtype,
    }
    if ts is not None:
        item["timestamp"] = ts
    return item


# --- load_feedback（查詢） ---

def test_load_feedback_reads_feedback_path_with_limit(monkeypatch):
    calls = {}

    def fake_read_jsonl(path, limit=None):
        calls["path"] = path
        calls["limit"] = limit
        return [{"prompt_hash": "x"}]

    monkeypatch.setattr(feedback, "read_jsonl", fake_read_jsonl)

    assert feedback.load_feedback(limit=5) == [{"prompt_hash": "x"}]
    assert calls == {"path": feedback.FEEDBACK_PATH, "limit": 5}


def test_load_feedback_default_limit_is_1000(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        feedback, "read_jsonl",
        lambda path, limit=None: calls.setdefault("limit", limit) and [] or [],
    )

    feedback.load_feedback()
    assert calls["limit"] == 1000


# --- analyze_feedback_by_hash（聚合／同 hash 累加＝覆寫語意） ---

def test_analyze_aggregates_same_hash_and_averages():
    data = [
        _item(total=80, scores={"issueHit": 16, "structure": 14}, qtype="申論題"),
        _item(total=60, scores={"issueHit": 12, "structure": 10}, qtype="案例題"),
    ]

    result = feedback.analyze_feedback_by_hash(data)

    assert set(result) == {"hash-a"}
    entry = result["hash-a"]
    assert entry["count"] == 2
    assert entry["avg_total"] == 70.0
    assert entry["avg_scores"] == {"issueHit": 14.0, "structure": 12.0}
    assert entry["avg_by_type"] == {"申論題": 80.0, "案例題": 60.0}


def test_analyze_skips_zero_count_bucket(monkeypatch):
    class SeededDefaultDict(dict):
        def __init__(self, factory):
            super().__init__()
            self.update(
                {
                    "seed": {
                        "count": 0,
                        "total_score": 0,
                        "scores": defaultdict(float),
                        "question_types": defaultdict(lambda: {"count": 0, "total": 0}),
                    }
                }
            )

    monkeypatch.setattr(feedback, "defaultdict", lambda factory: SeededDefaultDict(factory))
    result = feedback.analyze_feedback_by_hash([])
    assert result == {}
    assert "seed" not in result


def test_analyze_skips_zero_count_entry_directly(monkeypatch):
    """直接測試 count==0 時的 continue 分支（76->75）"""
    # 透過 monkeypatch 讓 analyze_feedback_by_hash 內部建立的 entry 初始 count=0
    orig_defaultdict = feedback.defaultdict

    def fake_defaultdict(factory):
        d = orig_defaultdict(factory)
        # 預先塞入一個 count=0 的 entry，模擬邊界情況
        d["zero-hash"] = {
            "count": 0,
            "total_score": 0,
            "scores": defaultdict(float),
            "question_types": defaultdict(lambda: {"count": 0, "total": 0}),
        }
        return d

    monkeypatch.setattr(feedback, "defaultdict", fake_defaultdict)
    result = feedback.analyze_feedback_by_hash([])
    # 因為 count==0，該 entry 應被 continue 跳過，不會出現在結果中
    assert "zero-hash" not in result


def test_analyze_separates_different_hashes():
    data = [_item("hash-a", total=90), _item("hash-b", total=50)]

    result = feedback.analyze_feedback_by_hash(data)

    assert result["hash-a"]["avg_total"] == 90.0
    assert result["hash-b"]["avg_total"] == 50.0


def test_analyze_rounds_averages_to_two_decimals():
    data = [
        _item(total=70, scores={"issueHit": 10}),
        _item(total=70, scores={"issueHit": 10}),
        _item(total=71, scores={"issueHit": 11}),
    ]

    entry = feedback.analyze_feedback_by_hash(data)["hash-a"]
    assert entry["avg_total"] == 70.33
    assert entry["avg_scores"]["issueHit"] == 10.33


def test_analyze_empty_input_returns_empty_dict():
    assert feedback.analyze_feedback_by_hash([]) == {}


def test_analyze_missing_fields_uses_defaults():
    # 全空 item：hash 歸為 unknown、分數計 0、題型歸為 unknown
    result = feedback.analyze_feedback_by_hash([{}])

    assert set(result) == {"unknown"}
    entry = result["unknown"]
    assert entry["count"] == 1
    assert entry["avg_total"] == 0
    assert entry["avg_scores"] == {}
    assert entry["avg_by_type"] == {"unknown": 0}


def test_analyze_none_input_falls_back_to_load_feedback(monkeypatch):
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: [_item(total=42)])

    result = feedback.analyze_feedback_by_hash(None)
    assert result["hash-a"]["avg_total"] == 42.0


# --- get_recent_feedback_trend（時間窗與非法 timestamp） ---

def test_recent_trend_filters_old_invalid_and_missing_timestamps(monkeypatch):
    now = datetime.now()
    data = [
        _item("recent", total=90, ts=(now - timedelta(days=1)).isoformat()),
        _item("old", total=10, ts=(now - timedelta(days=30)).isoformat()),
        _item("bad-ts", total=10, ts="not-a-timestamp"),
        _item("no-ts", total=10),  # 無 timestamp → fromisoformat("") 失敗被略過
    ]
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: data)

    result = feedback.get_recent_feedback_trend(days=7)
    assert set(result) == {"recent"}
    assert result["recent"]["avg_total"] == 90.0


def test_recent_trend_skips_non_string_timestamp(monkeypatch):
    data = [_item("num-ts", ts=12345)]
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: data)

    assert feedback.get_recent_feedback_trend(days=7) == {}


# --- get_weak_areas（弱點門檻與排序） ---

def test_weak_areas_thresholds_and_sorting(monkeypatch):
    long_hash = "abcdef1234567890"
    data = [
        _item(long_hash, total=60,
              scores={"issueHit": 10, "structure": 18}, qtype="案例題"),
        _item("strong-hash", total=95,
              scores={"issueHit": 19}, qtype="申論題"),
        _item("weaker-hash", total=50,
              scores={"scholarlyRef": 5}, qtype="測驗題"),
    ]
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: data)

    result = feedback.get_weak_areas()

    # 維度 <15 才算弱點；依 avg_score 遞增排序；hash 截斷為 12 碼
    dims = result["weak_dimensions"]
    assert [d["dimension"] for d in dims] == ["scholarlyRef", "issueHit"]
    assert dims[1]["prompt_hash"] == long_hash[:12]
    assert all(d["avg_score"] < 15 for d in dims)

    # 題型 <70 才算弱點
    types = result["weak_types"]
    assert [t["question_type"] for t in types] == ["測驗題", "案例題"]
    assert all(t["avg_score"] < 70 for t in types)


def test_weak_areas_empty_feedback_returns_empty_lists(monkeypatch):
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: [])

    assert feedback.get_weak_areas() == {"weak_dimensions": [], "weak_types": []}


# --- generate_optimization_hints（建議產生與未知維度過濾） ---

def test_optimization_hints_maps_known_dimensions_and_skips_unknown(monkeypatch):
    data = [
        _item(total=50, scores={"issueHit": 5, "unknownDim": 3}, qtype="案例題"),
    ]
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: data)
    monkeypatch.setattr(feedback, "load_json", lambda path, default=None: {})

    hints = feedback.generate_optimization_hints()

    dim_hints = [h for h in hints if h["type"] == "dimension"]
    type_hints = [h for h in hints if h["type"] == "question_type"]

    # unknownDim 無對應建議文案，應被過濾
    assert [h["target"] for h in dim_hints] == ["issueHit"]
    assert "審題" in dim_hints[0]["hint"]
    assert dim_hints[0]["avg_score"] == 5.0

    assert [h["target"] for h in type_hints] == ["案例題"]
    assert "案例題" in type_hints[0]["hint"]


def test_optimization_hints_caps_at_top_three_each(monkeypatch):
    dims = ["issueHit", "scholarlyRef", "practicalRef", "structure", "riskControl"]
    data = [
        _item(f"h{i}", total=30, scores={d: i + 1}, qtype=f"題型{i}")
        for i, d in enumerate(dims)
    ]
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: data)
    monkeypatch.setattr(feedback, "load_json", lambda path, default=None: {})

    hints = feedback.generate_optimization_hints()

    assert len([h for h in hints if h["type"] == "dimension"]) == 3
    assert len([h for h in hints if h["type"] == "question_type"]) == 3


def test_optimization_hints_no_weak_areas_returns_empty(monkeypatch):
    data = [_item(total=95, scores={"issueHit": 19}, qtype="申論題")]
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: data)
    monkeypatch.setattr(feedback, "load_json", lambda path, default=None: {})

    assert feedback.generate_optimization_hints() == []


# --- get_feedback_summary（整體摘要） ---

def test_feedback_summary_structure_and_baseline_score(monkeypatch):
    data = [
        _item("hash-a", total=80, scores={"issueHit": 16}, qtype="申論題"),
        _item("hash-b", total=50, scores={"issueHit": 10}, qtype="案例題"),
    ]
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: data)
    monkeypatch.setattr(
        feedback, "load_json", lambda path, default=None: {"dev_avg": 77.5}
    )

    summary = feedback.get_feedback_summary()

    assert summary["total_feedback"] == 2
    assert summary["unique_prompts"] == 2
    assert set(summary["prompt_analysis"]) == {"hash-a", "hash-b"}
    assert summary["baseline_score"] == 77.5
    assert "weak_areas" in summary
    assert "optimization_hints" in summary


def test_feedback_summary_empty_feedback_and_missing_baseline(monkeypatch):
    monkeypatch.setattr(feedback, "read_jsonl", lambda path, limit=None: [])
    monkeypatch.setattr(feedback, "load_json", lambda path, default=None: {})

    summary = feedback.get_feedback_summary()

    assert summary["total_feedback"] == 0
    assert summary["unique_prompts"] == 0
    assert summary["prompt_analysis"] == {}
    assert summary["weak_areas"] == {"weak_dimensions": [], "weak_types": []}
    assert summary["optimization_hints"] == []
    assert summary["baseline_score"] is None
