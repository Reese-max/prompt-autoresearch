# -*- coding: utf-8 -*-
"""tests/test_best_version_report.py — scripts/best_version_report.py 單元測試（tmp_path 隔離、無網路）。"""
import json
import os
import sys

import pytest

import scripts.best_version_report as bvr


# ---------- fixtures / helpers ----------

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """把所有路徑指到 tmp_path，隔離真實 repo。"""
    champions = tmp_path / "prompts" / "champions"
    champions.mkdir(parents=True)
    candidates = tmp_path / "prompts" / "candidates"
    candidates.mkdir(parents=True)
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(bvr, "ROOT", str(tmp_path))
    monkeypatch.setattr(bvr, "BASELINE_META_PATH", str(tmp_path / "prompts" / "baseline.meta.json"))
    monkeypatch.setattr(bvr, "CHAMPIONS_DIR", str(champions))
    monkeypatch.setattr(bvr, "CANDIDATES_DIR", str(candidates))
    monkeypatch.setattr(bvr, "EVOLUTION_LOG_PATH", str(tmp_path / "evolution_log.jsonl"))
    monkeypatch.setattr(bvr, "CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(bvr, "RUNS_DIR", str(runs))
    return tmp_path


def write_baseline_meta(tmp_path, **overrides):
    meta = {
        "prompt_hash": "abc123def456",
        "dev_avg": 88.5,
        "holdout_avg": 87.0,
        "dev_run": "runs/dev_run_001",
        "holdout_run": "runs/holdout_run_001",
        "smoke_avg": 90.0,
    }
    meta.update(overrides)
    path = tmp_path / "prompts" / "baseline.meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def write_champion_meta(tmp_path, name, **overrides):
    meta = {
        "kind": "type_champion",
        "type": "法律案例題",
        "type_slug": "legal_case",
        "candidate_hash": "hash123abc",
        "champion_prompt_path": f"prompts/champions/{name}.md",
        "dev_run": "runs/dev_champion",
        "baseline_avg": 74.0,
        "candidate_avg": 84.0,
        "diff": 10.0,
        "risk_rate": 100.0,
        "decision": "SPECIALTY_RETAINED",
    }
    meta.update(overrides)
    path = tmp_path / "prompts" / "champions" / f"{name}.meta.json"
    path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def write_scorecard(tmp_path, name, **overrides):
    card = {
        "candidate_path": f"prompts/candidates/{name}.md",
        "direction": "D01",
        "target_failures": ["F03"],
        "status": "completed",
        "final_decision": "ACCEPT",
        "smoke": {"score": 85.0, "passed": True},
        "dev": {"score": 88.0},
        "holdout": {"score": 87.0},
    }
    card.update(overrides)
    path = tmp_path / "prompts" / "candidates" / f"{name}.scorecard.json"
    path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return card


def write_evolution_log(tmp_path, rows):
    path = tmp_path / "evolution_log.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_config(tmp_path, content="thresholds:\n  dev_min_improvement: 2.0\n"):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")


def write_complete_report_evidence(tmp_path, **card_overrides):
    baseline_prompt = tmp_path / "prompts" / "baseline.md"
    baseline_prompt.write_text("完整 baseline 提示詞\n", encoding="utf-8")
    write_baseline_meta(tmp_path, prompt_hash=bvr.sha256_file(str(baseline_prompt)))
    for name, score in (("cand_1", 92.0), ("cand_2", 90.0)):
        candidate = tmp_path / "prompts" / "candidates" / f"{name}.md"
        candidate.write_text(f"完整候選 {name}\n", encoding="utf-8")
        card_kwargs = {
            "candidate_hash": bvr.sha256_file(str(candidate)),
            "final_decision": "ACCEPT",
            "dev": {"score": score},
        }
        card_kwargs.update(card_overrides.get(name, {}))
        write_scorecard(
            tmp_path,
            name,
            **card_kwargs,
        )
    write_config(tmp_path)
    write_evolution_log(tmp_path, [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {}},
        {"event": "stop", "timestamp": "2026-01-01 00:01:00"},
    ])


