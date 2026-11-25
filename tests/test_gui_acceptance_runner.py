import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from scripts.gui_acceptance.fixture_factory import create_fixture
from scripts.gui_acceptance.scenarios.newassetapp_smoke import run as run_newassetapp
from scripts.gui_acceptance.scenarios.studio_smoke import run as run_studio
from scripts.gui_acceptance.scenarios.phase3 import run as run_phase3
from scripts.gui_acceptance.scenarios.phase4 import (
    run_normal_body_states,
    run_professional_review,
    run_studio_import,
    run_studio_lifecycle,
)


class GuiAcceptanceRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_disposable_newassetapp_and_studio_smoke_capture(self):
        with tempfile.TemporaryDirectory(prefix="gui_acceptance_test_") as td:
            root = Path(td)
            fixture = create_fixture(root)
            app_screens = run_newassetapp(
                self.app, fixture, root / "reports", ((1280, 720),), capture=True)
            studio_screens = run_studio(
                self.app, fixture, root / "reports", ((1366, 768),), capture=True)
            self.assertTrue(app_screens["screenshots"])
            self.assertTrue(studio_screens["screenshots"])
            self.assertTrue(all(Path(item["path"]).is_file()
                                for item in app_screens["screenshots"] + studio_screens["screenshots"]))
            self.assertTrue(all(Path(item["path"]).stat().st_size > 0
                                for item in app_screens["screenshots"] + studio_screens["screenshots"]))

    def test_phase3_real_widget_normal_save_and_studio_navigation(self):
        with tempfile.TemporaryDirectory(prefix="gui_acceptance_phase3_test_") as td:
            root = Path(td)
            fixture = create_fixture(root)
            output = root / "evidence"
            result = run_phase3(
                self.app, fixture, output, ((1366, 768),), capture=False)
            self.assertTrue(result["pass"])
            self.assertEqual(result["status"], "PASS_REAL_APP_QT")
            self.assertEqual(len(result["navigation_map"]), 9)
            self.assertTrue((output / "manifests" / "isolation_manifest.json").is_file())
            self.assertTrue((output / "manifests" / "phase3_navigation.json").is_file())

    def test_phase4_normal_body_states_real_widget(self):
        with tempfile.TemporaryDirectory(prefix="gui_acceptance_phase4_normal_") as td:
            root = Path(td)
            fixture = create_fixture(root)
            result = run_normal_body_states(
                self.app, fixture, root / "evidence", ((1366, 768),), capture=False)
            self.assertEqual(result["status"], "PASS_REAL_APP_QT")
            self.assertEqual(len(result["interactions"]), 7)

    def test_phase4_professional_real_widget_review(self):
        with tempfile.TemporaryDirectory(prefix="gui_acceptance_phase4_professional_") as td:
            root = Path(td)
            fixture = create_fixture(root)
            result = run_professional_review(
                self.app, fixture, root / "evidence", ((1366, 768),), capture=False)
            self.assertIn(result["status"], {"PASS_REAL_APP_QT", "PARTIAL"})
            self.assertGreaterEqual(len(result["selected_rows"]), 2)

    def test_phase4_studio_import_real_widget(self):
        with tempfile.TemporaryDirectory(prefix="gui_acceptance_phase4_import_") as td:
            root = Path(td)
            fixture = create_fixture(root)
            result = run_studio_import(
                self.app, fixture, root / "evidence", ((1366, 768),), capture=False)
            self.assertEqual(result["status"], "PASS_REAL_APP_QT")
            self.assertGreater(result["accepted_records"], 0)

    def test_phase4_studio_lifecycle_real_widget(self):
        with tempfile.TemporaryDirectory(prefix="gui_acceptance_phase4_lifecycle_") as td:
            root = Path(td)
            fixture = create_fixture(root)
            result = run_studio_lifecycle(
                self.app, fixture, root / "evidence", ((1366, 768),), capture=False)
            self.assertEqual(result["status"], "PASS_REAL_APP_QT")
            self.assertIsInstance(result["version_id"], int)


if __name__ == "__main__":
    unittest.main()
