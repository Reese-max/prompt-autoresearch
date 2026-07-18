# -*- coding: utf-8 -*-
"""
跨平台驗證測試子集。

驗證關鍵流程在不同作業系統上以相同輸入產生一致的輸出、錯誤型別與退出碼。
CI 環境為 ubuntu-latest，開發環境為 Windows；本測試確保兩邊行為對齊。
"""
import hashlib
import json
import os
import platform
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

import lib.io as io

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 共用測試輸入：含中文字元的 prompt，與 gatekeeper 使用的格式一致
# 此 prompt 滿足 gatekeeper 所有硬性規則（長度 >= 100、含反問禁止、含防編造、含專家角色等）
UNICODE_PROMPT = (
    "你是閱卷委員兼考官，具備法學判斷能力。"
    "答案需以法理與法律案例題清楚區分，先建立比較基準：法條適用、事實比對與要件對照。"
    "處理法律題時，使用三段論（大前提與小前提）完成推理。"
    "不得反問、不得編造，並要直接輸出正文，不要輸出冗長前言與分析過程。"
    "此題以簡明語句回應。"
)
UNICODE_PAYLOAD = {"key": "中文值", "nested": {"路徑": "a/b/c", "數字": 42}}

PLATFORM = platform.system()  # "Windows", "Linux", "Darwin"
PLATFORM_PATH_TYPES = (
    pytest.param(PurePosixPath, id="posix"),
    pytest.param(PureWindowsPath, id="windows"),
)


# ---------------------------------------------------------------------------
# 1. 路徑正規化：normalize_path 輸出一致
# ---------------------------------------------------------------------------
class TestNormalizePath:
    """lib.io.normalize_path 在所有平台上應產生相同的 / 分隔結果。"""

    @pytest.mark.parametrize("input_path,expected", [
        (r"a\b\c.txt", "a/b/c.txt"),
        ("a/b/c.txt", "a/b/c.txt"),
        (r"lib\資料\測試.py", "lib/資料/測試.py"),
        ("lib/資料/測試.py", "lib/資料/測試.py"),
        ("single", "single"),
        ("", ""),
    ])
    def test_normalize_path_consistent(self, input_path, expected):
        result = io.normalize_path(input_path)
        assert result == expected, (
            f"normalize_path({input_path!r}) 在 {PLATFORM} 上回傳 {result!r}，"
            f"預期 {expected!r}"
        )


# ---------------------------------------------------------------------------
# 2. 檔案 I/O：Unicode 讀寫 round-trip 一致
# ---------------------------------------------------------------------------
class TestFileIORoundTrip:
    """load_file / write_file / load_json / write_json 在所有平台上
    應對中文字元產生相同的 round-trip 結果。"""

    def test_load_write_file_unicode_round_trip(self, tmp_path):
        path = tmp_path / "unicode.txt"
        content = "第一行中文\n第二行 mixed English 混合\n第三行\t\ttab"
        io.write_file(str(path), content)
        result = io.load_file(str(path))
        assert result == content, (
            f"load_file/write_file Unicode round-trip 在 {PLATFORM} 上不一致"
        )

    def test_load_file_strips_whitespace(self, tmp_path):
        path = tmp_path / "spaces.txt"
        path.write_text("  content  \n", encoding="utf-8")
        assert io.load_file(str(path)) == "content"

    def test_load_file_missing_returns_default(self, tmp_path):
        assert io.load_file(str(tmp_path / "nope.txt"), default="X") == "X"

    def test_sha256_text_cross_platform(self):
        text = "跨平台 SHA-256 測試 中文"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert io.sha256_text(text) == expected
        # 多次呼叫應穩定
        assert io.sha256_text(text) == expected

    def test_write_load_json_unicode_round_trip(self, tmp_path):
        path = tmp_path / "config.json"
        io.write_json(str(path), UNICODE_PAYLOAD)
        loaded = io.load_json(str(path))
        assert loaded == UNICODE_PAYLOAD, (
            f"write_json/load_json Unicode round-trip 在 {PLATFORM} 上不一致"
        )

    def test_json_file_is_valid_utf8(self, tmp_path):
        path = tmp_path / "utf8.json"
        io.write_json(str(path), UNICODE_PAYLOAD)
        raw = path.read_bytes()
        # 不應包含 BOM
        assert not raw.startswith(b"\xef\xbb\xbf"), "JSON 檔不應有 BOM"
        # 應可被 UTF-8 解碼
        decoded = raw.decode("utf-8")
        assert json.loads(decoded) == UNICODE_PAYLOAD

    @pytest.mark.parametrize("path_type", PLATFORM_PATH_TYPES)
    def test_platform_path_forms_have_same_unicode_round_trip(self, tmp_path, path_type):
        relative = path_type("資料") / "nested" / "output.txt"
        path = tmp_path.joinpath(*relative.parts)
        content = "第一行中文\n第二行 mixed English 混合"

        io.write_file(str(path), content)

        assert io.load_file(str(path)) == content

    @pytest.mark.parametrize(
        ("path_type", "newline"),
        [
            pytest.param(PurePosixPath, "\n", id="posix-lf"),
            pytest.param(PureWindowsPath, "\r\n", id="windows-crlf"),
        ],
    )
    def test_platform_path_newline_and_utf8_have_same_output(
        self, tmp_path, path_type, newline
    ):
        relative = path_type("資料") / "input.txt"
        path = tmp_path.joinpath(*relative.parts)
        io.ensure_dir(str(path.parent))
        path.write_bytes(f"第一行{newline}第二行".encode("utf-8"))

        result = io.load_file(str(path))

        assert type(result) is str
        assert result == "第一行\n第二行"

    @pytest.mark.parametrize("path_type", PLATFORM_PATH_TYPES)
    def test_platform_path_write_error_has_same_exception_type(self, tmp_path, path_type):
        relative = path_type("資料") / "output.txt"
        parent_file = tmp_path / relative.parts[0]
        parent_file.write_text("not a directory", encoding="utf-8")

        with pytest.raises(FileExistsError) as exc_info:
            io.write_file(str(tmp_path.joinpath(*relative.parts)), "content")

        assert type(exc_info.value) is FileExistsError


