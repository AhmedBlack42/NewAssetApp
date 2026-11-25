import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import tempfile
import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication


class StudioGuiLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from TrainingDatasetStudio.studio.config import StudioConfig
        from TrainingDatasetStudio.studio.store import StudioStore
        from TrainingDatasetStudio.studio.gui import StudioWindow

        self.temp_dir = tempfile.TemporaryDirectory(prefix="newassetapp_studio_gui_")
        root = Path(self.temp_dir.name)
        self.config = StudioConfig(root=root)
        self.config.ensure_directories()
        self.store = StudioStore(self.config.database_path)
        self.store.initialize()
        self.window = StudioWindow(self.config, self.store)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.temp_dir.cleanup()

    def test_nine_navigation_destinations_open_real_service_pages(self):
        for width, height in ((1280, 720), (1366, 768), (1920, 1080)):
            with self.subTest(size=(width, height)):
                self.window.resize(width, height)
                self.app.processEvents()
                self.assertGreater(self.window.studio_navigation.width(), 160)
                self.assertLess(self.window.studio_navigation.width(), 230)
        expected = [
            "Model Projects",
            "Dataset Segments",
            "Dataset Builder",
            "Dataset Records",
            "Validation",
            "Colab Packages",
            "Model Artifacts",
            "Import / Activation",
            "History",
        ]
        self.assertEqual(
            [self.window.studio_navigation.item(i).text()
             for i in range(self.window.studio_navigation.count())],
            expected,
        )
        self.assertEqual(self.window.studio_navigation.count(), 9)
        self.assertEqual(self.window.studio_pages.count(), 9)
        for row in range(9):
            self.window.studio_navigation.setCurrentRow(row)
            self.app.processEvents()
            self.assertEqual(self.window.studio_pages.currentIndex(), row)
            self.assertIsNotNone(self.window.studio_pages.currentWidget())


if __name__ == "__main__":
    unittest.main()
