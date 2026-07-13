# -*- coding: utf-8 -*-
"""server ↔ feedback ↔ continuous_optimizer 整合層測試。

與 test_api_server.py 的差異：那邊把 _feedback_module 整個 mock 掉、只驗單一
handler 的契約；這裡讓 server 走「真實 api.feedback 分析鏈 + 真實檔案 I/O」，
只 stub 最外圈（路徑常數指向 tmp_path、subprocess.run 换成 stub），驗證：
1. POST /api/feedback 寫入後，GET /api/feedback/* 能讀回真實分析結果（端到端）
2. 弱點閾值邊界（維度 <15、題型 <70）經過 HTTP 層仍然正確
3. 真實分析鏈拋例外時 server 映射為 500
4. server 寫入的 feedback.jsonl 對 continuous_optimizer 可見（共享儲存契約）
5. run_optimization_round 的 direction/parallel 參數正確傳給 subprocess，
   其寫入的 optimization_log.jsonl 反映在 GET /api/optimizer/status
"""
import json

import pytest

import api.continuous_optimizer as optimizer
import api.feedback as feedback
import api.server as server

from test_api_server import get_json, post_json


# --- 共用環境：所有模組的路徑常數指向同一個 tmp_path ---

@pytest.fixture
def env(tmp_path, monkeypatch):
    feedback_path = str(tmp_path / "feedback.jsonl")
    meta_path = str(tmp_path / "baseline.meta.json")
    monkeypatch.setattr(server, "FEEDBACK_PATH", feedback_path)
    monkeypatch.setattr(server, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(feedback, "FEEDBACK_PATH", feedback_path)
    monkeypatch.setattr(feedback, "BASELINE_META_PATH", meta_path)
    monkeypatch.setattr(optimizer, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        optimizer, "OPTIMIZATION_LOG", str(tmp_path / "optimization_log.jsonl")
    )
    # server 接上真實 feedback 模組（非 mock），走完整分析鏈
    monkeypatch.setattr(server, "_feedback_module", {
        "summary": feedback.get_feedback_summary,
        "weak_areas": feedback.get_weak_areas,
        "hints": feedback.generate_optimization_hints,
    })
    return tmp_path


def post_feedback(prompt_hash="hash-a", scores=None, total_score=80,
                  question_type="申論"):
    payload = {
        "source": "shenlun",
        "prompt_hash": prompt_hash,
        "scores": scores if scores is not None else {"structure": 16},
        "total_score": total_score,
        "question_type": question_type,
    }
    return post_json("/api/feedback", payload)


# --- 1. POST 寫入 → GET 分析 端到端 ---

def test_post_then_summary_end_to_end(env):
    (env / "baseline.meta.json").write_text(
        json.dumps({"dev_avg": 82.5}), encoding="utf-8"
    )
    status, _, accepted = post_feedback(total_score=80, scores={"structure": 16})
    assert status == 200 and accepted["status"] == "accepted"
    post_feedback(total_score=90, scores={"structure": 18})

    status, _, summary = get_json("/api/feedback/summary")
    assert status == 200
    assert summary["total_feedback"] == 2
    assert summary["unique_prompts"] == 1
    assert summary["baseline_score"] == 82.5
    analysis = summary["prompt_analysis"]["hash-a"]
    assert analysis["count"] == 2
    assert analysis["avg_total"] == 85.0
    assert analysis["avg_scores"] == {"structure": 17.0}
    assert analysis["avg_by_type"] == {"申論": 85.0}


def test_summary_with_no_feedback_file(env):
    status, _, summary = get_json("/api/feedback/summary")
    assert status == 200
    assert summary["total_feedback"] == 0
    assert summary["unique_prompts"] == 0
    assert summary["baseline_score"] is None


# --- 2. 弱點閾值邊界（經 HTTP 層） ---

def test_weak_dimension_boundary_15(env):
    post_feedback(prompt_hash="h-ok", scores={"structure": 15}, total_score=75)
    post_feedback(prompt_hash="h-weak", scores={"structure": 14}, total_score=75)

    status, _, data = get_json("/api/feedback/weak-areas")
    assert status == 200
    assert len(data["weak_dimensions"]) == 1
    weak = data["weak_dimensions"][0]
    assert weak["prompt_hash"] == "h-weak"[:12]
    assert weak["dimension"] == "structure"
    assert weak["avg_score"] == 14


def test_weak_type_boundary_70(env):
    post_feedback(prompt_hash="h-ok", total_score=70, question_type="測驗")
    post_feedback(prompt_hash="h-weak", total_score=69, question_type="申論")

    status, _, data = get_json("/api/feedback/weak-areas")
    assert status == 200
    assert [t["question_type"] for t in data["weak_types"]] == ["申論"]
    assert data["weak_types"][0]["avg_score"] == 69


def test_hints_generated_only_for_known_dimensions(env):
    post_feedback(scores={"structure": 10, "unknownDim": 5}, total_score=80)

    status, _, data = get_json("/api/feedback/hints")
    assert status == 200
    targets = [h["target"] for h in data["hints"] if h["type"] == "dimension"]
    assert "structure" in targets
    assert "unknownDim" not in targets  # 未知維度不產生 hint


def test_lazy_import_wires_real_feedback_module(env, monkeypatch):
    """_feedback_module=None 時 server 應 lazy import 到真實 api.feedback。"""
    monkeypatch.setattr(server, "_feedback_module", None)
    post_feedback(total_score=88)
    status, _, summary = get_json("/api/feedback/summary")
    assert status == 200
    assert summary["total_feedback"] == 1


# --- 3. 真實分析鏈錯誤 → 500 映射 ---

def test_malformed_feedback_row_maps_to_500(env):
    # scores 為字串時，真實分析鏈的 scores.items() 會拋 AttributeError
    post_feedback(scores="not-a-dict")

    status, _, data = get_json("/api/feedback/summary")
    assert status == 500
    assert data["error"].startswith("分析失敗")


# --- 4. server 寫入 ↔ continuous_optimizer 讀取（共享儲存契約） ---

def test_server_feedback_visible_to_optimizer_threshold(env):
    has_enough, count = optimizer.check_feedback_threshold(min_feedback=2)
    assert (has_enough, count) == (False, 0)

    post_feedback()
    has_enough, count = optimizer.check_feedback_threshold(min_feedback=2)
    assert (has_enough, count) == (False, 1)

    post_feedback()
    has_enough, count = optimizer.check_feedback_threshold(min_feedback=2)
    assert (has_enough, count) == (True, 2)


def test_analyze_and_suggest_consistent_with_server_summary(env):
    post_feedback(scores={"structure": 10}, total_score=60)

    result = optimizer.analyze_and_suggest()
    status, _, summary = get_json("/api/feedback/summary")
    assert status == 200
    assert result["total_feedback"] == summary["total_feedback"] == 1
    assert result["hints"] == summary["optimization_hints"]
    assert result["weak_areas"] == summary["weak_areas"]

    logs = [json.loads(line) for line in
            (env / "optimization_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(logs) == 1
    assert logs[0]["event"] == "analysis"
    assert logs[0]["total_feedback"] == 1


# --- 5. run_optimization_round 參數傳遞與 status 反映 ---

class FakeCompleted:
    def __init__(self, returncode=0, stdout="ok", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_optimization_round_passes_direction_and_parallel(env, monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        return FakeCompleted()

    monkeypatch.setattr(optimizer.subprocess, "run", fake_run)
    assert optimizer.run_optimization_round(direction="structure", parallel=3) is True

    cmd = captured["cmd"]
    assert cmd[1] == "run_opt.py"
    idx = cmd.index("--force-direction")
    assert cmd[idx + 1] == "structure"
    for flag in ("--smoke-parallel", "--dev-parallel", "--holdout-parallel"):
        assert cmd[cmd.index(flag) + 1] == "3"
    assert captured["cwd"] == str(env)


def test_optimization_round_subprocess_kwargs_and_output_truncation(env, monkeypatch):
    """驗證 subprocess.run 的呼叫方式（kwargs）與 stdout/stderr 回傳截斷處理。"""
    long_stdout = "長輸出" + "x" * 2000
    long_stderr = "錯" + "y" * 1000
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["kwargs"] = kwargs
        return FakeCompleted(returncode=0, stdout=long_stdout, stderr=long_stderr)

    monkeypatch.setattr(optimizer.subprocess, "run", fake_run)
    assert optimizer.run_optimization_round(direction="structure") is True

    kw = captured["kwargs"]
    assert kw["capture_output"] is True
    assert kw["text"] is True
    assert kw["timeout"] == 3600

    logs = [json.loads(line) for line in
            (env / "optimization_log.jsonl").read_text(encoding="utf-8").splitlines()]
    rec = logs[-1]
    assert rec["event"] == "optimization" and rec["success"] is True
    # log 只保留 stdout 尾 1000、stderr 尾 500 字元
    assert rec["stdout"] == long_stdout[-1000:]
    assert rec["stderr"] == long_stderr[-500:]


def test_optimization_round_without_direction_omits_flag(env, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        optimizer.subprocess, "run",
        lambda cmd, **kw: captured.setdefault("cmd", cmd) and FakeCompleted()
        or FakeCompleted(),
    )
    optimizer.run_optimization_round()
    assert "--force-direction" not in captured["cmd"]


def test_optimization_success_reflected_in_server_status(env, monkeypatch):
    monkeypatch.setattr(
        optimizer.subprocess, "run", lambda cmd, **kw: FakeCompleted(returncode=0)
    )
    post_feedback()
    assert optimizer.run_optimization_round(direction="structure") is True

    status, _, data = get_json("/api/optimizer/status")
    assert status == 200
    assert data["status"] == "active"
    assert data["feedback_count"] == 1
    assert data["last_optimization"]["event"] == "optimization"
    assert data["last_optimization"]["success"] is True
    assert data["last_optimization"]["direction"] == "structure"


def test_optimization_failure_logged_and_status_active(env, monkeypatch):
    monkeypatch.setattr(
        optimizer.subprocess, "run",
        lambda cmd, **kw: FakeCompleted(returncode=1, stderr="炸了"),
    )
    assert optimizer.run_optimization_round() is False

    status, _, data = get_json("/api/optimizer/status")
    assert status == 200
    # 契約：status 只看有無 optimization 事件，不看 success 與否
    assert data["status"] == "active"
    assert data["last_optimization"]["success"] is False


def test_optimization_exception_logged_as_error_status_idle(env, monkeypatch):
    def boom(cmd, **kw):
        raise optimizer.subprocess.TimeoutExpired(cmd=cmd, timeout=3600)

    monkeypatch.setattr(optimizer.subprocess, "run", boom)
    assert optimizer.run_optimization_round() is False

    logs = [json.loads(line) for line in
            (env / "optimization_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert logs[-1]["event"] == "optimization_error"

    status, _, data = get_json("/api/optimizer/status")
    assert status == 200
    assert data["status"] == "idle"
    assert data["last_optimization"] is None