def assert_inconclusive_with_reproduction_commands(data, report):
    assert data["decision"]["status"] == "inconclusive"
    assert data["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert data["decision"]["best_candidate_id"] is None
    assert data["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    commands = data["reproduction"]["commands"]
    assert commands
    assert all(command["argv"] and command["command"] and command["cwd"] == "." for command in commands)
    assert "可獨立執行的補證命令" in report


# ---------- load functions ----------

def test_load_json_missing_and_present(tmp_path):
    assert bvr.load_json(str(tmp_path / "nope.json")) == {}
    p = tmp_path / "a.json"
    p.write_text('{"k": 1}', encoding="utf-8")
    assert bvr.load_json(str(p)) == {"k": 1}


def test_read_text_missing_and_present(tmp_path):
    assert bvr.read_text(str(tmp_path / "nope.md")) == ""
    p = tmp_path / "a.md"
    p.write_text("hello", encoding="utf-8")
    assert bvr.read_text(str(p)) == "hello"


def test_read_jsonl_missing_and_present(tmp_path):
    assert bvr.read_jsonl(str(tmp_path / "nope.jsonl")) == []
    path = tmp_path / "data.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"a": 1}\n{"b": 2}\n\n{"c": 3}\n')
    rows = bvr.read_jsonl(str(path))
    assert len(rows) == 3
    assert rows[0] == {"a": 1}
    assert rows[2] == {"c": 3}


def test_read_jsonl_malformed_lines(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ok": 1}\nBAD JSON\n{"ok": 2}\n', encoding="utf-8")
    rows = bvr.read_jsonl(str(path))
    assert len(rows) == 2


# ---------- load_baseline_meta ----------

def test_load_baseline_meta_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bvr, "BASELINE_META_PATH", str(tmp_path / "nope.json"))
    assert bvr.load_baseline_meta() == {}


def test_load_baseline_meta_present(sandbox):
    meta = write_baseline_meta(sandbox)
    result = bvr.load_baseline_meta()
    assert result["prompt_hash"] == "abc123def456"
    assert result["dev_avg"] == 88.5


# ---------- load_champion_metas ----------

def test_load_champion_metas_empty(sandbox):
    assert bvr.load_champion_metas() == []


def test_load_champion_metas_multiple(sandbox):
    write_champion_meta(sandbox, "legal_case")
    write_champion_meta(sandbox, "compare", type="比較題", type_slug="compare")
    champions = bvr.load_champion_metas()
    assert len(champions) == 2
    types = {ch["type"] for ch in champions}
    assert "法律案例題" in types
    assert "比較題" in types


def test_load_champion_metas_includes_meta_file(sandbox):
    write_champion_meta(sandbox, "practical")
    champions = bvr.load_champion_metas()
    assert "_meta_file" in champions[0]
    assert champions[0]["_meta_file"].endswith("practical.meta.json")


# ---------- load_candidate_scorecards ----------

def test_load_candidate_scorecards_empty(sandbox):
    assert bvr.load_candidate_scorecards() == []


def test_load_candidate_scorecards_limit(sandbox):
    for i in range(5):
        write_scorecard(sandbox, f"cand_{i}")
    cards = bvr.load_candidate_scorecards(limit=3)
    assert len(cards) == 3


def test_load_candidate_scorecards_includes_file(sandbox):
    write_scorecard(sandbox, "test_cand")
    cards = bvr.load_candidate_scorecards()
    assert "_scorecard_file" in cards[0]
    assert cards[0]["_scorecard_file"].endswith("test_cand.scorecard.json")


def test_load_candidate_scorecards_skips_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bvr, "CANDIDATES_DIR", str(tmp_path / "nonexistent"))
    assert bvr.load_candidate_scorecards() == []


# ---------- load_evolution_summary ----------

def test_load_evolution_summary_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(bvr, "EVOLUTION_LOG_PATH", str(tmp_path / "nope.jsonl"))
    assert bvr.load_evolution_summary() == []


def test_load_evolution_summary_single_session(sandbox):
    rows = [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {"max_rounds": 3}, "baseline_dev_score": 80.0},
        {"event": "round_complete", "round": 1, "promoted": True},
        {"event": "round_complete", "round": 2, "promoted": False},
        {"event": "stop", "timestamp": "2026-01-01 01:00:00", "reason": "done", "best_score": 85.0, "estimated_api_calls_total": 100, "elapsed_seconds": 3600},
    ]
    write_evolution_log(sandbox, rows)
    sessions = bvr.load_evolution_summary()
    assert len(sessions) == 1
    assert sessions[0]["promotions"] == 1
    assert sessions[0]["best_score"] == 85.0
    assert len(sessions[0]["rounds"]) == 2


