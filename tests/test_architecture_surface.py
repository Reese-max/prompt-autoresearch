import json
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ArchitectureSurfaceTests(unittest.TestCase):
    def test_run_app_imports_without_starting_server(self):
        probe = (
            "import run_app; "
            "print(hasattr(run_app, 'build_architecture_snapshot'))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "True")

    def test_build_architecture_snapshot_contract(self):
        probe = (
            "import json, pathlib, run_app; "
            "print(json.dumps(run_app.build_architecture_snapshot(pathlib.Path.cwd()), ensure_ascii=False))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        snapshot = json.loads(proc.stdout)

        self.assertEqual(snapshot["version"], "v3")
        self.assertIn("generated_at", snapshot)
        self.assertEqual(snapshot["frontend"]["entry"], "index.html")
        self.assertIn("app.js", snapshot["frontend"]["assets"])
        self.assertEqual(snapshot["server"]["entry"], "run_app.py")
        self.assertIn("/api/architecture", snapshot["server"]["routes"])
        self.assertIn("/api/experiment-report", snapshot["server"]["routes"])
        self.assertIn("gatekeeper", [step["id"] for step in snapshot["pipeline"]])
        self.assertIn("smoke", snapshot["datasets"])
        self.assertGreaterEqual(snapshot["datasets"]["smoke"]["count"], 1)
        self.assertIn("champions", snapshot)
        self.assertGreaterEqual(snapshot["champions"]["count"], 1)
        self.assertIn("compare", [item["type_slug"] for item in snapshot["champions"]["items"]])
        self.assertIn("route_status", snapshot)
        self.assertEqual(snapshot["route_status"]["active"]["path"], "prompts/routes/type_champions.json")
        self.assertIn("loop_decision", snapshot["route_status"])
        self.assertIn("best", snapshot["route_status"]["loop_decision"])

    def test_experiment_report_snapshot_contract(self):
        probe = (
            "import json, run_app; "
            "print(json.dumps(run_app.build_experiment_report_snapshot(3), ensure_ascii=False))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )

        self.assertEqual(proc.returncode, 0, proc.stderr)
        snapshot = json.loads(proc.stdout)

        self.assertEqual(snapshot["path"], "generated:experiment_report")
        self.assertGreaterEqual(snapshot["run_count"], 1)
        self.assertEqual(snapshot["limit"], 3)
        self.assertIn("實驗治理報告", snapshot["content"])
        self.assertIn("Dev 卡點", snapshot["content"])

    def test_frontend_has_architecture_tab_contract(self):
        index_html = (PROJECT_ROOT / "index.html").read_text(encoding="utf-8")
        app_js = (PROJECT_ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-tab="architecture"', index_html)
        self.assertIn('id="tab-architecture"', index_html)
        self.assertIn('id="architecture-system-map"', index_html)
        self.assertIn('id="architecture-governance-status"', index_html)
        self.assertIn('id="architecture-route-status"', index_html)
        self.assertIn('id="architecture-champions-status"', index_html)
        self.assertIn("fetchJsonOrNull('/api/architecture')", app_js)
        self.assertIn("fetchJsonOrNull('/api/experiment-report?limit=8')", app_js)
        self.assertIn("function renderArchitectureSnapshot", app_js)
        self.assertIn("function renderExperimentGovernance", app_js)
        self.assertIn("function renderRouteStatus", app_js)
        self.assertIn("function renderChampionStatus", app_js)

    def test_architecture_document_summarizes_boundaries(self):
        doc_path = PROJECT_ROOT / "docs" / "architecture.md"
        self.assertTrue(doc_path.exists(), "docs/architecture.md should summarize the current architecture")

        doc = doc_path.read_text(encoding="utf-8")
        self.assertIn("Local UI Server", doc)
        self.assertIn("Prompt Store", doc)
        self.assertIn("Champion Store", doc)
        self.assertIn("route_status", doc)
        self.assertIn("/api/experiment-report", doc)
        self.assertIn("固定評估資產", doc)
        self.assertIn("/api/architecture", doc)


if __name__ == "__main__":
    unittest.main()
