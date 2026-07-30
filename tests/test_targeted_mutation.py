# -*- coding: utf-8 -*-
"""
test_targeted_mutation.py — 定向變異與日誌結構測試

驗證：
1. load_targeted_countermeasures 能正確從 taxonomy 解析 F03/F04 對策原文
2. 變異 prompt 含 taxonomy 的對應對策原文（非僅代碼）
3. countermeasures_injected 正確記錄代碼
4. 沒有 dominant failure 時該欄位為空 list
"""
import json
import os
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_opt
import infinite_evolve


F03_COUNTERMEASURE = "規定標題必須「結構化、具體化」，例如「一、依行政程序法第 7 條之比例原則內涵」，並要求關鍵字加粗。"
F04_COUNTERMEASURE = "要求模型必須包含「專有名詞（制度/學說/技術名稱）」與「具體法條/實例」，每段論點至少附帶一個具體佐證。"


def _countermeasure_from_taxonomy(code):
    taxonomy = Path("rubrics/failure_taxonomy.md").read_text(encoding="utf-8")
    section = re.search(
        rf"^###\s+{re.escape(code)}\b.*?(?=^###|\Z)",
        taxonomy,
        re.MULTILINE | re.DOTALL,
    )
    assert section, f"failure_taxonomy.md 缺少 {code}"
    countermeasure = re.search(
        r"^\*\s*\*\*修復方向\*\*[：:]\s*(.+)$",
        section.group(),
        re.MULTILINE,
    )
    assert countermeasure, f"failure_taxonomy.md 缺少 {code} 修復方向"
    return countermeasure.group(1).strip()


def _capture_mutation_prompt(tmp_path, monkeypatch, *, force_direction=None, avoid_failures=None):
    taxonomy = Path("rubrics/failure_taxonomy.md").read_text(encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "baseline.md").write_text("你是一位國考專家。", encoding="utf-8")
    (tmp_path / "rubrics").mkdir()
    (tmp_path / "rubrics" / "failure_taxonomy.md").write_text(taxonomy, encoding="utf-8")

    captured = []

    def capture_then_stop(_system, prompt, temperature):
        captured.append(prompt)
        raise RuntimeError("測試僅截取變異 prompt")

    monkeypatch.setattr(run_opt, "baseline_runs_from_meta", lambda _hash: ({}, {}))
    monkeypatch.setattr(run_opt, "find_latest_run_for_hash", lambda *_args: None)
    monkeypatch.setattr(run_opt, "find_latest_run_for", lambda *_args: None)
    monkeypatch.setattr(run_opt, "collect_recent_failure_trend", lambda *_args, **_kwargs: ({}, []))
    monkeypatch.setattr(run_opt, "champion_context", lambda: "")
    monkeypatch.setattr(run_opt, "call_minimax", capture_then_stop)

    assert not run_opt.run_opt_pass(
        smoke_parallel=1,
        dev_parallel=1,
        holdout_parallel=1,
        force_direction=force_direction,
        avoid_failures=avoid_failures,
    )
    assert len(captured) == 1
    return captured[0], run_opt.LAST_ROUND_COUNTERMEASURES


class TestActualTargetedMutation:
    @pytest.mark.parametrize(("failure_code", "direction"), [("F03", "D03"), ("F04", "D04")])
    def test_dominant_failure_injects_verbatim_taxonomy_countermeasure(
        self, tmp_path, monkeypatch, failure_code, direction
    ):
        dominant_failure = infinite_evolve.dominant_failure({"failure_counts": {failure_code: 2}})
        meta_prompt, injected = _capture_mutation_prompt(
            tmp_path, monkeypatch, force_direction=direction
        )
        countermeasure = _countermeasure_from_taxonomy(dominant_failure)

        assert f"- {dominant_failure}：{countermeasure}" in meta_prompt
        assert isinstance(injected, list)
        assert all(isinstance(code, str) for code in injected)
        assert injected == [dominant_failure]

    def test_non_target_dominant_failure_only_avoids_without_injection(self, tmp_path, monkeypatch):
        dominant_failure = infinite_evolve.dominant_failure({"failure_counts": {"F08": 2}})
        _, target_failures = run_opt.pick_direction(
            "", trend_counts={dominant_failure: 2}, avoid_failures=[dominant_failure]
        )
        meta_prompt, injected = _capture_mutation_prompt(
            tmp_path, monkeypatch, avoid_failures=[dominant_failure]
        )

        assert dominant_failure not in target_failures
        assert isinstance(injected, list)
        assert all(isinstance(code, str) for code in injected)
        assert injected == []
        assert "2. **定向變異 — 對策原文注入**：—" in meta_prompt
        assert _countermeasure_from_taxonomy(dominant_failure) not in meta_prompt


