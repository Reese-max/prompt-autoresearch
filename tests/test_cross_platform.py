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
# 1b. 路徑處理回歸：分隔符 / 絕對與相對 / 空白 / 非 ASCII
# ---------------------------------------------------------------------------
class TestCrossPlatformPathRegression:
    """跨平台路徑處理回歸測試。

    涵蓋 Windows/POSIX 分隔符、絕對與相對路徑、含空白及非 ASCII 字元的路徑。
    確保 normalize_path 與檔案 I/O 在這些路徑形式上行為一致。
    """

    # --- 分隔符：Windows \ 與 POSIX / ---
    @pytest.mark.parametrize(
        "input_path,expected",
        [
            pytest.param(r"dir\file.txt", "dir/file.txt", id="win-sep-simple"),
            pytest.param("dir/file.txt", "dir/file.txt", id="posix-sep-simple"),
            pytest.param(r"a\b\c\d.txt", "a/b/c/d.txt", id="win-sep-nested"),
            pytest.param("a/b/c/d.txt", "a/b/c/d.txt", id="posix-sep-nested"),
            pytest.param(r"mixed/path\parts", "mixed/path/parts", id="mixed-seps"),
            pytest.param(r"trailing\sep\\", "trailing/sep//", id="win-trailing"),
            pytest.param("trailing/sep//", "trailing/sep//", id="posix-trailing"),
        ],
    )
    def test_normalize_windows_and_posix_separators(self, input_path, expected):
        result = io.normalize_path(input_path)
        assert result == expected, (
            f"分隔符正規化失敗 ({PLATFORM}): "
            f"normalize_path({input_path!r}) -> {result!r}, 預期 {expected!r}"
        )
        assert "\\" not in result, (
            f"正規化後不應殘留反斜線: {result!r}"
        )

    # --- 絕對路徑 ---
    @pytest.mark.parametrize(
        "input_path,expected",
        [
            pytest.param(r"C:\Users\Admin\file.txt", "C:/Users/Admin/file.txt", id="win-drive"),
            pytest.param(r"D:\資料\專案\app.py", "D:/資料/專案/app.py", id="win-drive-nonascii"),
            pytest.param(
                r"C:\Program Files\My App\config.json",
                "C:/Program Files/My App/config.json",
                id="win-drive-spaces",
            ),
            pytest.param("/home/user/file.txt", "/home/user/file.txt", id="posix-abs"),
            pytest.param("/home/user/我的 專案/檔案.txt", "/home/user/我的 專案/檔案.txt", id="posix-abs-nonascii-space"),
            pytest.param(r"\\server\share\file.txt", "//server/share/file.txt", id="win-unc"),
        ],
    )
    def test_normalize_absolute_paths(self, input_path, expected):
        result = io.normalize_path(input_path)
        assert result == expected, (
            f"絕對路徑正規化失敗 ({PLATFORM}): "
            f"normalize_path({input_path!r}) -> {result!r}, 預期 {expected!r}"
        )

    # --- 相對路徑 ---
    @pytest.mark.parametrize(
        "input_path,expected",
        [
            pytest.param("./rel/file.txt", "./rel/file.txt", id="dot-posix"),
            pytest.param(r".\rel\file.txt", "./rel/file.txt", id="dot-win"),
            pytest.param("../parent/file.txt", "../parent/file.txt", id="dotdot-posix"),
            pytest.param(r"..\parent\file.txt", "../parent/file.txt", id="dotdot-win"),
            pytest.param("subdir/nested", "subdir/nested", id="plain-rel-posix"),
            pytest.param(r"subdir\nested", "subdir/nested", id="plain-rel-win"),
            pytest.param("file only.txt", "file only.txt", id="rel-space-filename"),
        ],
    )
    def test_normalize_relative_paths(self, input_path, expected):
        result = io.normalize_path(input_path)
        assert result == expected, (
            f"相對路徑正規化失敗 ({PLATFORM}): "
            f"normalize_path({input_path!r}) -> {result!r}, 預期 {expected!r}"
        )

    # --- 含空白路徑 ---
    @pytest.mark.parametrize(
        "input_path,expected",
        [
            pytest.param("my file.txt", "my file.txt", id="space-filename"),
            pytest.param("my dir/my file.txt", "my dir/my file.txt", id="space-posix"),
            pytest.param(r"my dir\my file.txt", "my dir/my file.txt", id="space-win"),
            pytest.param("  leading space/file.txt", "  leading space/file.txt", id="leading-space-dir"),
            pytest.param("path with   multi spaces/x", "path with   multi spaces/x", id="multi-spaces"),
            pytest.param(
                r"C:\Users\Admin\My Documents\report 2026.md",
                "C:/Users/Admin/My Documents/report 2026.md",
                id="abs-win-spaces",
            ),
        ],
    )
    def test_normalize_paths_with_spaces(self, input_path, expected):
        result = io.normalize_path(input_path)
        assert result == expected, (
            f"空白路徑正規化失敗 ({PLATFORM}): "
            f"normalize_path({input_path!r}) -> {result!r}, 預期 {expected!r}"
        )
        # 空白必須被保留，不可被剝除或壓縮
        assert " " in result or " " not in input_path

    # --- 非 ASCII 字元路徑 ---
    @pytest.mark.parametrize(
        "input_path,expected",
        [
            pytest.param("資料/測試.py", "資料/測試.py", id="cjk-posix"),
            pytest.param(r"資料\測試.py", "資料/測試.py", id="cjk-win"),
            pytest.param("日本語/ファイル.txt", "日本語/ファイル.txt", id="jp"),
            pytest.param("한국어/파일.txt", "한국어/파일.txt", id="kr"),
            pytest.param("emoji_📁_dir/file.txt", "emoji_📁_dir/file.txt", id="emoji"),
            pytest.param(
                r"專案\子目錄\設定 檔案.json",
                "專案/子目錄/設定 檔案.json",
                id="cjk-space-win",
            ),
            pytest.param(
                "/tmp/用戶 資料/報告.md",
                "/tmp/用戶 資料/報告.md",
                id="cjk-space-posix-abs",
            ),
        ],
    )
    def test_normalize_non_ascii_paths(self, input_path, expected):
        result = io.normalize_path(input_path)
        assert result == expected, (
            f"非 ASCII 路徑正規化失敗 ({PLATFORM}): "
            f"normalize_path({input_path!r}) -> {result!r}, 預期 {expected!r}"
        )

    # --- 檔案 I/O：含空白與非 ASCII 的相對路徑 round-trip ---
    def test_io_round_trip_relative_path_with_spaces_and_non_ascii(self, tmp_path):
        """相對路徑含空白與非 ASCII 時，write/load 應一致。"""
        rel = Path("子 目錄") / "報告 2026.txt"
        target = tmp_path / rel
        content = "跨平台路徑測試：空白 + 中文"

        io.write_file(str(target), content)
        assert target.exists(), f"檔案未建立: {target}"
        assert io.load_file(str(target)) == content

    # --- 檔案 I/O：絕對路徑 + 空白 + 非 ASCII ---
    def test_io_round_trip_absolute_path_with_spaces_and_non_ascii(self, tmp_path):
        """絕對路徑含空白與非 ASCII 時，write/load/json 應一致。"""
        target = (tmp_path / "我的 專案" / "設定.json").resolve()
        payload = {"路徑": str(target), "名稱": "測試 設定", "ok": True}

        assert os.path.isabs(str(target)), f"應為絕對路徑: {target}"
        io.write_json(str(target), payload)
        loaded = io.load_json(str(target))
        assert loaded == payload

    # --- PurePath 形式：Windows / POSIX 構造後仍可 I/O ---
    @pytest.mark.parametrize("path_type", PLATFORM_PATH_TYPES)
    def test_io_with_platform_path_forms_spaces_and_non_ascii(self, tmp_path, path_type):
        """以 PurePosixPath / PureWindowsPath 構造含空白與非 ASCII 的相對路徑。"""
        relative = path_type("資料 夾") / "nested sub" / "輸出.txt"
        path = tmp_path.joinpath(*relative.parts)
        content = "separator regression"

        io.ensure_dir(str(path.parent))
        io.write_file(str(path), content)
        assert io.load_file(str(path)) == content

        # normalize_path 對 str(relative) 應統一為 /
        normalized = io.normalize_path(str(relative))
        assert "\\" not in normalized
        assert "資料 夾" in normalized
        assert "nested sub" in normalized

    # --- JSONL：路徑含空白 ---
    def test_jsonl_path_with_spaces(self, tmp_path):
        path = tmp_path / "log with spaces" / "events.jsonl"
        rows = [{"id": 1, "訊息": "空白路徑"}, {"id": 2, "path": str(path)}]
        for row in rows:
            io.append_jsonl(str(path), row)
        assert io.read_jsonl(str(path)) == rows

    # --- ensure_dir：含空白與非 ASCII 的巢狀目錄 ---
    def test_ensure_dir_spaces_and_non_ascii(self, tmp_path):
        target = tmp_path / "a b" / "中文 目錄" / "nested"
        io.ensure_dir(str(target))
        assert target.is_dir()
        # 冪等
        io.ensure_dir(str(target))
        assert target.is_dir()


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
# 6. 暫存目錄行為：含空白與 Unicode 的路徑在暫存目錄中正常運作
# ---------------------------------------------------------------------------
class TestTempDirectoryBehavior:
    """暫存目錄行為測試，確保含空白與 Unicode 的路徑在暫存環境中正常運作。"""

    def test_temp_dir_with_spaces_creates_and_writes(self, tmp_path):
        """含空白的暫存目錄應能正常建立檔案並讀寫。"""
        space_dir = tmp_path / "my temp dir"
        space_dir.mkdir()
        test_file = space_dir / "test.txt"
        content = "測試內容"
        io.write_file(str(test_file), content)
        assert test_file.exists()
        assert io.load_file(str(test_file)) == content

    def test_temp_dir_with_unicode_creates_and_writes(self, tmp_path):
        """含 Unicode 的暫存目錄應能正常建立檔案並讀寫。"""
        unicode_dir = tmp_path / "測試目錄"
        unicode_dir.mkdir()
        test_file = unicode_dir / "檔案.txt"
        content = "中文內容"
        io.write_file(str(test_file), content)
        assert test_file.exists()
        assert io.load_file(str(test_file)) == content

    def test_temp_dir_nested_with_spaces_and_unicode(self, tmp_path):
        """巢狀暫存目錄含空白與 Unicode 應正常運作。"""
        nested = tmp_path / "temp space" / "中文 層" / "deep"
        io.ensure_dir(str(nested))
        assert nested.is_dir()
        test_file = nested / "output.json"
        payload = {"路徑": str(nested), "名稱": "測試"}
        io.write_json(str(test_file), payload)
        assert io.load_json(str(test_file)) == payload

    def test_temp_dir_normalize_path_with_spaces_and_unicode(self, tmp_path):
        """暫存目錄路徑經 normalize_path 處理後應保持一致。"""
        space_dir = tmp_path / "my temp dir"
        unicode_dir = space_dir / "中文目錄"
        io.ensure_dir(str(unicode_dir))
        
        # 建立測試檔案
        test_file = unicode_dir / "test.txt"
        io.write_file(str(test_file), "content")
        
        # 取得相對路徑並正規化
        rel_path = os.path.relpath(str(test_file), str(tmp_path))
        normalized = io.normalize_path(rel_path)
        
        # 正規化後應使用 / 分隔符且保留空白與 Unicode
        assert "\\" not in normalized
        assert "my temp dir" in normalized
        assert "中文目錄" in normalized

    def test_temp_dir_jsonl_with_spaces_and_unicode(self, tmp_path):
        """JSONL 檔案在含空白與 Unicode 的暫存目錄中應正常運作。"""
        log_dir = tmp_path / "log files" / "日誌"
        io.ensure_dir(str(log_dir))
        log_file = log_dir / "events.jsonl"
        
        rows = [
            {"id": 1, "訊息": "測試"},
            {"id": 2, "路徑": str(log_dir)},
        ]
        for row in rows:
            io.append_jsonl(str(log_file), row)
        
        loaded = io.read_jsonl(str(log_file))
        assert loaded == rows

    def test_temp_dir_ensure_dir_idempotent_with_spaces_and_unicode(self, tmp_path):
        """ensure_dir 在含空白與 Unicode 的路徑上應具冪等性。"""
        target = tmp_path / "a b" / "中文 c" / "nested"
        io.ensure_dir(str(target))
        assert target.is_dir()
        
        # 重複呼叫應不報錯
        io.ensure_dir(str(target))
        assert target.is_dir()