def test_load_evolution_summary_multiple_sessions(sandbox):
    rows = [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {}, "baseline_dev_score": 80.0},
        {"event": "stop", "timestamp": "2026-01-01 01:00:00", "reason": "done", "best_score": 82.0, "estimated_api_calls_total": 50, "elapsed_seconds": 1800},
        {"event": "start", "timestamp": "2026-01-02 00:00:00", "args": {}, "baseline_dev_score": 82.0},
        {"event": "round_complete", "round": 1, "promoted": True},
        {"event": "stop", "timestamp": "2026-01-02 02:00:00", "reason": "done", "best_score": 85.0, "estimated_api_calls_total": 60, "elapsed_seconds": 3600},
    ]
    write_evolution_log(sandbox, rows)
    sessions = bvr.load_evolution_summary()
    assert len(sessions) == 2
    assert sessions[1]["promotions"] == 1


def test_load_evolution_summary_unclosed_session(sandbox):
    rows = [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {}, "baseline_dev_score": 80.0},
        {"event": "round_complete", "round": 1, "promoted": False},
    ]
    write_evolution_log(sandbox, rows)
    sessions = bvr.load_evolution_summary()
    assert len(sessions) == 1
    assert len(sessions[0]["rounds"]) == 1


# ---------- classify_candidates ----------

def test_classify_candidates():
    cards = [
        {"final_decision": "ACCEPT"},
        {"final_decision": "REVERT"},
        {"final_decision": "SPECIALTY_RETAINED"},
        {"status": "rejected_smoke"},
        {},
    ]
    accepted, rejected, pending = bvr.classify_candidates(cards)
    assert len(accepted) == 2
    assert len(rejected) == 2
    assert len(pending) == 1


# ---------- format_table ----------

def test_format_table():
    out = bvr.format_table(["a", "b"], [[1, "x"], [2, "y"]])
    lines = out.splitlines()
    assert lines[0] == "| a | b |"
    assert lines[1] == "| --- | --- |"
    assert lines[2] == "| 1 | x |"
    assert lines[3] == "| 2 | y |"


def test_format_table_empty():
    out = bvr.format_table(["col"], [])
    lines = out.splitlines()
    assert len(lines) == 2  # header + separator only


# ---------- build_json_block ----------

def test_build_json_block():
    block = bvr.build_json_block({"key": "value"})
    assert block.startswith("```json\n")
    assert block.endswith("\n```")
    inner = block[len("```json\n"):-len("\n```")]
    parsed = json.loads(inner)
    assert parsed == {"key": "value"}


# ---------- build_report integration ----------

def test_build_report_empty(sandbox):
    report = bvr.build_report(limit=5)
    assert "# 最佳版本證據報告" in report
    assert "```json" in report
    assert "## 1. Winner（冠軍）" in report
    assert "## 4. 逐候選比較" in report
    # 空資料時證據不完整，應顯示 inconclusive 訊息
    assert "INCONCLUSIVE" in report
    assert "因證據不完整，無法選出冠軍" in report
    assert "_無候選記錄_" in report


def test_build_report_full(sandbox):
    write_baseline_meta(sandbox)
    write_champion_meta(sandbox, "legal_case")
    write_champion_meta(sandbox, "compare", type="比較題", type_slug="compare")
    write_scorecard(sandbox, "cand_1", final_decision="ACCEPT", direction="D01")
    write_scorecard(sandbox, "cand_2", final_decision="REVERT",
                    status="completed", reject_reasons=["dev score too low"])
    write_scorecard(sandbox, "cand_3", final_decision="REJECT", status="rejected_smoke")
    write_config(sandbox)

    rows = [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {"max_rounds": 5}, "baseline_dev_score": 85.0},
        {"event": "round_complete", "round": 1, "promoted": True},
        {"event": "round_complete", "round": 2, "promoted": False},
        {"event": "stop", "timestamp": "2026-01-01 02:00:00", "reason": "done", "best_score": 89.0, "estimated_api_calls_total": 200, "elapsed_seconds": 7200},
    ]
    write_evolution_log(sandbox, rows)

    report = bvr.build_report(limit=10)

    assert "# 最佳版本證據報告" in report
    assert "abc123def456" in report
    assert "88.5" in report
    assert "87.0" in report
    assert "法律案例題" in report
    assert "比較題" in report
    assert "ACCEPTED：1" in report
    assert "REJECTED：2" in report
    assert "最大輪次" in report
    assert "thresholds" in report
    assert "evolution_log.jsonl" in report
    assert "baseline.meta.json" in report


