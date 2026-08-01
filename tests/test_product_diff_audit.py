import os
import re
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


CORE_PATH_PREFIXES = ("api", "lib")
FORBIDDEN_SUFFIX = ".py"
FORCED_CORE_FILES = {"app.js", "index.html"}
ALLOWED_PREFIXES = ("tests/", "htmlcov/", "output/", ".github/", "lib/config.py", "lib/metrics.py")


def _windows_drive_path_to_posix(path: str) -> str | None:
    """將 Windows 絕對路徑（D:/...）轉成 WSL/Linux 可讀的 /mnt/<drive>/...。"""
    normalized = path.replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/(.*)$", normalized)
    if not match:
        return None
    drive, rest = match.group(1).lower(), match.group(2)
    return f"/mnt/{drive}/{rest}"


def _git_env_overrides() -> dict[str, str]:
    """
    非 Windows 上若 .git 為 gitdir 指標且指向 Windows 磁碟路徑
    （常見於 Windows worktree 在 WSL/Linux 下驗證），
    則以 GIT_DIR / GIT_WORK_TREE 覆寫，避免 git 把 D:/... 當相對路徑。
    """
    if os.name == "nt":
        return {}

    git_pointer = PROJECT_ROOT / ".git"
    if not git_pointer.is_file():
        return {}

    try:
        text = git_pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return {}

    if not text.lower().startswith("gitdir:"):
        return {}

    gitdir = text.split(":", 1)[1].strip()
    translated = _windows_drive_path_to_posix(gitdir)
    if not translated or not Path(translated).exists():
        return {}

    return {
        "GIT_DIR": translated,
        "GIT_WORK_TREE": str(PROJECT_ROOT),
    }


def _git_status_kwargs() -> dict:
    """組裝 git status 子程序啟動參數（含平台路徑／編碼）。"""
    kwargs: dict = {
        "cwd": PROJECT_ROOT,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
    }
    overrides = _git_env_overrides()
    if overrides:
        env = os.environ.copy()
        env.update(overrides)
        kwargs["env"] = env
    return kwargs


def _git_status_command() -> list[str]:
    """
    git status 命令列。
    固定 core.filemode=false、core.autocrlf=true，避免 Windows worktree
    在 Linux/WSL 下因執行位元／CRLF 被誤判為大量產品檔修改。
    """
    return [
        "git",
        "-c",
        "core.filemode=false",
        "-c",
        "core.autocrlf=true",
        "status",
        "--porcelain",
        "-uno",
    ]


def _diff_paths() -> list[str]:
    """Return changed file paths (working tree and index) compared to HEAD."""

    proc = subprocess.run(
        _git_status_command(),
        **_git_status_kwargs(),
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
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == _git_status_command()
    assert kwargs["cwd"] == PROJECT_ROOT
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert kwargs["check"] is False


def test_windows_drive_path_to_posix_translation():
    """平台路徑轉譯：Windows 磁碟路徑 → WSL /mnt 形式；非磁碟路徑維持 None。"""
    assert _windows_drive_path_to_posix(r"D:\Users\work\.git") == "/mnt/d/Users/work/.git"
    assert _windows_drive_path_to_posix("D:/Users/work/.git") == "/mnt/d/Users/work/.git"
    assert _windows_drive_path_to_posix("/home/user/.git") is None
    assert _windows_drive_path_to_posix("relative/path") is None


def test_git_status_kwargs_sets_env_for_windows_gitdir(monkeypatch, tmp_path):
    """非 Windows 且 .git 指向 Windows gitdir 時，應注入 GIT_DIR / GIT_WORK_TREE。"""
    if os.name == "nt":
        pytest.skip("此案例驗證非 Windows 程序啟動行為")

    import sys

    gitdir_host = tmp_path / "gitdir-host"
    gitdir_host.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: D:/fake/worktree/gitdir\n", encoding="utf-8")

    monkeypatch.setattr(sys.modules[__name__], "PROJECT_ROOT", repo)
    monkeypatch.setattr(
        sys.modules[__name__],
        "_windows_drive_path_to_posix",
        lambda _path: str(gitdir_host),
    )

    overrides = _git_env_overrides()
    assert overrides["GIT_DIR"] == str(gitdir_host)
    assert overrides["GIT_WORK_TREE"] == str(repo)

    kwargs = _git_status_kwargs()
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    assert kwargs["env"]["GIT_DIR"] == str(gitdir_host)
    assert kwargs["env"]["GIT_WORK_TREE"] == str(repo)


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
            args=_git_status_command(),
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository",
        )
        with pytest.raises(RuntimeError, match="無法讀取 git 狀態"):
            _diff_paths()

    # 模擬 Linux/macOS 成功輸出 (含 POSIX 路徑)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=_git_status_command(),
            returncode=0,
            stdout=" M lib/資料.py\n?? tests/讀取.txt\n",
            stderr="",
        )
        assert _diff_paths() == ["lib/資料.py", "tests/讀取.txt"]
