# -*- coding: utf-8 -*-
"""
跨平台錯誤處理測試。

涵蓋四類失敗情境，並斷言各平台上的錯誤型別、訊息／結構化錯誤碼、退出狀態一致：
1. 無效輸入
2. 缺少檔案
3. 權限不足
4. 外部程序／外部依賴失敗

設計原則：
- 不依賴真實網路；外部 API 以 mock 模擬
- 權限案例在 POSIX 用 chmod 0o000；在 Windows 用唯讀屬性模擬寫入拒絕
- 退出碼與結構化 payload 必須在 Windows／Linux／macOS 對齊
"""
from __future__ import annotations

import errno
import json
import os
import platform
import re
import runpy
import stat
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

import pytest

import lib.api as api
import lib.config as config
import lib.io as io

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLATFORM = platform.system()  # Windows / Linux / Darwin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_script_path(script_rel: str, argv: list[str], cwd: Path | None = None):
    """以 in-process 方式執行 scripts/*.py，回傳 (exit_code, stdout, stderr)。"""
    old_argv = list(sys.argv)
    old_cwd = os.getcwd()
    out = StringIO()
    err = StringIO()
    code = 0
    try:
        sys.argv = [script_rel, *argv]
        if cwd is not None:
            os.chdir(cwd)
        with redirect_stdout(out), redirect_stderr(err):
            try:
                runpy.run_path(str(PROJECT_ROOT / script_rel), run_name="__main__")
            except SystemExit as exc:
                raw = exc.code
                if raw is None:
                    code = 0
                elif isinstance(raw, int):
                    code = raw
                else:
                    code = 1
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
    return code, out.getvalue(), err.getvalue()


def _extract_json_object(text: str):
    """從 stdout 擷取最後一個 JSON object（gatekeeper --json / preflight --json）。"""
    match = re.search(r"\{[\s\S]*\}\s*$", text.strip())
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _make_unreadable(path: Path):
    """盡量讓 path 對目前行程不可讀；回傳 restore callable。"""
    if PLATFORM == "Windows":
        # Windows 上 chmod 無法可靠撤銷擁有者讀取權，改以目錄 ACL 模擬不可行；
        # 改測「唯讀檔寫入」——跨平台一致會產生 PermissionError / OSError。
        path.chmod(stat.S_IREAD)

        def restore():
            path.chmod(stat.S_IWRITE | stat.S_IREAD)

        return restore, "write"

    os.chmod(path, 0o000)

    def restore():
        os.chmod(path, 0o644)

    return restore, "read"


