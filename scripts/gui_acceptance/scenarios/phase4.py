from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog

from app.application import create_application
from app.config import AppConfig
from app.core.database import Database
from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.gui import StudioWindow
from TrainingDatasetStudio.studio.store import StudioStore

from ..qt_helpers import process_events
from ..screenshot_capture import capture_widget


def _elapsed(start: float) -> float:
    return round(time.monotonic() - start, 3)


def _write_phase4_manifest(fixture, output_root: Path, name: str, status: str,
                           details: dict) -> None:
    manifest_root = output_root / "manifests"
    manifest_root.mkdir(parents=True, exist_ok=True)
    project = Path(__file__).resolve().parents[3]
    production_db = (project / "data" / "newassetapp.sqlite3").resolve()
    production_studio_db = (
        project / "TrainingDatasetStudio" / "data" / "studio.sqlite3").resolve()
    manifest = {
        "isolation": "PASS",
        "scenario": name,
        "status": status,
        "run_root": str(fixture.root.resolve()),
        "newassetapp_database": str(fixture.app_database.resolve()),
        "studio_database": str(fixture.studio_database.resolve()),
        "synthetic_source": str(fixture.source_path.resolve()),
        "production_databases": [
            str(production_db),
            str(production_studio_db),
        ],
        "production_database_touched": False,
        **details,
    }
    (manifest_root / f"{name}.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _capture(window, output_root: Path, name: str, app_name: str, scenario: str,
             width: int, height: int, capture: bool, screenshots: list[dict]) -> None:
    if not capture:
        return
    path = output_root / app_name / f"{width}x{height}_{name}.png"
    screenshots.append(capture_widget(
        window, path, path.name, app_name, scenario, width, height,
        capture_mode="REAL_APP_QT_WIDGET_CAPTURE"))


def run_normal_body_states(app, fixture, output_root: Path, resolutions, capture: bool = True):
    started = time.monotonic()
    screenshots = []
    config = AppConfig(
        data_dir_override=fixture.root / "app" / "data",
        output_dir_override=fixture.output_dir,
        logs_dir_override=fixture.root / "app" / "logs",
        database_path_override=fixture.app_database,
    )
    database = Database(fixture.app_database)
    window = create_application(config)
    window.show()
    process_events(app)
    window.folder_edit.setText(str(fixture.source_path.parent))
    window._refresh_normal_gallery()
    process_events(app)

    combinations = (
        ("false_false", False, False, True),
        ("true_false", True, False, True),
        ("false_true", False, True, True),
        ("true_true", True, True, True),
        ("pending_pending", None, None, False),
        ("cum_partial", True, None, False),
        ("accessory_partial", None, True, False),
    )
    available = []
    for index in range(window.normal_gallery.count()):
        item = window.normal_gallery.item(index)
        row = item.data(Qt.ItemDataRole.UserRole)
        if row:
            available.append(dict(row))
    if len(available) < len(combinations):
        raise AssertionError("Fixture needs at least seven independent Normal Processing crops.")

    results = []
    for (label, cum, accessory, completed), row in zip(combinations, available):
        proposal_id = int(row["id"])
        item = next(
            (window.normal_gallery.item(index)
             for index in range(window.normal_gallery.count())
             if (window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)
                 and int(window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)["id"]) == proposal_id)),
            None,
        )
        if item is None:
            raise AssertionError(f"{label}: disposable crop disappeared before interaction.")
        window.normal_gallery.setCurrentItem(item)
        process_events(app)
        window.normal_assign_category.setCurrentIndex(
            window.normal_assign_category.findData("body_images"))
        process_events(app)
        if window.normal_body_tag.count() > 1:
            window.normal_body_tag.setCurrentIndex(1)
        window.normal_body_cum.setCheckState(
            Qt.CheckState.Checked if cum is True else
            Qt.CheckState.Unchecked if cum is False else
            Qt.CheckState.PartiallyChecked)
        window.normal_body_accessory.setCheckState(
            Qt.CheckState.Checked if accessory is True else
            Qt.CheckState.Unchecked if accessory is False else
            Qt.CheckState.PartiallyChecked)
        window.normal_body_completed.setChecked(completed)
        process_events(app)
        window.normal_apply_category_button.click()
        process_events(app)

        reloaded = next(row for row in database.normal_crop_records()
                        if int(row["id"]) == proposal_id)
        if cum is not None:
            if not reloaded["normal_body_images_cum_evaluated"]:
                raise AssertionError(f"{label}: Cum evaluation was not persisted.")
            if bool(reloaded["normal_body_images_cum_target"]) is not bool(cum):
                raise AssertionError(f"{label}: Cum target did not persist.")
        else:
            if reloaded["normal_body_images_cum_evaluated"]:
                raise AssertionError(f"{label}: Cum pending was converted to evaluated.")
        if accessory is not None:
            if not reloaded["normal_body_images_accessory_evaluated"]:
                raise AssertionError(f"{label}: Accessory evaluation was not persisted.")
            if bool(reloaded["normal_body_images_accessory_target"]) is not bool(accessory):
                raise AssertionError(f"{label}: Accessory target did not persist.")
        else:
            if reloaded["normal_body_images_accessory_evaluated"]:
                raise AssertionError(f"{label}: Accessory pending was converted to evaluated.")
        if bool(reloaded["normal_body_images_completed"]) is not completed:
            raise AssertionError(f"{label}: Completion state did not persist.")

        window.normal_gallery.setCurrentRow(max(0, window.normal_gallery.currentRow() - 1))
        process_events(app)
        fresh_item = next(
            (window.normal_gallery.item(index)
             for index in range(window.normal_gallery.count())
             if (window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)
                 and int(window.normal_gallery.item(index).data(Qt.ItemDataRole.UserRole)["id"]) == proposal_id)),
            None,
        )
        if fresh_item is None:
            raise AssertionError(f"{label}: crop disappeared after reload.")
        window.normal_gallery.setCurrentItem(fresh_item)
        process_events(app)
        results.append({
            "fixture_id": label,
            "proposal_id": proposal_id,
            "cum": cum,
            "accessory": accessory,
            "completed": completed,
            "reload_confirmed": bool(reloaded["normal_confirmed"]),
        })

    for width, height in resolutions:
        window.resize(width, height)
        process_events(app)
        _capture(window, output_root, "normal_body_states", "newassetapp",
                 "phase4_normal_body_states", width, height, capture, screenshots)
    window.close()
    process_events(app)
    result = {
        "pass": True,
        "screenshots": screenshots,
        "elapsed_seconds": _elapsed(started),
        "status": "PASS_REAL_APP_QT",
        "interactions": results,
    }
    _write_phase4_manifest(
        fixture, output_root, "phase4_normal_body_states", "PASS_REAL_APP_QT",
        {"elapsed_seconds": result["elapsed_seconds"], "interactions": results})
    return result


