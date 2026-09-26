# -*- coding: utf-8 -*-
"""tests/test_best_version_evidence_contract.py — 最佳版本證據契約回歸。

以 ``schemas/best_version_evidence_report.schema.json`` 為唯一權威的版本化
證據契約，鎖定 producer／consumer 不得各自漂移：

- 最小完整證據夾具（``build_minimal_complete_evidence``，即本契約的文件化
  範例）必須產生 ``decision.status == "valid"``、可採用的報告，且對
  canonical schema 的 ``schema_validation`` 零誤差。
- 從有效報告中移除任一 required 欄位、或給予不相容型別時，
  ``schema_validation_errors`` 必須點名缺失／不相容的欄位路徑。
- 從完整證據移除必要欄位 → 型別化 ``INCOMPLETE_EVIDENCE``；
  使被引用證據檔不可讀 → 型別化失敗，不得逸出未捕捉例外。
"""
import copy
import json
import os
import sys
import types

import pytest

import scripts.best_version_report as bvr


CANONICAL_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    bvr.SCHEMA_REL_PATH,
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """把所有報告輸入路徑指到 tmp_path，隔離真實 repo。"""
    (tmp_path / "prompts" / "champions").mkdir(parents=True)
    (tmp_path / "prompts" / "candidates").mkdir(parents=True)
    (tmp_path / "runs").mkdir()
    monkeypatch.setattr(bvr, "ROOT", str(tmp_path))
    monkeypatch.setattr(
        bvr, "BASELINE_META_PATH", str(tmp_path / "prompts" / "baseline.meta.json")
    )
    monkeypatch.setattr(bvr, "CHAMPIONS_DIR", str(tmp_path / "prompts" / "champions"))
    monkeypatch.setattr(bvr, "CANDIDATES_DIR", str(tmp_path / "prompts" / "candidates"))
    monkeypatch.setattr(bvr, "EVOLUTION_LOG_PATH", str(tmp_path / "evolution_log.jsonl"))
    monkeypatch.setattr(bvr, "CONFIG_PATH", str(tmp_path / "config.yaml"))
    monkeypatch.setattr(bvr, "RUNS_DIR", str(tmp_path / "runs"))
    return tmp_path


def build_minimal_complete_evidence(tmp_path):
    """契約要求的最小完整證據集合。

    每一項皆為完整性閘門所需的關鍵證據：
    - ``prompts/baseline.md``：可讀的 winner 提示詞內容。
    - ``prompts/baseline.meta.json``：``prompt_hash``（提示詞 sha256）、
      ``dev_avg``／``holdout_avg`` 可驗證分數與量測基準。
    - ``prompts/candidates/<name>.md`` + ``<name>.scorecard.json``：
      有效比較對象／淘汰依據，含 ``candidate_path``、``candidate_hash``、
      ``final_decision`` 與各資料集分數。
    - ``config.yaml``：巢狀 YAML 的重現設定（``thresholds`` 為非空 dict）。
    - ``evolution_log.jsonl``：至少一個完整 session（start + stop）。
    """
    baseline_prompt = tmp_path / "prompts" / "baseline.md"
    baseline_prompt.write_text("最小完整證據的 winner 提示詞\n", encoding="utf-8")
    baseline_meta = {
        "prompt_path": "prompts/baseline.md",
        "prompt_hash": bvr.sha256_file(str(baseline_prompt)),
        "dev_avg": 88.5,
        "holdout_avg": 87.0,
        "smoke_avg": 90.0,
        "dev_run": "runs/dev_run_001",
        "holdout_run": "runs/holdout_run_001",
    }
    (tmp_path / "prompts" / "baseline.meta.json").write_text(
        json.dumps(baseline_meta, ensure_ascii=False), encoding="utf-8"
    )

    candidate_prompt = tmp_path / "prompts" / "candidates" / "cand_1.md"
    candidate_prompt.write_text("最小完整證據的候選提示詞\n", encoding="utf-8")
    scorecard = {
        "candidate_path": "prompts/candidates/cand_1.md",
        "candidate_hash": bvr.sha256_file(str(candidate_prompt)),
        "status": "completed",
        "final_decision": "ACCEPT",
        "smoke": {"score": 90.0, "passed": True},
        "dev": {"score": 92.0},
        "holdout": {"score": 91.0},
    }
    (tmp_path / "prompts" / "candidates" / "cand_1.scorecard.json").write_text(
        json.dumps(scorecard, ensure_ascii=False), encoding="utf-8"
    )

    (tmp_path / "config.yaml").write_text(
        "thresholds:\n  dev_min_improvement: 2.0\n", encoding="utf-8"
    )
    with open(tmp_path / "evolution_log.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(
            {"event": "start", "timestamp": "2026-01-01 00:00:00", "args": {}},
            ensure_ascii=False,
        ) + "\n")
        f.write(json.dumps(
            {"event": "stop", "timestamp": "2026-01-01 00:01:00"},
            ensure_ascii=False,
        ) + "\n")
    return baseline_meta


