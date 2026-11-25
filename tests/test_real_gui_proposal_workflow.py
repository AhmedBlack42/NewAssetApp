import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import tempfile
import time
import statistics
import unittest
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QListWidgetItem

from app.application import create_application
from app.config import AppConfig
from app.core.database import Database
from scripts.gui_acceptance.qt_helpers import process_events


class RealGuiProposalWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_real_samples_proposal_switch_category_tags_persistence_and_timing(self):
        source_db = Path(
            r"C:\Users\asker\AppData\Local\Temp\newassetapp_real_samples_20261123_002448_real_samples"
            r"\app\newassetapp.sqlite3"
        )
        if not source_db.is_file():
            self.skipTest("Existing isolated real-samples database is unavailable.")

        with tempfile.TemporaryDirectory(prefix="real_gui_proposal_") as td:
            root = Path(td)
            db_path = root / "acceptance.sqlite3"
            output_dir = root / "output"
            logs_dir = root / "logs"
            output_dir.mkdir()
            logs_dir.mkdir()
            shutil.copy2(source_db, db_path)

            data_dir = root / "data"
            data_dir.mkdir()
            project_root = Path(__file__).resolve().parents[1]
            shutil.copytree(project_root / "data" / "tags", data_dir / "tags",
                            dirs_exist_ok=True)

            config = AppConfig(
                data_dir_override=data_dir,
                output_dir_override=output_dir,
                logs_dir_override=logs_dir,
                database_path_override=db_path,
            )
            database = Database(db_path)
            database.initialize()
            window = create_application(config)
            window.show()
            process_events(self.app)
            window.folder_edit.setText(str(project_root / "samples"))
            start = time.perf_counter()
            window._refresh_normal_gallery()
            process_events(self.app)
            gallery_ms = (time.perf_counter() - start) * 1000
            scrollbar = window.normal_gallery.verticalScrollBar()
            positions = []
            viewport_results = []
            for fraction in (0.0, 0.25, 0.50, 0.75, 1.0):
                value = round(scrollbar.maximum() * fraction)
                scrollbar.setValue(value)
                process_events(self.app)
                start_view = time.perf_counter()
                window._schedule_visible_normal_thumbnails()
                process_events(self.app)
                window._normal_thumbnail_debounce.timeout.emit()
                process_events(self.app)
                viewport_ms = (time.perf_counter() - start_view) * 1000
                viewport = window.normal_gallery.viewport()
                visible_rows = []
                for index in range(window.normal_gallery.count()):
                    rect = window.normal_gallery.visualRect(
                        window.normal_gallery.model().index(index, 0))
                    if rect.intersects(viewport.rect()):
                        visible_rows.append(index)
                if visible_rows:
                    first = visible_rows[0]
                    last = visible_rows[-1]
                else:
                    first = window.normal_gallery.indexAt(viewport.rect().topLeft()).row()
                    last = window.normal_gallery.indexAt(viewport.rect().bottomLeft()).row()
                    if first < 0:
                        first = 0
                    if last < 0:
                        last = min(first, window.normal_gallery.count() - 1)
                loaded = 0
                blank = 0
                missing = 0
                for index in range(max(0, first), min(window.normal_gallery.count(), last + 1)):
                    item = window.normal_gallery.item(index)
                    icon = item.icon()
                    if icon.isNull():
                        if "missing" in item.toolTip().lower() or "decode failed" in item.toolTip().lower():
                            missing += 1
                        else:
                            blank += 1
                    else:
                        loaded += 1
                viewport_results.append({
                    "fraction": fraction,
                    "first_row": first,
                    "last_row": last,
                    "loaded": loaded,
                    "blank": blank,
                    "missing": missing,
                    "load_ms": round(viewport_ms, 3),
                })
                positions.append(value)

            rows = []
            for index in range(window.normal_gallery.count()):
                item = window.normal_gallery.item(index)
                row = item.data(Qt.ItemDataRole.UserRole)
                if row:
                    rows.append((item, dict(row)))

            clothing = next(((item, row) for item, row in rows
                              if str(row.get("yolo_class_name") or "").startswith("pussy_cover_item")),
                            None)
            body = next(((item, row) for item, row in rows
                         if str(row.get("yolo_class_name") or "").casefold() == "face"),
                        None)
            if clothing is None or body is None:
                self.fail("Disposable real-samples database lacks representative clothing and body proposals.")

            clothing_samples = []
            body_samples = []
            for _ in range(20):
                start = time.perf_counter()
                window.normal_gallery.setCurrentItem(clothing[0])
                process_events(self.app)
                clothing_samples.append((time.perf_counter() - start) * 1000)
                start = time.perf_counter()
                window.normal_gallery.setCurrentItem(body[0])
                process_events(self.app)
                body_samples.append((time.perf_counter() - start) * 1000)

            heartbeat_ticks = []
            heartbeat = QTimer(window)
            heartbeat.setInterval(10)
            heartbeat.timeout.connect(lambda: heartbeat_ticks.append(time.perf_counter()))
            heartbeat.start()

            start = time.perf_counter()
            window.normal_gallery.setCurrentItem(clothing[0])
            process_events(self.app)
            clothing_selection_ms = (time.perf_counter() - start) * 1000
            self.assertEqual(
                window.normal_gallery.currentItem().data(Qt.ItemDataRole.UserRole)["id"],
                clothing[1]["id"],
            )

            window.normal_assign_category.setCurrentIndex(
                window.normal_assign_category.findData("clothing"))
            process_events(self.app)
            window.normal_clothing_broad.setCurrentIndex(
                window.normal_clothing_broad.findData("skirt"))
            process_events(self.app)
            skirt_details = {
                window.normal_body_tag.itemData(index)
                for index in range(window.normal_body_tag.count())
                if window.normal_body_tag.itemData(index) is not None
            }
            self.assertIn("mini_skirt", skirt_details)
            self.assertNotIn("t_shirt", skirt_details)

            start = time.perf_counter()
            window.normal_gallery.setCurrentItem(body[0])
            process_events(self.app)
            body_selection_ms = (time.perf_counter() - start) * 1000
            self.assertEqual(
                window.normal_gallery.currentItem().data(Qt.ItemDataRole.UserRole)["id"],
                body[1]["id"],
            )
            window.normal_assign_category.setCurrentIndex(
                window.normal_assign_category.findData("body_images"))
            process_events(self.app)
            body_tags = {
                window.normal_body_tag.itemData(index)
                for index in range(window.normal_body_tag.count())
                if window.normal_body_tag.itemData(index) is not None
            }
            self.assertIn("boobs", body_tags)
            self.assertNotIn("mini_skirt", body_tags)

            window.normal_gallery.setCurrentItem(clothing[0])
            process_events(self.app)
            self.assertEqual(window.normal_assign_category.currentData(), "clothing")

            heartbeat.stop()
            if len(heartbeat_ticks) >= 2:
                gaps = [
                    (heartbeat_ticks[index] - heartbeat_ticks[index - 1]) * 1000
                    for index in range(1, len(heartbeat_ticks))
                ]
                heartbeat_max_ms = max(gaps)
            else:
                heartbeat_max_ms = 0.0

            screenshot = root / "proposal_workflow_real_qt.png"
            pixmap = window.grab()
            pixmap.save(str(screenshot))
            self.assertTrue(screenshot.is_file())
            self.assertGreater(screenshot.stat().st_size, 0)

            window.close()
            process_events(self.app)
            reopened = create_application(config)
            reopened.show()
            process_events(self.app)
            reopened.folder_edit.setText(str(project_root / "samples"))
            reopened._refresh_normal_gallery()
            process_events(self.app)
            reopened_rows = {
                reopened.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)["id"]:
                reopened.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)
                for index in range(reopened.normal_gallery.count())
                if reopened.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)
            }
            self.assertIn(clothing[1]["id"], reopened_rows)
            reopened.close()
            process_events(self.app)

            print(
                "REAL_QT_TIMING",
                {
                    "gallery_refresh_ms": round(gallery_ms, 3),
                    "viewport_results": viewport_results,
                    "scroll_positions": positions,
                    "clothing_samples_ms": [round(value, 3) for value in clothing_samples],
                    "body_samples_ms": [round(value, 3) for value in body_samples],
                    "clothing_summary_ms": {
                        "min": round(min(clothing_samples), 3),
                        "avg": round(statistics.mean(clothing_samples), 3),
                        "median": round(statistics.median(clothing_samples), 3),
                        "p95": round(sorted(clothing_samples)[18], 3),
                        "max": round(max(clothing_samples), 3),
                        "count": len(clothing_samples),
                    },
                    "body_summary_ms": {
                        "min": round(min(body_samples), 3),
                        "avg": round(statistics.mean(body_samples), 3),
                        "median": round(statistics.median(body_samples), 3),
                        "p95": round(sorted(body_samples)[18], 3),
                        "max": round(max(body_samples), 3),
                        "count": len(body_samples),
                    },
                    "clothing_selection_ms": round(clothing_selection_ms, 3),
                    "body_selection_ms": round(body_selection_ms, 3),
                    "heartbeat_max_ms": round(heartbeat_max_ms, 3),
                    "screenshot": str(screenshot),
                },
            )