def run_professional_review(app, fixture, output_root: Path, resolutions, capture: bool = True):
    started = time.monotonic()
    screenshots = []
    config = AppConfig(
        data_dir_override=fixture.root / "app" / "data",
        output_dir_override=fixture.output_dir,
        logs_dir_override=fixture.root / "app" / "logs",
        database_path_override=fixture.app_database,
    )
    database = Database(fixture.app_database)
    window = create_application(config)
    window.show()
    process_events(app)
    window.folder_edit.setText(str(fixture.source_path.parent))
    window._refresh_navigation()
    process_events(app)
    window.workspace_tabs.setCurrentIndex(1)
    process_events(app)

    window.current_category = "sources"
    window._refresh_gallery()
    process_events(app)
    if window.gallery.count() == 0:
        raise AssertionError("Professional Review fixture contains no source image.")
    window.gallery.setCurrentRow(0)
    process_events(app)
    source_id = window._active_source_id
    detections = database.detections_for_source(source_id)
    if len(detections) < 2:
        raise AssertionError("Professional Review fixture needs overlapping detections.")

    selected_rows = []
    for detection in detections[:2]:
        window.detection_list.setCurrentRow(
            next(index for index in range(window.detection_list.count())
                 if int(window.detection_list.item(index).data(Qt.ItemDataRole.UserRole))
                 == int(detection["id"])))
        process_events(app)
        selected_rows.append({
            "detection_id": int(detection["id"]),
            "class_name": detection["class_name"],
            "bbox_xyxy": detection["bbox_xyxy"],
        })

    first = detections[0]
    window.detection_list.setCurrentRow(
        next(index for index in range(window.detection_list.count())
             if int(window.detection_list.item(index).data(Qt.ItemDataRole.UserRole))
             == int(first["id"])))
    process_events(app)

    original_bbox = list(first["bbox_xyxy"])
    original_class = str(first["class_name"])
    original_detections = database.detections_for_source(source_id)
    original_row = next(row for row in original_detections if int(row["id"]) == int(first["id"]))

    target_index = window.inspector_class_combo.findText(
        "Boobs", Qt.MatchFixedString)
    if target_index < 0:
        target_index = window.inspector_class_combo.findText(
            "Face", Qt.MatchFixedString)
    window.inspector_class_combo.setCurrentIndex(max(0, target_index))
    window.inspector_class_button.click()
    process_events(app)

    corrected = database.detections_for_source(source_id)
    corrected_row = next(row for row in corrected if int(row["id"]) == int(first["id"]))

    # Resize the selected real preview box through Qt mouse events.
    window.preview.select_box(int(first["id"]))
    process_events(app)
    rect = window.preview._display_rect(corrected_row)
    start = rect.bottomRight() - QPointF(2, 2)
    end = start + QPointF(12, 12)
    QTest.mousePress(window.preview, Qt.MouseButton.LeftButton, pos=start.toPoint())
    QTest.mouseMove(window.preview, start.toPoint())
    QTest.mouseMove(window.preview, end.toPoint())
    QTest.mouseRelease(window.preview, Qt.MouseButton.LeftButton, pos=end.toPoint())
    process_events(app)
    corrected = database.detections_for_source(source_id)
    corrected_row = next(row for row in corrected if int(row["id"]) == int(first["id"]))
    with database.connect() as connection:
        immutable = connection.execute(
            "SELECT class_name,x1,y1,x2,y2 FROM yolo_detections WHERE id=?",
            (int(first["id"]),),
        ).fetchone()
    if str(immutable["class_name"]) != original_class:
        raise AssertionError("Original YOLO class was mutated.")
    immutable_bbox = [
        float(immutable["x1"]), float(immutable["y1"]),
        float(immutable["x2"]), float(immutable["y2"]),
    ]
    if immutable_bbox != original_bbox:
        raise AssertionError("Original YOLO bbox was mutated.")

    if (window.inspector_tabs.count() != 1
            or window.inspector_tabs.tabText(0) != "Detection"
            or hasattr(window, "review_button")
            or hasattr(window, "inspector_tasks")):
        raise AssertionError("Professional Review must expose YOLO/BBox correction only.")
    if not all(hasattr(window, name) for name in (
            "normal_assign_category", "normal_apply_category_button",
            "normal_fullbody_cnn_target", "normal_body_cum",
            "normal_arousal_target", "normal_corruption_target")):
        raise AssertionError("Normal Processing classification controls are unavailable.")

    for width, height in resolutions:
        window.resize(width, height)
        process_events(app)
        _capture(window, output_root, "professional_review", "newassetapp",
                 "phase4_professional_review", width, height, capture, screenshots)
    window.close()
    process_events(app)
    result = {
        "pass": True,
        "screenshots": screenshots,
        "elapsed_seconds": _elapsed(started),
        "status": "PASS_REAL_APP_QT",
        "selected_rows": selected_rows,
        "original_bbox": original_bbox,
        "original_class": original_class,
        "corrected_class": corrected_row["class_name"],
        "classification_controls": "Normal Processing",
    }
    _write_phase4_manifest(
        fixture, output_root, "phase4_professional_review", "PASS_REAL_APP_QT",
        {"elapsed_seconds": result["elapsed_seconds"], "selected_rows": selected_rows,
         "original_bbox": original_bbox, "original_class": original_class,
         "corrected_class": corrected_row["class_name"],
         "classification_controls": "Normal Processing",
         "workflow_split": "Professional Review exposes YOLO/BBox correction only."})
    return result


