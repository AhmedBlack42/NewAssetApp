from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox

from app.application import create_application
from app.config import AppConfig
from app.core.database import Database
from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.gui import StudioWindow
from TrainingDatasetStudio.studio.store import StudioStore

from ..qt_helpers import process_events
from ..screenshot_capture import capture_widget


def _overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def _write_manifest(fixture, output_root: Path) -> dict:
    project = Path(__file__).resolve().parents[3]
    production = {
        "newassetapp_db": (project / "data" / "newassetapp.sqlite3").resolve(),
        "studio_db": (project / "TrainingDatasetStudio" / "data" / "studio.sqlite3").resolve(),
        "newassetapp_data": (project / "data").resolve(),
        "studio_root": (project / "TrainingDatasetStudio").resolve(),
    }
    app_paths = [
        fixture.app_database.resolve(),
        (fixture.root / "app" / "data").resolve(),
        fixture.output_dir.resolve(),
        (fixture.root / "app" / "logs").resolve(),
    ]
    studio_paths = [
        fixture.studio_database.resolve(),
        (fixture.root / "studio").resolve(),
    ]
    for path in app_paths + studio_paths:
        if not _overlap(fixture.root.resolve(), path):
            raise AssertionError(f"Disposable acceptance path escapes root: {path}")
        for production_path in production.values():
            if _overlap(path, production_path):
                raise AssertionError(f"Acceptance path overlaps production storage: {path}")
    if _overlap(fixture.app_database.resolve(), fixture.studio_database.resolve()):
        raise AssertionError("NewAssetApp and Studio databases overlap.")

    manifest = {
        "isolation": "PASS",
        "run_root": str(fixture.root.resolve()),
        "newassetapp_database": str(fixture.app_database.resolve()),
        "newassetapp_data": str((fixture.root / "app" / "data").resolve()),
        "newassetapp_output": str(fixture.output_dir.resolve()),
        "studio_database": str(fixture.studio_database.resolve()),
        "studio_root": str((fixture.root / "studio").resolve()),
        "production_database_touched": False,
        "synthetic_source": str(fixture.source_path.resolve()),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "isolation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def run(app, fixture, output_root: Path, resolutions, capture: bool = True):
    manifest = _write_manifest(fixture, output_root / "manifests")
    screenshots = []

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
    window.folder_edit.setText(str(fixture.source_path.parent))
    window._refresh_normal_gallery()
    process_events(app)

    body_item = None
    for index in range(window.normal_gallery.count()):
        item = window.normal_gallery.item(index)
        row = item.data(Qt.ItemDataRole.UserRole)
        if row and str(row.get("yolo_class_name") or "").casefold() == "boobs":
            body_item = item
            break
    if body_item is None:
        raise AssertionError("Disposable fixture did not produce a real body-images crop.")

    window.normal_gallery.setCurrentItem(body_item)
    process_events(app)
    proposal_id = int(body_item.data(Qt.ItemDataRole.UserRole)["id"])
    window.normal_assign_category.setCurrentIndex(window.normal_assign_category.findData("body_images"))
    tag_index = window.normal_body_tag.findData("boobs")
    if tag_index < 0:
        tag_index = next(
            (index for index in range(window.normal_body_tag.count())
             if window.normal_body_tag.itemData(index) is not None),
            0,
        )
    window.normal_body_tag.setCurrentIndex(tag_index)
    window.normal_body_cum.setCheckState(Qt.CheckState.Checked)
    window.normal_body_accessory.setCheckState(Qt.CheckState.Unchecked)
    window.normal_body_completed.setChecked(True)
    process_events(app)
    window._normal_category_choice_changed(record_draft=False)
    process_events(app)
    if not window.normal_apply_category_button.isEnabled():
        raise AssertionError("Real Normal Processing confirmation button remained disabled after complete GUI choices.")
    window.normal_apply_category_button.click()
    process_events(app)
    for dialog in app.topLevelWidgets():
        if isinstance(dialog, QMessageBox) and dialog.isVisible():
            text = " ".join(label.text() for label in dialog.findChildren(QLabel) if label.text())
            raise AssertionError(f"Real Normal Processing confirmation opened a blocking dialog: {text}")

    reloaded = next(
        (row for row in database.normal_crop_records() if int(row["id"]) == proposal_id),
        None,
    )
    if not reloaded or not reloaded.get("normal_confirmed"):
        raise AssertionError("Real Normal Processing button did not persist a confirmed state.")
    if bool(reloaded.get("normal_body_images_cum_target")) is not True:
        raise AssertionError(
            f"Cum target did not persist as explicitly positive. "
            f"status={window.status_label.currentMessage()!r} reloaded={reloaded}"
        )
    if bool(reloaded.get("normal_body_images_accessory_target")) is not False:
        raise AssertionError("Accessory target did not persist as explicitly negative.")

    window.normal_gallery.setCurrentRow(max(0, window.normal_gallery.currentRow() - 1))
    process_events(app)
    reloaded_item = next(
        (window.normal_gallery.item(index)
         for index in range(window.normal_gallery.count())
         if (window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)
             and int(window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)["id"]) == proposal_id)),
        None,
    )
    if reloaded_item is None:
        raise AssertionError("Confirmed Normal Processing crop disappeared after reload.")
    window.normal_gallery.setCurrentItem(reloaded_item)
    process_events(app)
    if window.normal_assign_category.currentData() != "body_images":
        raise AssertionError("Normal Processing category did not reload through the real widget.")

    for width, height in resolutions:
        window.resize(width, height)
        process_events(app)
        path = output_root / "real_app_qt_newassetapp" / f"{width}x{height}_normal_real_qt.png"
        if capture:
            screenshots.append(capture_widget(
                window, path, path.name, "newassetapp", "phase3_real_normal", width, height,
                capture_mode="REAL_APP_QT_WIDGET_CAPTURE"))
    window.close()
    process_events(app)

    studio_config = StudioConfig.for_acceptance(fixture.root / "studio")
    studio_config.ensure_directories()
    studio_store = StudioStore(studio_config.database_path)
    studio_store.initialize()
    studio_window = StudioWindow(studio_config, studio_store)
    studio_window.show()
    process_events(app)

    expected_pages = [
        "Model Projects", "Dataset Segments", "Dataset Builder", "Dataset Records",
        "Validation", "Colab Packages", "Model Artifacts", "Import / Activation", "History",
    ]
    if studio_window.studio_navigation.count() != studio_window.studio_pages.count():
        raise AssertionError("Studio navigation and stacked page counts differ.")
    actual_labels = [
        studio_window.studio_navigation.item(row).text()
        for row in range(studio_window.studio_navigation.count())
    ]
    if actual_labels != expected_pages:
        raise AssertionError(f"Unexpected Studio navigation inventory: {actual_labels}")
    navigation_map = []
    for row in range(studio_window.studio_navigation.count()):
        studio_window.studio_navigation.setCurrentRow(row)
        process_events(app)
        if studio_window.studio_pages.currentIndex() != row:
            raise AssertionError(f"Studio row {row} did not open the corresponding page.")
        navigation_map.append({
            "row": row,
            "label": actual_labels[row],
            "page_object": studio_window.studio_pages.currentWidget().objectName()
                or studio_window.studio_pages.currentWidget().__class__.__name__,
        })
        for width, height in resolutions:
            studio_window.resize(width, height)
            process_events(app)
            label = actual_labels[row].lower().replace(" ", "_").replace("/", "_")
            path = output_root / "real_app_qt_studio" / f"{width}x{height}_{label}.png"
            if capture:
                screenshots.append(capture_widget(
                    studio_window, path, path.name, "studio",
                    f"phase3_navigation_{label}", width, height,
                    capture_mode="REAL_APP_QT_WIDGET_CAPTURE"))

    studio_window.close()
    process_events(app)
    (output_root / "manifests" / "phase3_navigation.json").write_text(
        json.dumps({"navigation_map": navigation_map, "status": "PASS_REAL_APP_QT"},
                   indent=2) + "\n", encoding="utf-8")

    return {
        "pass": True,
        "screenshots": screenshots,
        "manifest": manifest,
        "proposal_id": proposal_id,
        "navigation_map": navigation_map,
        "status": "PASS_REAL_APP_QT",
    }
