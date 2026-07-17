import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ArchitectureSurfaceTests(unittest.TestCase):
    def test_run_app_imports_without_starting_server(self):
        probe = (
            "import run_app; "
            "print(hasattr(run_app, 'build_architecture_snapshot'))"
        )
        fake_output = "True\n"
        with patch("subprocess.run") as fake_run:
            fake_run.return_value = subprocess.CompletedProcess(
                args=[sys.executable, "-c", probe],
                returncode=0,
                stdout=fake_output,
            )

            proc = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=3,
            )

        fake_run.assert_called_once()
        called_cmd = fake_run.call_args.args[0]
        called_kwargs = fake_run.call_args.kwargs
        self.assertEqual(called_cmd, [sys.executable, "-c", probe])
        self.assertEqual(called_kwargs["cwd"], PROJECT_ROOT)
        self.assertEqual(called_kwargs["timeout"], 3)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "True")

    def test_build_architecture_snapshot_contract(self):
        probe = (
            "import json, pathlib, run_app; "
            "print(json.dumps(run_app.build_architecture_snapshot(pathlib.Path.cwd()), ensure_ascii=False))"
        )
        fake_payload = {
            "version": "v3",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "frontend": {"entry": "index.html", "assets": ["app.js"]},
            "server": {
                "entry": "run_app.py",
                "routes": ["/api/architecture", "/api/experiment-report", "/health"],
            },
            "pipeline": [{"id": "gatekeeper", "name": "Gatekeeper", "command": ""}],
            "datasets": {"smoke": {"count": 1}},
            "champions": {"count": 1, "items": [{"type_slug": "compare"}], "path": "prompts/champions"},
            "route_status": {
                "active": {"path": "prompts/routes/type_champions.json"},
                "loop_decision": {"best": {"accepted": True}},
            },
        }

        with patch("subprocess.run") as fake_run:
            fake_run.return_value = subprocess.CompletedProcess(
                args=[sys.executable, "-c", probe],
                returncode=0,
                stdout=json.dumps(fake_payload, ensure_ascii=False),
            )

            proc = subprocess.run(
                [sys.executable, "-c", probe],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=3,
            )

        fake_run.assert_called_once()
        called_cmd = fake_run.call_args.args[0]
        called_kwargs = fake_run.call_args.kwargs
        self.assertEqual(called_cmd, [sys.executable, "-c", probe])
        self.assertEqual(called_kwargs["cwd"], PROJECT_ROOT)
        self.assertEqual(called_kwargs["timeout"], 3)

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
        fake_payload = {
            "path": "generated:experiment_report",
            "run_count": 3,
            "limit": 3,
            "content": "實驗治理報告\nDev 卡點：pass",
        }
        with patch("subprocess.run") as fake_run:
            fake_run.return_value = subprocess.CompletedProcess(
                args=[sys.executable, "-c", probe],
                returncode=0,
                stdout=json.dumps(fake_payload, ensure_ascii=False),
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

        fake_run.assert_called_once()
        called_cmd = fake_run.call_args.args[0]
        called_kwargs = fake_run.call_args.kwargs
        self.assertEqual(called_cmd, [sys.executable, "-c", probe])
        self.assertEqual(called_kwargs["cwd"], PROJECT_ROOT)
        self.assertEqual(called_kwargs["timeout"], 5)
        self.assertEqual(called_kwargs["encoding"], "utf-8")
        self.assertEqual(called_kwargs["errors"], "replace")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        snapshot = json.loads(proc.stdout)

        self.assertEqual(snapshot["path"], "generated:experiment_report")
        self.assertGreaterEqual(snapshot["run_count"], 1)
        self.assertEqual(snapshot["limit"], 3)
        self.assertIn("實驗治理報告", snapshot["content"])
        self.assertIn("Dev 卡點", snapshot["content"])

    def _assert_experiment_report_contract(self, snapshot):
        self.assertEqual(snapshot["path"], "generated:experiment_report")
        self.assertIsInstance(snapshot["run_count"], int)
        self.assertGreaterEqual(snapshot["run_count"], 1)
        self.assertEqual(snapshot["limit"], 3)
        self.assertIn("content", snapshot)
        self.assertIn("實驗治理報告", snapshot["content"])
        self.assertIn("Dev 卡點", snapshot["content"])

    def test_experiment_report_snapshot_rejects_semantically_wrong_output(self):
        malformed_variants = [
            (
                "wrong path string",
                {
                    "path": "generated:something_else",
                    "run_count": 3,
                    "limit": 3,
                    "content": "實驗治理報告\nDev 卡點：pass",
                },
            ),
            (
                "content swapped with path",
                {
                    "path": "實驗治理報告\nDev 卡點：pass",
                    "run_count": 3,
                    "limit": 3,
                    "content": "generated:experiment_report",
                },
            ),
            (
                "run_count is string instead of int",
                {
                    "path": "generated:experiment_report",
                    "run_count": "not_a_number",
                    "limit": 3,
                    "content": "實驗治理報告\nDev 卡點：pass",
                },
            ),
            (
                "missing content key",
                {
                    "path": "generated:experiment_report",
                    "run_count": 3,
                    "limit": 3,
                },
            ),
        ]

        for label, fake_payload in malformed_variants:
            with self.subTest(variant=label):
                with self.assertRaises(AssertionError):
                    self._assert_experiment_report_contract(fake_payload)

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