# ---------------------------------------------------------------------------
# 7. Config 路徑解析：_CONFIG_PATH 在所有平台上指向有效路徑
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


# ---------------------------------------------------------------------------
# 9. 核心評估流程：固定輸入與輸出契約跨平台一致
# ---------------------------------------------------------------------------
class TestCoreEvaluationFlow:
    """固定輸入經核心評估流程後，輸出結構與檔案產物應一致。"""

    def test_same_input_produces_spec_compliant_output(self, monkeypatch, tmp_path):
        import shutil

        import scripts.evaluate as evaluate

        monkeypatch.chdir(tmp_path)
        prompt_path = tmp_path / "輸入 資料" / "提示詞.md"
        question_path = tmp_path / "輸入 資料" / "題庫.jsonl"
        io.ensure_dir(str(prompt_path.parent))
        prompt_path.write_bytes((UNICODE_PROMPT + "\r\n").encode("utf-8"))
        question = {
            "id": 1,
            "type": "案例題",
            "question": "請說明行政處分之要件。",
            "key_points": ["定義", "要件"],
        }
        question_path.write_bytes(
            (json.dumps(question, ensure_ascii=False) + "\r\n").encode("utf-8")
        )
        for rubric_name in (
            "general.md",
            "type_specific.md",
            "risk_rules.md",
            "failure_taxonomy.md",
        ):
            io.write_file(f"rubrics/{rubric_name}", "固定 UTF-8 評分規準")

        answer = ("第一行中文\n第二行 mixed English\n" * 40)
        judge_output = json.dumps(
            {
                "general_score": 55,
                "type_specific_score": 15,
                "risk_score": 9,
                "failures": ["F03"],
                "critique": "請加強採分點。",
            },
            ensure_ascii=False,
        )

        def fake_minimax(_system, _user, temperature=0.7):
            if temperature == 0.3:
                return answer
            assert temperature == 0.1
            return judge_output

        monkeypatch.setattr(evaluate, "call_minimax", fake_minimax)
        prompt_arg = io.normalize_path(str(prompt_path))
        question_arg = io.normalize_path(str(question_path))

        summary, results = evaluate.run_evaluation(
            prompt_arg, question_arg, max_workers=1
        )
        first = results[0]

        assert summary["prompt_file"] == prompt_arg
        assert summary["question_file"] == question_arg
        assert summary["prompt_hash"] == io.sha256_text(UNICODE_PROMPT)
        assert summary["total_questions"] == 1
        assert summary["average_score"] == 79.0
        assert summary["word_count_pass_rate"] == 100.0
        assert summary["risk_perfect_rate"] == 0.0
        assert summary["error_count"] == 0
        assert first["question_file"] == question_arg
        assert first["answer"] == answer
        assert first["char_count"] == len(answer)
        assert first["total_score"] == 55 + 15 + 9
        assert first["failures"] == ["F03"]

        shutil.rmtree(tmp_path / ".cache")
        repeat_summary, repeat_results = evaluate.run_evaluation(
            prompt_arg, question_arg, max_workers=1
        )
        for key in ("prompt_file", "question_file", "prompt_hash", "total_questions", "average_score", "word_count_pass_rate", "risk_perfect_rate", "error_count"):
            assert repeat_summary[key] == summary[key]
        assert repeat_results == results

        run_dir = Path(evaluate.save_run_results(summary, results))
        for name in ("details.jsonl", "summary.json", "summary.md"):
            artifact = run_dir / name
            raw = artifact.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf")
            raw.decode("utf-8")
            assert artifact.exists()
        details = [
            json.loads(line)
            for line in (run_dir / "details.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        stored_summary = json.loads(
            (run_dir / "summary.json").read_text(encoding="utf-8")
        )
        assert details == results
        assert stored_summary["question_file"] == question_arg
        assert stored_summary["average_score"] == 79.0
        assert len((run_dir / "summary.md").read_text(encoding="utf-8").splitlines()) > 1
        assert "\t79.00\t" in (Path("results.tsv").read_text(encoding="utf-8"))
        assert all((Path("runs/latest") / name).exists() for name in ("details.jsonl", "summary.json", "summary.md"))
