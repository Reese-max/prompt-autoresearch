import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

BASE_PROMPT = (
    "你是閱卷委員兼考官，具備法學判斷能力。"
    "答案需以法理與法律案例題清楚區分，先建立比較基準：法條適用、事實比對與要件對照。"
    "處理法律題時，使用三段論（大前提與小前提）完成推理。"
    "不得反問、不得編造，並要直接輸出正文，不要輸出冗長前言與分析過程。"
    "此題以簡明語句回應。"
)

RULE_TRIGGER_CASES = (
    ("R01_LENGTH_REJECT", "長度超過700字上限（Reject）", BASE_PROMPT + "補充完整性說明，請保留每步判斷與推理細節；" * 50, False, 1, True, "reject", "超過 700 字硬性上限"),
    ("R01_LENGTH_REJECT", "長度不超標（No trigger）", BASE_PROMPT, True, 0, False, None, None),
    ("R02_ANALYSIS_LEAK", "要求先分析題型（Reject）", BASE_PROMPT + "請先分析題型後再進行回答。", False, 1, True, "reject", "包含「先分析題型」"),
    ("R02_ANALYSIS_LEAK", "未要求先分析題型（No trigger）", BASE_PROMPT, True, 0, False, None, None),
    ("R03_NO_ANTI_QUESTION", "缺少反問禁止（Warning）", BASE_PROMPT.replace("不得反問、", ""), True, 0, True, "warning", "未設定反問禁止語句"),
    ("R03_NO_ANTI_QUESTION", "有明確反問禁止（No trigger）", BASE_PROMPT, True, 0, False, None, None),
    ("R04_NO_ANTI_FABRICATION", "缺少防編造宣告（Reject）", BASE_PROMPT.replace("不得編造，", ""), False, 1, True, "reject", "未設定法條/判決/年份/統計的防編造宣告"),
    ("R04_NO_ANTI_FABRICATION", "有明確防編造宣告（No trigger）", BASE_PROMPT, True, 0, False, None, None),
    ("R05_NO_EXPERT_ROLE", "缺少國考專家角色（Reject）", BASE_PROMPT.replace("你是閱卷委員兼考官，", "你是題目檢核者，"), False, 1, True, "reject", "缺乏國考專家角色設定宣告"),
    ("R05_NO_EXPERT_ROLE", "有國考專家角色（No trigger）", BASE_PROMPT, True, 0, False, None, None),
    ("R06_NO_COMPARE_CRITERIA", "缺少比較基準（Warning）", BASE_PROMPT.replace("先建立比較基準：法條適用、事實比對與要件對照。", "先列出答案重點。"), True, 0, True, "warning", "未提及比較題需建立比較基準"),
    ("R06_NO_COMPARE_CRITERIA", "有比較基準（No trigger）", BASE_PROMPT, True, 0, False, None, None),
    ("R07_NO_LEGAL_DIFFERENTIATION", "缺少法理/案例分流（Warning）", BASE_PROMPT.replace(
        "答案需以法理與法律案例題清楚區分，先建立比較基準：法條適用、事實比對與要件對照。處理法律題時，使用三段論（大前提與小前提）完成推理。",  # noqa: E501
        "比較題時先列出答題重點與作答順序，並補充必要的法學判斷步驟與解題節奏，另外補充條件判斷與要件對照。",
    ), True, 0, True, "warning", "未區分法律法理題與法律案例題的作答策略"),
    ("R07_NO_LEGAL_DIFFERENTIATION", "有法理/案例分流（No trigger）", BASE_PROMPT, True, 0, False, None, None),
    ("R08_NO_DIRECT_OUTPUT", "缺少直接輸出要求（Warning）", BASE_PROMPT.replace("並要直接輸出正文，不要輸出冗長前言與分析過程。", "請補充每一步理由，並先行說明背景。"), True, 0, True, "warning", "未要求模型直接輸出答案正文"),
    ("R08_NO_DIRECT_OUTPUT", "有直接輸出要求（No trigger）", BASE_PROMPT, True, 0, False, None, None),
)


SEMANTIC_EQUIVALENT_CASES = (
    (
        "R04_NO_ANTI_FABRICATION",
        "語意等價降級：不可捏造（Reject->Warning）",
        BASE_PROMPT.replace("不得反問、", "不必反問、").replace("不得編造，", "避免編造，") + "另外補充「不可捏造」關鍵詞。",
        True,
        0,
        "warning",
    ),
    (
        "R04_NO_ANTI_FABRICATION",
        "語意等價降級失敗：保持缺漏",
        BASE_PROMPT.replace("不得反問、", "不必反問、").replace("不得編造，", "避免編造，") + "此外再加上事實要件逐步驗證。",  # 語意等價不足
        False,
        1,
        "reject",
    ),
    (
        "R05_NO_EXPERT_ROLE",
        "語意等價降級：國考顧問（Reject->Warning）",
        "你是國考顧問，" + BASE_PROMPT.replace("你是閱卷委員兼考官，", ""),
        True,
        0,
        "warning",
    ),
    (
        "R05_NO_EXPERT_ROLE",
        "語意等價降級失敗：保持缺漏",
        "你是題目顧問，" + BASE_PROMPT.replace("你是閱卷委員兼考官，", ""),
        False,
        1,
        "reject",
    ),
)