# ---------------------------------------------------------------------------
# 3. JSONL 讀寫一致
# ---------------------------------------------------------------------------
class TestJSONLRoundTrip:
    """append_jsonl / read_jsonl 在所有平台上應產生相同的行序與內容。"""

    def test_jsonl_round_trip_unicode(self, tmp_path):
        path = tmp_path / "data.jsonl"
        rows = [
            {"id": 1, "名稱": "甲"},
            {"id": 2, "名稱": "乙"},
            {"id": 3, "name": "C", "mixed": "中en混合"},
        ]
        for row in rows:
            io.append_jsonl(str(path), row)

        result = io.read_jsonl(str(path))
        assert result == rows

    def test_jsonl_limit(self, tmp_path):
        path = tmp_path / "limited.jsonl"
        for i in range(5):
            io.append_jsonl(str(path), {"i": i})
        assert io.read_jsonl(str(path), limit=2) == [{"i": 0}, {"i": 1}]

    def test_jsonl_missing_file_returns_empty(self, tmp_path):
        assert io.read_jsonl(str(tmp_path / "nope.jsonl")) == []


# ---------------------------------------------------------------------------
# 4. 路徑分隔符處理：_is_protected_product_file 跨平台一致
# ---------------------------------------------------------------------------
class TestProtectedFilePathHandling:
    """scripts/product_diff_audit 的路徑判斷應同時處理 / 與反斜線分隔符。"""

    def _is_protected(self, rel_path: str) -> bool:
        """複製 product_diff_audit 的判斷邏輯以驗證跨平台一致性。"""
        FORCED_CORE = {"app.js", "index.html"}
        if rel_path in FORCED_CORE:
            return True
        if not rel_path:
            return False
        parts = rel_path.replace("\\", "/").split("/")
        if len(parts) >= 2 and parts[0] in ("api", "lib") and rel_path.endswith(".py"):
            return True
        return False

    @pytest.mark.parametrize("path_str", [
        "lib/config.py",
        r"lib\config.py",
        "api/server.py",
        r"api\server.py",
    ])
    def test_protected_core_files_detected(self, path_str):
        assert self._is_protected(path_str), (
            f"_is_protected({path_str!r}) 在 {PLATFORM} 上應回傳 True"
        )

    @pytest.mark.parametrize("path_str", [
        "tests/test_x.py",
        r"tests\test_x.py",
        "docs/readme.md",
        "lib/config.py.bak",
        "",
    ])
    def test_non_protected_files_rejected(self, path_str):
        assert not self._is_protected(path_str), (
            f"_is_protected({path_str!r}) 在 {PLATFORM} 上應回傳 False"
        )


