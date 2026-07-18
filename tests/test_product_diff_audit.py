import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath
import pytest


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
        encoding="utf-8",
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
    parts = rel_path.replace("\\", "/").split("/")
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


def test_diff_paths_handles_platform_paths_unicode_and_line_endings(monkeypatch):
    posix_path = str(PurePosixPath("lib") / "資料.py")
    windows_path = str(PureWindowsPath("lib", "資料.py"))
    text_path = str(PurePosixPath("tests") / "讀取.txt")
    stdout = f" M {posix_path}\r\n M {windows_path}\n?? {text_path}\r\n"
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _diff_paths() == [posix_path, windows_path, text_path]
    assert _is_protected_product_file(posix_path)
    assert _is_protected_product_file(windows_path)
    assert not _is_protected_product_file(text_path)
    assert calls == [
        (
            ["git", "status", "--porcelain", "-uno"],
            {
                "cwd": PROJECT_ROOT,
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "check": False,
            },
        )
    ]


def test_simulate_linux_macos_git_failure_and_success():
    """精簡 pytest 子集：模擬 Linux/macOS 環境下 git 失敗/成功輸出，
    確認 RuntimeError 與成功路徑可穩定重現並修正。
    這是任務要求的最小新增，僅新增此測試，不影響其他行為。
    """
    import subprocess
    from unittest.mock import patch

    # 模擬 Linux/macOS 失敗輸出 (非0 退出碼)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "status", "--porcelain", "-uno"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )
        with pytest.raises(RuntimeError, match="無法讀取 git 狀態"):
            _diff_paths()

    # 模擬 Linux/macOS 成功輸出 (含 POSIX 路徑)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["git", "status", "--porcelain", "-uno"],
            returncode=0,
            stdout=" M lib/資料.py\n?? tests/讀取.txt\n",
            stderr="",
        )
        assert _diff_paths() == ["lib/資料.py", "tests/讀取.txt"]
