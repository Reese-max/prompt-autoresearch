# -*- coding: utf-8 -*-
"""
101e43a17c523c52-prompt-shell-injection.py — 候選提示詞 shell 注入防護受控評測。

候選提示詞內含命令替換（`$(...)`、反引號）、管線、重導向、分號與換行命令等 payload，
以「受控評測流程」跑完整候選流動路徑（write_file → run_evaluation → call_minimax），
斷言：
1. sentinel 檔案／命令副作用均未發生（payload 從未被 shell 解譯執行）。
2. 模型／假評測器收到的提示詞位元內容與原始 payload 完全一致（逐位元相等）。
3. subprocess 邊界只傳檔案路徑，payload 字串不進 argv。

可直接執行：
    python tests/101e43a17c523c52-prompt-shell-injection.py

或以 pytest 執行：
    python -m pytest -q tests/101e43a17c523c52-prompt-shell-injection.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest

import lib.io as io
import run_opt
import scripts.evaluate as evaluate

SENTINEL = "prompt-shell-injection-sentinel.txt"

JUDGE_JSON = {
    "general_score": 55,
    "general_reason": "ok",
    "type_specific_score": 15,
    "type_specific_reason": "ok",
    "risk_score": 9,
    "risk_reason": "ok",
    "total_score": 999,
    "failures": ["F03"],
    "critique": "加強採分點",
}

# 每筆 payload 皆無前後空白，確保 load_file 的 .strip() 為 no-op，
# 位元比對（payload == 收到內容）保持精確成立。
PAYLOADS = [
    ("dollar_paren", f"$(touch {SENTINEL})"),
    ("backtick", f"`touch {SENTINEL}`"),
    ("pipe", f"touch {SENTINEL} | cat"),
    ("redirect", f"echo pwned > {SENTINEL}"),
    ("semicolon", f"touch {SENTINEL}; ls -la"),
    ("newline", f"第一行指令\ntouch {SENTINEL}\n第二行"),
    ("combined", f"$(touch {SENTINEL}) ; echo pwned > {SENTINEL} | cat\n`touch {SENTINEL}`"),
]

PAYLOAD_IDS = [name for name, _ in PAYLOADS]


def _find_sentinel(root):
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn == SENTINEL:
                return os.path.join(dirpath, fn)
    return None


def _fake_minimax(captured):
    judge_out = "```json\n" + json.dumps(JUDGE_JSON, ensure_ascii=False) + "\n```"

    def fake(system, user, temperature=0.7):
        captured.append(system)
        return ["模擬答案", judge_out][len(captured) - 1]

    return fake


def _write_question_file(root, q_id=1):
    qpath = root / "questions" / "q.jsonl"
    qpath.parent.mkdir(parents=True, exist_ok=True)
    qpath.write_text(
        json.dumps(
            {"id": q_id, "type": "案例題", "question": "何謂行政處分？", "key_points": ["定義"]},
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    return "questions/q.jsonl"


# ---------------------------------------------------------------------------
# 1. 檔案邊界：候選提示詞寫入→讀取，位元內容原樣
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,payload", PAYLOADS, ids=PAYLOAD_IDS)
def test_prompt_bytes_preserved_across_file_boundary(name, payload, tmp_path, monkeypatch):
    """候選提示詞經 write_file→load_file 往返後位元內容保持原樣。"""
    monkeypatch.chdir(tmp_path)
    prompt_path = "prompts/current.md"
    io.write_file(prompt_path, payload)
    assert io.load_file(prompt_path) == payload, "寫入與讀回必須逐位元一致"
    with open(prompt_path, encoding="utf-8") as f:
        assert f.read().strip() == payload, "檔案內容必須與原始 payload 一致"
    assert _find_sentinel(tmp_path) is None, "純檔案往返不應產生任何副作用"


# ---------------------------------------------------------------------------
# 2. 受控評測流程：write_file → run_evaluation → 假評測器（call_minimax）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,payload", PAYLOADS, ids=PAYLOAD_IDS)
def test_controlled_eval_no_side_effect_and_prompt_bits_preserved(
    name, payload, tmp_path, monkeypatch
):
    """候選提示詞含注入 payload 走受控評測流程：
    sentinel 副作用均未發生，且假評測器收到的提示詞位元內容原樣。"""
    monkeypatch.chdir(tmp_path)
    prompt_path = "prompts/current.md"
    question_file = _write_question_file(tmp_path)
    io.write_file(prompt_path, payload)

    captured = []
    monkeypatch.setattr(evaluate, "call_minimax", _fake_minimax(captured))

    summary, results = evaluate.run_evaluation(prompt_path, question_file, max_workers=1)

    # 評測流程正常完成，payload 未造成執行中斷或錯誤產出
    assert summary["total_questions"] == 1
    assert len(results) == 1 and "error" not in results[0], "payload 不得使評測流程崩潰"

    # 假評測器至少收到一次提示詞，且收到的 system 位元內容與原始 payload 完全一致
    assert captured, "假評測器應收到候選提示詞"
    assert captured[0] == payload, "模型／假評測器收到的提示詞必須與原始 payload 逐位元一致"

    # sentinel 檔案／命令副作用均未發生
    assert _find_sentinel(tmp_path) is None, "評測流程不得執行任何 shell 命令產生 sentinel"


# ---------------------------------------------------------------------------
# 3. subprocess 邊界：payload 只以受控檔案路徑進入，不進 argv
# ---------------------------------------------------------------------------

def test_run_evaluate_subprocess_argv_never_contains_payload(tmp_path, monkeypatch):
    """run_opt.run_evaluate 的 subprocess 呼叫必須是明確 argv list，
    payload 字串不得以任何形式出現在 argv，只傳受控檔案路徑。"""
    monkeypatch.chdir(tmp_path)
    payload = f"$(touch {SENTINEL}) ; echo pwned > {SENTINEL} | cat\n`touch {SENTINEL}`"
    prompt_path = "prompts/current.md"
    question_file = _write_question_file(tmp_path)
    io.write_file(prompt_path, payload)

    captured_cmds = []

    def fake_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run_opt.subprocess, "run", fake_run)
    monkeypatch.setattr(run_opt, "newest_run_after", lambda before: None)

    res, run_dir, summary = run_opt.run_evaluate(prompt_path, question_file, 1, capture=True)

    assert len(captured_cmds) == 1, "run_evaluate 應恰好觸發一次 subprocess"
    cmd = captured_cmds[0]
    assert isinstance(cmd, list), "subprocess 必須使用明確 argv list，不得為 shell 字串"
    assert not any(payload in str(part) for part in cmd), "payload 不得出現在任何 argv 元素"
    assert any(part == prompt_path for part in cmd), "應以受控檔案路徑傳遞候選提示詞"
    assert _find_sentinel(tmp_path) is None, "argv 邊界不應產生任何命令副作用"


# ---------------------------------------------------------------------------
# 4. 反證控制：同一 payload 若真的被 shell 解譯，sentinel 會被建立
# ---------------------------------------------------------------------------

def test_negative_control_payload_would_execute_in_shell(tmp_path):
    """證明上述「無副作用」斷言具判別力：
    同樣的 payload 若被真實 shell 解譯執行，sentinel 檔案確實會被建立。"""
    payload = f"echo pwned > {SENTINEL}"
    try:
        subprocess.run(
            payload,
            shell=True,
            cwd=str(tmp_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        pytest.skip(f"本環境無法以 shell 執行反證控制: {e}")
    assert os.path.exists(tmp_path / SENTINEL), (
        "反證控制失敗：同一 payload 在真實 shell 中未產生 sentinel，"
        "表示 payload 可能不具可執行性，主斷言將失去判別力"
    )


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