# ---------------------------------------------------------------------------
# 1. 無效輸入
# ---------------------------------------------------------------------------
class TestInvalidInputErrors:
    """無效輸入應產生穩定的退出碼／例外型別／結構化錯誤碼。"""

    def test_gatekeeper_short_prompt_exits_one_with_structured_rule(self, tmp_path):
        prompt = tmp_path / "short.md"
        prompt.write_text("太短", encoding="utf-8")

        code, stdout, _ = _run_script_path(
            "scripts/gatekeeper.py",
            [str(prompt), "--json"],
            cwd=tmp_path,
        )

        assert code == 1, f"無效 prompt 退出碼應為 1（{PLATFORM}），實際 {code}"
        payload = _extract_json_object(stdout)
        assert payload is not None, f"應輸出 JSON payload（{PLATFORM}）: {stdout!r}"
        assert payload["passed"] is False
        assert isinstance(payload["violations"], list)
        assert payload["violations"], "至少一條 violation"
        rules = {v["rule"] for v in payload["violations"]}
        assert "R01_LENGTH_TOO_SHORT" in rules
        for v in payload["violations"]:
            assert v["severity"] in ("reject", "warning")
            assert isinstance(v["detail"], str) and v["detail"]

    def test_gatekeeper_no_args_exits_one_with_usage(self, tmp_path):
        code, stdout, _ = _run_script_path("scripts/gatekeeper.py", [], cwd=tmp_path)
        assert code == 1
        assert "用法:" in stdout

    def test_evaluate_usage_error_exits_one(self):
        code, stdout, _ = _run_script_path("scripts/evaluate.py", [])
        assert code == 1
        assert "用法:" in stdout

    def test_test_matrix_invalid_platform_exits_two_with_argparse_message(self, capsys):
        import scripts.run_test_matrix as matrix

        with pytest.raises(SystemExit) as excinfo:
            matrix.main(["--platform", "Plan9", "--python-version", "3.11"])

        assert excinfo.value.code == 2
        assert "invalid choice: 'Plan9'" in capsys.readouterr().err

    def test_invalid_env_config_raises_value_error_not_silent(self, monkeypatch):
        """格式異常環境變數必須被驗證擋下，不可默默接受。"""
        config._CONFIG = None
        monkeypatch.setenv("AUTORESEARCH_API_TIMEOUT", "not-a-number")
        try:
            with pytest.raises(ValueError, match="AUTORESEARCH_API_TIMEOUT") as excinfo:
                config.get_all()
            err = excinfo.value
            assert type(err) is ValueError
            assert "AUTORESEARCH_API_TIMEOUT" in str(err)
        finally:
            config._CONFIG = None
            monkeypatch.delenv("AUTORESEARCH_API_TIMEOUT", raising=False)

    def test_api_missing_key_raises_runtime_error(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="MINIMAX_API_KEY") as excinfo:
            api.call_minimax("sys", "user")
        assert type(excinfo.value) is RuntimeError
        assert "MINIMAX_API_KEY" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 2. 缺少檔案
