import importlib
import json
import re
import os
import sys
import runpy
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

BASE_PROMPT = (
    "你是閱卷委員兼考官，具備法學判斷能力。"
    "答案需以法理與法律案例題清楚區分，先建立比較基準：法條適用、事實比對與要件對照。"
    "處理法律題時，使用三段論（大前提與小前提）完成推理。"
    "不得反問、不得編造，並要直接輸出正文，不要輸出冗長前言與分析過程。"
    "此題以簡明語句回應。"
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_gatekeeper_entry(argv):
    """在 process 內執行 gatekeeper，不啟動子程序並保留輸出。"""
    old_argv = list(sys.argv)
    old_cwd = os.getcwd()
    output = StringIO()
    try:
        sys.argv = list(argv)
        with redirect_stdout(output), redirect_stderr(output):
            try:
                runpy.run_path(str(PROJECT_ROOT / "scripts" / "gatekeeper.py"), run_name="__main__")
            except SystemExit as exc:
                code = exc.code
            else:
                code = 0
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    return code, _extract_gatekeeper_json_output(output.getvalue()), output.getvalue()

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


def _extract_gatekeeper_json_output(stdout: str):
    match = re.search(r"^\{\s*\"passed\"\s*:", stdout, flags=re.MULTILINE)
    if not match:
        return None
    return json.loads(stdout[match.start():])


def _run_gatekeeper_cli(prompt: str, tmp_path: Path, extra_args=None):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    cmd = ["scripts/gatekeeper.py", str(prompt_file)]
    if extra_args is None:
        extra_args = ["--json"]
    if extra_args:
        cmd.extend(extra_args)

    return _run_gatekeeper_entry(cmd)


def test_semantic_check_hits_equivalent_expression(gatekeeper_module):
    # 命中同義語意詞時，應回傳 True（降級前提成立）。
    assert gatekeeper_module._semantic_check(
        "R04_NO_ANTI_FABRICATION",
        "禁止出現捏造，請嚴禁捏造與憑空推測。",
    ) is True


def test_semantic_check_fails_without_equivalent_or_context_mismatch(gatekeeper_module):
    # 未命中關鍵詞，或命中的是其他規則語意，皆應回傳 False（不降級）。
    assert gatekeeper_module._semantic_check(
        "R04_NO_ANTI_FABRICATION",
        "你是專家，請先建立比較基準。",
    ) is False
    assert gatekeeper_module._semantic_check(
        "R05_NO_EXPERT_ROLE",
        "答案不得捏造與杜絕捏造，否則將影響題目品質。",
    ) is False


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


def test_gatekeeper_direct_runs_clean_prompt_without_violations(gatekeeper_module):
    passed, violations = gatekeeper_module.run_gatekeeper(BASE_PROMPT)
    assert passed is True
    assert violations == []


def test_gatekeeper_direct_checks_length_bands(gatekeeper_module):
    short_prompt = "你是閱卷委員兼考官，先建立比較基準與法理區分，處理法律題時使用三段論，大前提為核心，不要反問，不要編造，直接輸出答案。"
    assert gatekeeper_module.run_gatekeeper(short_prompt)[0] is False

    warning_prompt = BASE_PROMPT + (" 比較基準、法條對照與大前提；" * 38)
    passed, violations = gatekeeper_module.run_gatekeeper(warning_prompt)
    assert passed is True
    _assert_violation(violations, "R01_LENGTH_WARNING", expected_present=True, expected_severity="warning")

    reject_prompt = BASE_PROMPT + (" 比較基準、法條對照與大前提；" * 39)
    passed, violations = gatekeeper_module.run_gatekeeper(reject_prompt)
    assert passed is False
    _assert_violation(violations, "R01_LENGTH_REJECT", expected_present=True, expected_severity="reject")


def test_gatekeeper_direct_blocks_unknown_rule_in_semantic_checker(gatekeeper_module):
    assert gatekeeper_module._semantic_check("R99_NO_SUCH_RULE", "只含一般字詞即可") is False


def test_run_gatekeeper_direct_allows_semantic_equivalent_for_expert_role(gatekeeper_module):
    prompt = BASE_PROMPT.replace("你是閱卷委員兼考官", "你是國考顧問")
    passed, violations = gatekeeper_module.run_gatekeeper(prompt)

    assert passed is True
    matched = _assert_violation(
        violations,
        "R05_NO_EXPERT_ROLE",
        expected_present=True,
        expected_severity="warning",
    )
    assert any("語意驗證通過：包含等價表達" in v["detail"] for v in matched)


def test_run_gatekeeper_direct_no_semantic_downgrade_when_not_equivalent(gatekeeper_module):
    prompt = (
        "你是題目顧問，"
        "這是完整規則示範文字：比較基準、比對、法理與三段論，"
        "請用大前提與小前提完成推論並直接輸出。"
    )
    passed, violations = gatekeeper_module.run_gatekeeper(prompt)
    assert passed is False

    _assert_violation(
        violations,
        "R05_NO_EXPERT_ROLE",
        expected_present=True,
        expected_severity="reject",
    )


def test_gatekeeper_direct_allows_semantic_suppressed_analysis_leak(gatekeeper_module):
    prompt = (
        "你是閱卷委員兼考官，具備法學判斷能力。"
        "先建立比較基準：法條適用、事實比對與要件對照。"
        "先分析題型後再回答，請先判斷題目類型。"
        "不得輸出審題，避免輸出題型分析步驟。"
        "答案需以法理與法律案例題清楚區分。不得反問、不得編造，並要直接輸出正文，無需輸出冗長前言與分析過程。"
        "本題以簡明語句回應。"
    )

    passed, violations = gatekeeper_module.run_gatekeeper(prompt)
    assert passed is True
    _assert_violation(violations, "R02_ANALYSIS_LEAK", expected_present=False)


def test_gatekeeper_direct_reports_rule6_to8_violations(gatekeeper_module):
    compare_prompt = (
        "你是閱卷委員兼考官，具備法學判斷能力。答案需清楚區分並直接輸出結論。"
        "請依序說明前提、論證與結論，不要反問、不做廢話延伸，"
        "並要直接輸出正文，不要輸出冗長前言與分析過程，需包含大前提與小前提，並不得編造。"
        "本題以簡明語句回應。"
    )
    passed, compare_violations = gatekeeper_module.run_gatekeeper(compare_prompt)
    assert passed is True
    _assert_violation(compare_violations, "R06_NO_COMPARE_CRITERIA", expected_present=True, expected_severity="warning")

    legal_prompt = (
        "你是閱卷委員兼考官，具備法學判斷能力。先建立比較基準：法條適用與要件對照。"
        "請條列解題步驟，聚焦條件與程序，避免提及理論與案例術語。"
        "不得反問、不得編造，並要直接輸出正文，不要輸出冗長前言與分析過程。"
        "本題以簡明語句回應。"
    )
    passed, legal_violations = gatekeeper_module.run_gatekeeper(legal_prompt)
    assert passed is True
    _assert_violation(legal_violations, "R07_NO_LEGAL_DIFFERENTIATION", expected_present=True, expected_severity="warning")

    output_prompt = BASE_PROMPT.replace("並要直接輸出正文，不要輸出冗長前言與分析過程。", "請補充簡短前言與分析，說明處理過程。")
    passed, output_violations = gatekeeper_module.run_gatekeeper(output_prompt)
    assert passed is True
    _assert_violation(output_violations, "R08_NO_DIRECT_OUTPUT", expected_present=True, expected_severity="warning")


def test_gatekeeper_direct_analysis_leak_violation(gatekeeper_module):
    prompt = BASE_PROMPT.replace("並要直接輸出正文，不要輸出冗長前言與分析過程。", "")
    prompt += "先分析題型後再進行回答。"
    passed, violations = gatekeeper_module.run_gatekeeper(prompt)
    assert passed is False
    _assert_violation(violations, "R02_ANALYSIS_LEAK", expected_present=True, expected_severity="reject")


def test_gatekeeper_entrypoint_success_run_with_json_in_process(monkeypatch, tmp_path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(BASE_PROMPT, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["scripts/gatekeeper.py", str(prompt_file), "--json"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "gatekeeper.py"), run_name="__main__")

    assert exc_info.value.code == 0


def test_gatekeeper_entrypoint_reject_without_json_in_process(monkeypatch, tmp_path):
    prompt = BASE_PROMPT.replace("你是閱卷委員兼考官，", "")
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["scripts/gatekeeper.py", str(prompt_file)])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "gatekeeper.py"), run_name="__main__")

    assert exc_info.value.code == 1


