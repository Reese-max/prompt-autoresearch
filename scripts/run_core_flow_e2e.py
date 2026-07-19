# -*- coding: utf-8 -*-
"""在單一平台執行核心流程端到端測試，輸出可比對的正規化結果。

固定輸入（與 tests/test_cross_platform.py::TestCoreEvaluationFlow 對齊）：
  - Unicode prompt（含 CRLF）
  - 單題 JSONL 題庫（含 CRLF）
  - mock LLM 回傳固定答案與評分 JSON

可比對欄位（platform-neutral）：
  - gatekeeper.passed / violations / char_count
  - evaluation.summary 關鍵欄位與 results 契約
  - 產物 SHA-256（details.jsonl / summary.json / summary.md / results.tsv 正規化）
  - prompt_hash 與 expected_digest

用法：
  python scripts/run_core_flow_e2e.py
  python scripts/run_core_flow_e2e.py --out docs/evidence/core-flow-e2e-Windows-3.11.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# evaluate.py 會在 import 時 chdir 到專案根；runner 稍後會切到 tmp workspace
import scripts.evaluate as evaluate  # noqa: E402
from lib import io  # noqa: E402
from scripts.gatekeeper import run_gatekeeper  # noqa: E402

UNICODE_PROMPT = (
    "你是閱卷委員兼考官，具備法學判斷能力。"
    "答案需以法理與法律案例題清楚區分，先建立比較基準：法條適用、事實比對與要件對照。"
    "處理法律題時，使用三段論（大前提與小前提）完成推理。"
    "不得反問、不得編造，並要直接輸出正文，不要輸出冗長前言與分析過程。"
    "此題以簡明語句回應。"
)

QUESTION = {
    "id": 1,
    "type": "案例題",
    "question": "請說明行政處分之要件。",
    "key_points": ["定義", "要件"],
}

ANSWER = "第一行中文\n第二行 mixed English\n" * 40
JUDGE_OUTPUT = json.dumps(
    {
        "general_score": 55,
        "type_specific_score": 15,
        "risk_score": 9,
        "failures": ["F03"],
        "critique": "請加強採分點。",
    },
    ensure_ascii=False,
)

# 規格期望（與 TestCoreEvaluationFlow 一致；跨平台應完全相同）
EXPECTED = {
    "prompt_hash": io.sha256_text(UNICODE_PROMPT),
    "total_questions": 1,
    "average_score": 79.0,
    "word_count_pass_rate": 100.0,
    "risk_perfect_rate": 0.0,
    "error_count": 0,
    "total_score": 79,
    "failures": ["F03"],
    "char_count": len(ANSWER),
    "gatekeeper_passed": True,
    "gatekeeper_char_count": len(UNICODE_PROMPT),
}


def _platform_label() -> str:
    system = platform.system()
    if system == "Darwin":
        return "macOS"
    return system


def _runtime_fingerprint() -> dict[str, Any]:
    return {
        "platform": _platform_label(),
        "system": platform.system(),
        "release": platform.release(),
        "python_version": platform.python_version(),
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "sys_platform": sys.platform,
        "executable": sys.executable,
        "hostname": socket.gethostname(),
        "cwd": str(Path.cwd()),
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strip_volatile(summary: dict[str, Any], results: list[dict[str, Any]]) -> tuple[dict, list]:
    """移除時間戳等不可跨跑比對的欄位，保留契約欄位。"""
    summary_keys = (
        "prompt_file",
        "question_file",
        "prompt_hash",
        "total_questions",
        "average_score",
        "word_count_pass_rate",
        "risk_perfect_rate",
        "error_count",
    )
    result_keys = (
        "id",
        "type",
        "question",
        "answer",
        "char_count",
        "prompt_hash",
        "question_file",
        "general_score",
        "type_specific_score",
        "risk_score",
        "total_score",
        "failures",
        "critique",
    )
    clean_summary = {k: summary[k] for k in summary_keys if k in summary}
    clean_results = []
    for row in results:
        clean = {k: row[k] for k in result_keys if k in row}
        # 路徑只保留可移植相對段，避免 tmp 絕對路徑破壞比對
        if "question_file" in clean:
            clean["question_file"] = _portable_path(clean["question_file"])
        clean_results.append(clean)
    if "prompt_file" in clean_summary:
        clean_summary["prompt_file"] = _portable_path(clean_summary["prompt_file"])
    if "question_file" in clean_summary:
        clean_summary["question_file"] = _portable_path(clean_summary["question_file"])
    return clean_summary, clean_results


def _portable_path(path_str: str) -> str:
    """將絕對/平台路徑收斂為以『輸入 資料/…』結尾的可移植鍵。"""
    normalized = io.normalize_path(path_str)
    marker = "輸入 資料/"
    idx = normalized.find(marker)
    if idx >= 0:
        return normalized[idx:]
    return Path(normalized).name


def _run_core_evaluation(workspace: Path) -> dict[str, Any]:
    prompt_path = workspace / "輸入 資料" / "提示詞.md"
    question_path = workspace / "輸入 資料" / "題庫.jsonl"
    io.ensure_dir(str(prompt_path.parent))
    prompt_path.write_bytes((UNICODE_PROMPT + "\r\n").encode("utf-8"))
    question_path.write_bytes(
        (json.dumps(QUESTION, ensure_ascii=False) + "\r\n").encode("utf-8")
    )
    for rubric_name in (
        "general.md",
        "type_specific.md",
        "risk_rules.md",
        "failure_taxonomy.md",
    ):
        io.write_file(f"rubrics/{rubric_name}", "固定 UTF-8 評分規準")

    def fake_minimax(_system, _user, temperature=0.7):
        if temperature == 0.3:
            return ANSWER
        if temperature == 0.1:
            return JUDGE_OUTPUT
        raise AssertionError(f"unexpected temperature={temperature}")

    original = evaluate.call_minimax
    evaluate.call_minimax = fake_minimax
    try:
        prompt_arg = io.normalize_path(str(prompt_path))
        question_arg = io.normalize_path(str(question_path))
        summary, results = evaluate.run_evaluation(
            prompt_arg, question_arg, max_workers=1
        )
        # 清 cache 後再跑一次，驗證冪等
        cache_dir = workspace / ".cache"
        if cache_dir.exists():
            import shutil

            shutil.rmtree(cache_dir)
        summary2, results2 = evaluate.run_evaluation(
            prompt_arg, question_arg, max_workers=1
        )
        run_dir = Path(evaluate.save_run_results(summary, results))
    finally:
        evaluate.call_minimax = original

    artifacts = {}
    for name in ("details.jsonl", "summary.json", "summary.md"):
        raw = (run_dir / name).read_bytes()
        artifacts[name] = {
            "exists": True,
            "has_bom": raw.startswith(b"\xef\xbb\xbf"),
            "sha256": _sha256_bytes(raw),
            "utf8_ok": True,
        }
        raw.decode("utf-8")

    tsv_raw = Path("results.tsv").read_bytes()
    # TSV 第一欄常為 run id（時間戳），正規化為只比對分數欄位列
    tsv_text = tsv_raw.decode("utf-8")
    tsv_score_marker = "\t79.00\t" in tsv_text
    artifacts["results.tsv"] = {
        "exists": True,
        "has_bom": tsv_raw.startswith(b"\xef\xbb\xbf"),
        "contains_score_79": tsv_score_marker,
        "sha256_full": _sha256_bytes(tsv_raw),
    }

    clean_summary, clean_results = _strip_volatile(summary, results)
    clean_summary2, clean_results2 = _strip_volatile(summary2, results2)

    return {
        "summary": clean_summary,
        "results": clean_results,
        "repeat_identical": (
            clean_summary == clean_summary2 and clean_results == clean_results2
        ),
        "artifacts": artifacts,
        "latest_symlink_ok": all(
            (Path("runs/latest") / n).exists()
            for n in ("details.jsonl", "summary.json", "summary.md")
        ),
        "canonical_digest": _sha256_text(
            _canonical_json({"summary": clean_summary, "results": clean_results})
        ),
    }


def _run_gatekeeper_probe() -> dict[str, Any]:
    passed, violations = run_gatekeeper(UNICODE_PROMPT)
    short_passed, short_violations = run_gatekeeper("短")
    return {
        "valid_prompt": {
            "passed": passed,
            "char_count": len(UNICODE_PROMPT),
            "violation_rules": sorted(v["rule"] for v in violations),
            "reject_count": sum(1 for v in violations if v.get("severity") == "reject"),
        },
        "short_prompt": {
            "passed": short_passed,
            "char_count": 1,
            "violation_rules": sorted(v["rule"] for v in short_violations),
            "reject_count": sum(
                1 for v in short_violations if v.get("severity") == "reject"
            ),
        },
    }


def _check_spec(eval_result: dict[str, Any], gate: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    s = eval_result["summary"]
    r0 = eval_result["results"][0] if eval_result["results"] else {}

    checks = [
        (s.get("prompt_hash") == EXPECTED["prompt_hash"], "prompt_hash"),
        (s.get("total_questions") == EXPECTED["total_questions"], "total_questions"),
        (s.get("average_score") == EXPECTED["average_score"], "average_score"),
        (
            s.get("word_count_pass_rate") == EXPECTED["word_count_pass_rate"],
            "word_count_pass_rate",
        ),
        (s.get("risk_perfect_rate") == EXPECTED["risk_perfect_rate"], "risk_perfect_rate"),
        (s.get("error_count") == EXPECTED["error_count"], "error_count"),
        (r0.get("total_score") == EXPECTED["total_score"], "total_score"),
        (r0.get("failures") == EXPECTED["failures"], "failures"),
        (r0.get("char_count") == EXPECTED["char_count"], "char_count"),
        (r0.get("answer") == ANSWER, "answer"),
        (eval_result.get("repeat_identical") is True, "repeat_identical"),
        (eval_result.get("latest_symlink_ok") is True, "latest_symlink_ok"),
        (
            all(not a.get("has_bom") for a in eval_result["artifacts"].values() if "has_bom" in a),
            "no_bom",
        ),
        (
            eval_result["artifacts"]["results.tsv"].get("contains_score_79") is True,
            "tsv_score",
        ),
        (
            gate["valid_prompt"]["passed"] is EXPECTED["gatekeeper_passed"],
            "gatekeeper_passed",
        ),
        (
            gate["valid_prompt"]["char_count"] == EXPECTED["gatekeeper_char_count"],
            "gatekeeper_char_count",
        ),
        (gate["short_prompt"]["passed"] is False, "gatekeeper_reject_short"),
        (gate["short_prompt"]["reject_count"] >= 1, "gatekeeper_reject_count"),
    ]
    for ok, name in checks:
        if not ok:
            failures.append(name)
    return failures


def run_e2e() -> dict[str, Any]:
    runtime = _runtime_fingerprint()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="core-flow-e2e-") as tmp:
        workspace = Path(tmp)
        os.chdir(workspace)
        try:
            eval_result = _run_core_evaluation(workspace)
            gate = _run_gatekeeper_probe()
        finally:
            os.chdir(old_cwd)

    spec_failures = _check_spec(eval_result, gate)
    comparable = {
        "schema_version": 1,
        "flow": "core_evaluation_e2e",
        "expected": EXPECTED,
        "gatekeeper": gate,
        "evaluation": {
            "summary": eval_result["summary"],
            "results": eval_result["results"],
            "repeat_identical": eval_result["repeat_identical"],
            "latest_symlink_ok": eval_result["latest_symlink_ok"],
            "canonical_digest": eval_result["canonical_digest"],
            "artifact_flags": {
                name: {
                    k: v
                    for k, v in meta.items()
                    if k in ("exists", "has_bom", "contains_score_79", "utf8_ok")
                }
                for name, meta in eval_result["artifacts"].items()
            },
        },
    }
    # 完整可比對 digest：不含 runtime 指紋
    comparable_digest = _sha256_text(_canonical_json(comparable))

    return {
        "runtime": runtime,
        "comparable": comparable,
        "comparable_digest": comparable_digest,
        "spec_ok": len(spec_failures) == 0,
        "spec_failures": spec_failures,
        "exit_code": 0 if not spec_failures else 1,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="核心流程端到端測試（可比對輸出）")
    parser.add_argument(
        "--out",
        type=str,
        default="",
        help="將完整結果寫入 JSON 檔（UTF-8）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="只輸出一行 SUMMARY JSON",
    )
    args = parser.parse_args(argv)

    result = run_e2e()
    payload = {
        "runtime": result["runtime"],
        "comparable_digest": result["comparable_digest"],
        "spec_ok": result["spec_ok"],
        "spec_failures": result["spec_failures"],
        "comparable": result["comparable"],
        "exit_code": result["exit_code"],
    }
    out_path = None
    out_parent_created = False

    try:
        if args.out:
            out_path = Path(args.out)
            if not out_path.is_absolute():
                out_path = PROJECT_ROOT / out_path
            if not out_path.parent.exists():
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_parent_created = True
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        summary_line = {
            "platform": result["runtime"]["platform"],
            "python_version": result["runtime"]["python_version"],
            "comparable_digest": result["comparable_digest"],
            "spec_ok": result["spec_ok"],
            "spec_failures": result["spec_failures"],
            "exit_code": result["exit_code"],
            "evaluation_digest": result["comparable"]["evaluation"]["canonical_digest"],
            "average_score": result["comparable"]["evaluation"]["summary"]["average_score"],
            "gatekeeper_passed": result["comparable"]["gatekeeper"]["valid_prompt"]["passed"],
        }
        if args.quiet:
            print(json.dumps(summary_line, ensure_ascii=False), flush=True)
        else:
            print(
                "CORE_FLOW_E2E_SUMMARY " + json.dumps(summary_line, ensure_ascii=False),
                flush=True,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    except Exception:
        if out_path is not None and out_path.exists():
            out_path.unlink()
        if out_path is not None and out_parent_created:
            try:
                out_path.parent.rmdir()
            except OSError:
                pass
        raise

    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
