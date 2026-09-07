# -*- coding: utf-8 -*-
"""tests/test_preflight.py — scripts/preflight.py 單元與 CLI 測試。

不做真實網路呼叫（preflight 本身只讀檔與環境變數）；
所有檔案 I/O 以 tmp_path 隔離，測試前 monkeypatch.chdir(tmp_path)。
"""
import importlib
import json
import runpy
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "preflight.py"

sys.path.insert(0, str(PROJECT_ROOT))
preflight = importlib.import_module("scripts.preflight")


# ---------- 測試資料 helpers ----------

def write_jsonl(path, count):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"id": i}) for i in range(count)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_run_dir(base, name):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "summary.md").write_text("summary", encoding="utf-8")
    (d / "details.jsonl").write_text("{}", encoding="utf-8")
    return d


def build_healthy_env(tmp_path, monkeypatch):
    """在 tmp_path 建出一套會全數通過的 preflight 環境。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    for var in ("AUTORESEARCH_SMOKE_PARALLEL", "AUTORESEARCH_DEV_PARALLEL", "AUTORESEARCH_HOLDOUT_PARALLEL"):
        monkeypatch.delenv(var, raising=False)

    for rel, expected in preflight.EXPECTED_COUNTS.items():
        write_jsonl(tmp_path / rel, expected)

    baseline_text = "baseline prompt 內容"
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "baseline.md").write_text(baseline_text, encoding="utf-8")
    (tmp_path / "prompts" / "current.md").write_text("current prompt 內容", encoding="utf-8")

    dev_run = make_run_dir(tmp_path, "runs/dev1")
    smoke_run = make_run_dir(tmp_path, "runs/smoke1")
    holdout_run = make_run_dir(tmp_path, "runs/holdout1")
    meta = {
        "prompt_hash": preflight.sha256_text(baseline_text.strip()),
        "dev_run": str(dev_run),
        "smoke_run": str(smoke_run),
        "holdout_run": str(holdout_run),
    }
    (tmp_path / "prompts" / "baseline.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "runs" / "latest").mkdir(parents=True, exist_ok=True)
    (tmp_path / "runs" / "latest" / "summary.md").write_text("latest", encoding="utf-8")
    return meta


# ---------- 純函式 ----------

def test_read_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert preflight.read_text("no_such.md") == ""
    (tmp_path / "a.md").write_text("hello", encoding="utf-8")
    assert preflight.read_text("a.md") == "hello"


def test_sha256_text():
    # sha256("abc") 已知值
    assert preflight.sha256_text("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_count_jsonl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert preflight.count_jsonl("missing.jsonl") is None
    p = tmp_path / "q.jsonl"
    p.write_text('{"id": 1}\n\n{"id": 2}\n', encoding="utf-8")
    assert preflight.count_jsonl("q.jsonl") == 2


def test_count_jsonl_invalid_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad.jsonl").write_text("not-json\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        preflight.count_jsonl("bad.jsonl")


def test_load_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert preflight.load_json("missing.json") == {}
    (tmp_path / "m.json").write_text('{"k": 1}', encoding="utf-8")
    assert preflight.load_json("m.json") == {"k": 1}


def test_check_run_path(tmp_path):
    assert preflight.check_run_path(None) is False
    assert preflight.check_run_path("") is False
    incomplete = tmp_path / "run_incomplete"
    incomplete.mkdir()
    (incomplete / "summary.md").write_text("s", encoding="utf-8")
    assert preflight.check_run_path(str(incomplete)) is False  # 缺 details.jsonl
    complete = make_run_dir(tmp_path, "run_ok")
    assert preflight.check_run_path(str(complete)) is True


# ---------- main() ----------

def test_main_all_pass_text_output(tmp_path, monkeypatch, capsys):
    build_healthy_env(tmp_path, monkeypatch)
    rc = preflight.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PASS" in out
    assert "[OK]" in out
    assert "FAIL" not in out.replace("PASS", "")  # 不應有 FAIL 標記


def test_main_all_pass_json_output(tmp_path, monkeypatch, capsys):
    build_healthy_env(tmp_path, monkeypatch)
    rc = preflight.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["passed"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []
    names = {c["name"] for c in payload["checks"]}
    assert "MINIMAX_API_KEY" in names
    assert "runs/latest" in names


def test_main_offline_passes_without_provider_key(tmp_path, monkeypatch, capsys):
    build_healthy_env(tmp_path, monkeypatch)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    rc = preflight.main(["--json", "--offline"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["offline"] is True
    assert payload["passed"] is True
    key_check = next(c for c in payload["checks"] if c["name"] == "MINIMAX_API_KEY")
    assert key_check["passed"] is True
    assert "略過" in key_check["detail"]


def test_main_empty_dir_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    rc = preflight.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["passed"] is False
    failing = {c["name"] for c in payload["errors"]}
    assert "MINIMAX_API_KEY" in failing
    assert "questions/dev.jsonl" in failing
    assert "prompts/baseline.md" in failing
    assert "baseline.meta hash" in failing
    assert "baseline dev run" in failing
    assert "runs/latest" in failing


def test_main_fail_text_output_marks(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    rc = preflight.main([])
    out = capsys.readouterr().out
    assert rc == 1
    assert "[FAIL]" in out
    assert "[WARN]" in out  # smoke/holdout run 為 warn severity
    assert "FAIL" in out.splitlines()[-1]  # 結果列


def test_main_invalid_jsonl_reports_parse_error(tmp_path, monkeypatch, capsys):
    build_healthy_env(tmp_path, monkeypatch)
    (tmp_path / "questions" / "smoke.jsonl").write_text("not-json\n", encoding="utf-8")
    rc = preflight.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    smoke = next(c for c in payload["checks"] if c["name"] == "questions/smoke.jsonl")
    assert smoke["passed"] is False
    assert "題庫解析失敗" in smoke["detail"]


def test_main_missing_smoke_run_is_warning_only(tmp_path, monkeypatch, capsys):
    meta = build_healthy_env(tmp_path, monkeypatch)
    # 刪掉 smoke run 的 summary.md → warn，不影響整體 PASS
    (Path(meta["smoke_run"]) / "summary.md").unlink()
    rc = preflight.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["passed"] is True
    assert [w["name"] for w in payload["warnings"]] == ["baseline smoke run"]


def test_main_bad_parallel_settings_fail(tmp_path, monkeypatch, capsys):
    build_healthy_env(tmp_path, monkeypatch)
    rc = preflight.main(["--smoke-parallel", "0"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "parallel settings" in out


def test_main_parallel_defaults_from_env(tmp_path, monkeypatch, capsys):
    build_healthy_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "3")
    monkeypatch.setenv("AUTORESEARCH_DEV_PARALLEL", "12")
    monkeypatch.setenv("AUTORESEARCH_HOLDOUT_PARALLEL", "8")
    rc = preflight.main(["--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    parallel = next(c for c in payload["checks"] if c["name"] == "parallel settings")
    assert parallel["detail"] == "smoke=3, dev=12, holdout=8"


def test_main_parallel_env_non_integer_fails(tmp_path, monkeypatch, capsys):
    """覆蓋 preflight.py 12->14 / 14->17：環境變數非整數字串導致 int() 失敗。
    任務要求：明確斷言錯誤被驗證機制攔下。"""
    build_healthy_env(tmp_path, monkeypatch)
    monkeypatch.setenv("AUTORESEARCH_SMOKE_PARALLEL", "abc")  # 非數字
    with pytest.raises(ValueError, match="invalid literal for int"):
        preflight.main(["--json"])


# ---------- __main__ ----------

def test_script_main_guard(monkeypatch, tmp_path):
    # runpy 重跑頂層會 chdir 回專案根，對真實 repo 只做唯讀檢查，無網路呼叫。
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["preflight.py", "--json"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
    assert exc.value.code in (0, 1)
