import importlib
import json
import re
import subprocess
import sys
import pytest
from pathlib import Path

BASE_PROMPT = (
    "你是閱卷委員兼考官，具備法學判斷能力。"
    "答案需以法理與法律案例題清楚區分，先建立比較基準：法條適用、事實比對與要件對照。"
    "處理法律題時，使用三段論（大前提與小前提）完成推理。"
    "不得反問、不得編造，並要直接輸出正文，不要輸出冗長前言與分析過程。"
    "此題以簡明語句回應。"
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

    prompt = (
        "你是專家，依法理與法律案例作答，請直接輸出正文；不得反問，不得編造。"
        "比較基準請明確列出，並依規則判斷，這段提示詞刻意補足字數以符合最小長度要求，"
        "內容聚焦於考試閱卷與評分要點，避免過短，同時避免輸出冗長前言與分析。"
    )
    passed, _ = gatekeeper_module.run_gatekeeper(prompt)
    assert isinstance(passed, bool)


def test_gatekeeper_hard_rule_01_length_reject_and_pass(tmp_path):
    long_prompt = (
        BASE_PROMPT + "補充完整性說明，請保留每步判斷與推理細節；" * 50
    )
    short_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(long_prompt, tmp_path)
    assert code == 1
    assert payload is not None
    assert payload["passed"] is False
    _assert_violation(
        payload["violations"],
        "R01_LENGTH_REJECT",
        expected_present=True,
        expected_severity="reject",
        expect_fragment="超過 700 字硬性上限",
    )

    code, payload, _ = _run_gatekeeper_cli(short_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R01_LENGTH_REJECT", expected_present=False)
    _assert_violation(payload["violations"], "R01_LENGTH_TOO_SHORT", expected_present=False)


def test_gatekeeper_hard_rule_02_analysis_leak_triggers_and_no_trigger(tmp_path):
    trigger_prompt = BASE_PROMPT + "請先分析題型後再進行答題。"
    no_trigger_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(trigger_prompt, tmp_path)
    assert code == 1
    assert payload is not None
    assert payload["passed"] is False
    _assert_violation(
        payload["violations"],
        "R02_ANALYSIS_LEAK",
        expected_present=True,
        expected_severity="reject",
        expect_fragment="包含「先分析題型」",
    )

    code, payload, _ = _run_gatekeeper_cli(no_trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R02_ANALYSIS_LEAK", expected_present=False)


def test_gatekeeper_hard_rule_03_anti_question_warning_and_no_trigger(tmp_path):
    trigger_prompt = BASE_PROMPT.replace("不得反問、", "")
    no_trigger_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(
        payload["violations"],
        "R03_NO_ANTI_QUESTION",
        expected_present=True,
        expected_severity="warning",
        expect_fragment="未設定反問禁止語句",
    )

    code, payload, _ = _run_gatekeeper_cli(no_trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R03_NO_ANTI_QUESTION", expected_present=False)


def test_gatekeeper_hard_rule_04_anti_fabrication_reject_and_no_trigger(tmp_path):
    trigger_prompt = BASE_PROMPT.replace("、不得編造", "")
    no_trigger_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(trigger_prompt, tmp_path)
    assert code == 1
    assert payload is not None
    assert payload["passed"] is False
    _assert_violation(
        payload["violations"],
        "R04_NO_ANTI_FABRICATION",
        expected_present=True,
        expected_severity="reject",
        expect_fragment="未設定法條/判決/年份/統計的防編造宣告",
    )

    code, payload, _ = _run_gatekeeper_cli(no_trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R04_NO_ANTI_FABRICATION", expected_present=False)


def test_gatekeeper_hard_rule_05_expert_role_reject_and_no_trigger(tmp_path):
    trigger_prompt = BASE_PROMPT.replace("你是閱卷委員兼考官，", "")
    no_trigger_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(trigger_prompt, tmp_path)
    assert code == 1
    assert payload is not None
    assert payload["passed"] is False
    _assert_violation(
        payload["violations"],
        "R05_NO_EXPERT_ROLE",
        expected_present=True,
        expected_severity="reject",
        expect_fragment="缺乏國考專家角色設定宣告",
    )

    code, payload, _ = _run_gatekeeper_cli(no_trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R05_NO_EXPERT_ROLE", expected_present=False)


def test_gatekeeper_hard_rule_06_compare_criteria_warning_and_no_trigger(tmp_path):
    trigger_prompt = BASE_PROMPT.replace("先建立比較基準：法條適用、事實比對與要件對照。", "")
    no_trigger_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(
        payload["violations"],
        "R06_NO_COMPARE_CRITERIA",
        expected_present=True,
        expected_severity="warning",
        expect_fragment="未提及比較題需建立比較基準",
    )

    code, payload, _ = _run_gatekeeper_cli(no_trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R06_NO_COMPARE_CRITERIA", expected_present=False)


def test_gatekeeper_hard_rule_07_legal_differentiation_warning_and_no_trigger(tmp_path):
    trigger_prompt = (
        "你是閱卷委員兼考官，具備法學判斷能力。"
        "請依題目需求直接回答，不要輸出冗長前言與分析過程。"
        "比較基準請以法條適用、事實比對與要件對照進行整理。"
        "不得反問、不得編造，並要直接輸出正文。"
        "此題以簡明語句回應。"
        "為避免過短，補上必要示範句與判斷條件。"
    )
    no_trigger_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(
        payload["violations"],
        "R07_NO_LEGAL_DIFFERENTIATION",
        expected_present=True,
        expected_severity="warning",
        expect_fragment="未區分法律法理題與法律案例題的作答策略",
    )

    code, payload, _ = _run_gatekeeper_cli(no_trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R07_NO_LEGAL_DIFFERENTIATION", expected_present=False)


def test_gatekeeper_hard_rule_08_direct_output_warning_and_no_trigger(tmp_path):
    trigger_prompt = BASE_PROMPT.replace("並要直接輸出正文，", "").replace(
        "不要輸出冗長前言與分析過程。",
        "請避免冗長前言與分析過程。",
    )
    no_trigger_prompt = BASE_PROMPT

    code, payload, _ = _run_gatekeeper_cli(trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(
        payload["violations"],
        "R08_NO_DIRECT_OUTPUT",
        expected_present=True,
        expected_severity="warning",
        expect_fragment="未要求模型直接輸出答案正文",
    )

    code, payload, _ = _run_gatekeeper_cli(no_trigger_prompt, tmp_path)
    assert code == 0
    assert payload is not None
    assert payload["passed"] is True
    _assert_violation(payload["violations"], "R08_NO_DIRECT_OUTPUT", expected_present=False)


@pytest.mark.parametrize(
    ("role_phrase", "expected_passed", "expected_severity"),
    [
        ("國考顧問", True, "warning"),      # 同義改寫：應正確降級
        ("國考、顧問", False, "reject"),   # 標點插入：未命中等價關鍵詞，應保留 Reject
        ("顧問國考", False, "reject"),     # 詞序微調：未命中等價關鍵詞，應保留 Reject
    ],
)
def test_gatekeeper_semantic_equivalent_layer_covers_rewrite_punctuation_order(role_phrase, expected_passed, expected_severity, tmp_path):
    prompt = BASE_PROMPT.replace("你是閱卷委員兼考官，", f"你是{role_phrase}，")

    code, payload, _ = _run_gatekeeper_cli(prompt, tmp_path)
    assert payload is not None
    assert payload["passed"] is expected_passed
    assert code == (0 if expected_passed else 1)

    _assert_violation(
        payload["violations"],
        "R05_NO_EXPERT_ROLE",
        expected_present=True,
        expected_severity=expected_severity,
    )

    target = [v for v in payload["violations"] if v["rule"] == "R05_NO_EXPERT_ROLE"][0]
    has_semantic_pass = "語意驗證通過：包含等價表達" in target["detail"]
    if expected_passed:
        assert has_semantic_pass is True
    else:
        assert has_semantic_pass is False
