"""可執行檢查:tests/ 下每個測試函式必須至少包含一個真斷言。

禁止「僅 import」或「僅執行不驗證」的測試。真斷言認定為下列任一:
- ``assert`` 陳述式
- ``pytest.raises`` / ``pytest.warns`` / ``pytest.deprecated_call`` / ``pytest.fail``
  (含 ``from pytest import raises`` 的裸名呼叫)
- unittest 風格 ``self.assert*``

執行方式:
  pytest tests/test_assertion_guard.py   # 隨測試套件自動執行
  python tests/test_assertion_guard.py   # 獨立執行,違規則 exit code 1
"""

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

_PYTEST_ASSERTION_ATTRS = {"raises", "warns", "deprecated_call", "fail"}


def _is_real_assertion(node):
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "pytest" and func.attr in _PYTEST_ASSERTION_ATTRS:
                return True
            if func.value.id == "self" and func.attr.startswith("assert"):
                return True
        if isinstance(func, ast.Name) and func.id in _PYTEST_ASSERTION_ATTRS:
            return True
    return False


def _iter_test_functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                yield node


def find_violations(tests_dir=TESTS_DIR):
    violations = []
    for path in sorted(Path(tests_dir).glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for func in _iter_test_functions(tree):
            if not any(_is_real_assertion(n) for n in ast.walk(func)):
                violations.append(f"{path.name}:{func.lineno} {func.name}")
    return violations


def test_every_test_function_has_a_real_assertion():
    violations = find_violations()
    assert not violations, (
        "以下測試缺少真斷言(禁止僅 import/僅執行不驗證):\n" + "\n".join(violations)
    )


def test_guard_detects_assertionless_test(tmp_path):
    (tmp_path / "test_bad.py").write_text(
        "import os\n\ndef test_only_runs():\n    os.getcwd()\n",
        encoding="utf-8",
    )
    violations = find_violations(tmp_path)
    assert violations == ["test_bad.py:3 test_only_runs"]


def test_guard_accepts_real_assertions(tmp_path):
    (tmp_path / "test_good.py").write_text(
        "import pytest\n"
        "def test_assert():\n    assert 1 + 1 == 2\n"
        "def test_raises():\n"
        "    with pytest.raises(ValueError):\n        int('x')\n",
        encoding="utf-8",
    )
    assert find_violations(tmp_path) == []


if __name__ == "__main__":
    found = find_violations()
    if found:
        print("FAIL: 以下測試缺少真斷言:")
        for line in found:
            print("  " + line)
        raise SystemExit(1)
    print("OK: tests/ 所有測試函式皆含真斷言")
