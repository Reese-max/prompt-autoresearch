import hashlib
import json

import lib.io as io


def test_load_file_returns_stripped_content_and_missing_path_default(tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("  hello world  \n", encoding="utf-8")

    assert io.load_file(str(file_path)) == "hello world"
    assert io.load_file(str(tmp_path / "missing.txt"), default="fallback") == "fallback"


def test_write_file_auto_creates_parent_dir_and_writes_content(tmp_path):
    target = tmp_path / "nested" / "dir" / "output.txt"

    io.write_file(str(target), "abc\n123")

    assert target.read_text(encoding="utf-8") == "abc\n123"


def test_sha256_text_matches_python_hashlib():
    text = "中文測試\n2026"
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()

    assert io.sha256_text(text) == expected


def test_load_json_returns_default_when_missing_or_error(tmp_path):
    default = {"fallback": True}

    missing = tmp_path / "not_exists.json"
    assert io.load_json(str(missing), default=default) == default

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid json", encoding="utf-8")
    assert io.load_json(str(invalid), default=default) == default

    # Directory 也會觸發例外，應回傳預設值
    assert io.load_json(str(tmp_path), default=default) == default


def test_write_and_load_json_round_trip_preserves_unicode(tmp_path):
    payload = {"status": "ok", "text": "測試", "n": 3}
    path = tmp_path / "config.json"

    io.write_json(str(path), payload)
    loaded = io.load_json(str(path))

    assert loaded == payload
    text = path.read_text(encoding="utf-8")
    assert '"text": "測試"' in text


def test_read_jsonl_with_limit_and_append_jsonl_json_dumps_newline(tmp_path):
    path = tmp_path / "rows.jsonl"
    io.append_jsonl(str(path), {"idx": 1})
    io.append_jsonl(str(path), {"idx": 2})

    raw = path.read_text(encoding="utf-8")
    lines = raw.strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"idx": 1}
    assert json.loads(lines[1]) == {"idx": 2}

    path.write_text("{\"a\":1}\n\n{\"b\":2}\n", encoding="utf-8")
    rows = io.read_jsonl(str(path))
    assert rows == [{"a": 1}, {"b": 2}]

    assert io.read_jsonl(str(path), limit=1) == [{"a": 1}]


def test_normalize_path_and_ensure_dir(tmp_path):
    assert io.normalize_path(r"a\b\c.txt") == "a/b/c.txt"

    target_dir = tmp_path / "x" / "y"
    io.ensure_dir(str(target_dir))
    assert target_dir.exists() and target_dir.is_dir()
