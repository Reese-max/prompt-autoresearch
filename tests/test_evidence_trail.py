# -*- coding: utf-8 -*-
"""tests/test_evidence_trail.py — 機械可解析證據鏈與低分冠軍防護測試。

驗證項目：
1. compare() 回傳值包含完整評測證據路徑
2. LAST_COMPARISON 包含 candidate_id、round_no、details 路徑
3. scorecard 包含各階段實際分數
4. 低分候選不會被選為 elite/champion
5. record_round 包含 per-candidate 資訊
"""
import json
import os
import shutil
import time

import pytest

import scripts.compare_runs as cr


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------

def make_run(dirpath, records):
    dirpath.mkdir(parents=True, exist_ok=True)
    path = dirpath / "details.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return str(dirpath)


def rec(qid, qtype="事實", score=80.0, failures=None, char_count=1000, risk=10):
    return {
        "id": qid,
        "type": qtype,
        "total_score": score,
        "failures": failures or [],
        "char_count": char_count,
        "risk_score": risk,
    }


# ---------------------------------------------------------------------------
# compare() 返回值包含完整證據路徑
# ---------------------------------------------------------------------------

class TestCompareEvidencePaths:
    """驗證 compare() 回傳的 LAST_COMPARISON 包含可追溯的證據路徑。"""

    def test_last_comparison_includes_candidate_id_and_round(self, tmp_path):
        base = make_run(tmp_path / "base", [rec("q1", score=80.0)])
        new = make_run(tmp_path / "new", [rec("q1", score=86.0)])
        cr.compare(new, base, candidate_id="prompts/candidates/c_001.md", round_no=3)
        lc = cr.LAST_COMPARISON
        assert lc["candidate_id"] == "prompts/candidates/c_001.md"
        assert lc["round_no"] == 3

    def test_last_comparison_includes_details_paths(self, tmp_path):
        base = make_run(tmp_path / "base", [rec("q1")])
        new = make_run(tmp_path / "new", [rec("q1", score=85.0)])
        cr.compare(new, base)
        lc = cr.LAST_COMPARISON
        assert lc["new_details_path"] is not None
        assert lc["base_details_path"] is not None
        assert lc["new_details_path"].endswith("details.jsonl")
        assert lc["base_details_path"].endswith("details.jsonl")

    def test_last_comparison_includes_type_diffs(self, tmp_path):
        base = make_run(tmp_path / "base", [
            rec("q1", "事實", 80.0), rec("q2", "推理", 78.0),
        ])
        new = make_run(tmp_path / "new", [
            rec("q1", "事實", 86.0), rec("q2", "推理", 84.0),
        ])
        cr.compare(new, base)
        lc = cr.LAST_COMPARISON
        assert "事實" in lc["type_diffs"]
        assert "推理" in lc["type_diffs"]
        assert lc["type_diffs"]["事實"]["baseline_avg"] == pytest.approx(80.0)
        assert lc["type_diffs"]["事實"]["candidate_avg"] == pytest.approx(86.0)
        assert lc["type_diffs"]["事實"]["diff"] == pytest.approx(6.0)

    def test_last_comparison_includes_failure_counts(self, tmp_path):
        base = make_run(tmp_path / "base", [rec("q1", failures=["F03"])])
        new = make_run(tmp_path / "new", [rec("q1", failures=["F12", "F12"])])
        cr.compare(new, base)
        lc = cr.LAST_COMPARISON
        assert lc["failure_new"]["F12"] == 2
        assert lc["failure_base"]["F03"] == 1

    def test_last_comparison_without_candidate_id_defaults_none(self, tmp_path):
        base = make_run(tmp_path / "base", [rec("q1")])
        new = make_run(tmp_path / "new", [rec("q1", score=85.0)])
        cr.compare(new, base)
        assert cr.LAST_COMPARISON["candidate_id"] is None
        assert cr.LAST_COMPARISON["round_no"] is None


# ---------------------------------------------------------------------------
# 低分候選不應成為 champion
# ---------------------------------------------------------------------------

