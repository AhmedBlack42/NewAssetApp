import hashlib
import os
import tempfile
import unittest
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.application import create_application
from app.config import AppConfig
from app.core.database import Database
from scripts.gui_acceptance.qt_helpers import process_events


class ManualProposalAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_manual_proposal_opens_yolo_inspector_without_classification_dialog(self):
        with tempfile.TemporaryDirectory(prefix="manual_proposal_acceptance_") as td:
            root = Path(td)
            source_dir = root / "sources"
            source_dir.mkdir()
            data_dir = root / "data"
            data_dir.mkdir()
            project_root = Path(__file__).resolve().parents[1]
            shutil.copytree(project_root / "data" / "tags",
                            data_dir / "tags",
                            dirs_exist_ok=True)
            source_path = source_dir / "manual.png"
            Image.new("RGB", (600, 800), "teal").save(source_path)

            database_path = root / "app.sqlite3"
            database = Database(database_path)
            database.initialize()
            source_id, _ = database.upsert_source_image({
                "path": str(source_path.resolve()),
                "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "width": 600,
                "height": 800,
                "file_size": source_path.stat().st_size,
                "modified_ns": source_path.stat().st_mtime_ns,
            })

            config = AppConfig(
                data_dir_override=data_dir,
                output_dir_override=root / "output",
                logs_dir_override=root / "logs",
                database_path_override=database_path,
            )
            window = create_application(config)
            window.show()
            process_events(self.app)
            window.folder_edit.setText(str(source_dir))
            window._refresh_gallery()
            process_events(self.app)
            window.current_category = "sources"
            window._refresh_gallery()
            process_events(self.app)

            if window.gallery.count() != 1:
                self.fail("Diagnostic fixture must expose exactly one source.")
            window.gallery.setCurrentRow(0)
            process_events(self.app)
            self.assertTrue(window.manual_proposal_button.isEnabled())

            QTest.mouseClick(window.manual_proposal_button, Qt.MouseButton.LeftButton)
            process_events(self.app)
            detections = database.detections_for_source(source_id)
            manual = next((row for row in detections
                           if row["origin"] == "manual"), None)
            if manual is None:
                self.fail("Manual detection was not persisted.")
            self.assertEqual(manual["class_name"], "manual_annotation")
            self.assertEqual(manual["bbox_xyxy"], [30.0, 40.0, 570.0, 760.0])
            current_detection = window.detection_list.currentItem()
            if current_detection is None:
                self.fail("Manual detection was not selected in the YOLO inspector.")
            self.assertEqual(
                current_detection.data(Qt.ItemDataRole.UserRole),
                manual["id"],
            )
            selected_box = window.preview.selected_box()
            if selected_box is None:
                self.fail("Manual detection was not selected in the preview.")
            self.assertEqual(selected_box["id"], manual["id"])
            self.assertIn(f"Detection #{manual['id']}", window.inspector_original.text())

            reloaded = database.detections_for_source(source_id)
            reloaded_manual = next(row for row in reloaded if row["origin"] == "manual")
            self.assertEqual(reloaded_manual["class_name"], "manual_annotation")
            self.assertEqual(reloaded_manual["bbox_xyxy"], [30.0, 40.0, 570.0, 760.0])

            with database.connect() as connection:
                original = connection.execute(
                    "SELECT class_name,x1,y1,x2,y2,status FROM yolo_detections "
                    "WHERE id=?",
                    (int(manual["id"]),),
                ).fetchone()
            self.assertIsNotNone(original)
            self.assertEqual(original["class_name"], "manual_annotation")
            self.assertEqual(
                [float(original["x1"]), float(original["y1"]),
                 float(original["x2"]), float(original["y2"])],
                [30.0, 40.0, 570.0, 760.0],
            )

            window.close()
            process_events(self.app)


if __name__ == "__main__":
    unittest.main()
