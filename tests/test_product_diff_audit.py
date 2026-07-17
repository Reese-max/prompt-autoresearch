import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


CORE_PATH_PREFIXES = ("api", "lib")
FORBIDDEN_SUFFIX = ".py"
FORCED_CORE_FILES = {"app.js", "index.html"}
ALLOWED_PREFIXES = ("tests/", "htmlcov/", "output/", ".github/", "lib/config.py")


def _diff_paths() -> list[str]:
    """Return changed file paths (working tree and index) compared to HEAD."""

    proc = subprocess.run(
        ["git", "status", "--porcelain", "-uno"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"無法讀取 git 狀態：{proc.returncode} {proc.stderr.strip()}")

    paths: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            # rename/copy: 目標檔名才是實際影響
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def _is_protected_product_file(rel_path: str) -> bool:
    if rel_path in FORCED_CORE_FILES:
        return True
    if rel_path in {"", None}:
        return False
    parts = rel_path.split("/")
    if len(parts) >= 2 and parts[0] in CORE_PATH_PREFIXES and rel_path.endswith(FORBIDDEN_SUFFIX):
        return True
    return False


def test_product_code_should_not_be_edited_for_coverage_tuning():
    changed = _diff_paths()

    unexpected = [
        path
        for path in changed
        if not path.startswith(ALLOWED_PREFIXES)
        and _is_protected_product_file(path)
    ]

    assert not unexpected, (
        "發現受保護產品檔案有未授權修改，可能為湊覆蓋率/刪簡化邏輯："
        f"{', '.join(unexpected)}"
    )
