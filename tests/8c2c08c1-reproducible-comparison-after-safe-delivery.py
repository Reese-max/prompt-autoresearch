# -*- coding: utf-8 -*-
"""
8c2c08c1-reproducible-comparison-after-safe-delivery.py — 安全傳遞後的可重複比較證據測試。

在固定 seed 與受控模型／評測器（假 call_minimax，依候選提示詞內容決定論輸出）下，
對「正常提示詞」與「含 Shell payload 的純文字提示詞」各走完整評測流程
（write_file → evaluate.run_evaluation → evaluate.save_run_results），再以
compare_runs.compare 比較基準與候選，斷言下列證據均可機械解析、且相同輸入得到一致結果：

1. 候選識別：LAST_COMPARISON.candidate_id / round_no 機械可解析。
2. 輸入雜湊：summary.prompt_hash 為候選提示詞位元內容的 sha256，重跑一致。
3. 分數：details.jsonl 每筆 total_score 為數值、summary.average_score 為數值、均可 json.loads。
4. 淘汰／winner 決定：LAST_COMPARISON.passed 為 bool，輸出含 ACCEPT/REVERT。
5. 證據位置：LAST_COMPARISON.evidence_manifest 條目含 path/sha256 且檔案實際存在，
   new/base_details_path 指向實際存在的 details.jsonl。
6. 相同輸入重跑：無快取下兩次評測逐欄一致、兩次比較決定一致。

可直接執行：
    python tests/8c2c08c1-reproducible-comparison-after-safe-delivery.py

或以 pytest 執行：
    python -m pytest -q tests/8c2c08c1-reproducible-comparison-after-safe-delivery.py
"""
import json
import os
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

import lib.io as io
import scripts.compare_runs as compare_runs
import scripts.evaluate as evaluate

SENTINEL = "reproducible-comparison-sentinel.txt"
FIXED_SEED = 20260802

NORMAL_PROMPT = (
    "正常品質候選：你是一位國考申論題專家，直接輸出正文，"
    "不得編造，建立比較基準，法律題採三段論法。"
)

# 純文字提示詞內含 shell payload（命令替換、反引號、重導向、分號），
# 需作為普通文字安全傳遞，不得被任何 subprocess 解譯執行。
PAYLOAD_PROMPT = (
    "低分品質候選：你是一位國考申論題專家，直接輸出正文。\n"
    f"$(touch {SENTINEL}) ; `touch {SENTINEL}` ; echo pwned > {SENTINEL} | cat\n"
    "以上僅為提示詞文字內容，不可執行。"
)


def _find_sentinel(root):
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn == SENTINEL:
                return os.path.join(dirpath, fn)
    return None


def _write_question_file(root):
    qpath = root / "questions" / "q.jsonl"
    qpath.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"id": 1, "type": "案例題", "question": "何謂行政處分？", "key_points": ["定義"]},
        {"id": 2, "type": "法理題", "question": "何謂依法行政？", "key_points": ["意義"]},
    ]
    qpath.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return "questions/q.jsonl"


def _make_fake_minimax(captured):
    """受控評測器：依候選提示詞內容（system）決定論輸出，固定 seed 確保可重複。"""

    def fake(system, user, temperature=0.7):
        captured.append({"system": system, "temperature": temperature})
        digest = int(io.sha256_text(system), 16) & 0xFFFFFFFF
        rng = random.Random(FIXED_SEED ^ digest)
        if temperature == 0.3:
            return "模擬答案正文。" + "補充論述與法條涵攝。" * 90
        judge = {
            "general_score": rng.randint(40, 60),
            "general_reason": "ok",
            "type_specific_score": rng.randint(10, 18),
            "type_specific_reason": "ok",
            "risk_score": rng.randint(8, 10),
            "risk_reason": "ok",
            "total_score": 999,  # 故意給錯值，驗證會被防呆重算
            "failures": ["F03"] if rng.random() < 0.5 else [],
            "critique": "ok",
        }
        return "```json\n" + json.dumps(judge, ensure_ascii=False) + "\n```"

    return fake


def _run_pipeline(tmp_path, monkeypatch, prompt_text, captured, disable_cache=False):
    """完整評測流程：write_file → run_evaluation → save_run_results，回傳 (summary, results, run_dir)。"""
    prompt_path = "prompts/current.md"
    question_file = "questions/q.jsonl"
    io.write_file(prompt_path, prompt_text)
    _write_question_file(tmp_path)
    monkeypatch.setattr(evaluate, "call_minimax", _make_fake_minimax(captured))
    if disable_cache:
        monkeypatch.setattr(evaluate, "load_cached_result", lambda *a, **k: None)
    summary, results = evaluate.run_evaluation(prompt_path, question_file, max_workers=1)
    run_dir = evaluate.save_run_results(summary, results)
    return summary, results, run_dir


# ---------------------------------------------------------------------------
# 1. 正常與 payload 提示詞的評測證據機械可解析
# ---------------------------------------------------------------------------

