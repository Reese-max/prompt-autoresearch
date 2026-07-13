# -*- coding: utf-8 -*-
"""tests/test_evaluate.py — scripts/evaluate.py 單元測試（全 mock，無真實網路呼叫）。"""
import json
import os
import sys

import pytest

import scripts.evaluate as evaluate

JUDGE_JSON = {
    "general_score": 55,
    "general_reason": "ok",
    "type_specific_score": 15,
    "type_specific_reason": "ok",
    "risk_score": 9,
    "risk_reason": "無",
    "total_score": 999,  # 故意錯，驗證會被重算
    "failures": ["F03"],
    "critique": "加強採分點",
}

QUESTION = {"id": 1, "type": "案例題", "question": "何謂行政處分？", "key_points": ["定義", "要件"]}


def make_result(**over):
    r = {
        "id": 1, "type": "案例題", "question": "Q", "answer": "A" * 900, "char_count": 900,
        "general_score": 55, "type_specific_score": 15, "risk_score": 10,
        "total_score": 80, "failures": ["F03"],
    }
    r.update(over)
    return r


def make_summary(**over):
    s = {
        "timestamp": "2026-01-01 00:00:00",
        "prompt_file": "prompt.md",
        "question_file": "q.jsonl",
        "prompt_hash": "abc123def456",
        "elapsed_seconds": 1.5,
        "total_questions": 2,
        "average_score": 80.0,
        "type_averages": {"案例題": 80.0},
        "failure_counts": {"F03": 2},
        "word_count_pass_rate": 100.0,
        "risk_perfect_rate": 100.0,
        "char_count": 100,
    }
    s.update(over)
    return s


# ---------- parse_judge_json ----------

def test_parse_judge_json_fenced():
    out = "```json\n" + json.dumps(JUDGE_JSON, ensure_ascii=False) + "\n```"
    assert evaluate.parse_judge_json(out)["general_score"] == 55


def test_parse_judge_json_bare():
    assert evaluate.parse_judge_json(json.dumps(JUDGE_JSON))["risk_score"] == 9


def test_parse_judge_json_embedded_in_prose():
    out = "評分如下 {\"general_score\": 40, \"risk_score\": 10} 以上"
    assert evaluate.parse_judge_json(out) == {"general_score": 40, "risk_score": 10}


def test_parse_judge_json_invalid_raises():
    with pytest.raises(Exception):
        evaluate.parse_judge_json("完全不是 JSON")


# ---------- cache ----------

def test_cache_path_structure():
    p = evaluate.cache_path("a" * 64, "questions/smoke.jsonl", 3)
    parts = p.replace("\\", "/").split("/")
    assert parts[0] == ".cache" and parts[1] == "eval"
    assert parts[2] == "a" * 16
    assert parts[-1] == "3.json"


def test_load_cached_result_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert evaluate.load_cached_result("h" * 64, "q.jsonl", 1) is None


def test_save_and_load_cached_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    evaluate.save_cached_result("h" * 64, "q.jsonl", 1, {"total_score": 80, "cached": True})
    path = evaluate.cache_path("h" * 64, "q.jsonl", 1)
    with open(path, encoding="utf-8") as f:
        on_disk = json.load(f)
    assert "cached" not in on_disk  # 存檔時剔除 cached 旗標
    loaded = evaluate.load_cached_result("h" * 64, "q.jsonl", 1)
    assert loaded["total_score"] == 80 and loaded["cached"] is True


