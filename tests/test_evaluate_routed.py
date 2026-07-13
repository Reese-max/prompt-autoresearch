# -*- coding: utf-8 -*-
"""tests/test_evaluate_routed.py — scripts/evaluate_routed.py 單元與 CLI 測試。

外部呼叫（lib.api / MiniMax）全部透過 monkeypatch evaluate 模組隔離，
檔案 I/O 以 tmp_path 隔離。
"""
import importlib
import json
import runpy
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "evaluate_routed.py"

sys.path.insert(0, str(PROJECT_ROOT))
er = importlib.import_module("scripts.evaluate_routed")
# evaluate_routed 內部以 `import evaluate` 匯入 scripts/evaluate.py，
# 這裡取同一個模組物件，monkeypatch 它即可攔截所有外部呼叫。
evaluate_mod = sys.modules["evaluate"]


# ---------- 測試資料 helpers ----------

def make_route(tmp_path, route=None):
    route = route if route is not None else {
        "name": "test-route",
        "default_prompt": "prompts/p_default.md",
        "by_type": {"legal": "prompts/p_legal.md"},
    }
    path = tmp_path / "route.json"
    path.write_text(json.dumps(route, ensure_ascii=False), encoding="utf-8")
    return path, route


def make_questions(tmp_path, rows):
    path = tmp_path / "questions.jsonl"
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    # 夾一行空白，驗證跳過空行
    path.write_text("\n".join(lines[:1] + [""] + lines[1:]) + "\n", encoding="utf-8")
    return path


def patch_evaluate(monkeypatch, tmp_path, single_fn=None):
    """把 evaluate 模組所有會碰網路/真實 runs 目錄的函式換成假件。"""
    monkeypatch.setattr(evaluate_mod, "load_file", lambda p, default="": f"TEXT:{p}")

    def default_single(q, prompt_text, gr, tr, rr, ft, prompt_hash, qf):
        return {
            "id": q["id"], "type": q["type"], "question": q.get("question", ""),
            "total_score": 90, "failures": [], "cached": q.get("id") == "q2",
        }

    monkeypatch.setattr(evaluate_mod, "evaluate_single_question", single_fn or default_single)
    monkeypatch.setattr(
        evaluate_mod, "calculate_statistics",
        lambda results, elapsed, pf, qf, ph: {
            "average_score": 90.0, "risk_perfect_rate": 100.0, "n": len(results),
        },
    )
    run_dir = tmp_path / "run_out"
    run_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(evaluate_mod, "save_run_results", lambda summary, results: str(run_dir))
    return run_dir


# ---------- 純函式 ----------

def test_load_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "a.json"
    p.write_text('{"k": "v"}', encoding="utf-8")
    assert er.load_json(str(p)) == {"k": "v"}


def test_load_questions_skips_blank_lines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = make_questions(tmp_path, [{"id": "q1", "type": "legal"}, {"id": "q2", "type": "essay"}])
    rows = er.load_questions(str(path))
    assert [r["id"] for r in rows] == ["q1", "q2"]


def test_resolve_prompt_by_type_and_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evaluate_mod, "load_file", lambda p, default="": f"TEXT:{p}")
    route = {"default_prompt": "d.md", "by_type": {"legal": "l.md"}}

    path, text, digest = er.resolve_prompt(route, "legal")
    assert path == "l.md" and text == "TEXT:l.md"
    assert digest == evaluate_mod.sha256_text("TEXT:l.md")

    path, _, _ = er.resolve_prompt(route, "unknown-type")
    assert path == "d.md"


def test_resolve_prompt_no_route_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="default_prompt"):
        er.resolve_prompt({}, "legal")


def test_resolve_prompt_empty_file_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evaluate_mod, "load_file", lambda p, default="": "")
    with pytest.raises(RuntimeError, match="不存在或空白"):
        er.resolve_prompt({"default_prompt": "d.md"}, "legal")


def test_route_hash_deterministic_and_sensitive(tmp_path):
    route_a = {"default_prompt": "a.md", "by_type": {"legal": "l.md"}}
    route_b = {"default_prompt": "b.md", "by_type": {"legal": "l.md"}}
    h1 = er.route_hash("route.json", route_a)
    h2 = er.route_hash("route.json", route_a)
    h3 = er.route_hash("route.json", route_b)
    assert h1 == h2
    assert h1 != h3


def test_calculate_route_usage():
    results = [{"prompt_file": "a.md"}, {"prompt_file": "a.md"}, {"prompt_file": "b.md"}, {}]
    assert er.calculate_route_usage(results) == {"a.md": 2, "b.md": 1, "": 1}