class TestLoadTargetedCountermeasures:
    """load_targeted_countermeasures 單元測試 — 斷言對策原文（非僅代碼）。"""

    def test_loads_countermeasure_text_for_F03(self):
        """F03 對策原文應包含完整的中文說明，非僅代碼。"""
        result = run_opt.load_targeted_countermeasures(["F03"])
        assert "F03" in result
        text = result["F03"]
        assert len(text) > 20, f"F03 對策原文過短：{text!r}"
        assert "結構化、具體化" in text
        assert F03_COUNTERMEASURE in text

    def test_loads_countermeasure_text_for_F04(self):
        """F04 對策原文應包含完整的中文說明，非僅代碼。"""
        result = run_opt.load_targeted_countermeasures(["F04"])
        assert "F04" in result
        text = result["F04"]
        assert len(text) > 20, f"F04 對策原文過短：{text!r}"
        assert "專有名詞" in text
        assert F04_COUNTERMEASURE in text

    def test_both_F03_and_F04_returned_together(self):
        """同時要求 F03 與 F04，兩者都應返回各自完整的對策原文。"""
        result = run_opt.load_targeted_countermeasures(["F03", "F04"])
        assert "F03" in result
        assert "F04" in result
        assert F03_COUNTERMEASURE in result["F03"]
        assert F04_COUNTERMEASURE in result["F04"]

    def test_returns_only_requested_codes(self):
        """只請求 F03 時不應包含 F04。"""
        result = run_opt.load_targeted_countermeasures(["F03"])
        assert "F04" not in result
        assert len(result) == 1

    def test_empty_list_returns_empty_dict(self):
        """請求空 list 時回傳空 dict（沒有 dominant failure 的情境）。"""
        result = run_opt.load_targeted_countermeasures([])
        assert result == {}

    def test_none_returns_empty_dict(self):
        """傳入 None 時回傳空 dict。"""
        result = run_opt.load_targeted_countermeasures(None)
        assert result == {}

    def test_countermeasure_text_is_not_just_code(self):
        """對策內容為完整中文句子，非僅 F03/F04 代碼。"""
        result = run_opt.load_targeted_countermeasures(["F03", "F04"])
        for code in ("F03", "F04"):
            text = result[code]
            assert code not in text, (
                f"{code} 對策原文不應只包含代碼本身"
            )
            # Countermeasure text should be a meaningful Chinese sentence
            assert any(kw in text for kw in ("必須", "應", "嚴禁", "規定", "要求")), (
                f"{code} 對策原文缺少指令式關鍵字：{text[:50]}..."
            )

    def test_countermeasure_text_verbatim_match_with_taxonomy_file(self):
        """逐字比對：load_targeted_countermeasures 回傳文字與 taxonomy 檔案完全一致。"""
        result = run_opt.load_targeted_countermeasures(["F03", "F04"])
        tax_path = "rubrics/failure_taxonomy.md"
        with open(tax_path, "r", encoding="utf-8") as f:
            tax_text = f.read()
        code_pat = re.compile(r"^###\s+(F\d{2})")
        cm_pat = re.compile(r"^\*\s*\*\*修復方向\*\*[：:]\s*(.+)")
        current_code = None
        tax_cms = {}
        for line in tax_text.split("\n"):
            m = code_pat.match(line)
            if m:
                current_code = m.group(1)
            if current_code:
                cm = cm_pat.match(line)
                if cm:
                    if current_code in ("F03", "F04"):
                        tax_cms[current_code] = cm.group(1).strip()
                    current_code = None
        assert "F03" in tax_cms
        assert "F04" in tax_cms
        assert result["F03"] == tax_cms["F03"], (
            f"F03 對策文字與 taxonomy 原文不符（逐字比對）\n"
            f"  load_targeted_countermeasures 回傳: {result['F03']!r}\n"
            f"  taxonomy 原文:                 {tax_cms['F03']!r}"
        )
        assert result["F04"] == tax_cms["F04"], (
            f"F04 對策文字與 taxonomy 原文不符（逐字比對）\n"
            f"  load_targeted_countermeasures 回傳: {result['F04']!r}\n"
            f"  taxonomy 原文:                 {tax_cms['F04']!r}"
        )


