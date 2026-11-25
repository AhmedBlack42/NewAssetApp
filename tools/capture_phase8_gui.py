"""Render Phase 8 GUI evidence from the real Qt widgets without changing app data.

These are offscreen widget renders, not desktop input/capture acceptance evidence.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.config import AppConfig
from app.core.database import Database
from app.gui.correction_dialog import CorrectionDialog
from app.gui.main_window import MainWindow


OUTPUT = ROOT / "gui_screenshots" / "phase8"


def capture(widget, name: str) -> None:
    QApplication.processEvents()
    pixmap = widget.grab()
    if pixmap.isNull() or not pixmap.save(str(OUTPUT / name), "PNG"):
        raise RuntimeError(f"Could not render screenshot {name}")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")
    if font_id >= 0:
        app.setFont(QFont("Segoe UI", 10))
    config = AppConfig.load()
    database = Database(config.database_path)
    window = MainWindow(config, database)
    window.resize(1360, 768)
    window.show()
    QApplication.processEvents()

    window.workspace_tabs.setCurrentIndex(0)
    capture(window, "normal_initial.png")
    if window.normal_gallery.count() and window.normal_gallery.item(0).data(Qt.ItemDataRole.UserRole):
        first = window.normal_gallery.item(0)
        window.normal_gallery.setCurrentItem(first)
        first.setCheckState(Qt.CheckState.Checked)
        capture(window, "normal_crop_selected.png")

    folder_dialog = QFileDialog(window, "Select image folder", str(ROOT / "samples"))
    folder_dialog.setFileMode(QFileDialog.FileMode.Directory)
    folder_dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
    folder_dialog.show()
    QApplication.processEvents()
    capture(folder_dialog, "normal_folder_selection.png")
    folder_dialog.close()

    for category, filename in (
        ("fullbody", "normal_fullbody_suggestions.png"),
        ("body_images", "normal_body_images_suggestions.png"),
        ("clothing", "normal_clothing_suggestions.png"),
    ):
        index = window.normal_category_filter.findData(category)
        if index >= 0:
            window.normal_category_filter.setCurrentIndex(index)
            QApplication.processEvents()
            capture(window, filename)

    body_index = window.normal_category_filter.findData("body_images")
    if body_index >= 0:
        window.normal_category_filter.setCurrentIndex(body_index)
        if window.normal_gallery.count() and window.normal_gallery.item(0).data(Qt.ItemDataRole.UserRole):
            candidate = window.normal_gallery.item(0)
            window.normal_gallery.setCurrentItem(candidate)
            candidate.setCheckState(Qt.CheckState.Checked)
            QApplication.processEvents()
            original_picker = QFileDialog.getExistingDirectory
            QFileDialog.getExistingDirectory = lambda *args, **kwargs: str(OUTPUT / "preview_output")

            def dismiss_export_confirmation():
                dialog = QApplication.activeModalWidget()
                if isinstance(dialog, QMessageBox):
                    capture(dialog, "normal_export_confirmation.png")
                    dialog.done(QMessageBox.StandardButton.No)

            QTimer.singleShot(100, dismiss_export_confirmation)
            try:
                window._export_selected_normal_crops()
            finally:
                QFileDialog.getExistingDirectory = original_picker

    window.workspace_tabs.setCurrentIndex(1)
    window._refresh_gallery()
    capture(window, "professional_initial.png")

    source_rows = database.source_images()
    selected_source = None
    selected_boxes = []
    for source in source_rows:
        boxes = database.detections_for_source(int(source["id"]))
        if len(boxes) > len(selected_boxes):
            selected_source, selected_boxes = source, boxes
    if selected_source:
        for index in range(window.gallery.count()):
            item = window.gallery.item(index)
            row = item.data(Qt.ItemDataRole.UserRole)
            if row and int(row.get("id", -1)) == int(selected_source["id"]):
                window.gallery.setCurrentItem(item)
                break
        QApplication.processEvents()
        capture(window, "professional_selected_image.png")
        if window.detection_list.count():
            window.detection_list.setCurrentRow(0)
            QApplication.processEvents()
            capture(window, "professional_selected_detection.png")
        window.details_toggle.setChecked(True)
        QApplication.processEvents()
        capture(window, "professional_details_expanded.png")
        window.details_toggle.setChecked(False)

        overlap_pair = None
        for index, left in enumerate(selected_boxes):
            ax1, ay1, ax2, ay2 = left["bbox_xyxy"]
            for right in selected_boxes[index + 1:]:
                bx1, by1, bx2, by2 = right["bbox_xyxy"]
                if max(ax1, bx1) < min(ax2, bx2) and max(ay1, by1) < min(ay2, by2):
                    overlap_pair = (left["id"], right["id"])
                    break
            if overlap_pair:
                break
        if overlap_pair and window.show_rejected_boxes:
            capture(window, "professional_overlapping_boxes.png")
            window.show_box_labels.setChecked(True)
            QApplication.processEvents()
            capture(window, "professional_overlapping_labels.png")

    proposal_rows = database.proposals_for_category("body_images")
    if proposal_rows:
        dialog = CorrectionDialog(dict(proposal_rows[0]), window.tag_library, window)
        dialog.show()
        QApplication.processEvents()
        capture(dialog, "professional_classification_tag_editor.png")
        dialog.close()

    window.resize(900, 560)
    QApplication.processEvents()
    capture(window, "smaller_window_layout.png")
    window.close()
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
