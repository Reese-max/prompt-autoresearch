#!/usr/bin/env python3
"""scripts/verify_reproducibility.py - 驗證測試執行的可重複性

以相同輸入、設定與隨機種子連續執行測試兩次，逐位元比較所有輸出產物。
若結果不同時以非零退出碼確認「NOT-REPRODUCIBLE」。

用法:
  python3 scripts/verify_reproducibility.py [--pytest-args ARGS ...]

環境變數:
  PYTHONHASHSEED - 設定 Python 雜湊種子以確保可重複性 (預設: 0)
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run_test(run_dir, pytest_args):
    """執行測試並將產物輸出到指定目錄"""
    # 確保輸出目錄存在
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # 建構 pytest 命令
    cmd = [
        sys.executable, "-m", "pytest",
        "--cov=lib", "--cov=api", "--cov=scripts",
        "--cov-report=xml",
        f"--cov-fail-under=0",  # 不因覆蓋率不足而失敗
    ]
    
    # 添加額外的 pytest 參數
    if pytest_args:
        cmd.extend(pytest_args)
    
    # 設定輸出路徑
    env = os.environ.copy()
    env["COVERAGE_FILE"] = str(run_dir / ".coverage")
    env["PYTHONHASHSEED"] = env.get("PYTHONHASHSEED", "0")
    
    # 執行測試
    result = subprocess.run(
        cmd,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True
    )
    
    # 移動 coverage.xml 到輸出目錄
    coverage_src = Path.cwd() / "coverage.xml"
    if coverage_src.exists():
        shutil.move(str(coverage_src), str(run_dir / "coverage.xml"))
    
    # 保存 stdout 和 stderr
    (run_dir / "stdout.txt").write_text(result.stdout, encoding='utf-8')
    (run_dir / "stderr.txt").write_text(result.stderr, encoding='utf-8')
    
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="驗證測試執行的可重複性")
    parser.add_argument(
        "--pytest-args",
        nargs="*",
        default=[],
        help="傳遞給 pytest 的額外參數"
    )
    args = parser.parse_args()
    
    # 建立暫時目錄存放兩次執行的結果
    with tempfile.TemporaryDirectory() as tmpdir:
        run1_dir = Path(tmpdir) / "run1"
        run2_dir = Path(tmpdir) / "run2"
        
        success1 = run_test(run1_dir, args.pytest_args)
        success2 = run_test(run2_dir, args.pytest_args)
        
        # 檢查兩次執行是否都成功
        if not success1 or not success2:
            print("錯誤: 測試執行失敗", file=sys.stderr)
            if not success1:
                print("第一次執行失敗", file=sys.stderr)
                print((run1_dir / "stderr.txt").read_text(encoding='utf-8'), file=sys.stderr)
            if not success2:
                print("第二次執行失敗", file=sys.stderr)
                print((run2_dir / "stderr.txt").read_text(encoding='utf-8'), file=sys.stderr)
            return 1
        
        # 使用 compare_test_runs.py 比較兩次執行
        compare_script = Path(__file__).parent / "compare_test_runs.py"
        if not compare_script.exists():
            print(f"錯誤: 找不到比較腳本 {compare_script}", file=sys.stderr)
            return 1
        
        result = subprocess.run(
            [sys.executable, str(compare_script), str(run1_dir), str(run2_dir)],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        
        if result.returncode != 0:
            print("NOT-REPRODUCIBLE", file=sys.stderr)
            return 1
        
        print("REPRODUCIBLE")
        return 0


if __name__ == "__main__":
    sys.exit(main())