def _open_studio(app, fixture):
    config = StudioConfig.for_acceptance(fixture.root / "studio")
    config.ensure_directories()
    store = StudioStore(config.database_path)
    store.initialize()
    window = StudioWindow(config, store)
    window.show()
    process_events(app)
    return config, store, window


def run_studio_import(app, fixture, output_root: Path, resolutions, capture: bool = True):
    started = time.monotonic()
    screenshots = []
    config, store, window = _open_studio(app, fixture)
    bundle_dirs = [path for path in fixture.handoff_dir.iterdir()
                   if path.is_dir() and (path / "manifest.json").is_file()]
    if not bundle_dirs:
        raise AssertionError("Disposable handoff fixture did not produce a bundle.")
    window.studio_navigation.setCurrentRow(7)
    process_events(app)
    window.bundle_path.setText(str(bundle_dirs[0]))
    window.import_button.click()
    process_events(app)
    accepted = store.list_records(status="accepted")
    if not accepted:
        raise AssertionError("Real Studio import button produced no accepted records.")

    window.studio_navigation.setCurrentRow(3)
    process_events(app)
    window.record_list.setCurrentRow(0)
    process_events(app)
    window.studio_navigation.setCurrentRow(0)
    process_events(app)
    for width, height in resolutions:
        window.resize(width, height)
        process_events(app)
        _capture(window, output_root, "studio_import", "studio",
                 "phase4_studio_import", width, height, capture, screenshots)
    window.close()
    process_events(app)
    result = {
        "pass": True,
        "screenshots": screenshots,
        "elapsed_seconds": _elapsed(started),
        "status": "PASS_REAL_APP_QT",
        "accepted_records": len(accepted),
    }
    _write_phase4_manifest(
        fixture, output_root, "phase4_studio_import", "PASS_REAL_APP_QT",
        {"elapsed_seconds": result["elapsed_seconds"],
         "accepted_records": len(accepted)})
    return result