def test_load_cached_result_corrupt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = evaluate.cache_path("h" * 64, "q.jsonl", 1)
    os.makedirs(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write("{broken json")
    assert evaluate.load_cached_result("h" * 64, "q.jsonl", 1) is None


# ---------- evaluate_single_question ----------

def test_esq_cache_hit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    evaluate.save_cached_result("h" * 64, "q.jsonl", 1, {"total_score": 77})

    def boom(*a, **k):
        raise AssertionError("cache hit 不應呼叫 API")

    monkeypatch.setattr(evaluate, "call_minimax", boom)
    res = evaluate.evaluate_single_question(QUESTION, "sp", "g", "t", "r", "f", "h" * 64, "q.jsonl")
    assert res["total_score"] == 77 and res["cached"] is True


def test_esq_answer_generation_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(evaluate, "call_minimax", boom)
    res = evaluate.evaluate_single_question(QUESTION, "sp", "g", "t", "r", "f", "h" * 64, "q.jsonl")
    assert res["error"] == "Answer Generation Failed: boom"
    assert res["total_score"] == 0 and res["failures"] == ["F01"]


def _fake_minimax(responses):
    calls = []

    def fake(system, user, temperature=0.7):
        calls.append(user)
        return responses[len(calls) - 1]

    return fake, calls


def test_esq_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    judge_out = "```json\n" + json.dumps(JUDGE_JSON, ensure_ascii=False) + "\n```"
    fake, calls = _fake_minimax(["答案" * 500, judge_out])
    monkeypatch.setattr(evaluate, "call_minimax", fake)
    res = evaluate.evaluate_single_question(QUESTION, "sp", "g", "t", "r", "f", "h" * 64, "q.jsonl")
    assert res["total_score"] == 55 + 15 + 9  # 防呆重算，非 999
    assert res["id"] == 1 and res["char_count"] == 1000
    assert len(calls) == 2
    # 成功後應寫入快取
    assert evaluate.load_cached_result("h" * 64, "q.jsonl", 1)["total_score"] == 79


def test_esq_judge_retry_then_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    judge_out = "```json\n" + json.dumps(JUDGE_JSON, ensure_ascii=False) + "\n```"
    fake, calls = _fake_minimax(["答案", "亂七八糟非 JSON", judge_out])
    monkeypatch.setattr(evaluate, "call_minimax", fake)
    res = evaluate.evaluate_single_question(QUESTION, "sp", "g", "t", "r", "f", "h" * 64, "q.jsonl")
    assert res["total_score"] == 79
    assert len(calls) == 3
    assert "重試要求" in calls[2]  # 第二輪 judge 帶重試提示


def test_esq_judge_fails_both_attempts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake, calls = _fake_minimax(["答案", "bad1", "bad2"])
    monkeypatch.setattr(evaluate, "call_minimax", fake)
    res = evaluate.evaluate_single_question(QUESTION, "sp", "g", "t", "r", "f", "h" * 64, "q.jsonl")
    assert res["error"].startswith("Judging Failed:")
    assert res["raw_judge_output"] == "bad2"
    assert res["total_score"] == 0 and res["failures"] == ["F01"]
    assert len(calls) == 3


# ---------- run_evaluation ----------

def _write_inputs(tmp_path, n_questions=3):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("測試提示詞", encoding="utf-8")
    qfile = tmp_path / "q.jsonl"
    lines = [json.dumps({"id": i, "type": "案例題", "question": f"Q{i}"}, ensure_ascii=False)
             for i in range(1, n_questions + 1)]
    qfile.write_text("\n".join(lines) + "\n\n", encoding="utf-8")
    return "prompt.md", "q.jsonl"


def test_run_evaluation_missing_prompt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        evaluate.run_evaluation("no_such_prompt.md", "q.jsonl")


def test_run_evaluation_missing_question_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("提示詞", encoding="utf-8")
    with pytest.raises(SystemExit):
        evaluate.run_evaluation("prompt.md", "no_such_q.jsonl")


def test_run_evaluation_normal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pf, qf = _write_inputs(tmp_path, 3)

    def fake_esq(q, *a, **k):
        return make_result(id=q["id"], question=q["question"], cached=(q["id"] == 1))

    monkeypatch.setattr(evaluate, "evaluate_single_question", fake_esq)
    summary, results = evaluate.run_evaluation(pf, qf, max_workers=2)
    assert len(results) == 3
    assert summary["total_questions"] == 3
    assert summary["average_score"] == 80.0
    assert summary["cache_hit_count"] == 1
    assert summary["estimated_api_calls"] == (3 - 1) * 2


def test_run_evaluation_worker_exception(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pf, qf = _write_inputs(tmp_path, 2)

    def fake_esq(q, *a, **k):
        raise ValueError("worker 爆炸")

    monkeypatch.setattr(evaluate, "evaluate_single_question", fake_esq)
    summary, results = evaluate.run_evaluation(pf, qf, max_workers=1)
    assert len(results) == 2
    assert all(r["error"] == "worker 爆炸" and r["total_score"] == 0 for r in results)


def test_run_evaluation_early_stop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pf, qf = _write_inputs(tmp_path, 6)

    def fake_esq(q, *a, **k):
        return make_result(id=q["id"], total_score=10)

    monkeypatch.setattr(evaluate, "evaluate_single_question", fake_esq)
    summary, results = evaluate.run_evaluation(pf, qf, max_workers=1, early_stop_threshold=90.0)
    # 1/3 = 2 題處檢查：平均 10 << 90-3，應提前中止
    assert len(results) < 6
    assert len(results) >= 2


# ---------- calculate_statistics ----------

def test_calculate_statistics_empty():
    assert evaluate.calculate_statistics([], 0.0, "p", "q", "h") == {}


def test_calculate_statistics_full(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompt.md").write_text("x" * 50, encoding="utf-8")
    results = [
        make_result(id=1, type="案例題", char_count=900, risk_score=10, failures=["F03", "F04"]),
        make_result(id=2, type="法理題", char_count=300, risk_score=5, total_score=60,
                    failures=[], cached=True),
        make_result(id=3, type="案例題", char_count=1000, risk_score=10, total_score=40,
                    failures=["F03", ""], error="oops"),
    ]
    s = evaluate.calculate_statistics(results, 12.3, "prompt.md", "q.jsonl", "h" * 64)
    assert s["total_questions"] == 3
    assert s["average_score"] == pytest.approx((80 + 60 + 40) / 3)
    assert s["type_averages"]["案例題"] == pytest.approx(60.0)
    assert s["type_averages"]["法理題"] == pytest.approx(60.0)
    assert s["failure_counts"] == {"F03": 2, "F04": 1}  # 空字串缺陷不計
    assert s["word_count_pass_rate"] == pytest.approx(2 / 3 * 100)
    assert s["risk_perfect_rate"] == pytest.approx(2 / 3 * 100)
    assert s["cache_hit_count"] == 1
    assert s["error_count"] == 1
    assert s["estimated_api_calls"] == (3 - 1) * 2
    assert s["char_count"] == 50


# ---------- save_run_results ----------

def test_save_run_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    results = [make_result(id=1), make_result(id=2, failures=[])]
    run_dir = evaluate.save_run_results(make_summary(), results)
    assert os.path.exists(f"{run_dir}/details.jsonl")
    assert os.path.exists(f"{run_dir}/summary.md")
    assert os.path.exists(f"{run_dir}/summary.json")
    for name in ("details.jsonl", "summary.md", "summary.json"):
        assert os.path.exists(f"runs/latest/{name}")
    with open(f"{run_dir}/details.jsonl", encoding="utf-8") as f:
        assert len([l for l in f if l.strip()]) == 2
    with open("results.tsv", encoding="utf-8") as f:
        tsv = f.read()
    assert "q.jsonl\t80.00\t100" in tsv
    with open(f"{run_dir}/summary.md", encoding="utf-8") as f:
        md = f.read()
    assert "F03" in md and "採分點不外露" in md


def test_save_run_results_collision_and_no_failures(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evaluate.time, "strftime", lambda fmt: "20260101_000000")
    os.makedirs("runs/20260101_000000")
    summary = make_summary(failure_counts={})
    run_dir = evaluate.save_run_results(summary, [make_result(failures=[])])
    assert run_dir == "runs/20260101_000000_02"  # 撞名走 suffix 分支
    with open(f"{run_dir}/summary.md", encoding="utf-8") as f:
        assert "無任何缺陷" in f.read()


# ---------- main ----------

def test_main_too_few_args(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evaluate.py"])
    with pytest.raises(SystemExit) as ei:
        evaluate.main()
    assert ei.value.code == 1


def _patch_pipeline(monkeypatch, captured):
    def fake_run(pf, qf, max_workers=6, early_stop_threshold=None):
        captured.update(pf=pf, qf=qf, workers=max_workers, threshold=early_stop_threshold)
        return make_summary(), [make_result()]

    monkeypatch.setattr(evaluate, "run_evaluation", fake_run)
    monkeypatch.setattr(evaluate, "save_run_results", lambda s, r: "runs/x")


def test_main_with_flags(monkeypatch):
    captured = {}
    _patch_pipeline(monkeypatch, captured)
    monkeypatch.setattr(sys, "argv",
                        ["evaluate.py", "p.md", "q.jsonl", "--parallel", "3", "--early-stop", "75.5"])
    evaluate.main()
    assert captured == {"pf": "p.md", "qf": "q.jsonl", "workers": 3, "threshold": 75.5}


def test_main_defaults_and_bad_flag_values(monkeypatch):
    captured = {}
    _patch_pipeline(monkeypatch, captured)
    # --parallel 給非數字、--early-stop 缺值 → 兩個 except 分支都吃掉，回退預設
    monkeypatch.setattr(sys, "argv",
                        ["evaluate.py", "p.md", "q.jsonl", "--parallel", "abc", "--early-stop"])
    evaluate.main()
    assert captured["workers"] == 6 and captured["threshold"] is None