# ---------- run_routed_evaluation ----------

def test_run_routed_evaluation_success(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    route_file, route = make_route(tmp_path)
    q_file = make_questions(tmp_path, [
        {"id": "q1", "type": "legal", "question": "Q1"},
        {"id": "q2", "type": "essay", "question": "Q2"},
    ])
    run_dir = patch_evaluate(monkeypatch, tmp_path)

    summary, results = er.run_routed_evaluation(str(route_file), str(q_file), max_workers=2)

    assert len(results) == 2
    assert summary["route_name"] == "test-route"
    assert summary["route"] == route
    assert summary["prompt_usage"] == {"prompts/p_legal.md": 1, "prompts/p_default.md": 1}
    # run_dir 內應寫出 route.json 與 route_source.json
    saved_route = json.loads((run_dir / "route.json").read_text(encoding="utf-8"))
    assert saved_route == route
    assert (run_dir / "route_source.json").exists()
    out = capsys.readouterr().out
    assert "路由評估完成" in out
    assert "cache" in out  # q2 標記 cached 分支


def test_run_routed_evaluation_worker_exception(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    route_file, _ = make_route(tmp_path)
    q_file = make_questions(tmp_path, [
        {"id": "q1", "type": "legal", "question": "Q1"},
        {"id": "q2", "type": "essay", "question": "Q2"},
    ])

    def boom(q, *a, **k):
        if q["id"] == "q1":
            raise ValueError("模擬 API 失敗")
        return {"id": q["id"], "type": q["type"], "total_score": 80, "failures": ["F02"]}

    patch_evaluate(monkeypatch, tmp_path, single_fn=boom)

    summary, results = er.run_routed_evaluation(str(route_file), str(q_file), max_workers=1)

    err_rows = [r for r in results if r.get("error")]
    assert len(err_rows) == 1
    assert err_rows[0]["failures"] == ["F01"]
    assert err_rows[0]["total_score"] == 0
    assert err_rows[0]["prompt_file"] == "prompts/p_legal.md"
    assert "F02" in capsys.readouterr().out


def test_run_routed_evaluation_empty_questions_raises(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    route_file, _ = make_route(tmp_path)
    q_file = tmp_path / "empty.jsonl"
    q_file.write_text("\n", encoding="utf-8")
    monkeypatch.setattr(evaluate_mod, "load_file", lambda p, default="": f"TEXT:{p}")
    with pytest.raises(RuntimeError, match="題庫空白"):
        er.run_routed_evaluation(str(route_file), str(q_file))


# ---------- __main__ CLI ----------

def run_as_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", argv)
    return runpy.run_path(str(SCRIPT_PATH), run_name="__main__")


def test_main_usage_exit(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run_as_main(monkeypatch, ["evaluate_routed.py"])
    assert exc.value.code == 1


def test_main_bad_parallel_exit(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    route_file, _ = make_route(tmp_path)
    q_file = make_questions(tmp_path, [{"id": "q1", "type": "legal"}])
    with pytest.raises(SystemExit) as exc:
        run_as_main(monkeypatch, ["evaluate_routed.py", str(route_file), str(q_file), "--parallel", "abc"])
    assert exc.value.code == 1


def test_main_success_path(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    route_file, _ = make_route(tmp_path)
    q_file = make_questions(tmp_path, [{"id": "q1", "type": "legal", "question": "Q1"}])
    patch_evaluate(monkeypatch, tmp_path)

    # runpy 重新執行 script 頂層（含 os.chdir 回專案根），但 `import evaluate`
    # 命中 sys.modules 快取，因此上面 patch 過的假件仍然生效，不會打真 API。
    run_as_main(monkeypatch, ["evaluate_routed.py", str(route_file), str(q_file), "--parallel", "2"])

    out = capsys.readouterr().out
    assert "路由評估完成" in out
    assert "prompts/p_legal.md" in out


def test_main_without_parallel_defaults_to_24(monkeypatch, tmp_path, capsys):
    """CLI 不帶 --parallel → not-in 分支，workers 使用預設 24。"""
    monkeypatch.chdir(tmp_path)
    route_file, _ = make_route(tmp_path)
    q_file = make_questions(tmp_path, [{"id": "q1", "type": "legal", "question": "Q1"}])
    patch_evaluate(monkeypatch, tmp_path)

    run_as_main(monkeypatch, ["evaluate_routed.py", str(route_file), str(q_file)])

    out = capsys.readouterr().out
    assert "並行執行緒: 24" in out
    assert "路由評估完成" in out