# ---------------------------------------------------------------------------
class TestMissingFileErrors:
    """缺少檔案應有穩定訊息與退出狀態（或安全預設）。"""

    def test_gatekeeper_missing_file_exits_one(self, tmp_path):
        missing = tmp_path / "nope.md"
        code, stdout, _ = _run_script_path(
            "scripts/gatekeeper.py",
            [str(missing)],
            cwd=tmp_path,
        )
        assert code == 1
        assert "[錯誤] 找不到檔案" in stdout
        # 路徑字串應出現在訊息中（分隔符可能因平台而異，比對 basename）
        assert missing.name in stdout

    def test_evaluate_missing_prompt_exits_one(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        import scripts.evaluate as evaluate

        with pytest.raises(SystemExit) as excinfo:
            evaluate.run_evaluation("missing_prompt.md", "q.jsonl")
        assert excinfo.value.code == 1

    def test_evaluate_missing_question_exits_one(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        import scripts.evaluate as evaluate

        (tmp_path / "prompt.md").write_text("提示詞內容", encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            evaluate.run_evaluation("prompt.md", "missing_q.jsonl")
        assert excinfo.value.code == 1
        captured = capsys.readouterr().out
        assert "找不到題庫檔案" in captured

    def test_io_missing_file_safe_defaults(self, tmp_path):
        missing_txt = str(tmp_path / "nope.txt")
        missing_json = str(tmp_path / "nope.json")
        missing_jsonl = str(tmp_path / "nope.jsonl")

        assert io.load_file(missing_txt, default="DEF") == "DEF"
        assert io.load_json(missing_json, default={"ok": False}) == {"ok": False}
        assert io.read_jsonl(missing_jsonl) == []

    def test_load_json_invalid_content_returns_default(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not-json", encoding="utf-8")
        assert io.load_json(str(bad), default={"fallback": True}) == {"fallback": True}

    def test_write_file_parent_file_is_path_error(self, tmp_path):
        parent = tmp_path / "既存檔案"
        parent.write_text("not a directory", encoding="utf-8")
        target = parent / "output.txt"

        with pytest.raises(FileExistsError) as excinfo:
            io.write_file(str(target), "content")

        error = excinfo.value
        assert type(error) is FileExistsError
        assert error.errno == errno.EEXIST
        assert parent.name in str(error)


# ---------------------------------------------------------------------------
# 3. 權限不足
# ---------------------------------------------------------------------------
class TestPermissionErrors:
    """權限不足時應拋出 OSError 子類（PermissionError 或 Windows 對等）。"""

    def test_write_to_readonly_file_raises_oserror(self, tmp_path):
        path = tmp_path / "readonly.txt"
        path.write_text("original", encoding="utf-8")
        restore, mode = _make_unreadable(path)
        assert mode in ("read", "write")
        try:
            if mode == "write":
                with pytest.raises(OSError) as excinfo:
                    io.write_file(str(path), "overwrite")
            else:
                with pytest.raises(OSError) as excinfo:
                    # POSIX：不可讀檔存在時 load_file 不走 default 分支
                    io.load_file(str(path), default="should-not-return")
            err = excinfo.value
            # PermissionError 是 OSError 子類；部分平台 errno 為 EACCES/EPERM
            assert isinstance(err, OSError)
            assert type(err).__name__ in (
                "PermissionError",
                "OSError",
                "FileNotFoundError",  # 極端路徑不應出現，但保留防禦
            ) or issubclass(type(err), OSError)
            # 至少 errno 有值或訊息非空
            assert err.errno is not None or str(err)
        finally:
            restore()

    def test_write_into_readonly_directory_raises_oserror(self, tmp_path):
        if PLATFORM == "Windows":
            pytest.skip("Windows 對目錄 chmod 行為不一致，改由唯讀檔案例覆蓋")

        locked_dir = tmp_path / "locked"
        locked_dir.mkdir()
        os.chmod(locked_dir, 0o555)  # r-x：不可寫入
        target = locked_dir / "child.txt"
        try:
            with pytest.raises(OSError) as excinfo:
                io.write_file(str(target), "x")
            assert isinstance(excinfo.value, OSError)
            assert isinstance(excinfo.value, (PermissionError, OSError))
        finally:
            os.chmod(locked_dir, 0o755)

    def test_permission_error_type_is_stable_across_path_forms(self, tmp_path):
        """路徑含空白／非 ASCII 時，權限錯誤型別仍應為 OSError 子類。"""
        path = tmp_path / "權限 目錄" / "locked file.txt"
        path.parent.mkdir(parents=True)
        path.write_text("data", encoding="utf-8")
        restore, mode = _make_unreadable(path)
        try:
            with pytest.raises(OSError) as excinfo:
                if mode == "write":
                    io.write_file(str(path), "new")
                else:
                    io.load_file(str(path))
            assert isinstance(excinfo.value, OSError)
        finally:
            restore()


# ---------------------------------------------------------------------------
# 4. 外部程序／外部依賴失敗
# ---------------------------------------------------------------------------
class TestExternalProcessFailures:
    """外部程序無法啟動或外部 API 失敗時的錯誤契約。"""

    def test_run_test_matrix_command_oserror_returns_exit_one(self, capsys):
        import scripts.run_test_matrix as matrix

        def boom(*_a, **_k):
            raise OSError(2, "No such file or directory", "fake-bin")

        with mock.patch.object(matrix.subprocess, "run", side_effect=boom):
            result = matrix._run_command(["fake-bin", "--version"])

        assert isinstance(result, subprocess.CompletedProcess)
        assert result.returncode == 1
        assert result.args[0] == "fake-bin"
        captured = capsys.readouterr()
        assert "無法執行子程序" in captured.err
        assert "No such file" in captured.err or "fake-bin" in captured.err

    def test_run_test_matrix_pytest_failure_propagates_nonzero(self, monkeypatch):
        import scripts.run_test_matrix as matrix

        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(command, 7, stdout="", stderr="boom")

        monkeypatch.setattr(matrix.subprocess, "run", fake_run)
        code = matrix._run_pytest("M2", ("tests/test_cross_platform.py",))
        assert code == 7

    def test_api_http_error_structured_message_and_type(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        monkeypatch.setattr(
            api,
            "get",
            lambda section, key=None, default=None: {
                "url": "https://api.example.local/v1",
                "model": "m",
                "timeout": 1,
                "retry": 1,
                "rate_limit": {"max_concurrent": 1, "min_interval_ms": 0},
            }.get(key, default)
            if section == "api" and key is not None
            else (
                {
                    "url": "https://api.example.local/v1",
                    "model": "m",
                    "timeout": 1,
                    "retry": 1,
                    "rate_limit": {"max_concurrent": 1, "min_interval_ms": 0},
                }
                if section == "api"
                else default
            ),
        )
        monkeypatch.setattr(api, "_rate_wait", lambda: None)
        monkeypatch.setattr(api, "_semaphore", None)
        monkeypatch.setattr(api, "_last_call_ts", 0.0)

        original = HTTPError(
            url="https://api.example.local/v1",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=None,
        )
        with mock.patch.object(api.urllib.request, "urlopen", side_effect=original):
            with pytest.raises(api.APIError) as excinfo:
                api.call_minimax("s", "u")

        err = excinfo.value
        assert type(err) is api.APIError
        assert isinstance(err, RuntimeError)
        assert not isinstance(err, api.APITimeoutError)
        msg = str(err)
        assert "503" in msg
        assert "retry=1" in msg
        assert err.__cause__ is original

    def test_api_timeout_is_api_timeout_error(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        monkeypatch.setattr(
            api,
            "get",
            lambda section, key=None, default=None: 1
            if key in ("timeout", "retry")
            else (
                {"max_concurrent": 1, "min_interval_ms": 0}
                if key == "rate_limit"
                else (
                    "https://api.example.local/v1"
                    if key == "url"
                    else ("m" if key == "model" else default)
                )
            )
            if section == "api"
            else default,
        )
        monkeypatch.setattr(api, "_rate_wait", lambda: None)
        monkeypatch.setattr(api, "_semaphore", None)
        monkeypatch.setattr(api, "_last_call_ts", 0.0)

        with mock.patch.object(
            api.urllib.request, "urlopen", side_effect=TimeoutError("timed out")
        ):
            with pytest.raises(api.APITimeoutError) as excinfo:
                api.call_minimax("s", "u")

        err = excinfo.value
        assert isinstance(err, TimeoutError)
        assert isinstance(err, api.APIError)
        assert "逾時" in str(err)
        assert "retry=1" in str(err)

    def test_subprocess_nonzero_exit_is_platform_int(self):
        """真子程序失敗時 returncode 為 int 且非 0（各平台一致）。"""
        result = subprocess.run(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert isinstance(result.returncode, int)
        assert result.returncode == 3


# ---------------------------------------------------------------------------
# 5. 錯誤契約摘要：型別／訊息／退出碼對照表一致性
# ---------------------------------------------------------------------------
class TestErrorContractSummary:
    """彙整斷言：四類錯誤在當前平台的契約欄位齊全。"""

    def test_error_contract_fields_documented_by_assertions(self, tmp_path):
        """用一組最小案例再次確認四類錯誤皆具備型別或退出狀態。"""
        # 無效輸入
        code, stdout, _ = _run_script_path("scripts/gatekeeper.py", [], cwd=tmp_path)
        assert code == 1 and "用法:" in stdout

        # 缺少檔案
        code, stdout, _ = _run_script_path(
            "scripts/gatekeeper.py",
            [str(tmp_path / "absent.md")],
            cwd=tmp_path,
        )
        assert code == 1 and "找不到檔案" in stdout

        # 權限不足
        path = tmp_path / "ro.txt"
        path.write_text("x", encoding="utf-8")
        restore, mode = _make_unreadable(path)
        try:
            with pytest.raises(OSError):
                if mode == "write":
                    io.write_file(str(path), "y")
                else:
                    io.load_file(str(path))
        finally:
            restore()

        # 外部程序
        import scripts.run_test_matrix as matrix

        with mock.patch.object(
            matrix.subprocess,
            "run",
            side_effect=OSError(13, "Permission denied", "tool"),
        ):
            result = matrix._run_command(["tool"])
        assert result.returncode == 1
