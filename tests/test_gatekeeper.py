import importlib
import sys
from pathlib import Path


def _load_gatekeeper_from_tmp(monkeypatch, tmp_path: Path):
    """在匯入前將 cwd 切到 tmp 路徑，避免匯入時的 os.chdir 外溢。"""
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(project_root))

    # 清除 cache，確保每次測試都會重新執行匯入邏輯
    sys.modules.pop("scripts.gatekeeper", None)
    importlib.invalidate_caches()

    return importlib.import_module("scripts.gatekeeper")


def test_gatekeeper_import_side_effect_is_isolated_by_tmp_cwd(monkeypatch, tmp_path):
    original_cwd = Path.cwd()

    with monkeypatch.context() as m:
        gatekeeper = _load_gatekeeper_from_tmp(m, tmp_path)

        # scripts.gatekeeper 在匯入時會 os.chdir 到專案根目錄
        expected_root = Path(__file__).resolve().parents[1]
        assert Path.cwd() == expected_root
        assert gatekeeper.__file__.startswith(str(expected_root))
        assert Path(gatekeeper.__file__).name == "gatekeeper.py"
        assert Path(gatekeeper.__file__).parent.name == "scripts"

        prompt = (
            "你是專家，依法理與法律案例作答，請直接輸出正文；不得反問，不得編造。"
            "比較基準請明確列出，並依規則判斷，這段提示詞刻意補足字數以符合最小長度要求，"
            "內容聚焦於考試閱卷與評分要點，避免過短，同時避免輸出冗長前言與分析。"
        )
        passed, _ = gatekeeper.run_gatekeeper(prompt)
        assert isinstance(passed, bool)

    # 恢復到測試前 cwd，避免污染整個測試程序
    assert Path.cwd() == original_cwd