def test_build_report_limit_candidates(sandbox):
    write_baseline_meta(sandbox)
    for i in range(20):
        write_scorecard(sandbox, f"cand_{i}", final_decision="ACCEPT")
    report = bvr.build_report(limit=5)
    # Should only show 5 candidates in the table
    assert "| ACCEPT |" in report


def test_build_report_with_sessions(sandbox):
    write_baseline_meta(sandbox)
    rows = [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {"max_rounds": 3, "parallel": 24}, "baseline_dev_score": 80.0},
        {"event": "round_complete", "round": 1, "promoted": True},
        {"event": "round_complete", "round": 2, "promoted": True},
        {"event": "stop", "timestamp": "2026-01-01 01:00:00", "reason": "done", "best_score": 85.0, "estimated_api_calls_total": 100, "elapsed_seconds": 3600},
    ]
    write_evolution_log(sandbox, rows)
    report = bvr.build_report()
    assert "演化 session 數：1" in report
    assert "總輪次：2" in report
    assert "成功晉升次數：2" in report


# ---------- main ----------

def test_main_stdout_only(sandbox, monkeypatch, capsys):
    write_baseline_meta(sandbox)
    monkeypatch.setattr(sys, "argv", ["best_version_report.py"])
    bvr.main()
    out = capsys.readouterr().out
    assert "# 最佳版本證據報告" in out


def test_main_with_out(sandbox, monkeypatch, capsys):
    write_baseline_meta(sandbox)
    monkeypatch.setattr(sys, "argv", ["best_version_report.py", "--out", "output/best_report.md"])
    bvr.main()
    out_file = sandbox / "output" / "best_report.md"
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "# 最佳版本證據報告" in content
    stdout = capsys.readouterr().out
    assert "# 最佳版本證據報告" in stdout
    assert len(content) > 100
    assert len(stdout) > 100


def test_main_with_limit(sandbox, monkeypatch, capsys):
    write_baseline_meta(sandbox)
    for i in range(10):
        write_scorecard(sandbox, f"c{i}")
    monkeypatch.setattr(sys, "argv", ["best_version_report.py", "--limit", "3"])
    bvr.main()
    out = capsys.readouterr().out
    assert "# 最佳版本證據報告" in out


# ---------- 證據完整性閘門 ----------