def test_minimal_complete_evidence_fixture_is_valid_and_schema_clean(sandbox):
    """最小完整證據夾具 → VALID 可採用報告，且完全符合 canonical schema。"""
    build_minimal_complete_evidence(sandbox)

    data = bvr.build_structured_report()

    assert data["decision"]["status"] == "valid"
    assert data["decision"]["code"] == "VALID"
    assert data["decision"]["best_candidate_id"]
    assert data["winner"]["decision"] == "ADOPT"
    assert data["evidence_integrity"]["valid"] is True
    assert data["evidence_integrity"]["errors"] == []
    assert data["schema_validation"]["valid"] is True
    assert data["schema_validation"]["errors"] == []
    canonical_schema = bvr.load_json(CANONICAL_SCHEMA_PATH, {})
    assert bvr.schema_validation_errors(data, schema=canonical_schema) == []


def test_canonical_schema_pins_version_and_report_type(sandbox):
    """canonical schema 必須要求 schema_version／report_type，報告必須如實填寫。"""
    assert os.path.isfile(CANONICAL_SCHEMA_PATH)
    schema = bvr.load_json(CANONICAL_SCHEMA_PATH, {})
    assert "schema_version" in schema["required"]
    assert "report_type" in schema["required"]
    assert schema["properties"]["report_type"]["const"] == "best_version_evidence"

    build_minimal_complete_evidence(sandbox)
    data = bvr.build_structured_report()
    assert data["schema_version"] == "1.0.0"
    assert data["report_type"] == "best_version_evidence"
    assert data["$schema"] == bvr.SCHEMA_REL_PATH


@pytest.mark.parametrize(
    "field",
    [
        "schema_version",
        "report_type",
        "generated_at",
        "decision",
        "winner",
        "quality",
        "candidate_comparison",
        "reproduction",
        "execution",
        "evidence",
        "delivery_consistency",
        "schema_validation",
    ],
)
def test_schema_drift_names_missing_required_field(sandbox, field):
    """producer 漏掉任一 required 欄位時，診斷必須點名該欄位路徑。"""
    build_minimal_complete_evidence(sandbox)
    data = bvr.build_structured_report()
    drifted = copy.deepcopy(data)
    drifted.pop(field)

    canonical_schema = bvr.load_json(CANONICAL_SCHEMA_PATH, {})
    errors = bvr.schema_validation_errors(drifted, schema=canonical_schema)

    assert errors, f"移除 {field} 後必須產生 schema 誤差"
    assert any(f"$.{field}" in error for error in errors), (
        f"診斷必須點名 $.{field}，實際：{errors}"
    )


def test_schema_drift_names_incompatible_field_value(sandbox):
    """producer 給出不相容欄位值時，診斷必須點名該欄位路徑。"""
    build_minimal_complete_evidence(sandbox)
    data = bvr.build_structured_report()
    drifted = copy.deepcopy(data)
    drifted["decision"]["status"] = "unknown_status"

    canonical_schema = bvr.load_json(CANONICAL_SCHEMA_PATH, {})
    errors = bvr.schema_validation_errors(drifted, schema=canonical_schema)

    assert errors
    assert any("$.decision.status" in error for error in errors), (
        f"診斷必須點名 $.decision.status，實際：{errors}"
    )


class _FakeValidationError:
    """模擬 jsonschema.ValidationError 所需欄位的最小替身。"""

    def __init__(self, absolute_path, message, validator="", validator_value=None, instance=None):
        self.absolute_path = absolute_path
        self.message = message
        self.validator = validator
        self.validator_value = validator_value or []
        self.instance = instance or {}


def test_schema_drift_diagnostic_format_matches_jsonschema_path(monkeypatch):
    """jsonschema 存在與否，診斷路徑格式必須一致（皆為 $.dotted.path）。"""

    class _FakeValidator:
        def __init__(self, _schema):
            pass

        def iter_errors(self, _report):
            return iter([
                _FakeValidationError(
                    (), "'decision' is a required property",
                    validator="required",
                    validator_value=["decision", "winner"],
                    instance={"winner": {}},
                ),
                _FakeValidationError(
                    ("decision", "status"), "'x' is not one of ['valid']",
                    validator="enum",
                ),
                _FakeValidationError((), "root type mismatch"),
            ])

    monkeypatch.setitem(
        sys.modules,
        "jsonschema",
        types.SimpleNamespace(Draft202012Validator=_FakeValidator),
    )

    errors = bvr.schema_validation_errors({}, schema={"type": "object"})

    assert "$.decision: 'decision' is a required property" in errors
    assert "$.decision.status: 'x' is not one of ['valid']" in errors
    assert "$: root type mismatch" in errors