class TestLowScoreChampionGuard:
    """驗證 save_elite_candidate 在候選均分低於門檻時不寫入 champion pool。"""

    def _import_run_opt(self):
        import run_opt
        return run_opt

    def test_low_score_candidate_rejected(self, tmp_path, monkeypatch):
        """候選均分 < 60 時，即使有題型突破也不應被保存為 elite/champion。"""
        ro = self._import_run_opt()
        monkeypatch.chdir(tmp_path)
        os.makedirs("prompts/candidates", exist_ok=True)
        os.makedirs("prompts/champions", exist_ok=True)
        os.makedirs("prompts/candidates/elite", exist_ok=True)

        cand_path = "prompts/candidates/low_score.md"
        with open(cand_path, "w", encoding="utf-8") as f:
            f.write("test prompt")
        shutil.copy(cand_path, "prompts/current.md")

        comparison = {
            "avg_new": 55.0,
            "score_diff": -5.0,
            "risk_rate": 100.0,
            "base_risk_rate": 100.0,
            "type_breakthroughs": [
                {"type": "事實", "baseline_avg": 50.0, "candidate_avg": 58.0, "diff": 8.0},
            ],
        }

        saved = ro.save_elite_candidate(
            "test prompt", cand_path, "D01", "hypothesis",
            "runs/dev_run", "runs/base_dev_run", comparison,
        )
        assert saved == [], "低分候選不應被保存為 elite"
        assert not os.path.exists("prompts/champions/general.meta.json"), \
            "低分候選不應晉升為 champion"

    def test_high_score_candidate_accepted(self, tmp_path, monkeypatch):
        """候選均分 >= 60 且有題型突破時，應被保存。"""
        ro = self._import_run_opt()
        monkeypatch.chdir(tmp_path)
        os.makedirs("prompts/candidates", exist_ok=True)
        os.makedirs("prompts/champions", exist_ok=True)
        os.makedirs("prompts/candidates/elite", exist_ok=True)

        cand_path = "prompts/candidates/high_score.md"
        with open(cand_path, "w", encoding="utf-8") as f:
            f.write("test prompt high score")

        comparison = {
            "avg_new": 85.0,
            "score_diff": 5.0,
            "risk_rate": 100.0,
            "base_risk_rate": 100.0,
            "type_breakthroughs": [
                {"type": "事實", "baseline_avg": 78.0, "candidate_avg": 90.0, "diff": 12.0},
            ],
        }

        saved = ro.save_elite_candidate(
            "test prompt high score", cand_path, "D01", "hypothesis",
            "runs/dev_run", "runs/base_dev_run", comparison,
        )
        assert len(saved) == 1
        meta = saved[0]
        assert meta["overall_avg"] == 85.0
        assert meta["overall_diff"] == 5.0
        assert meta["candidate_avg"] == 90.0

    def test_boundary_score_60_accepted(self, tmp_path, monkeypatch):
        """候選均分恰好 60 分時應被接受（>= 門檻）。"""
        ro = self._import_run_opt()
        monkeypatch.chdir(tmp_path)
        os.makedirs("prompts/candidates", exist_ok=True)
        os.makedirs("prompts/champions", exist_ok=True)
        os.makedirs("prompts/candidates/elite", exist_ok=True)

        cand_path = "prompts/candidates/boundary.md"
        with open(cand_path, "w", encoding="utf-8") as f:
            f.write("test prompt boundary")

        comparison = {
            "avg_new": 60.0,
            "score_diff": 3.0,
            "risk_rate": 100.0,
            "base_risk_rate": 100.0,
            "type_breakthroughs": [
                {"type": "事實", "baseline_avg": 50.0, "candidate_avg": 65.0, "diff": 15.0},
            ],
        }

        saved = ro.save_elite_candidate(
            "test prompt boundary", cand_path, "D01", "hypothesis",
            "runs/dev_run", "runs/base_dev_run", comparison,
        )
        assert len(saved) == 1


# ---------------------------------------------------------------------------
# metrics.record_round 證據完整性
# ---------------------------------------------------------------------------

class TestRecordRoundEvidence:
    """驗證 record_round 記錄 per-candidate 資訊。"""

    def test_record_round_with_candidate_details(self, tmp_path, monkeypatch):
        import lib.metrics as metrics
        metrics_path = tmp_path / "metrics.jsonl"
        monkeypatch.setattr(metrics, "METRICS_PATH", str(metrics_path))

        payload = metrics.record_round(
            round_no=2,
            direction="D03",
            target_failures=["F03"],
            smoke_score=82.5,
            dev_score=80.0,
            holdout_score=79.0,
            accept=True,
            score_diff=3.5,
            candidate_id="prompts/candidates/c_002.md",
            candidate_scores=[
                {"stage": "smoke", "score": 82.5, "run": "runs/smoke_run"},
                {"stage": "dev", "score": 80.0, "run": "runs/dev_run"},
                {"stage": "holdout", "score": 79.0, "run": "runs/holdout_run"},
            ],
            winner_id="prompts/candidates/c_002.md",
        )

        assert payload["candidate_id"] == "prompts/candidates/c_002.md"
        assert payload["winner_id"] == "prompts/candidates/c_002.md"
        assert len(payload["candidate_scores"]) == 3
        assert payload["candidate_scores"][0]["stage"] == "smoke"
        assert payload["candidate_scores"][1]["score"] == 80.0

        with open(metrics_path, encoding="utf-8") as f:
            line = f.readline().strip()
        saved = json.loads(line)
        assert saved["candidate_id"] == "prompts/candidates/c_002.md"
        assert saved["winner_id"] == "prompts/candidates/c_002.md"

    def test_record_round_with_elimination_reasons(self, tmp_path, monkeypatch):
        import lib.metrics as metrics
        metrics_path = tmp_path / "metrics.jsonl"
        monkeypatch.setattr(metrics, "METRICS_PATH", str(metrics_path))

        payload = metrics.record_round(
            round_no=1,
            direction="D01",
            target_failures=["F01"],
            smoke_score=70.0,
            dev_score=65.0,
            accept=False,
            score_diff=-3.0,
            candidate_id="prompts/candidates/c_003.md",
            candidate_scores=[
                {"stage": "smoke", "score": 70.0, "run": "runs/smoke"},
                {"stage": "dev", "score": 65.0, "run": "runs/dev"},
            ],
            elimination_reasons=["dev acceptance failed: score 65 < 70 baseline"],
        )

        assert payload["accept"] is False
        assert len(payload["elimination_reasons"]) == 1
        assert "dev acceptance failed" in payload["elimination_reasons"][0]

    def test_record_round_backward_compatible(self, tmp_path, monkeypatch):
        """舊版呼叫方式（不帶新參數）仍能正常運作。"""
        import lib.metrics as metrics
        metrics_path = tmp_path / "metrics.jsonl"
        monkeypatch.setattr(metrics, "METRICS_PATH", str(metrics_path))

        payload = metrics.record_round(
            round_no=0, direction="D01", smoke_score=80.0, dev_score=78.0, accept=True,
        )
        assert payload["candidate_id"] is None
        assert payload["candidate_scores"] == []
        assert payload["winner_id"] is None
        assert payload["elimination_reasons"] == []