class TestEvidenceIntegrityGate:
    """驗證 evidence integrity gate 在缺少關鍵證據時輸出 inconclusive。"""

    def test_all_evidence_present(self):
        """所有證據齊全時應通過。"""
        baseline_meta = {
            "prompt_hash": "abc123",
            "dev_avg": 88.5,
            "holdout_avg": 87.0,
        }
        champions = [{"type": "事實", "candidate_avg": 90.0}]
        cards = [{"final_decision": "ACCEPT"}]
        sessions = [{"start": "2026-01-01", "stop": "2026-01-02"}]
        config = {"thresholds": {"dev_min_improvement": 2.0}}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is True
        assert errors == []

    def test_missing_prompt_hash(self):
        """缺少 prompt_hash 時應失敗。"""
        baseline_meta = {
            "dev_avg": 88.5,
            "holdout_avg": 87.0,
        }
        champions = []
        cards = [{"final_decision": "ACCEPT"}]
        sessions = [{"start": "2026-01-01", "stop": "2026-01-02"}]
        config = {"thresholds": {}}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is False
        assert any("可讀提示詞" in e for e in errors)

    def test_missing_scores(self):
        """缺少 dev_avg/holdout_avg 時應失敗。"""
        baseline_meta = {
            "prompt_hash": "abc123",
        }
        champions = []
        cards = [{"final_decision": "ACCEPT"}]
        sessions = [{"start": "2026-01-01", "stop": "2026-01-02"}]
        config = {"thresholds": {}}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is False
        assert any("可驗證分數" in e for e in errors)

    def test_missing_comparison(self):
        """無候選分數卡時應失敗。"""
        baseline_meta = {
            "prompt_hash": "abc123",
            "dev_avg": 88.5,
            "holdout_avg": 87.0,
        }
        champions = []
        cards = []
        sessions = [{"start": "2026-01-01", "stop": "2026-01-02"}]
        config = {"thresholds": {}}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is False
        assert any("比較對象" in e for e in errors)

    def test_missing_evolution_session(self):
        """無完整演化 session 時應失敗。"""
        baseline_meta = {
            "prompt_hash": "abc123",
            "dev_avg": 88.5,
            "holdout_avg": 87.0,
        }
        champions = []
        cards = [{"final_decision": "ACCEPT"}]
        sessions = []
        config = {"thresholds": {}}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is False
        assert any("演化 session" in e for e in errors)

    def test_incomplete_evolution_session(self):
        """只有 start 沒有 stop 的 session 應失敗。"""
        baseline_meta = {
            "prompt_hash": "abc123",
            "dev_avg": 88.5,
            "holdout_avg": 87.0,
        }
        champions = []
        cards = [{"final_decision": "ACCEPT"}]
        sessions = [{"start": "2026-01-01"}]
        config = {"thresholds": {}}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is False
        assert any("演化 session" in e for e in errors)

    def test_missing_config(self):
        """config 為空時應失敗。"""
        baseline_meta = {
            "prompt_hash": "abc123",
            "dev_avg": 88.5,
            "holdout_avg": 87.0,
        }
        champions = []
        cards = [{"final_decision": "ACCEPT"}]
        sessions = [{"start": "2026-01-01", "stop": "2026-01-02"}]
        config = {}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is False
        assert any("重現設定" in e for e in errors)

    def test_multiple_missing_evidence(self):
        """多項證據缺失時應回報所有缺失。"""
        baseline_meta = {}
        champions = []
        cards = []
        sessions = []
        config = {}

        is_valid, errors = bvr.verify_evidence_integrity(
            baseline_meta, champions, cards, sessions, config
        )
        assert is_valid is False
        assert len(errors) >= 4

    def test_report_inconclusive_when_evidence_missing(self, sandbox):
        """報告在證據不完整時應輸出 inconclusive。"""
        report = bvr.build_report(limit=5)
        assert "INCONCLUSIVE" in report
        assert "inconclusive" in report
        assert "拒絕選優" in report

    def test_report_valid_when_evidence_complete(self, sandbox):
        """報告在證據完整時應正常顯示冠軍。"""
        baseline_prompt = sandbox / "prompts" / "baseline.md"
        baseline_prompt.write_text("baseline content", encoding="utf-8")
        write_baseline_meta(
            sandbox,
            prompt_hash=bvr.sha256_file(str(baseline_prompt)),
        )
        champion_prompt = sandbox / "prompts" / "champions" / "legal_case.md"
        champion_prompt.write_text("champion content", encoding="utf-8")
        write_champion_meta(sandbox, "legal_case")
        champion_meta = json.loads(
            (sandbox / "prompts" / "champions" / "legal_case.meta.json").read_text(encoding="utf-8")
        )
        champion_meta["candidate_hash"] = bvr.sha256_file(str(champion_prompt))
        (sandbox / "prompts" / "champions" / "legal_case.meta.json").write_text(
            json.dumps(champion_meta, ensure_ascii=False), encoding="utf-8"
        )
        candidate_prompt = sandbox / "prompts" / "candidates" / "cand_1.md"
        candidate_prompt.write_text("candidate content", encoding="utf-8")
        write_scorecard(
            sandbox,
            "cand_1",
            final_decision="ACCEPT",
            candidate_hash=bvr.sha256_file(str(candidate_prompt)),
        )
        write_config(sandbox)

        rows = [
            {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {"max_rounds": 3}, "baseline_dev_score": 85.0},
            {"event": "round_complete", "round": 1, "promoted": True},
            {"event": "stop", "timestamp": "2026-01-01 01:00:00", "reason": "done", "best_score": 89.0, "estimated_api_calls_total": 100, "elapsed_seconds": 3600},
        ]
        write_evolution_log(sandbox, rows)

        report = bvr.build_report(limit=10)
        assert "PASS" in report
        assert "valid" in report
        assert "_尚無全域冠軍_" not in report


# ---------- 路徑正規化 ----------

