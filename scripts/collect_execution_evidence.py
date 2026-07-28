#!/usr/bin/env python3
"""scripts/collect_execution_evidence.py - 執行兩次測試並收集完整可核驗佐證

保存完整命令、依賴鎖定檔、環境資訊、輸入雜湊、輸出檔案及差異報告。
"""

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "docs" / "evidence"


def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_env():
    import platform
    info = {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "arch": platform.machine(),
        "hashseed": os.environ.get("PYTHONHASHSEED", "not set"),
        "time": datetime.datetime.now().isoformat(),
    }
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
        info["commit"] = r.stdout.strip()
    except Exception:
        info["commit"] = "unknown"
    return info


def collect_dep_hashes():
    h = {}
    lf = REPO_ROOT / "requirements.lock"
    if lf.exists():
        h["requirements.lock"] = sha256_file(lf)
    return h


def collect_src_hashes():
    h = {}
    for d in ["lib", "api", "scripts"]:
        p = REPO_ROOT / d
        if p.is_dir():
            for f in sorted(p.glob("**/*.py")):
                rel = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
                h[rel] = sha256_file(f)
    return h


def run_once(label):
    tmpdir = tempfile.mkdtemp(prefix=f"{label}_")
    run_dir = Path(tmpdir) / label
    run_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=lib", "--cov=api", "--cov=scripts",
        "--cov-report=xml", "--cov-report=html",
        "--cov-fail-under=0",
    ]

    env = os.environ.copy()
    env["COVERAGE_FILE"] = str(run_dir / ".coverage")
    env["PYTHONHASHSEED"] = "0"

    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600)

    # Move coverage artifacts
    for fname in ["coverage.xml"]:
        src = REPO_ROOT / fname
        if src.exists():
            shutil.move(str(src), str(run_dir / fname))

    htmlcov = REPO_ROOT / "htmlcov"
    if htmlcov.is_dir():
        dst = run_dir / "htmlcov"
        if dst.exists():
            shutil.rmtree(str(dst))
        shutil.copytree(str(htmlcov), str(dst))

    # Save outputs
    (run_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    (run_dir / "command.txt").write_text(
        f"Command: {' '.join(cmd)}\nCWD: {REPO_ROOT}\nExit: {result.returncode}\nHASHSEED: {env.get('PYTHONHASHSEED')}\n",
        encoding="utf-8",
    )

    # Parse summary
    summary_line = ""
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped and ("passed" in stripped or "failed" in stripped or "error" in stripped) and "short" not in stripped.lower() and "TOTAL" not in stripped:
            summary_line = stripped
        if stripped.startswith("TOTAL"):
            summary_line = stripped

    info = {
        "cmd": cmd,
        "exit_code": result.returncode,
        "run_dir": str(run_dir),
        "stdout_summary": summary_line,
        "stdout_full": result.stdout,
        "stderr_full": result.stderr,
        "coverage_xml": (run_dir / "coverage.xml").exists(),
    }
    return info, run_dir


def compare(r1_dir, r2_dir):
    cmp_script = REPO_ROOT / "scripts" / "compare_test_runs.py"
    r = subprocess.run(
        [sys.executable, str(cmp_script), str(r1_dir), str(r2_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    report = None
    if r.stdout.strip():
        try:
            report = json.loads(r.stdout)
        except json.JSONDecodeError:
            report = {"raw": r.stdout}
    return {"exit_code": r.returncode, "report": report, "stdout": r.stdout, "stderr": r.stderr}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    print("[1/5] 環境資訊...")
    env = collect_env()
    dep_h = collect_dep_hashes()
    src_h = collect_src_hashes()

    print("[2/5] 第一次執行...")
    r1, d1 = run_once("run1")
    print(f"  exit={r1['exit_code']}  {r1['stdout_summary']}")

    print("[3/5] 第二次執行...")
    r2, d2 = run_once("run2")
    print(f"  exit={r2['exit_code']}  {r2['stdout_summary']}")

    print("[4/5] 比較兩次執行...")
    cmp = compare(d1, d2)
    print(f"  compare exit={cmp['exit_code']}")

    # Copy requirements.lock snapshot
    lock_src = REPO_ROOT / "requirements.lock"
    if lock_src.exists():
        shutil.copy2(str(lock_src), str(OUTPUT_DIR / f"requirements.lock.{ts}"))

    # Save full stdout/stderr to evidence dir
    (OUTPUT_DIR / f"run1-stdout.{ts}.txt").write_text(r1["stdout_full"], encoding="utf-8")
    (OUTPUT_DIR / f"run1-stderr.{ts}.txt").write_text(r1["stderr_full"], encoding="utf-8")
    (OUTPUT_DIR / f"run2-stdout.{ts}.txt").write_text(r2["stdout_full"], encoding="utf-8")
    (OUTPUT_DIR / f"run2-stderr.{ts}.txt").write_text(r2["stderr_full"], encoding="utf-8")
    (OUTPUT_DIR / f"compare-output.{ts}.txt").write_text(cmp["stdout"], encoding="utf-8")

    reproducible = r1["exit_code"] == r2["exit_code"] == 0 and cmp["exit_code"] == 0

    report = {
        "task": "保存兩次執行完整命令、依賴鎖定檔、環境資訊、輸入雜湊、輸出檔案及差異報告",
        "timestamp": ts,
        "reproducibility": "REPRODUCIBLE" if reproducible else "NOT-REPRODUCIBLE",
        "environment": env,
        "dependency_hashes": dep_h,
        "source_hash_count": len(src_h),
        "source_hashes_sample": dict(list(sorted(src_h.items()))[:10]),
        "run1": {"exit_code": r1["exit_code"], "summary": r1["stdout_summary"], "cmd": r1["cmd"]},
        "run2": {"exit_code": r2["exit_code"], "summary": r2["stdout_summary"], "cmd": r2["cmd"]},
        "comparison": {"exit_code": cmp["exit_code"], "report": cmp["report"]},
    }

    # Write JSON
    json_path = OUTPUT_DIR / f"execution-evidence-{ts}.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Write Markdown
    md = []
    md.append(f"# 執行佐證報告 ({ts})")
    md.append("")
    md.append(f"**可重複性判定: {report['reproducibility']}**")
    md.append("")
    md.append("## 環境")
    for k in ["python", "platform", "arch", "hashseed", "commit", "time"]:
        md.append(f"- {k}: `{env[k]}`")
    md.append("")
    md.append("## 依賴鎖定檔")
    for k, v in dep_h.items():
        md.append(f"- `{k}`: `{v}`")
    md.append("")
    md.append("## 第一次執行")
    md.append(f"- 命令: `{' '.join(r1['cmd'])}`")
    md.append(f"- Exit: {r1['exit_code']}")
    md.append(f"- 摘要: {r1['stdout_summary']}")
    md.append("")
    md.append("## 第二次執行")
    md.append(f"- 命令: `{' '.join(r2['cmd'])}`")
    md.append(f"- Exit: {r2['exit_code']}")
    md.append(f"- 摘要: {r2['stdout_summary']}")
    md.append("")
    md.append("## 比較結果")
    md.append(f"- Compare exit: {cmp['exit_code']}")
    if cmp["report"]:
        md.append(f"- Has differences: {cmp['report'].get('has_differences', 'unknown')}")
    md.append("")
    md.append("## 原始碼雜湊 (前 10)")
    for i, (k, v) in enumerate(sorted(src_h.items())):
        if i >= 10:
            md.append(f"- ... (共 {len(src_h)} 項)")
            break
        md.append(f"- `{k}`: `{v[:16]}...`")

    md_path = OUTPUT_DIR / f"execution-evidence-{ts}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(f"\n[5/5] 報告完成")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print(f"  判定: {report['reproducibility']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