# ---------------------------------------------------------------------------
# scorecard 包含各階段實際分數
# ---------------------------------------------------------------------------

class TestScorecardScores:
    """驗證 run_opt 的 scorecard 包含各階段實際分數與 evidence 路徑。"""

    def test_scorecard_accept_includes_evidence(self, tmp_path, monkeypatch):
        """ACCEPT 後的 scorecard 應包含 evidence 與 type_averages。"""
        ro_module = __import__("run_opt", fromlist=["update_candidate_scorecard", "scorecard_path"])
        monkeypatch.chdir(tmp_path)
        os.makedirs("prompts/candidates", exist_ok=True)
        cand_path = "prompts/candidates/test_cand.md"
        with open(cand_path, "w", encoding="utf-8") as f:
            f.write("test")

        ro_module.update_candidate_scorecard(
            cand_path,
            smoke={"passed": True, "score": 82.5, "run": "runs/smoke_run", "type_averages": {"事實": 85.0}},
            dev={"score": 80.0, "run": "runs/dev_run", "type_averages": {"事實": 82.0}},
            holdout={"score": 79.0, "run": "runs/holdout_run", "accepted": True, "type_averages": {"事實": 80.0}},
            final_decision="ACCEPT",
            evidence={
                "smoke_run": "runs/smoke_run",
                "smoke_score": 82.5,
                "dev_run": "runs/dev_run",
                "dev_score": 80.0,
                "holdout_run": "runs/holdout_run",
                "holdout_score": 79.0,
                "baseline_dev_run": "runs/baseline_dev",
                "score_diff": 3.5,
            },
        )

        card_path = cand_path.replace(".md", ".scorecard.json")
        with open(card_path, encoding="utf-8") as f:
            card = json.load(f)
        assert card["final_decision"] == "ACCEPT"
        assert card["smoke"]["score"] == 82.5
        assert card["smoke"]["type_averages"]["事實"] == 85.0
        assert card["dev"]["score"] == 80.0
        assert card["dev"]["type_averages"]["事實"] == 82.0
        assert card["holdout"]["score"] == 79.0
        assert card["holdout"]["type_averages"]["事實"] == 80.0
        assert card["evidence"]["dev_score"] == 80.0
        assert card["evidence"]["score_diff"] == 3.5

    def test_scorecard_revert_includes_reject_reasons(self, tmp_path, monkeypatch):
        """REVERT 後的 scorecard 應包含 reject_reasons 與 evidence。"""
        ro_module = __import__("run_opt", fromlist=["update_candidate_scorecard"])
        monkeypatch.chdir(tmp_path)
        os.makedirs("prompts/candidates", exist_ok=True)
        cand_path = "prompts/candidates/rejected.md"
        with open(cand_path, "w", encoding="utf-8") as f:
            f.write("test")

        ro_module.update_candidate_scorecard(
            cand_path,
            final_decision="REVERT",
            reject_reasons=["dev acceptance failed"],
            evidence={
                "smoke_score": 75.0,
                "dev_score": 70.0,
                "score_diff": -2.0,
            },
        )

        card_path = cand_path.replace(".md", ".scorecard.json")
        with open(card_path, encoding="utf-8") as f:
            card = json.load(f)
        assert card["final_decision"] == "REVERT"
        assert "dev acceptance failed" in card["reject_reasons"]
        assert card["evidence"]["dev_score"] == 70.0