def test_repo_rel_relative_forward_slash(sandbox):
    assert bvr.repo_rel("prompts/baseline.md") == "prompts/baseline.md"


def test_repo_rel_backslashes_normalized(sandbox):
    assert bvr.repo_rel(r"prompts\champions\compare.md") == "prompts/champions/compare.md"


def test_repo_rel_absolute_inside_repo(sandbox):
    abs_path = str(sandbox / "prompts" / "baseline.md").replace("\\", "/")
    assert bvr.repo_rel(abs_path) == "prompts/baseline.md"


def test_repo_rel_outside_repo_returns_none(sandbox, tmp_path):
    outside = str(tmp_path / ".." / "outside.md").replace("\\", "/")
    assert bvr.repo_rel(outside) is None


def test_repo_rel_empty_returns_none(sandbox):
    assert bvr.repo_rel("") is None
    assert bvr.repo_rel(None) is None


def test_display_path_inside_repo(sandbox):
    assert bvr.display_path(r"prompts\champions\compare.md") == "prompts/champions/compare.md"


def test_display_path_unresolvable_dash(sandbox, tmp_path):
    outside = str(tmp_path / ".." / "outside.md").replace("\\", "/")
    assert bvr.display_path(outside) == "-"


# ---------- 證據驗證 ----------

def test_verify_evidence_file_present_and_hash_match(sandbox):
    (sandbox / "prompts").mkdir(exist_ok=True)
    p = sandbox / "prompts" / "p.md"
    p.write_text("hello evidence", encoding="utf-8")
    digest = bvr.sha256_file(str(p))
    result = bvr.verify_evidence_file("prompts/p.md", recorded_hash=digest)
    assert result["exists"] is True
    assert result["nonempty"] is True
    assert result["hash_match"] is True
    assert result["ok"] is True


def test_verify_evidence_file_missing(sandbox):
    result = bvr.verify_evidence_file("prompts/nope.md", recorded_hash="abc")
    assert result["exists"] is False
    assert result["nonempty"] is False
    assert result["hash_match"] is None
    assert result["ok"] is False


def test_verify_evidence_file_empty(sandbox):
    (sandbox / "prompts").mkdir(exist_ok=True)
    p = sandbox / "prompts" / "empty.md"
    p.write_text("", encoding="utf-8")
    result = bvr.verify_evidence_file("prompts/empty.md", recorded_hash="abc")
    assert result["exists"] is True
    assert result["nonempty"] is False
    assert result["ok"] is False


def test_verify_evidence_file_hash_mismatch(sandbox):
    (sandbox / "prompts").mkdir(exist_ok=True)
    p = sandbox / "prompts" / "p.md"
    p.write_text("content", encoding="utf-8")
    result = bvr.verify_evidence_file("prompts/p.md", recorded_hash="deadbeef")
    assert result["exists"] is True
    assert result["hash_match"] is False
    assert result["ok"] is False


def test_verify_evidence_file_no_recorded_hash(sandbox):
    (sandbox / "prompts").mkdir(exist_ok=True)
    p = sandbox / "prompts" / "p.md"
    p.write_text("content", encoding="utf-8")
    result = bvr.verify_evidence_file("prompts/p.md")
    assert result["exists"] is True
    assert result["hash_match"] is None
    assert result["ok"] is True


# ---------- 證據驗證收集 ----------

def test_collect_evidence_verification_includes_baseline_prompt(sandbox):
    write_baseline_meta(sandbox)
    (sandbox / "prompts").mkdir(exist_ok=True)
    (sandbox / "prompts" / "baseline.md").write_text("baseline content", encoding="utf-8")
    checks = bvr.collect_evidence_verification(
        {"prompt_path": "prompts/baseline.md", "prompt_hash": "abc123def456"},
        [], [],
    )
    prompts = [c for c in checks if c["path"] == "prompts/baseline.md"]
    assert len(prompts) == 1
    assert prompts[0]["exists"] is True
    assert prompts[0]["hash_match"] is False  # recorded hash 與實際不符


def test_collect_evidence_verification_champion_prompt_missing(sandbox):
    write_champion_meta(sandbox, "legal_case")
    champions = bvr.load_champion_metas()
    checks = bvr.collect_evidence_verification({}, champions, [])
    missing = [c for c in checks if c["path"] == "prompts/champions/legal_case.md"]
    assert len(missing) == 1
    assert missing[0]["exists"] is False
    assert missing[0]["ok"] is False


