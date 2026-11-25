from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea

from app.application import create_application
from app.config import AppConfig
from app.core.database import Database

from ..qt_helpers import process_events
from ..screenshot_capture import capture_widget


def run(app, fixture, output_root: Path, resolutions, capture: bool = True):
    config = AppConfig(
        data_dir_override=fixture.root / "app" / "data",
        output_dir_override=fixture.output_dir,
        logs_dir_override=fixture.root / "app" / "logs",
        database_path_override=fixture.app_database,
    )
    database = Database(fixture.app_database)
    database.initialize()
    window = create_application(config)
    window.show()
    process_events(app)
    screenshots = []
    window.folder_edit.setText(str(fixture.source_path.parent))
    window._refresh_normal_gallery()
    process_events(app)
    interactions = []
    body_item = None
    for index in range(window.normal_gallery.count()):
        item = window.normal_gallery.item(index)
        row = item.data(Qt.ItemDataRole.UserRole)
        if row and str(row.get("yolo_class_name") or "").casefold() == "boobs":
            body_item = item
            break
    if body_item is None:
        raise AssertionError("Disposable fixture did not produce a boobs Normal Processing crop.")
    window.normal_gallery.setCurrentItem(body_item)
    process_events(app)
    body_row_before = body_item.data(Qt.ItemDataRole.UserRole)
    proposal_id = int(body_row_before["id"])
    window.normal_assign_category.setCurrentIndex(
        window.normal_assign_category.findData("body_images"))
    window.normal_body_tag.setCurrentIndex(window.normal_body_tag.findData("boobs"))
    window.normal_body_cum.setCheckState(Qt.CheckState.Checked)
    window.normal_body_accessory.setCheckState(Qt.CheckState.Unchecked)
    window.normal_body_completed.setChecked(True)
    for index in range(window.normal_subtags.count()):
        subtag = window.normal_subtags.item(index)
        subtag.setSelected(
            subtag.data(Qt.ItemDataRole.UserRole) == "cum")
    process_events(app)
    window._confirm_current_normal_crop()
    process_events(app)
    canonical = [item for item in database.current_training_examples()
                 if item["proposal_id"] == proposal_id]
    if not canonical:
        raise AssertionError("Face Normal Processing confirmation did not create a training example.")
    interactions.append({
        "category": "body_images",
        "main_tag": "boobs",
        "subtags": ["cum"],
        "proposal_id": proposal_id,
        "training_examples": len(canonical),
    })
    reloaded_item = None
    for index in range(window.normal_gallery.count()):
        item = window.normal_gallery.item(index)
        row = item.data(Qt.ItemDataRole.UserRole)
        if row and int(row["id"]) == proposal_id:
            reloaded_item = item
            break
    if reloaded_item is None:
        raise AssertionError("Normal Processing item disappeared after confirmation.")
    window.normal_gallery.setCurrentItem(reloaded_item)
    process_events(app)
    restored = window.normal_gallery.currentItem()
    restored_row = restored.data(Qt.ItemDataRole.UserRole) if restored else {}
    reloaded_db_row = next(
        (row for row in database.normal_crop_records()
         if int(row["id"]) == proposal_id),
        None,
    )
    if not reloaded_db_row or not reloaded_db_row.get("normal_confirmed"):
        raise AssertionError("Normal Processing saved state was not persisted in the disposable database.")
    if window.normal_assign_category.currentData() != "body_images":
        raise AssertionError("Normal Processing category was not restored in the real widget.")
    for width, height in resolutions:
        window.resize(width, height)
        window.workspace_tabs.setCurrentIndex(0)
        process_events(app)
        scroll = window.findChild(QScrollArea, "NormalClassificationScroll")
        if scroll is not None:
            scroll.ensureWidgetVisible(window.normal_filename_preview)
            process_events(app)
        path = output_root / "newassetapp" / f"{width}x{height}_normal_processing.png"
        if capture:
            screenshots.append(capture_widget(
                window, path, f"{width}x{height}_normal_processing.png",
                "newassetapp", "normal_processing", width, height))
    window.close()
    process_events(app)
    return {"pass": True, "screenshots": screenshots,
            "database": str(fixture.app_database),
            "interactions": interactions,
            "note": "Body Images face crop was selected, confirmed in the real widget, reloaded, and verified against the disposable database."}