@pytest.fixture
def gatekeeper_module(monkeypatch, tmp_path: Path):
    """以隔離的臨時目錄載入 scripts.gatekeeper，避免 import 時的 os.chdir 汙染。"""
    project_root = Path(__file__).resolve().parents[1]

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(project_root))

    # 清除 cache，確保每次測試都會重新執行匯入邏輯
    sys.modules.pop("scripts.gatekeeper", None)
    importlib.invalidate_caches()
    gatekeeper = importlib.import_module("scripts.gatekeeper")
    # 模組匯入會嘗試 os.chdir 到專案根目錄，先再恢復到暫存路徑，避免污染下一步測試。
    monkeypatch.chdir(tmp_path)

    yield gatekeeper

    assert Path.cwd() == tmp_path


def _run_gatekeeper_cli(prompt: str, tmp_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts" / "gatekeeper.py"),
            str(prompt_file),
            "--json",
        ],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    payload = None
    if result.returncode in (0, 1):
        match = re.search(r"^\{\s*\"passed\"\s*:", result.stdout, flags=re.MULTILINE)
        if match:
            payload = json.loads(result.stdout[match.start():])

    return result.returncode, payload, result.stdout


def _assert_violation(violations, rule, expected_present=True, *, expected_severity=None, expect_fragment=None):
    matched = [v for v in violations if v["rule"] == rule]
    if expected_present:
        assert matched, f"應該出現 {rule} 違規"
        if expected_severity is not None:
            assert any(v["severity"] == expected_severity for v in matched), (
                f"{rule} 應為 {expected_severity}"
            )
        if expect_fragment is not None:
            assert any(expect_fragment in v["detail"] for v in matched), (
                f"{rule} 違規訊息應包含：{expect_fragment}"
            )
        return matched
    else:
        assert not matched, f"{rule} 應為不觸發"


def test_gatekeeper_import_side_effect_is_isolated_by_tmp_cwd(gatekeeper_module, tmp_path):
    expected_root = Path(__file__).resolve().parents[1]
    assert Path.cwd() == tmp_path
    assert Path.cwd() != expected_root

    # scripts.gatekeeper 在匯入時會 os.chdir 到專案根目錄
    assert gatekeeper_module.__file__.startswith(str(expected_root))
    assert Path(gatekeeper_module.__file__).name == "gatekeeper.py"
    assert Path(gatekeeper_module.__file__).parent.name == "scripts"

    passed, _ = gatekeeper_module.run_gatekeeper(BASE_PROMPT)
    assert isinstance(passed, bool)


@pytest.mark.parametrize(
    (
        "rule_id",
        "case_label",
        "prompt",
        "expected_passed",
        "expected_return_code",
        "expect_violation",
        "expected_severity",
        "expect_fragment",
    ),
    RULE_TRIGGER_CASES,
)
def test_gatekeeper_hard_rules_matrix(
    rule_id,
    case_label,
    prompt,
    expected_passed,
    expected_return_code,
    expect_violation,
    expected_severity,
    expect_fragment,
    tmp_path,
):
    """8 條硬規則：逐條列出觸發 / 不觸發樣例。"""
    code, payload, _ = _run_gatekeeper_cli(prompt, tmp_path)
    assert payload is not None
    assert code == expected_return_code
    assert payload["passed"] == expected_passed

    if expect_violation:
        _assert_violation(
            payload["violations"],
            rule_id,
            expected_present=True,
            expected_severity=expected_severity,
            expect_fragment=expect_fragment,
        )
        matched = [v for v in payload["violations"] if v["rule"] == rule_id]
        # 不同矩陣列的 case_label 僅用於可讀性註解
        _ = case_label, matched
    else:
        _assert_violation(payload["violations"], rule_id, expected_present=False)


@pytest.mark.parametrize(
    (
        "rule_id",
        "case_label",
        "prompt",
        "expected_passed",
        "expected_return_code",
        "expected_severity",
    ),
    SEMANTIC_EQUIVALENT_CASES,
)
def test_gatekeeper_semantic_equivalent_matrix(
    rule_id,
    case_label,
    prompt,
    expected_passed,
    expected_return_code,
    expected_severity,
    tmp_path,
):
    """
    語意等價降級邏輯：同一規則提供等價改寫樣例與非等價失敗樣例各一筆。
    """
    code, payload, _ = _run_gatekeeper_cli(prompt, tmp_path)
    assert payload is not None
    assert code == expected_return_code
    assert payload["passed"] == expected_passed

    matches = _assert_violation(
        payload["violations"],
        rule_id,
        expected_present=True,
        expected_severity=expected_severity,
    )

    # 僅在降級成功時，detail 會加上「語意驗證通過」標記
    has_semantic_tag = any("語意驗證通過：包含等價表達" in v["detail"] for v in matches)
    if expected_severity == "warning" and expected_passed:
        assert has_semantic_tag is True
    if expected_severity == "reject":
        assert has_semantic_tag is False

    # case_label 僅用於錯誤訊息可讀性（避免未使用參數警告）
    assert isinstance(case_label, str)