def test_collect_evidence_verification_candidate_scorecard(sandbox):
    write_scorecard(sandbox, "cand_1")
    cards = bvr.load_candidate_scorecards()
    checks = bvr.collect_evidence_verification({}, [], cards)
    sc = [c for c in checks if c["path"] == "prompts/candidates/cand_1.scorecard.json"]
    assert len(sc) == 1
    assert sc[0]["exists"] is True
    assert sc[0]["ok"] is True


# ---------- 重跑設定 ----------

def test_collect_rerun_settings_winner_and_evaluator(sandbox):
    write_config(sandbox, content="api:\n  url: https://example.invalid/v1\n  model: Test-Model\nthresholds:\n  dev_min_improvement: 2.0\n")
    config = bvr.load_config()
    settings = bvr.collect_rerun_settings(
        {"prompt_path": "prompts/baseline.md", "prompt_hash": "abc123def456"},
        [], config, [],
    )
    assert settings["winner_input"]["prompt_path"] == "prompts/baseline.md"
    assert settings["winner_input"]["prompt_hash"] == "abc123def456"
    assert settings["evaluator"]["url"] == "https://example.invalid/v1"
    assert settings["evaluator"]["model"] == "Test-Model"
    assert settings["evaluator"]["evaluate_script"] == "scripts/evaluate.py"
    assert "commit" in settings["version"]
    assert settings["seed"] in ("not set", "")


def test_collect_rerun_settings_candidate_identification(sandbox):
    write_champion_meta(sandbox, "legal_case")
    write_champion_meta(sandbox, "compare", type="比較題", type_slug="compare")
    champions = bvr.load_champion_metas()
    settings = bvr.collect_rerun_settings({}, champions, {}, [])
    ids = settings["candidate_identification"]
    assert any(x["prompt_path"] == "prompts/champions/legal_case.md" for x in ids)
    assert any(x["type"] == "比較題" for x in ids)


def test_collect_rerun_settings_execution_time(sandbox):
    sessions = [
        {"start": "2026-01-01 00:00:00", "stop": "2026-01-01 01:00:00", "elapsed": 3600},
        {"start": "2026-01-02 00:00:00", "stop": "2026-01-02 02:00:00", "elapsed": 7200},
    ]
    settings = bvr.collect_rerun_settings({}, [], {}, sessions)
    assert settings["execution_time"]["sessions"] == 2
    assert settings["execution_time"]["first_start"] == "2026-01-01 00:00:00"
    assert settings["execution_time"]["last_stop"] == "2026-01-02 02:00:00"
    assert settings["execution_time"]["total_elapsed_seconds"] == 10800.0


def test_build_report_includes_rerun_and_verification_sections(sandbox):
    write_baseline_meta(sandbox)
    write_champion_meta(sandbox, "legal_case")
    write_scorecard(sandbox, "cand_1", final_decision="ACCEPT")
    write_config(sandbox)
    report = bvr.build_report(limit=10)
    assert "## 7. 重跑所需設定（Rerun Settings）" in report
    assert "## 8. 證據驗證（產生時重新驗證）" in report
    assert "winner_input" in report
    assert "prompts/baseline.md" in report


def test_build_structured_report_is_complete_and_unlimited(sandbox):
    baseline_prompt = sandbox / "prompts" / "baseline.md"
    baseline_prompt.write_text("完整 winner 提示詞\n", encoding="utf-8")
    write_baseline_meta(sandbox, prompt_hash=bvr.sha256_file(str(baseline_prompt)))
    write_config(sandbox)
    write_evolution_log(sandbox, [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {"max_rounds": 1}},
        {"event": "stop", "timestamp": "2026-01-01 00:01:00", "reason": "done"},
    ])
    for index in range(3):
        candidate = sandbox / "prompts" / "candidates" / f"cand_{index}.md"
        candidate.write_text(f"candidate {index}\n", encoding="utf-8")
        write_scorecard(
            sandbox,
            f"cand_{index}",
            candidate_hash=bvr.sha256_file(str(candidate)),
            final_decision="ACCEPT" if index == 0 else "REJECT",
        )

    data = bvr.build_structured_report(limit=1)

    assert data["decision"]["status"] == "valid"
    assert data["winner"]["candidate_id"] == data["champion"]["prompt_hash"]
    assert data["winner"]["prompt"]["content"] == "完整 winner 提示詞\n"
    assert data["winner"]["workflow"]["commands"]
    assert len(data["candidate_comparison"]) == 3
    assert data["quality"]["measurement_basis"]["datasets"]
    assert data["reproduction"]["environment"]["python_version"]
    assert data["reproduction"]["input_data_versions"]
    assert data["execution"]["records"]
    assert data["schema_validation"]["valid"] is True
    assert bvr.validate_report_schema(data) is True