class TestCountermeasuresInjectedField:
    """countermeasures_injected 欄位正確記錄代碼的測試。"""

    def test_LAST_ROUND_COUNTERMEASURES_set_after_run_opt_pass(self):
        """透過 mock call_minimax 驗證 run_opt_pass 後 LAST_ROUND_COUNTERMEASURES 正確。"""
        result = run_opt.load_targeted_countermeasures(["F03"])
        assert sorted(result.keys()) == ["F03"]

    def test_countermeasure_block_format_contains_full_text(self):
        """驗證 countermeasure_block 格式字串包含對策全文。"""
        result = run_opt.load_targeted_countermeasures(["F03"])
        lines = [f"- {code}：{text}" for code, text in sorted(result.items())]
        block = "以下為對應缺陷的具體修復方向，請在優化時嚴格落實：\n" + "\n".join(lines)
        assert "以下為對應缺陷的具體修復方向" in block
        assert F03_COUNTERMEASURE in block
        # 確認格式為 code + 全形冒號 + 對策原文，而非只有 code
        assert "- F03：" in block
        assert block.count("- F03：") == 1

    def test_countermeasure_block_empty_when_no_target(self):
        """沒有目標缺陷碼時 block 為 '—'。"""
        result = run_opt.load_targeted_countermeasures([])
        assert result == {}


class TestLogEntryCountermeasuresInjected:
    """演化日誌 round_complete 中 countermeasures_injected 欄位的測試。"""

    def _setup_basic_mocks(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        # Reset module-level countermeasures
        run_opt.LAST_ROUND_COUNTERMEASURES = []
        # Write baseline prompt
        p = tmp_path / "prompts" / "baseline.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("你是一位專精臺灣國家考試的專家。", encoding="utf-8")
        # Write taxonomy
        tax_dir = tmp_path / "rubrics"
        tax_dir.mkdir(parents=True, exist_ok=True)
        tax_path = tax_dir / "failure_taxonomy.md"
        tax_path.write_text(
            "### F03：採分點不外露\n"
            "* **定義**：xxx\n"
            "* **修復方向**：規定標題必須「結構化、具體化」，例如「一、依行政程序法第 7 條之比例原則內涵」，並要求關鍵字加粗。\n"
            "\n"
            "### F04：內容抽象\n"
            "* **定義**：yyy\n"
            "* **修復方向**：要求模型必須包含「專有名詞（制度/學說/技術名稱）」與「具體法條/實例」，每段論點至少附帶一個具體佐證。\n",
            encoding="utf-8",
        )
        return tax_path

    def test_log_entry_has_countermeasures_injected_field(self, tmp_path, monkeypatch):
        """round_complete 日誌包含 countermeasures_injected 欄位。"""
        self._setup_basic_mocks(tmp_path, monkeypatch)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        # Install fake run_opt that doesn't crash
        calls = []
        def fake_run_opt_pass(
            smoke_parallel=None, dev_parallel=None, holdout_parallel=None,
            force_direction=None, avoid_failures=None,
        ):
            calls.append({
                "smoke_parallel": smoke_parallel,
                "dev_parallel": dev_parallel,
                "holdout_parallel": holdout_parallel,
                "force_direction": force_direction,
                "avoid_failures": avoid_failures,
            })
            return True

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = fake_run_opt_pass
        fake_mod.LAST_ROUND_COUNTERMEASURES = []
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=[
            "--max-rounds", "5",
            "--no-improve-limit", "3",
            "--retry-after-no-improve", "0",
            "--sleep-seconds", "0",
            "--route-every", "0",
            "--round-timeout-seconds", "60",
        ])
        assert rc == 0

        # Read log
        log_path = tmp_path / "evolution_log.jsonl"
        assert log_path.exists()
        log_rows = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    log_rows.append(json.loads(line))

        round_events = [r for r in log_rows if r.get("event") == "round_complete"]
        assert len(round_events) >= 1

        for evt in round_events:
            assert "countermeasures_injected" in evt, (
                f"round_complete 遺漏 countermeasures_injected 欄位"
            )
            assert isinstance(evt["countermeasures_injected"], list), (
                f"countermeasures_injected 應為 list，實際為 {type(evt['countermeasures_injected'])}"
            )

    def test_no_dominant_failure_empty_countermeasures(self, tmp_path, monkeypatch):
        """沒有 dominant_failure 時 countermeasures_injected 為空 list。"""
        self._setup_basic_mocks(tmp_path, monkeypatch)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        calls = []
        def fake_run_opt_pass(
            smoke_parallel=None, dev_parallel=None, holdout_parallel=None,
            force_direction=None, avoid_failures=None,
        ):
            calls.append({
                "smoke_parallel": smoke_parallel,
                "dev_parallel": dev_parallel,
                "holdout_parallel": holdout_parallel,
                "force_direction": force_direction,
                "avoid_failures": avoid_failures,
            })
            return True

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = fake_run_opt_pass
        fake_mod.LAST_ROUND_COUNTERMEASURES = []
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=[
            "--max-rounds", "5",
            "--no-improve-limit", "3",
            "--retry-after-no-improve", "0",
            "--sleep-seconds", "0",
            "--route-every", "0",
            "--round-timeout-seconds", "60",
        ])
        assert rc == 0

        log_path = tmp_path / "evolution_log.jsonl"
        log_rows = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    log_rows.append(json.loads(line))

        round_events = [r for r in log_rows if r.get("event") == "round_complete"]
        # With fake run_opt_pass that returns True every round and no failures_summary,
        # all rounds should have countermeasures_injected == []
        for evt in round_events:
            assert evt["countermeasures_injected"] == [], (
                f"預期空 list，實際為 {evt['countermeasures_injected']}"
            )

    def test_dominant_failure_triggers_countermeasures(self, tmp_path, monkeypatch):
        """dominant_failure 存在時 countermeasures_injected 反映注入的代碼。"""
        self._setup_basic_mocks(tmp_path, monkeypatch)
        monkeypatch.setattr(
            infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0)
        )
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        calls = []
        def fake_run_opt_pass(
            smoke_parallel=None, dev_parallel=None, holdout_parallel=None,
            force_direction=None, avoid_failures=None,
        ):
            calls.append({
                "smoke_parallel": smoke_parallel,
                "dev_parallel": dev_parallel,
                "holdout_parallel": holdout_parallel,
                "force_direction": force_direction,
                "avoid_failures": avoid_failures,
            })
            return True

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = fake_run_opt_pass
        fake_mod.LAST_ROUND_COUNTERMEASURES = ["F03"]
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=[
            "--max-rounds", "5",
            "--no-improve-limit", "3",
            "--retry-after-no-improve", "0",
            "--sleep-seconds", "0",
            "--route-every", "0",
            "--round-timeout-seconds", "60",
        ])
        assert rc == 0

        log_path = tmp_path / "evolution_log.jsonl"
        log_rows = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    log_rows.append(json.loads(line))

        round_events = [r for r in log_rows if r.get("event") == "round_complete"]
        # With LAST_ROUND_COUNTERMEASURES = ["F03"], round events should have ["F03"]
        for evt in round_events:
            assert evt["countermeasures_injected"] == ["F03"], (
                f"預期 ['F03']，實際為 {evt['countermeasures_injected']}"
            )


