import json
import re

from lib import metrics


def test_record_event_append_payload_with_timestamp(monkeypatch, tmp_path):
    temp_metrics = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", str(temp_metrics))

    metrics.record_event("start", {"baseline_dev_score": 72.5})

    lines = temp_metrics.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    data = json.loads(lines[0])
    assert data["event"] == "start"
    assert data["baseline_dev_score"] == 72.5
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
        data["timestamp"],
    )


def test_record_event_without_data_omits_optional_payload(monkeypatch, tmp_path):
    temp_metrics = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", str(temp_metrics))

    metrics.record_event("heartbeat")

    data = json.loads(temp_metrics.read_text(encoding="utf-8"))
    assert data["event"] == "heartbeat"
    assert set(data) == {"event", "timestamp"}
    assert "baseline_dev_score" not in data


def test_record_round_returns_payload_and_default_conversion(monkeypatch, tmp_path):
    path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", str(path))

    payload = metrics.record_round(
        4,
        direction="D01",
        target_failures=["A", "B"],
        smoke_score=88.0,
        dev_score=74.1,
        holdout_score=61.0,
        accept=True,
        score_diff=3.3,
        api_calls=12,
        elapsed_seconds=2.7,
        error="ok",
        candidates_count=5,
    )

    assert payload["event"] == "round"
    assert payload["round"] == 4
    assert payload["direction"] == "D01"
    assert payload["target_failures"] == ["A", "B"]
    assert payload["smoke_score"] == 88.0
    assert payload["api_calls"] == 12
    assert payload["accept"] is True
    assert payload["candidates_count"] == 5

    raw = path.read_text(encoding="utf-8").strip()
    stored = json.loads(raw)
    assert stored == payload


def test_record_round_default_target_failures_is_list(monkeypatch, tmp_path):
    path = tmp_path / "metrics.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", str(path))

    payload = metrics.record_round(1)

    assert isinstance(payload["target_failures"], list)
    assert payload["target_failures"] == []
    assert payload["event"] == "round"
    assert path.read_text(encoding="utf-8").strip().startswith("{")
