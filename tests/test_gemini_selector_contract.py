"""Run the browser provider contract against the actual app.js functions."""

import shutil
import subprocess
from pathlib import Path


def test_gemini_selector_and_request_contract():
    node = shutil.which("node")
    assert node, "Node.js is required to exercise the browser provider path"
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, str(root / "tests" / "gemini_selector_contract.cjs")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
