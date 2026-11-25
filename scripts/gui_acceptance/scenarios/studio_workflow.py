from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.store import StudioStore
from TrainingDatasetStudio.studio.gui import StudioWindow
from TrainingDatasetStudio.studio.datasets import DatasetService

from ..qt_helpers import process_events
from .studio_smoke import run as studio_smoke


def run(app, fixture, output_root, resolutions, capture: bool = True):
    result = studio_smoke(app, fixture, output_root, resolutions, capture=capture)
    config = StudioConfig(root=fixture.root / "studio")
    config.ensure_directories()
    store = StudioStore(config.database_path)
    store.initialize()
    window = StudioWindow(config, store)
    window.show()
    process_events(app)
    bundle_dirs = [path for path in fixture.handoff_dir.iterdir()
                   if path.is_dir() and (path / "manifest.json").is_file()]
    if not bundle_dirs:
        raise AssertionError("Disposable NewAssetApp handoff bundle was not generated.")
    window.studio_navigation.setCurrentRow(7)
    process_events(app)
    window.staging_bundle_path.setText(str(bundle_dirs[0]))
    window.staging_import_button.click()
    process_events(app)
    accepted = [record for record in store.list_records(status="accepted")]
    if not accepted:
        raise AssertionError("Studio import produced no accepted records.")
    window.studio_navigation.setCurrentRow(3)
    process_events(app)
    window.record_list.setCurrentRow(0)
    process_events(app)
    record = window.current_record
    if record is None:
        raise AssertionError("Studio Dataset Records did not select an imported record.")
    window.studio_navigation.setCurrentRow(2)
    process_events(app)
    window.dataset_name.setText("Disposable GUI acceptance dataset")
    window.dataset_task.setCurrentText(record["task"])
    window.dataset_registry.setText(record["registry_id"] or "")
    window.dataset_registry_version.setText(record["registry_version"] or "")
    window.create_dataset_button.click()
    process_events(app)
    if not window.dataset_combo.count():
        raise AssertionError("Studio did not create a disposable dataset.")
    window.create_version_button.click()
    process_events(app)
    version_id = window.version_combo.currentData()
    if version_id is None:
        raise AssertionError("Studio did not create a dataset version.")
    window.finalize_version_button.click()
    process_events(app)
    package_root = fixture.output_dir / "gui_acceptance_colab_package"
    with patch.object(QFileDialog, "getExistingDirectory", return_value=str(fixture.output_dir)):
        with patch("TrainingDatasetStudio.studio.gui.QMessageBox.information", return_value=None):
            window.export_colab_button.click()
            process_events(app)
    package_dirs = [
        path for path in fixture.output_dir.iterdir()
        if path.is_dir() and (path / "metadata.json").is_file()
    ]
    if not package_dirs:
        raise AssertionError("Studio package did not produce metadata.json.")
    package_root = package_dirs[-1]
    if not (package_root / "hash_manifest.json").is_file():
        raise AssertionError("Studio package did not produce hash_manifest.json.")
    window.close()
    process_events(app)
    result["interactions"] = [{
        "accepted_records": len(accepted),
        "dataset_name": "Disposable GUI acceptance dataset",
        "version_id": int(version_id),
        "package_records": len(store.version_rows(int(version_id))),
        "package_path": str(package_root),
    }]
    result["note"] = "Studio import, record selection, dataset creation, immutable version finalization, and Colab package export were exercised with disposable data."
    return result