def test_normal_and_payload_evaluation_evidence_mechanically_parseable(tmp_path, monkeypatch):
    """兩種提示詞走完整評測後，候選識別／輸入雜湊／分數均可機械解析，且無 shell 副作用。"""
    monkeypatch.chdir(tmp_path)
    captured = []

    for kind, prompt in [("normal", NORMAL_PROMPT), ("payload", PAYLOAD_PROMPT)]:
        summary, results, run_dir = _run_pipeline(tmp_path, monkeypatch, prompt, captured)

        # 輸入雜湊：prompt_hash == sha256(提示詞位元內容)
        assert isinstance(summary["prompt_hash"], str)
        assert len(summary["prompt_hash"]) == 64
        assert summary["prompt_hash"] == io.sha256_text(prompt), (
            f"[{kind}] summary.prompt_hash 必須為候選提示詞位元內容的 sha256"
        )

        # summary.json / details.jsonl 均可 json 機械解析
        with open(os.path.join(run_dir, "summary.json"), encoding="utf-8") as f:
            saved_summary = json.load(f)
        assert saved_summary["prompt_hash"] == io.sha256_text(prompt)
        assert isinstance(saved_summary["average_score"], (int, float))

        details_path = os.path.join(run_dir, "details.jsonl")
        assert os.path.isfile(details_path)
        rows = []
        with open(details_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        assert len(rows) == 2, f"[{kind}] details.jsonl 應有 2 筆可解析結果"
        for row in rows:
            assert isinstance(row["total_score"], (int, float))
            assert row["prompt_hash"] == io.sha256_text(prompt)
            assert isinstance(row["id"], int)

    assert _find_sentinel(tmp_path) is None, "含 shell payload 的純文字提示詞不得被執行"


# ---------------------------------------------------------------------------
# 2. 比較證據：候選識別、分數、淘汰／winner 決定、證據位置機械可解析
# ---------------------------------------------------------------------------

def test_compare_decision_and_evidence_locations_parseable(tmp_path, monkeypatch, capsys):
    """payload 候選 vs 正常基準的比較結果機械可解析，證據檔案實際存在。"""
    monkeypatch.chdir(tmp_path)
    captured = []
    _, _, base_run = _run_pipeline(tmp_path, monkeypatch, NORMAL_PROMPT, captured)
    _, _, cand_run = _run_pipeline(tmp_path, monkeypatch, PAYLOAD_PROMPT, captured)

    candidate_id = "prompts/candidates/8c2c08c1-payload-candidate.md"
    passed, avg_new, score_diff = compare_runs.compare(
        cand_run, base_run, candidate_id=candidate_id, round_no=1
    )
    lc = compare_runs.LAST_COMPARISON

    # 候選識別機械可解析
    assert lc["candidate_id"] == candidate_id
    assert lc["round_no"] == 1

    # 分數機械可解析
    assert isinstance(lc["avg_new"], float)
    assert isinstance(lc["avg_base"], float)
    assert isinstance(lc["score_diff"], float)
    assert avg_new == pytest.approx(lc["avg_new"])
    assert score_diff == pytest.approx(lc["score_diff"])

    # 淘汰／winner 決定機械可解析
    assert isinstance(lc["passed"], bool)
    assert passed == lc["passed"]
    out = capsys.readouterr().out
    assert ("ACCEPT" in out) or ("REVERT" in out)

    # 證據位置機械可解析且實際存在
    assert lc["new_details_path"] and os.path.isfile(lc["new_details_path"])
    assert lc["base_details_path"] and os.path.isfile(lc["base_details_path"])
    manifest = lc["evidence_manifest"]
    assert manifest, "completed comparison 應有非空 evidence_manifest"
    for entry in manifest:
        assert "path" in entry and "sha256" in entry and entry.get("verified") is True
        resolved = os.path.join(tmp_path, entry["path"])
        assert os.path.isfile(resolved), f"證據檔案不存在: {entry['path']}"


# ---------------------------------------------------------------------------
# 3. 相同輸入 → 一致結果（可重複）
# ---------------------------------------------------------------------------

def test_identical_input_reproducible_without_cache(tmp_path, monkeypatch):
    """無快取下，相同提示詞兩次評測結果逐欄一致。"""
    monkeypatch.chdir(tmp_path)
    captured = []

    s1, r1, _ = _run_pipeline(tmp_path, monkeypatch, NORMAL_PROMPT, captured, disable_cache=True)
    s2, r2, _ = _run_pipeline(tmp_path, monkeypatch, NORMAL_PROMPT, captured, disable_cache=True)

    assert s1["prompt_hash"] == s2["prompt_hash"]
    assert s1["average_score"] == s2["average_score"]
    assert len(r1) == len(r2) == 2
    for a, b in zip(r1, r2):
        assert a["id"] == b["id"]
        assert a["total_score"] == b["total_score"]
        assert a["general_score"] == b["general_score"]
        assert a["type_specific_score"] == b["type_specific_score"]
        assert a["risk_score"] == b["risk_score"]
        assert a["failures"] == b["failures"]


def test_identical_input_compare_decision_consistent(tmp_path, monkeypatch):
    """相同輸入重跑完整比較兩次，淘汰／winner 決定與分數一致。"""
    monkeypatch.chdir(tmp_path)
    captured = []
    decisions = []

    for _ in range(2):
        _, _, base_run = _run_pipeline(tmp_path, monkeypatch, NORMAL_PROMPT, captured)
        _, _, cand_run = _run_pipeline(tmp_path, monkeypatch, PAYLOAD_PROMPT, captured)
        passed, avg_new, score_diff = compare_runs.compare(
            cand_run, base_run, candidate_id="cand.md", round_no=1
        )
        decisions.append((passed, avg_new, score_diff))

    assert decisions[0] == decisions[1], (
        "相同輸入重跑比較應得到一致的淘汰／winner 決定與分數"
    )


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
