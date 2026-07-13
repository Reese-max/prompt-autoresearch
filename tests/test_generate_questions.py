# -*- coding: utf-8 -*-
"""scripts/generate_questions.py 單元測試（tmp_path 隔離、無網路）。"""
import json

import scripts.generate_questions as gq


def _read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_generate_all_writes_three_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    gq.generate_all()

    out = capsys.readouterr().out
    for name in ("dev.jsonl", "holdout.jsonl", "final.jsonl"):
        assert (tmp_path / "questions" / name).exists()
        assert f"Successfully wrote {name}" in out

    dev = _read_jsonl(tmp_path / "questions" / "dev.jsonl")
    holdout = _read_jsonl(tmp_path / "questions" / "holdout.jsonl")
    final = _read_jsonl(tmp_path / "questions" / "final.jsonl")
    assert len(dev) == 36
    assert len(holdout) == 18
    assert len(final) == 12

    expected_types = {"說明題", "比較題", "評析題", "實務應用題", "法律法理題", "法律案例題"}
    for bank in (dev, holdout, final):
        assert {q["type"] for q in bank} == expected_types
        for q in bank:
            assert q["id"]
            assert q["question"]
            assert isinstance(q["key_points"], list) and q["key_points"]

    # id 在各題庫內不得重複（跨題庫存在既有重複 legal_case_002/003，屬資料現況）
    for bank in (dev, holdout, final):
        ids = [q["id"] for q in bank]
        assert len(ids) == len(set(ids))


def test_generate_all_idempotent_with_existing_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "questions").mkdir()
    gq.generate_all()  # exist_ok=True，不應炸
    assert (tmp_path / "questions" / "dev.jsonl").exists()