def test_incomplete_evidence_has_explicit_code_and_no_best_claim(sandbox):
    write_baseline_meta(sandbox)
    write_champion_meta(sandbox, "legal_case")
    write_scorecard(sandbox, "cand_1", final_decision="ACCEPT")
    write_config(sandbox)
    write_evolution_log(sandbox, [
        {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {}},
        {"event": "stop", "timestamp": "2026-01-01 00:01:00"},
    ])

    data = bvr.build_structured_report()

    assert data["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert data["evidence_integrity"]["status"] == "INCOMPLETE_EVIDENCE"
    assert data["decision"]["best_candidate_id"] is None
    assert data["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    assert data["quality"]["type_champions"] == []
    assert "INCOMPLETE_EVIDENCE" in bvr.build_report(structured=data)


def test_validate_report_schema_rejects_missing_required_field(sandbox):
    data = bvr.build_structured_report()
    del data["winner"]

    assert bvr.validate_report_schema(data) is False
    assert any("winner" in error for error in bvr.schema_validation_errors(data))


def test_report_rejects_candidates_with_different_evaluation_bases(sandbox):
    basis = {
        "dataset": "questions/dev.jsonl",
        "metric": "average_score",
        "evaluator_version": "evaluate-v1",
        "measurement_settings": {"parallel": 1},
    }
    other_basis = dict(basis, dataset="questions/dev-v2.jsonl")
    write_complete_report_evidence(
        sandbox,
        cand_1={"comparison_basis": basis},
        cand_2={"comparison_basis": other_basis},
    )

    data = bvr.build_structured_report()
    report = bvr.build_report(structured=data)

    assert_inconclusive_with_reproduction_commands(data, report)
    assert any("評測基準不同" in error for error in data["evidence_integrity"]["errors"])


def test_report_rejects_accepted_candidate_with_missing_measurement_field(sandbox):
    basis = {
        "dataset": "questions/dev.jsonl",
        "metric": "average_score",
        "evaluator_version": "evaluate-v1",
        "measurement_settings": {"parallel": 1},
    }
    write_complete_report_evidence(
        sandbox,
        cand_1={"comparison_basis": basis},
        cand_2={"comparison_basis": {key: value for key, value in basis.items() if key != "metric"}},
    )

    data = bvr.build_structured_report()
    report = bvr.build_report(structured=data)

    assert_inconclusive_with_reproduction_commands(data, report)
    assert any("關鍵量測欄位" in error for error in data["evidence_integrity"]["errors"])


@pytest.mark.parametrize("unreadable", [False, True])
def test_report_rejects_missing_or_unreadable_evidence_file(sandbox, monkeypatch, unreadable):
    write_complete_report_evidence(sandbox)
    config = sandbox / "config.yaml"
    if not unreadable:
        config.unlink()
    else:
        real_open = open

        def unreadable_open(path, *args, **kwargs):
            if str(path).replace("\\", "/").endswith("/config.yaml"):
                raise PermissionError("evidence is unreadable")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", unreadable_open)

    data = bvr.build_structured_report()
    report = bvr.build_report(structured=data)

    assert_inconclusive_with_reproduction_commands(data, report)
    assert any("有效執行證據" in error for error in data["evidence_integrity"]["errors"])


def test_report_rejects_tied_highest_accepted_score(sandbox):
    write_complete_report_evidence(
        sandbox,
        cand_1={"dev": {"score": 92.0}},
        cand_2={"dev": {"score": 92.0}},
    )

    data = bvr.build_structured_report()
    report = bvr.build_report(structured=data)

    assert_inconclusive_with_reproduction_commands(data, report)
    assert any("最高分同分" in error for error in data["evidence_integrity"]["errors"])