def test_gatekeeper_entrypoint_invalid_args_in_process(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["scripts/gatekeeper.py"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "gatekeeper.py"), run_name="__main__")

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "用法: python3 scripts/gatekeeper.py <prompt_file>" in captured.out


def test_gatekeeper_entrypoint_missing_file_in_process(monkeypatch, tmp_path, capsys):
    missing_file = tmp_path / "missing_prompt.md"
    monkeypatch.setattr(sys, "argv", ["scripts/gatekeeper.py", str(missing_file)])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "gatekeeper.py"), run_name="__main__")

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert f"[錯誤] 找不到檔案: {missing_file}" in captured.out


def test_gatekeeper_cli_output_contract_and_human_readable_summary(tmp_path):
    code, payload, stdout = _run_gatekeeper_cli(BASE_PROMPT, tmp_path, extra_args=["--json"])

    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    assert set(payload.keys()) == {"passed", "violations", "char_count"}
    assert payload["char_count"] == len(BASE_PROMPT)
    assert payload["violations"] == []
    assert "結果: ✅ 通過" in stdout
    assert "全部通過！無任何違規" in stdout


def test_gatekeeper_cli_reports_json_on_reject_with_warning_mix(tmp_path):
    prompt = (
        BASE_PROMPT.replace("你是閱卷委員兼考官，", "")
        + "先分析題型，先判斷題目類型後再回答。"
    )
    code, payload, stdout = _run_gatekeeper_cli(prompt, tmp_path, extra_args=["--json"])

    assert code == 1
    assert payload is not None
    assert payload["passed"] is False

    matched = _assert_violation(payload["violations"], "R02_ANALYSIS_LEAK", expected_present=True, expect_fragment="先分析題型")
    assert not payload["passed"]
    assert any("❌ [R02_ANALYSIS_LEAK]" in line for line in stdout.splitlines())
    assert any(v["rule"] == "R05_NO_EXPERT_ROLE" and v["severity"] == "reject" for v in payload["violations"])
    assert any("缺乏國考專家角色設定宣告。" in v["detail"] for v in payload["violations"])


def test_gatekeeper_cli_accepts_warning_only_output(tmp_path):
    warning_prompt = BASE_PROMPT + (" 比較基準、法條對照與大前提；" * 38)
    code, payload, stdout = _run_gatekeeper_cli(warning_prompt, tmp_path, extra_args=["--json"])

    assert code == 0
    assert payload["passed"] is True
    _assert_violation(
        payload["violations"],
        "R01_LENGTH_WARNING",
        expected_present=True,
        expected_severity="warning",
        expect_fragment="超過 550 字警告線",
    )
    assert "⚠️ [R01_LENGTH_WARNING]" in stdout


def test_gatekeeper_cli_invalid_argument_errored(tmp_path):
    code, _, stdout = _run_gatekeeper_entry(["scripts/gatekeeper.py"])
    assert code == 1
    assert "用法: python3 scripts/gatekeeper.py <prompt_file>" in stdout


def test_gatekeeper_cli_missing_prompt_file_prints_error(tmp_path):
    missing_file = tmp_path / "not_exists.md"
    code, _, stdout = _run_gatekeeper_entry([
        "scripts/gatekeeper.py",
        str(missing_file),
    ])
    assert code == 1
    assert f"[錯誤] 找不到檔案: {missing_file}" in stdout