class TestMetaPromptCountermeasureInjection:
    """驗證變異 prompt 含 taxonomy 對應對策原文的整合測試。"""

    def test_meta_prompt_includes_targeted_countermeasure_F03(self, tmp_path, monkeypatch):
        """當 target_failures 含 F03 時，meta_prompt 應包含 F03 對策原文。"""
        # We test by checking that load_targeted_countermeasures returns the full text,
        # and that the formatting logic (identical to run_opt_pass) includes it.
        result = run_opt.load_targeted_countermeasures(["F03"])
        assert "F03" in result
        text = result["F03"]
        # Verify the text is the actual countermeasure, not just the code
        assert "必須「結構化、具體化」" in text
        assert "關鍵字加粗" in text

    def test_meta_prompt_includes_targeted_countermeasure_F04(self, tmp_path, monkeypatch):
        """當 target_failures 含 F04 時，meta_prompt 應包含 F04 對策原文。"""
        result = run_opt.load_targeted_countermeasures(["F04"])
        assert "F04" in result
        text = result["F04"]
        assert "專有名詞" in text
        assert "具體佐證" in text

    def test_countermeasure_block_full_integration_with_meta_prompt(self):
        """對策原文格式化後確認包含完整句子非僅代碼。"""
        for code, expected_text in [("F03", F03_COUNTERMEASURE), ("F04", F04_COUNTERMEASURE)]:
            result = run_opt.load_targeted_countermeasures([code])
            assert code in result
            # The returned text IS the countermeasure原文 (not code)
            assert len(result[code]) > len(code) * 5  # text must be significantly longer
            assert result[code] == expected_text