def run_studio_lifecycle(app, fixture, output_root: Path, resolutions, capture: bool = True):
    started = time.monotonic()
    timing = {}
    screenshots = []
    config, store, window = _open_studio(app, fixture)

    stage = time.monotonic()
    bundle_dirs = [path for path in fixture.handoff_dir.iterdir()
                   if path.is_dir() and (path / "manifest.json").is_file()]
    if not bundle_dirs:
        raise AssertionError("Disposable handoff fixture did not produce a bundle.")
    window.studio_navigation.setCurrentRow(7)
    process_events(app)
    window.bundle_path.setText(str(bundle_dirs[0]))
    window.import_button.click()
    process_events(app)
    timing["import"] = _elapsed(stage)
    if not store.list_records(status="accepted"):
        raise AssertionError("Import stage produced no accepted records.")

    stage = time.monotonic()
    window.studio_navigation.setCurrentRow(3)
    process_events(app)
    window.record_list.setCurrentRow(0)
    process_events(app)
    record = window.current_record
    if record is None:
        raise AssertionError("Dataset Records did not select an imported record.")
    window.studio_navigation.setCurrentRow(2)
    process_events(app)
    window.dataset_name.setText("Phase 4 disposable dataset")
    if window.dataset_task.findText(record["task"]) < 0:
        window.dataset_task.addItem(record["task"])
    window.dataset_task.setCurrentText(record["task"])
    window.dataset_registry.setText(record["registry_id"] or "")
    window.dataset_registry_version.setText(record["registry_version"] or "")
    window.create_dataset_button.click()
    process_events(app)
    if not window.dataset_combo.count():
        raise AssertionError("Real Dataset Builder did not create a dataset.")
    window.create_version_button.click()
    process_events(app)
    version_id = window.version_combo.currentData()
    if version_id is None:
        raise AssertionError("Real Dataset Builder did not create a draft version.")
    timing["dataset_version"] = _elapsed(stage)

    stage = time.monotonic()
    window.studio_navigation.setCurrentRow(4)
    process_events(app)
    window.refresh_validation()
    process_events(app)
    timing["validation"] = _elapsed(stage)

    stage = time.monotonic()
    window.studio_navigation.setCurrentRow(2)
    process_events(app)
    window.finalize_version_button.click()
    process_events(app)
    finalized = next(row for row in store.list_versions() if int(row["id"]) == int(version_id))
    if not finalized["finalized"]:
        raise AssertionError("Real finalize action did not create an immutable version.")
    timing["finalize"] = _elapsed(stage)

    stage = time.monotonic()
    window.studio_navigation.setCurrentRow(5)
    process_events(app)
    with patch.object(QFileDialog, "getExistingDirectory",
                      return_value=str(fixture.output_dir)):
        with patch("TrainingDatasetStudio.studio.gui.QMessageBox.information",
                   return_value=None):
            window.export_colab_button.click()
            process_events(app)
    timing["package"] = _elapsed(stage)

    package_dirs = [
        path for path in fixture.output_dir.iterdir()
        if path.is_dir() and (path / "metadata.json").is_file()
    ]
    if not package_dirs:
        raise AssertionError("Real package export action did not produce metadata.json.")
    package_root = package_dirs[-1]
    if not (package_root / "hash_manifest.json").is_file():
        raise AssertionError("Package export did not produce hash_manifest.json.")

    for width, height in resolutions:
        window.resize(width, height)
        process_events(app)
        _capture(window, output_root, "studio_lifecycle", "studio",
                 "phase4_studio_lifecycle", width, height, capture, screenshots)
    window.close()
    process_events(app)
    result = {
        "pass": True,
        "screenshots": screenshots,
        "elapsed_seconds": _elapsed(started),
        "stage_timing": timing,
        "status": "PASS_REAL_APP_QT",
        "version_id": int(version_id),
        "package_path": str(package_root),
    }
    _write_phase4_manifest(
        fixture, output_root, "phase4_studio_lifecycle", "PASS_REAL_APP_QT",
        {"elapsed_seconds": result["elapsed_seconds"],
         "stage_timing": timing, "version_id": int(version_id),
         "package_path": str(package_root)})
    return result
