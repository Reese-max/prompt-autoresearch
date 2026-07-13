# -*- coding: utf-8 -*-
"""scripts/backfill_candidate_scorecards.py 單元測試（tmp_path 隔離、無網路）。"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

import scripts.backfill_candidate_scorecards as bf


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """把 ROOT / CANDIDATE_DIR 指到 tmp_path，隔離檔案 I/O。"""
    candidate_dir = tmp_path / "prompts" / "candidates"
    candidate_dir.mkdir(parents=True)
    monkeypatch.setattr(bf, "ROOT", tmp_path)
    monkeypatch.setattr(bf, "CANDIDATE_DIR", candidate_dir)
    return candidate_dir


class TestHelpers:
    def test_sha256_text(self):
        assert bf.sha256_text("abc") == hashlib.sha256(b"abc").hexdigest()

    def test_read_text_missing(self, tmp_path):
        assert bf.read_text(tmp_path / "nope.md") == ""

    def test_read_text_exists(self, tmp_path):
        p = tmp_path / "a.md"
        p.write_text("內容", encoding="utf-8")
        assert bf.read_text(p) == "內容"

    def test_load_json_missing(self, tmp_path):
        assert bf.load_json(tmp_path / "nope.json") == {}

    def test_load_json_invalid(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{oops", encoding="utf-8")
        assert bf.load_json(p) == {}

    def test_load_json_valid(self, tmp_path):
        p = tmp_path / "ok.json"
        p.write_text('{"direction": "d1"}', encoding="utf-8")
        assert bf.load_json(p) == {"direction": "d1"}

    def test_parse_meta_md(self, tmp_path):
        p = tmp_path / "m.meta.md"
        p.write_text(
            "# 標題\n- direction: 修正格式\n- temperature: 0.7\n沒有 dash 的行\n",
            encoding="utf-8",
        )
        meta = bf.parse_meta_md(p)
        assert meta == {"direction": "修正格式", "temperature": "0.7"}


class TestIsCandidatePrompt:
    def test_accepts_candidate_prefixes(self):
        for name in ("candidate_1.md", "compare_x.md", "analyze_y.md",
                     "explain_z.md", "legal_a.md", "practical_b.md"):
            assert bf.is_candidate_prompt(Path(name)) is True

    def test_rejects_non_md(self):
        assert bf.is_candidate_prompt(Path("candidate_1.txt")) is False

    def test_rejects_meta_and_scorecard(self):
        assert bf.is_candidate_prompt(Path("candidate_1.meta.md")) is False
        assert bf.is_candidate_prompt(Path("candidate_1.scorecard.md")) is False

    def test_rejects_other_prefix(self):
        assert bf.is_candidate_prompt(Path("readme.md")) is False


class TestBuildScorecard:
    def test_with_meta_md_and_json(self, sandbox):
        cand = sandbox / "candidate_1.md"
        cand.write_text("prompt 本體", encoding="utf-8")
        (sandbox / "candidate_1.meta.md").write_text(
            "- direction: 加強結構\n- target_failures: F1,F2\n- candidate_index: 3\n",
            encoding="utf-8",
        )
        (sandbox / "candidate_1.meta.json").write_text(
            json.dumps({"hypothesis": "假說 A"}), encoding="utf-8"
        )
        card = bf.build_scorecard(cand)
        assert card["candidate_path"] == "prompts/candidates/candidate_1.md"
        assert card["candidate_hash"] == bf.sha256_text("prompt 本體")
        assert card["candidate_length"] == len("prompt 本體")
        assert card["status"] == "backfilled_existing"
        assert card["direction"] == "加強結構"
        assert card["target_failures"] == "F1,F2"
        assert card["hypothesis"] == "假說 A"
        assert card["candidate_index"] == "3"
        assert card["source_meta"]["meta_md"].endswith("candidate_1.meta.md")
        assert card["source_meta"]["meta_json"].endswith("candidate_1.meta.json")

    def test_without_meta(self, sandbox):
        cand = sandbox / "candidate_2.md"
        cand.write_text("x", encoding="utf-8")
        card = bf.build_scorecard(cand)
        assert card["direction"] == ""
        assert card["hypothesis"] == ""
        assert card["source_meta"] == {"meta_md": "", "meta_json": ""}


class TestMain:
    def _run(self, monkeypatch, *argv):
        monkeypatch.setattr(sys, "argv", ["backfill_candidate_scorecards.py", *argv])
        bf.main()

    def test_creates_scorecards(self, sandbox, monkeypatch, capsys):
        (sandbox / "candidate_1.md").write_text("a", encoding="utf-8")
        (sandbox / "candidate_1.meta.md").write_text("- direction: d\n", encoding="utf-8")
        (sandbox / "other.md").write_text("skip me", encoding="utf-8")
        self._run(monkeypatch)
        assert "candidates=1 created=1 skipped=0" in capsys.readouterr().out
        card = json.loads((sandbox / "candidate_1.scorecard.json").read_text(encoding="utf-8"))
        assert card["direction"] == "d"

    def test_skips_existing(self, sandbox, monkeypatch, capsys):
        (sandbox / "candidate_1.md").write_text("a", encoding="utf-8")
        (sandbox / "candidate_1.scorecard.json").write_text("{}", encoding="utf-8")
        self._run(monkeypatch)
        assert "created=0 skipped=1" in capsys.readouterr().out
        assert (sandbox / "candidate_1.scorecard.json").read_text(encoding="utf-8") == "{}"

    def test_force_overwrites(self, sandbox, monkeypatch, capsys):
        (sandbox / "candidate_1.md").write_text("a", encoding="utf-8")
        (sandbox / "candidate_1.scorecard.json").write_text("{}", encoding="utf-8")
        self._run(monkeypatch, "--force")
        assert "created=1 skipped=0" in capsys.readouterr().out
        card = json.loads((sandbox / "candidate_1.scorecard.json").read_text(encoding="utf-8"))
        assert card["candidate_hash"] == bf.sha256_text("a")

    def test_missing_candidate_dir(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(bf, "ROOT", tmp_path)
        monkeypatch.setattr(bf, "CANDIDATE_DIR", tmp_path / "prompts" / "candidates")
        self._run(monkeypatch)
        assert "candidates=0 created=0 skipped=0" in capsys.readouterr().out
