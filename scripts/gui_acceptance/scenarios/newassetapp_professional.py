from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt

from app.application import create_application
from app.config import AppConfig
from app.core.database import Database

from ..assertions import assert_visible
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
    window.current_category = "sources"
    window._refresh_gallery()
    process_events(app)
    if window.gallery.count():
        window.gallery.setCurrentRow(0)
        process_events(app)
        current = window.gallery.currentItem()
        if current:
            window._selection_changed(current, None)
            process_events(app)
    if not getattr(window, "_all_detection_boxes", []):
        raise AssertionError("Professional fixture source did not expose detection boxes.")
    window.detection_filter.setCurrentIndex(window.detection_filter.findData("all"))
    window._refresh_professional_detection_view()
    process_events(app)
    if window.detection_list.count() < 2:
        raise AssertionError("Professional fixture did not expose multiple detections.")
    first = window.detection_list.item(0)
    window.detection_list.setCurrentItem(first)
    process_events(app)
    first_id = int(first.data(Qt.ItemDataRole.UserRole))
    if window.detection_list.currentRow() != 0:
        raise AssertionError("Professional detection selection did not update.")
    if window.detection_list.count() > 1:
        window.detection_list.setCurrentRow(1)
        process_events(app)
        second_id = int(window.detection_list.currentItem().data(Qt.ItemDataRole.UserRole))
        if second_id == first_id:
            raise AssertionError("Professional previous/next detection selection stayed on the same detection.")
    for width, height in resolutions:
        window.resize(width, height)
        window.workspace_tabs.setCurrentIndex(1)
        process_events(app)
        assert_visible(window.detection_list, "Professional detection list")
        assert_visible(window.inspector_tabs, "Professional inspector tabs")
        path = output_root / "newassetapp" / f"{width}x{height}_professional_review.png"
        if capture:
            screenshots.append(capture_widget(
                window, path, f"{width}x{height}_professional_review.png",
                "newassetapp", "professional_review", width, height))
    interactions = [{"first_detection_id": first_id, "second_detection_id": second_id if window.detection_list.count() > 1 else None}]
    window.close()
    process_events(app)
    return {"pass": True, "screenshots": screenshots,
            "interactions": interactions,
            "database": str(fixture.app_database)}
