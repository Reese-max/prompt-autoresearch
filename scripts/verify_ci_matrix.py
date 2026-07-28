# -*- coding: utf-8 -*-
"""驗證 CI workflow 矩陣與正式支援清單是否完全對齊。"""

import sys
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
RUN_TEST_MATRIX_PATH = PROJECT_ROOT / "scripts" / "run_test_matrix.py"


def load_supported_from_script():
    """從 run_test_matrix.py 讀取正式支援清單。"""
    with open(RUN_TEST_MATRIX_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 提取 SUPPORTED_PLATFORMS = ("Linux", "macOS", "Windows")
    # 只匹配變數定義行，不匹配使用它的行
    platforms_match = None
    versions_match = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("SUPPORTED_PLATFORMS ="):
            platforms_match = line
        if line.startswith("SUPPORTED_PYTHON_VERSIONS ="):
            versions_match = line
    
    if not platforms_match or not versions_match:
        print("錯誤：無法從 run_test_matrix.py 提取支援清單", file=sys.stderr)
        sys.exit(1)
    
    # 簡單解析 tuple
    platforms = []
    # 找到括號內容
    start = platforms_match.find("(")
    end = platforms_match.rfind(")")
    if start != -1 and end != -1:
        tuple_content = platforms_match[start+1:end]
        for item in tuple_content.split(","):
            item = item.strip().strip('"').strip("'")
            if item:
                platforms.append(item)
    
    versions = []
    start = versions_match.find("(")
    end = versions_match.rfind(")")
    if start != -1 and end != -1:
        tuple_content = versions_match[start+1:end]
        for item in tuple_content.split(","):
            item = item.strip().strip('"').strip("'")
            if item:
                versions.append(item)
    
    return tuple(platforms), tuple(versions)


def load_workflow_matrix():
    """從 ci.yml 讀取矩陣配置。"""
    try:
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
    except Exception as e:
        print(f"錯誤：無法讀取 workflow 檔案: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        matrix_entries = workflow["jobs"]["test"]["strategy"]["matrix"]["include"]
    except KeyError as e:
        print(f"錯誤：workflow 結構不符預期，缺少鍵值: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 提取 platform 和 python_version
    workflow_combinations = set()
    for entry in matrix_entries:
        platform = entry["platform"]
        python_version = entry["python_version"]
        workflow_combinations.add((platform, python_version))
    
    return workflow_combinations


def main():
    supported_platforms, supported_versions = load_supported_from_script()
    workflow_combinations = load_workflow_matrix()
    
    # 產生所有應有的組合
    expected_combinations = set()
    for platform in supported_platforms:
        for version in supported_versions:
            expected_combinations.add((platform, version))
    
    # 檢查缺漏
    missing = expected_combinations - workflow_combinations
    if missing:
        print("錯誤：CI 矩陣缺少以下組合：", file=sys.stderr)
        for platform, version in sorted(missing):
            print(f"  - {platform} × Python {version}", file=sys.stderr)
        sys.exit(1)
    
    # 檢查多餘
    extra = workflow_combinations - expected_combinations
    if extra:
        print("錯誤：CI 矩陣包含未在正式支援清單中的組合：", file=sys.stderr)
        for platform, version in sorted(extra):
            print(f"  - {platform} × Python {version}", file=sys.stderr)
        sys.exit(1)
    
    # 檢查重複
    if len(workflow_combinations) != len(expected_combinations):
        print("錯誤：CI 矩陣組合數量與預期不符（可能有重複）", file=sys.stderr)
        sys.exit(1)
    
    print("CI 矩陣驗證通過：所有 OS × Python 組合與正式支援清單完全對齊")
    return 0


if __name__ == "__main__":
    sys.exit(main())