def test_schema_drift_does_not_mislabel_multiple_missing_required_fields(monkeypatch):
    """同一 required 清單缺漏兩項時，每個錯誤只標示自己的欄位。"""

    class _FakeValidator:
        def __init__(self, _schema):
            pass

        def iter_errors(self, _report):
            return iter([
                _FakeValidationError(
                    (), "'decision' is a required property",
                    validator="required",
                    validator_value=["decision", "winner"],
                    instance={},
                ),
                _FakeValidationError(
                    (), "'winner' is a required property",
                    validator="required",
                    validator_value=["decision", "winner"],
                    instance={},
                ),
            ])

    monkeypatch.setitem(
        sys.modules,
        "jsonschema",
        types.SimpleNamespace(Draft202012Validator=_FakeValidator),
    )

    assert bvr.schema_validation_errors({}, schema={"type": "object"}) == [
        "$.decision: 'decision' is a required property",
        "$.winner: 'winner' is a required property",
    ]


def test_removing_required_evidence_field_fails_closed(sandbox):
    """移除完整證據的必要欄位 → 型別化 INCOMPLETE_EVIDENCE，不得宣稱最佳。"""
    build_minimal_complete_evidence(sandbox)
    meta_path = sandbox / "prompts" / "baseline.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.pop("prompt_hash")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    data = bvr.build_structured_report()

    assert data["decision"]["status"] == "inconclusive"
    assert data["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert data["decision"]["best_candidate_id"] is None
    assert data["winner"]["decision"] == "INCOMPLETE_EVIDENCE"
    assert data["evidence_integrity"]["errors"]


@pytest.mark.parametrize(
    "target",
    ["prompts/baseline.md", "prompts/candidates/cand_1.md", "config.yaml"],
)
def test_unreadable_evidence_file_fails_closed_without_exception(
    sandbox, monkeypatch, target
):
    """任一被引用證據檔不可讀 → 型別化失敗，不得逸出 PermissionError。"""
    build_minimal_complete_evidence(sandbox)
    real_open = open

    def unreadable_open(path, *args, **kwargs):
        if str(path).replace("\\", "/").endswith("/" + target):
            raise PermissionError("evidence is unreadable")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", unreadable_open)

    data = bvr.build_structured_report()

    assert data["decision"]["status"] == "inconclusive"
    assert data["decision"]["code"] == "INCOMPLETE_EVIDENCE"
    assert data["decision"]["best_candidate_id"] is None


# ---------- load_config 契約：任何失敗皆為型別化 fail-closed ----------


def test_load_config_malformed_yaml_fails_closed(sandbox):
    """config.yaml 語法錯誤 → {}，不得逸出 YAMLError。"""
    (sandbox / "config.yaml").write_text("a: [unclosed\n  bad: : :\n", encoding="utf-8")
    assert bvr.load_config() == {}


def test_load_config_non_dict_yaml_fails_closed(sandbox):
    """config.yaml 解析出非 dict（如 list）→ {}，不得讓下游 .get 崩潰。"""
    (sandbox / "config.yaml").write_text("- a\n- b\n", encoding="utf-8")
    assert bvr.load_config() == {}


def test_load_config_without_pyyaml_uses_flat_fallback(sandbox, monkeypatch):
    """無 PyYAML 時退回扁平解析；巢狀區段缺漏由閘門 fail-closed 兜住。"""
    (sandbox / "config.yaml").write_text(
        "flat_key: value\n# comment\n\nnested:\n  inner: 1\n", encoding="utf-8"
    )
    monkeypatch.setitem(sys.modules, "yaml", None)
    config = bvr.load_config()
    assert config["flat_key"] == "value"
    assert config["inner"] == "1"


def test_load_config_without_pyyaml_unreadable_fails_closed(sandbox, monkeypatch):
    """無 PyYAML 且 config.yaml 不可讀 → {}，不得逸出 PermissionError。"""
    (sandbox / "config.yaml").write_text("key: value\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)
    real_open = open

    def unreadable_open(path, *args, **kwargs):
        if str(path).replace("\\", "/").endswith("/config.yaml"):
            raise PermissionError("evidence is unreadable")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", unreadable_open)
    assert bvr.load_config() == {}


def test_load_config_without_pyyaml_fallback_error_fails_closed(sandbox, monkeypatch):
    """無 PyYAML 且後備解析器自身拋錯 → {}，不得逸出任何例外。"""
    (sandbox / "config.yaml").write_text("key: value\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "yaml", None)

    def broken_parse(_path):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(bvr, "_parse_config_simple", broken_parse)
    assert bvr.load_config() == {}