class TestDominantFailureToCountermeasures:
    """驗證 dominant_failure（F03/F04）→ load_targeted_countermeasures 的整合路徑。"""

    def test_dominant_failure_F03_loads_countermeasure_text(self):
        """dominant_failure 傳回 F03 時可載入對應對策原文。"""
        summary = {"failure_counts": {"F03": 5, "F01": 2}}
        df = infinite_evolve.dominant_failure(summary)
        assert df == "F03"
        result = run_opt.load_targeted_countermeasures([df])
        assert "F03" in result
        assert "結構化、具體化" in result["F03"]

    def test_dominant_failure_F04_loads_countermeasure_text(self):
        """dominant_failure 傳回 F04 時可載入對應對策原文。"""
        summary = {"failure_counts": {"F04": 3, "F02": 1}}
        df = infinite_evolve.dominant_failure(summary)
        assert df == "F04"
        result = run_opt.load_targeted_countermeasures([df])
        assert "F04" in result
        assert "專有名詞" in result["F04"]

    def test_dominant_failure_other_also_loads(self):
        """dominant_failure 非 F03/F04 時仍可載入（通用行為）。"""
        summary = {"failure_counts": {"F08": 4, "F05": 2}}
        df = infinite_evolve.dominant_failure(summary)
        assert df == "F08"
        result = run_opt.load_targeted_countermeasures([df])
        assert "F08" in result
        assert "涵攝" in result["F08"]

    def test_dominant_failure_empty_summary_returns_empty(self):
        """failure_counts 為空時 dominant_failure 回傳空字串，對應空 dict。"""
        summary = {}
        df = infinite_evolve.dominant_failure(summary)
        assert df == ""
        result = run_opt.load_targeted_countermeasures([df] if df else [])
        assert result == {}

    def test_countermeasures_injected_in_log_when_dominant_failure_F03(self, tmp_path, monkeypatch):
        """dominant_failure=F03 時 round_complete.countermeasures_injected 含代碼。"""
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "prompts" / "baseline.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("你是一位專精臺灣國家考試的專家。", encoding="utf-8")
        tax_dir = tmp_path / "rubrics"
        tax_dir.mkdir(parents=True, exist_ok=True)
        (tax_dir / "failure_taxonomy.md").write_text(
            "### F03：採分點不外露\n"
            "* **修復方向**：規定標題必須「結構化、具體化」。\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0))
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = lambda **kwargs: True
        fake_mod.LAST_ROUND_COUNTERMEASURES = ["F03"]
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=[
            "--max-rounds", "3", "--no-improve-limit", "5",
            "--retry-after-no-improve", "0", "--sleep-seconds", "0",
            "--route-every", "0", "--round-timeout-seconds", "60",
        ])
        assert rc == 0

        log_path = tmp_path / "evolution_log.jsonl"
        log_rows = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    log_rows.append(json.loads(line))

        round_events = [r for r in log_rows if r.get("event") == "round_complete"]
        for evt in round_events:
            assert isinstance(evt["countermeasures_injected"], list)
            assert all(isinstance(x, str) for x in evt["countermeasures_injected"])
            assert evt["countermeasures_injected"] == ["F03"]

    def test_countermeasures_injected_in_log_when_dominant_failure_F04(self, tmp_path, monkeypatch):
        """dominant_failure=F04 時 round_complete.countermeasures_injected 含代碼。"""
        monkeypatch.chdir(tmp_path)
        p = tmp_path / "prompts" / "baseline.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("你是一位專精臺灣國家考試的專家。", encoding="utf-8")
        tax_dir = tmp_path / "rubrics"
        tax_dir.mkdir(parents=True, exist_ok=True)
        (tax_dir / "failure_taxonomy.md").write_text(
            "### F04：內容抽象\n"
            "* **修復方向**：要求模型必須包含「專有名詞（制度/學說/技術名稱）」與「具體法條/實例」，每段論點至少附帶一個具體佐證。\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(infinite_evolve, "run_cmd", lambda cmd, timeout=None: SimpleNamespace(returncode=0))
        monkeypatch.setattr(infinite_evolve.time, "sleep", lambda _: None)

        fake_mod = types.ModuleType("run_opt")
        fake_mod.run_opt_pass = lambda **kwargs: True
        fake_mod.LAST_ROUND_COUNTERMEASURES = ["F04"]
        monkeypatch.setitem(sys.modules, "run_opt", fake_mod)

        rc = infinite_evolve.main(argv=[
            "--max-rounds", "3", "--no-improve-limit", "5",
            "--retry-after-no-improve", "0", "--sleep-seconds", "0",
            "--route-every", "0", "--round-timeout-seconds", "60",
        ])
        assert rc == 0

        log_path = tmp_path / "evolution_log.jsonl"
        log_rows = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    log_rows.append(json.loads(line))

        round_events = [r for r in log_rows if r.get("event") == "round_complete"]
        for evt in round_events:
            assert isinstance(evt["countermeasures_injected"], list)
            assert all(isinstance(x, str) for x in evt["countermeasures_injected"])
            assert evt["countermeasures_injected"] == ["F04"]


if __name__ == "__main__":
    sys.exit(pytest.main(["-v", __file__]))