# ---------------------------------------------------------------------------
# 5. Gatekeeper CLI：退出碼與 JSON 輸出契約跨平台一致
# ---------------------------------------------------------------------------
class TestGatekeeperCrossPlatform:
    """以固定輸入執行 gatekeeper，斷言退出碼與 JSON 輸出結構一致。"""

    @pytest.fixture
    def run_gatekeeper(self, monkeypatch, tmp_path):
        """以 in-process 方式執行 gatekeeper，回傳 (exit_code, payload, stdout)。"""
        import runpy
        from contextlib import redirect_stdout, redirect_stderr
        from io import StringIO

        def _run(argv):
            old_argv = list(sys.argv)
            old_cwd = os.getcwd()
            output = StringIO()
            try:
                sys.argv = list(argv)
                monkeypatch.chdir(tmp_path)
                with redirect_stdout(output), redirect_stderr(output):
                    try:
                        runpy.run_path(
                            str(PROJECT_ROOT / "scripts" / "gatekeeper.py"),
                            run_name="__main__",
                        )
                    except SystemExit as exc:
                        code = exc.code
                    else:
                        code = 0
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)

            stdout = output.getvalue()
            # 提取 JSON 輸出
            match = re.search(r"^\{\s*\"passed\"\s*:", stdout, flags=re.MULTILINE)
            payload = json.loads(stdout[match.start():]) if match else None
            return code, payload, stdout

        return _run

    def test_valid_prompt_exits_zero(self, run_gatekeeper, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text(UNICODE_PROMPT, encoding="utf-8")

        code, payload, stdout = run_gatekeeper([
            "scripts/gatekeeper.py", str(prompt_file), "--json",
        ])

        assert code == 0, (
            f"有效 prompt 在 {PLATFORM} 上退出碼應為 0，實際為 {code}"
        )
        assert payload is not None
        assert payload["passed"] is True
        assert payload["char_count"] == len(UNICODE_PROMPT)
        assert payload["violations"] == []
        assert set(payload.keys()) == {"passed", "violations", "char_count"}

    def test_rejected_prompt_exits_one(self, run_gatekeeper, tmp_path):
        # 短 prompt 會觸發 R01_LENGTH_TOO_SHORT reject
        short_prompt = "短"
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text(short_prompt, encoding="utf-8")

        code, payload, stdout = run_gatekeeper([
            "scripts/gatekeeper.py", str(prompt_file), "--json",
        ])

        assert code == 1, (
            f"無效 prompt 在 {PLATFORM} 上退出碼應為 1，實際為 {code}"
        )
        assert payload is not None
        assert payload["passed"] is False
        assert len(payload["violations"]) > 0

    def test_missing_file_exits_one(self, run_gatekeeper, tmp_path):
        missing = tmp_path / "nonexistent.md"

        code, payload, stdout = run_gatekeeper([
            "scripts/gatekeeper.py", str(missing),
        ])

        assert code == 1
        assert payload is None
        assert "[錯誤] 找不到檔案" in stdout

    def test_no_args_exits_one(self, run_gatekeeper):
        code, payload, stdout = run_gatekeeper(["scripts/gatekeeper.py"])

        assert code == 1
        assert payload is None
        assert "用法:" in stdout


# ---------------------------------------------------------------------------
# 6. Config 路徑解析：_CONFIG_PATH 在所有平台上指向有效路徑
# ---------------------------------------------------------------------------
class TestConfigPathResolution:
    """lib.config._CONFIG_PATH 應在所有平台上解析為專案根目錄下的 config.json。"""

    def test_config_path_resolves_to_project_root(self):
        import lib.config as config
        assert config._CONFIG_PATH.endswith("config.json")
        # 路徑應可被解析（不論使用 / 或 \）
        resolved = os.path.normpath(config._CONFIG_PATH)
        assert os.path.isabs(resolved), (
            f"_CONFIG_PATH={config._CONFIG_PATH!r} 在 {PLATFORM} 上不是絕對路徑"
        )

    def test_config_defaults_are_valid(self):
        import lib.config as config
        defaults = config._DEFAULTS
        assert isinstance(defaults, dict)
        assert "api" in defaults
        assert "parallel" in defaults
        assert "thresholds" in defaults
        # 預設值應通過驗證
        config.validate_config(dict(defaults))


# ---------------------------------------------------------------------------
# 7. 行尾處理：\r\n 與 \n 應被一致讀取
# ---------------------------------------------------------------------------
class TestLineEndingConsistency:
    """檔案含 \\r\\n 與 \\n 行尾時，load_file 與 read_jsonl 應一致處理。"""

    def test_load_file_crlf_and_lf_identical(self, tmp_path):
        content_lf = "line1\nline2\nline3"
        content_crlf = "line1\r\nline2\r\nline3"

        path_lf = tmp_path / "lf.txt"
        path_crlf = tmp_path / "crlf.txt"
        path_lf.write_bytes(content_lf.encode("utf-8"))
        path_crlf.write_bytes(content_crlf.encode("utf-8"))

        result_lf = io.load_file(str(path_lf))
        result_crlf = io.load_file(str(path_crlf))
        # Python 的 universal newline 模式應將 \r\n 轉為 \n
        assert result_lf == result_crlf, (
            f"load_file 對 LF vs CRL 結果不同 ({PLATFORM}): "
            f"LF={result_lf!r}, CRLF={result_crlf!r}"
        )

    def test_jsonl_mixed_line_endings(self, tmp_path):
        path = tmp_path / "mixed.jsonl"
        raw = '{"a":1}\r\n{"b":2}\n{"c":3}\r\n'
        path.write_bytes(raw.encode("utf-8"))

        rows = io.read_jsonl(str(path))
        assert rows == [{"a": 1}, {"b": 2}, {"c": 3}]


# ---------------------------------------------------------------------------
# 8. ensure_dir 跨平台一致
# ---------------------------------------------------------------------------
class TestEnsureDir:
    """io.ensure_dir 在所有平台上應建立相同的目錄結構。"""

    def test_ensure_dir_creates_nested(self, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        io.ensure_dir(str(target))
        assert target.exists() and target.is_dir()

    def test_ensure_dir_idempotent(self, tmp_path):
        target = tmp_path / "x"
        io.ensure_dir(str(target))
        io.ensure_dir(str(target))  # 第二次不應報錯
        assert target.exists()
