from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, Signal, QUrl
from PySide6.QtGui import QColor, QBrush, QPen, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGraphicsRectItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QFrame, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from .config import StudioConfig
from .datasets import DatasetError, DatasetService
from .importer import BundleImporter
from .store import StudioStore
from .training import TrainingManager, cpu_compatibility


logger = logging.getLogger("training_dataset_studio")


class BoxItem(QGraphicsRectItem):
    def __init__(self, rect: QRectF):
        super().__init__(rect)
        self._resize = False
        self._press = None
        self.setFlags(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setZValue(3)
        self.setPen(QPen(QColor(75, 230, 145, 230), 3))
        self.setBrush(QBrush(QColor(75, 230, 145, 25)))

    def paint(self, painter, option, widget=None):
        painter.save()
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 206, 75, 255), 4))
            painter.setBrush(QBrush(QColor(255, 206, 75, 36)))
        else:
            painter.setPen(QPen(QColor(75, 230, 145, 225), 3))
            painter.setBrush(QBrush(QColor(75, 230, 145, 24)))
        painter.drawRect(self.rect())
        if self.isSelected():
            painter.setBrush(QColor(255, 206, 75, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(self.rect().right() - 6, self.rect().bottom() - 6, 12, 12)
        painter.restore()

    def mousePressEvent(self, event):
        rect = self.rect()
        local = event.pos()
        self._resize = abs(local.x() - rect.right()) < 12 and abs(local.y() - rect.bottom()) < 12
        if self._resize:
            self._press = local
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize and self._press is not None:
            rect = self.rect()
            delta = event.pos() - self._press
            rect.setRight(max(rect.left() + 4, rect.right() + delta.x()))
            rect.setBottom(max(rect.top() + 4, rect.bottom() + delta.y()))
            self.setRect(rect)
            self._press = event.pos()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize = False
        self._press = None
        super().mouseReleaseEvent(event)


class ReviewView(QGraphicsView):
    box_drawn = Signal(QRectF)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setBackgroundBrush(QColor(18, 21, 28))
        self.drawing = False
        self._start = None
        self._rubber = None
        self.pixmap_item = None

    def set_pixmap(self, pixmap: QPixmap):
        self.scene().clear()
        self.pixmap_item = self.scene().addPixmap(pixmap)
        self.pixmap_item.setZValue(0)
        self.scene().setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event):
        if self.drawing and event.button() == Qt.MouseButton.LeftButton and self.pixmap_item:
            self._start = self.mapToScene(event.position().toPoint())
            self._rubber = self.scene().addRect(QRectF(self._start, self._start),
                QPen(QColor(255, 206, 75, 230), 2, Qt.PenStyle.DashLine), QBrush(QColor(255, 206, 75, 25)))
            self._rubber.setZValue(4)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drawing and self._rubber is not None and self._start is not None:
            self._rubber.setRect(QRectF(self._start, self.mapToScene(event.position().toPoint())).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drawing and self._rubber is not None:
            rect = self._rubber.rect().normalized()
            self.scene().removeItem(self._rubber)
            self._rubber = None; self._start = None; self.drawing = False
            if rect.width() >= 4 and rect.height() >= 4:
                self.box_drawn.emit(rect)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pixmap_item:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class StudioWindow(QMainWindow):
    def __init__(self, config: StudioConfig, store: StudioStore):
        super().__init__()
        self.config = config
        self.store = store
        self.importer = BundleImporter(config, store)
        self.datasets = DatasetService(store, config.output_dir)
        self.training = TrainingManager(store, config.output_dir)
        self.current_record = None
        self.current_pixmap = QPixmap()
        self.box_item: BoxItem | None = None
        self._loading_version = False
        self.setWindowTitle("TrainingDatasetStudio")
        self.resize(1440, 920)
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)

        navigation = QFrame()
        navigation.setObjectName("StudioNavigation")
        navigation.setMinimumWidth(190)
        navigation.setMaximumWidth(220)
        navigation_layout = QVBoxLayout(navigation)
        brand = QLabel("TrainingDatasetStudio")
        brand.setObjectName("StudioBrand")
        brand.setWordWrap(True)
        navigation_layout.addWidget(brand)
        navigation_layout.addWidget(QLabel("WORKSPACE"))
        self.studio_navigation = QListWidget()
        self.studio_navigation.setObjectName("StudioNavigationList")
        for label in ("Model Projects", "Dataset Segments", "Dataset Builder",
                      "Dataset Records", "Validation", "Colab Packages",
                      "Model Artifacts", "Import / Activation", "History"):
            self.studio_navigation.addItem(label)
        navigation_layout.addWidget(self.studio_navigation, 1)
        root_layout.addWidget(navigation)

        self.studio_pages = QStackedWidget()
        self.studio_projects_page = self._projects_page()
        self.studio_segments_page = self._segments_page()
        self.studio_builder_page = self._dataset_page()
        self.studio_records_page = self._review_page()
        self.studio_validation_page = self._validation_page()
        self.studio_packages_page = self._packages_page()
        self.studio_artifacts_page = self._artifacts_page()
        self.studio_import_page = self._import_activation_page()
        self.studio_history_page = self._history_page()
        self.studio_pages.addWidget(self.studio_projects_page)
        self.studio_pages.addWidget(self.studio_segments_page)
        self.studio_pages.addWidget(self.studio_builder_page)
        self.studio_pages.addWidget(self.studio_records_page)
        self.studio_pages.addWidget(self.studio_validation_page)
        self.studio_pages.addWidget(self.studio_packages_page)
        self.studio_pages.addWidget(self.studio_artifacts_page)
        self.studio_pages.addWidget(self.studio_import_page)
        self.studio_pages.addWidget(self.studio_history_page)
        self.studio_navigation.currentRowChanged.connect(self._studio_navigation_changed)
        self.studio_navigation.setCurrentRow(0)
        root_layout.addWidget(self.studio_pages, 1)
        self.setCentralWidget(root)
        self._apply_studio_style()
        self.statusBar().showMessage("Studio storage and database are independent from NewAssetApp.")
        self.refresh_records()
        self.refresh_datasets()
        self.refresh_training_versions()
        self.refresh_projects()
        self.refresh_segments()
        self.refresh_validation()
        self.refresh_packages()
        self.refresh_artifacts()
        self.refresh_import_status()
        self.refresh_history()

    def _review_page(self):
        page = QWidget(); outer = QVBoxLayout(page)
        bar = QHBoxLayout()
        self.bundle_path = QLineEdit(); self.bundle_path.setPlaceholderText("Select a NewAssetApp bundle directory")
        browse = QPushButton("Browse…"); browse.clicked.connect(self._choose_bundle)
        self.import_button = QPushButton("Validate & Import Bundle"); self.import_button.clicked.connect(self._import_bundle)
        bar.addWidget(self.bundle_path, 1); bar.addWidget(browse); bar.addWidget(self.import_button)
        outer.addLayout(bar)
        self.import_result = QLabel("Bundles are copied into Studio storage; source bundles remain read-only.")
        self.import_result.setWordWrap(True); outer.addWidget(self.import_result)
        filters = QHBoxLayout()
        self.task_filter = QComboBox(); self.task_filter.addItem("All tasks", "all")
        self.status_filter = QComboBox()
        for value in ("all", "accepted", "warning", "quarantined", "rejected"):
            self.status_filter.addItem(value.title(), value)
        self.task_filter.currentIndexChanged.connect(self.refresh_records)
        self.status_filter.currentIndexChanged.connect(self.refresh_records)
        filters.addWidget(QLabel("Task")); filters.addWidget(self.task_filter)
        filters.addWidget(QLabel("Review")); filters.addWidget(self.status_filter)
        filters.addStretch(); outer.addLayout(filters)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.record_list = QListWidget(); self.record_list.currentItemChanged.connect(self._select_record)
        split.addWidget(self.record_list)
        right = QWidget(); right_layout = QVBoxLayout(right)
        self.record_header = QLabel("Select a record to inspect the original predictions and annotation.")
        self.record_header.setWordWrap(True); right_layout.addWidget(self.record_header)
        target_row = QHBoxLayout(); target_row.addWidget(QLabel("Human-confirmed task / registry"))
        self.target_task = QComboBox(); self.target_task.currentIndexChanged.connect(self._target_task_changed)
        target_row.addWidget(self.target_task, 1); right_layout.addLayout(target_row)
        self.preview = ReviewView(); self.preview.box_drawn.connect(self._box_drawn); right_layout.addWidget(self.preview, 1)
        controls = QHBoxLayout()
        self.class_list = QListWidget(); self.class_list.setMaximumHeight(125)
        self.class_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        controls.addWidget(self.class_list, 2)
        action_col = QVBoxLayout()
        self.add_box_button = QPushButton("Draw box"); self.add_box_button.clicked.connect(self._start_box)
        self.delete_box_button = QPushButton("Delete selected box"); self.delete_box_button.clicked.connect(self._delete_box)
        self.save_button = QPushButton("Save correction"); self.save_button.clicked.connect(self._save_correction)
        self.confirm_button = QPushButton("Confirm for training"); self.confirm_button.clicked.connect(self._confirm_record)
        self.reject_button = QPushButton("Reject record"); self.reject_button.clicked.connect(self._reject_record)
        self.history_button = QPushButton("Correction history"); self.history_button.clicked.connect(self._show_history)
        for button in (self.add_box_button, self.delete_box_button, self.save_button,
                       self.confirm_button, self.reject_button, self.history_button):
            action_col.addWidget(button)
        controls.addLayout(action_col, 1); right_layout.addLayout(controls)
        split.addWidget(right); split.setSizes([360, 1000]); outer.addWidget(split, 1)
        return page

    def _choose_bundle(self):
        path = QFileDialog.getExistingDirectory(self, "Choose NewAssetApp bundle", str(self.config.root.parent))
        if path:
            self.bundle_path.setText(path)

    def _projects_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("MODEL PROJECTS"))
        self.projects_summary = QLabel()
        self.projects_summary.setWordWrap(True)
        layout.addWidget(self.projects_summary)
        self.projects_table = QTableWidget(0, 5)
        self.projects_table.setHorizontalHeaderLabels(
            ["Model / Task", "Registry", "Segments", "Records", "Used bytes"])
        self.projects_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.projects_table, 1)
        refresh = QPushButton("Refresh projects")
        refresh.clicked.connect(self.refresh_projects)
        layout.addWidget(refresh)
        return page

    def refresh_projects(self):
        bundles = self.store.list_training_bundles()
        projects = {}
        for bundle in bundles:
            key = (bundle["task"], bundle["registry_id"], bundle["registry_version"])
            item = projects.setdefault(key, {"segments": 0, "records": 0, "bytes": 0})
            item["segments"] += 1
            item["records"] += int(bundle["record_count"])
            item["bytes"] += int(bundle["size_bytes"])
        self.projects_table.setRowCount(len(projects))
        for row, (key, values) in enumerate(sorted(projects.items())):
            task, registry, version = key
            labels = (task, f"{registry}@{version}", str(values["segments"]),
                      str(values["records"]), f"{values['bytes']:,}")
            for column, text in enumerate(labels):
                self.projects_table.setItem(row, column, QTableWidgetItem(text))
        self.projects_summary.setText(
            f"{len(projects)} model project(s) · {len(bundles)} segment(s) · "
            f"{sum(item['records'] for item in projects.values())} accepted records"
        )

    def _segments_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("DATASET SEGMENTS"))
        self.segments_table = QTableWidget(0, 8)
        self.segments_table.setHorizontalHeaderLabels(
            ["Segment", "Task", "Registry", "State", "Records", "Used bytes", "Capacity", "Train / Val / Test"])
        self.segments_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.segments_table, 1)
        refresh = QPushButton("Refresh segments")
        refresh.clicked.connect(self.refresh_segments)
        layout.addWidget(refresh)
        return page

    def refresh_segments(self):
        bundles = self.store.list_training_bundles()
        self.segments_table.setRowCount(len(bundles))
        for row, bundle in enumerate(bundles):
            split_counts = {"train": 0, "validation": 0, "test": 0}
            for record in self.store.list_records(task=bundle["task"]):
                training_bundle_id = record.get("training_bundle_id")
                if training_bundle_id == bundle["id"]:
                    split = record.get("split")
                    if split in split_counts:
                        split_counts[split] += 1
            values = (
                bundle["bundle_key"], bundle["task"],
                f"{bundle['registry_id']}@{bundle['registry_version']}",
                bundle["state"], str(bundle["record_count"]),
                f"{bundle['size_bytes']:,}", f"{bundle['max_bytes']:,}",
                f"{split_counts['train']} / {split_counts['validation']} / {split_counts['test']}",
            )
            for column, text in enumerate(values):
                self.segments_table.setItem(row, column, QTableWidgetItem(str(text)))

    def _validation_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("DATASET VALIDATION"))
        self.validation_summary = QLabel()
        self.validation_summary.setWordWrap(True)
        layout.addWidget(self.validation_summary)
        self.readiness_summary = QLabel("CNN readiness has not been evaluated.")
        self.readiness_summary.setWordWrap(True)
        layout.addWidget(self.readiness_summary)
        self.readiness_table = QTableWidget(0, 8)
        self.readiness_table.setHorizontalHeaderLabels(
            ["Head", "Class/Outcome", "Crop records", "Unique sources",
             "Train", "Validation", "Test", "Status"])
        self.readiness_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.readiness_table)
        self.validation_table = QTableWidget(0, 7)
        self.validation_table.setHorizontalHeaderLabels(
            ["Version", "Dataset", "Task", "Finalized", "Train", "Validation", "Test"])
        self.validation_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.validation_table, 1)
        refresh = QPushButton("Refresh validation")
        refresh.clicked.connect(self.refresh_validation)
        layout.addWidget(refresh)
        return page

    def refresh_validation(self):
        datasets = {row["id"]: row for row in self.store.list_datasets()}
        versions = self.store.list_versions()
        finalized = 0
        self.validation_table.setRowCount(len(versions))
        for row, version in enumerate(versions):
            rows = self.store.version_rows(version["id"])
            counts = {split: sum(1 for item in rows if item["included"] and item["split"] == split)
                      for split in ("train", "validation", "test")}
            dataset = datasets.get(version["dataset_id"], {})
            values = (
                f"v{version['version_number']}", dataset.get("name", "Unknown"),
                dataset.get("task", ""), "Yes" if version["finalized"] else "Draft",
                str(counts["train"]), str(counts["validation"]), str(counts["test"]),
            )
            finalized += int(bool(version["finalized"]))
            for column, text in enumerate(values):
                self.validation_table.setItem(row, column, QTableWidgetItem(str(text)))
        self.validation_summary.setText(
            f"{len(versions)} dataset version(s) · {finalized} finalized · "
            "Immutable versions are validated against source-group split rules."
        )
        try:
            report = self.datasets.readiness_report()
        except Exception as error:
            self.readiness_summary.setText(f"CNN readiness unavailable: {error}")
            return
        rows = report["single_label"] + report["body_images"]
        self.readiness_table.setRowCount(len(rows))
        for row_index, entry in enumerate(rows):
            values = (
                entry["head"],
                entry.get("class") or entry.get("outcome"),
                str(entry["eligible_crop_records"]),
                str(entry["unique_source_groups"]),
                str(entry["train_source_groups"]),
                str(entry["validation_source_groups"]),
                str(entry["test_source_groups"]),
                entry["status"].replace("_", " ").title(),
            )
            for column, value in enumerate(values):
                self.readiness_table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self.readiness_summary.setText(
            f"Model readiness: {report['model_status'].replace('_',' ').title()} · "
            "Positive/negative Body Images outcomes are independent."
        )

    def _packages_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("COLAB PACKAGES"))
        self.packages_table = QTableWidget(0, 4)
        self.packages_table.setHorizontalHeaderLabels(["Package", "Type", "Size", "Modified"])
        self.packages_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.packages_table, 1)
        refresh = QPushButton("Refresh packages")
        refresh.clicked.connect(self.refresh_packages)
        layout.addWidget(refresh)
        return page

    def refresh_packages(self):
        output_root = Path(self.config.output_dir)
        packages = [path for path in output_root.iterdir()
                    if path.is_dir()] if output_root.exists() else []
        packages.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        self.packages_table.setRowCount(len(packages))
        for row, path in enumerate(packages):
            size = sum(file.stat().st_size for file in path.rglob("*") if file.is_file())
            package_type = "Shared CNN" if (path / "shared_dataset.json").is_file() else "Dataset package"
            values = (path.name, package_type, f"{size:,}", datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"))
            for column, text in enumerate(values):
                self.packages_table.setItem(row, column, QTableWidgetItem(str(text)))

    def _artifacts_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("MODEL ARTIFACTS"))
        self.artifacts_table = QTableWidget(0, 5)
        self.artifacts_table.setHorizontalHeaderLabels(
            ["Run", "Status", "Model", "Checkpoint", "Completed"])
        self.artifacts_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.artifacts_table, 1)
        refresh = QPushButton("Refresh artifacts")
        refresh.clicked.connect(self.refresh_artifacts)
        layout.addWidget(refresh)
        return page

    def refresh_artifacts(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM training_runs ORDER BY id DESC").fetchall()
        self.artifacts_table.setRowCount(len(rows))
        for row, run in enumerate(rows):
            values = (
                run["run_key"], run["status"], run["model_id"],
                run["checkpoint_path"] or "No checkpoint",
                run["finished_at"] or "Running / incomplete",
            )
            for column, text in enumerate(values):
                self.artifacts_table.setItem(row, column, QTableWidgetItem(str(text)))

    def _import_activation_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("IMPORT / STAGING"))
        row = QHBoxLayout()
        self.staging_bundle_path = QLineEdit()
        self.staging_bundle_path.setPlaceholderText("Select a NewAssetApp handoff bundle")
        browse = QPushButton("Browse bundle")
        browse.clicked.connect(self._choose_staging_bundle)
        self.staging_import_button = QPushButton("Validate & Import")
        self.staging_import_button.clicked.connect(self._import_staging_bundle)
        row.addWidget(self.staging_bundle_path, 1)
        row.addWidget(browse)
        row.addWidget(self.staging_import_button)
        layout.addLayout(row)
        self.staging_status = QLabel("No bundle staged.")
        self.staging_status.setWordWrap(True)
        layout.addWidget(self.staging_status)
        self.staging_table = QTableWidget(0, 4)
        self.staging_table.setHorizontalHeaderLabels(["Bundle", "Imported", "Accepted", "Source"])
        self.staging_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.staging_table, 1)
        return page

    def _choose_staging_bundle(self):
        path = QFileDialog.getExistingDirectory(self, "Choose NewAssetApp bundle", str(self.config.root.parent))
        if path:
            self.staging_bundle_path.setText(path)

    def _import_staging_bundle(self):
        path = self.staging_bundle_path.text().strip()
        if not path:
            QMessageBox.information(self, "Bundle required", "Choose a bundle directory first.")
            return
        try:
            result = self.importer.import_bundle(path)
            counts = ", ".join(f"{key}: {result.get(key, 0)}"
                               for key in ("accepted", "warning", "quarantined", "rejected"))
            self.staging_status.setText(f"{result['message']} · Bundle {result['bundle_id']} · {counts}")
            self.refresh_records()
            self.refresh_datasets()
            self.refresh_import_status()
        except Exception as error:
            QMessageBox.critical(self, "Import failed", str(error))
            self.staging_status.setText("No records were committed.")

    def refresh_import_status(self):
        with self.store.connect() as db:
            rows = db.execute("SELECT * FROM bundles ORDER BY id DESC").fetchall()
        self.staging_table.setRowCount(len(rows))
        for row, bundle in enumerate(rows):
            manifest = json.loads(bundle["manifest_json"])
            counts = manifest.get("record_counts", {})
            values = (
                bundle["bundle_id"], bundle["imported_at"],
                str(counts.get("accepted", 0)), bundle["source_path"],
            )
            for column, text in enumerate(values):
                self.staging_table.setItem(row, column, QTableWidgetItem(str(text)))

    def _history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("HISTORY / ANNOTATION EVENTS"))
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ["Event", "Record", "Task", "Class", "Occurred"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.history_table, 1)
        refresh = QPushButton("Refresh history")
        refresh.clicked.connect(self.refresh_history)
        layout.addWidget(refresh)
        return page

    def refresh_history(self):
        with self.store.connect() as db:
            rows = db.execute(
                """SELECT ae.event_type,ae.occurred_at,r.external_id,r.task,r.class_label
                   FROM annotation_events ae JOIN records r ON r.id=ae.record_id
                   ORDER BY ae.id DESC""").fetchall()
        self.history_table.setRowCount(len(rows))
        for row, event in enumerate(rows):
            values = (event["event_type"], event["external_id"], event["task"],
                      event["class_label"] or "", event["occurred_at"])
            for column, text in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(str(text)))

    def _studio_navigation_changed(self, row: int):
        if 0 <= row < self.studio_pages.count():
            self.studio_pages.setCurrentIndex(row)
            refresh = (
                self.refresh_projects, self.refresh_segments, self.refresh_datasets,
                self.refresh_records, self.refresh_validation, self.refresh_packages,
                self.refresh_artifacts, self.refresh_import_status, self.refresh_history,
            )
            refresh[row]()

    def _apply_studio_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #10151d; color: #e8edf5; font-size: 13px; }
            #StudioNavigation { background: #171d28; border: 1px solid #303b4a;
                                border-radius: 10px; }
            #StudioBrand { color: #f5f7fb; font-size: 18px; font-weight: 700;
                           padding: 8px 4px 14px 4px; }
            #StudioNavigationList { background: transparent; border: 0; outline: 0; }
            #StudioNavigationList::item { padding: 10px 8px; margin: 2px;
                                          border-radius: 7px; color: #b7c1d0; }
            #StudioNavigationList::item:selected { background: #34466b; color: #ffffff; }
            #StudioNavigationList::item:hover { background: #252f3d; color: #ffffff; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #0c1117; border: 1px solid #334050; border-radius: 7px;
                padding: 7px 9px; color: #edf3fb;
            }
            QComboBox QAbstractItemView { background: #171d28; color: #edf3fb;
                selection-background-color: #40557f; selection-color: #ffffff; }
            QPushButton { background: #252f3d; border: 1px solid #3b485a;
                          border-radius: 7px; padding: 8px 12px; font-weight: 600; }
            QPushButton:hover { background: #303e50; }
            QTableWidget, QListWidget, QTextEdit { background: #151b24;
                border: 1px solid #303b4a; border-radius: 7px; color: #e8edf5; }
            QListWidget::item:selected { background: #40557f; color: #ffffff; }
            QTabWidget::pane { border: 1px solid #303b4a; border-radius: 7px; }
            QSplitter::handle { background: #2a3442; }
            QStatusBar { background: #0d1218; color: #a9b3c2; }
        """)

    def _import_bundle(self):
        try:
            self.import_button.setEnabled(False)
            self.import_result.setText("Validating manifest, registries and all source payload hashes…")
            result = self.importer.import_bundle(self.bundle_path.text().strip())
            counts = ", ".join(f"{key}: {result.get(key,0)}" for key in ("accepted", "warning", "quarantined", "rejected"))
            self.import_result.setText(f"{result['message'] if result.get('duplicate') else 'Import committed.'} "
                                       f"Bundle {result['bundle_id']} · {counts}")
            self.statusBar().showMessage("Bundle import complete.")
            self.refresh_records(); self.refresh_datasets(); self.refresh_training_versions()
        except Exception as error:
            logger.exception("Bundle import failed")
            QMessageBox.critical(self, "Bundle import failed", str(error))
            self.import_result.setText("No bundle records were committed.")
        finally:
            self.import_button.setEnabled(True)

    def refresh_records(self, *_):
        task = self.task_filter.currentData() if hasattr(self, "task_filter") else "all"
        status = self.status_filter.currentData() if hasattr(self, "status_filter") else "all"
        rows = self.store.list_records(task=task, status=status)
        selected_id = self.current_record["id"] if self.current_record else None
        if hasattr(self, "task_filter"):
            known = {self.task_filter.itemData(i) for i in range(self.task_filter.count())}
            self.task_filter.blockSignals(True)
            for value in sorted({r["task"] for r in self.store.list_records()} - known):
                self.task_filter.addItem(value.replace("_", " ").title(), value)
            self.task_filter.blockSignals(False)
        self.record_list.blockSignals(True); self.record_list.clear()
        for row in rows:
            item = QListWidgetItem(f"{row['task']} · {row['class_label'] or 'unlabeled'} · {row['status']}\n{row['external_id']}")
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setToolTip(row.get("reason") or row.get("source_sha256") or "")
            self.record_list.addItem(item)
            if row["id"] == selected_id:
                self.record_list.setCurrentItem(item)
        self.record_list.blockSignals(False)
        if not rows:
            self.current_record = None; self.current_pixmap = QPixmap()
            self.record_header.setText("No records match the filters. Import a bundle or change the filters.")
            self.preview.set_pixmap(QPixmap()); self.class_list.clear()

    def _select_record(self, current, _previous=None):
        if not current:
            return
        row = self.store.get_record(current.data(Qt.ItemDataRole.UserRole))
        if not row:
            return
        self.current_record = row
        self.record_header.setText(
            f"{row['external_id']} · {row['task']} · {row['status']}\n"
            f"Class: {row['class_label'] or 'unresolved'} · Registry: {row['registry_id'] or 'unresolved'}"
            f"@{row['registry_version'] or '?'}\nSource SHA-256: {row['source_sha256'] or 'unavailable'}\n"
            f"Training bundle: {row.get('training_bundle_key') or 'not eligible / awaiting confirmation'}"
            + (f" · {row.get('training_bundle_size_bytes', 0):,}/"
               f"{row.get('training_bundle_max_bytes', 5_000_000_000):,} bytes"
               if row.get('training_bundle_id') else "") + "\n"
            f"Reason: {row['reason'] or 'none'}")
        self.current_pixmap = QPixmap(row["media_path"]) if row.get("media_path") else QPixmap()
        self.preview.set_pixmap(self.current_pixmap)
        self._populate_target_tasks(row)
        annotation = row["annotation"]
        box = annotation.get("bbox_xyxy")
        if box and self.current_pixmap.width() > 0:
            self.box_item = BoxItem(QRectF(float(box[0]), float(box[1]),
                                           float(box[2])-float(box[0]), float(box[3])-float(box[1])))
            self.preview.scene().addItem(self.box_item)
        else:
            self.box_item = None
        self._populate_class_list(row)
        self._load_datasets_for_record(row)

    def _registry_for_record(self, row: dict) -> dict | None:
        if not row.get("registry_id"):
            return None
        with self.store.connect() as db:
            value = db.execute("""SELECT payload_json FROM registries WHERE registry_id=? AND version=?
                               ORDER BY id DESC LIMIT 1""",
                               (row["registry_id"], str(row.get("registry_version") or ""))).fetchone()
        return json.loads(value["payload_json"]) if value else None

    def _target_options(self):
        rows = []
        task_map = {
            "newassetapp_yolo_detector_v1": [("yolo_detection", "YOLO Detection")],
            "newassetapp_unified_body_images_fullbody": [
                ("body_images_classification", "Body Images features"),
                ("fullbody_state_classification", "Fullbody state"),
                ("portrait_classification", "Portrait"),
                ("arousal_classification", "Arousal"),
                ("corruption_classification", "Corruption")],
            "clothing_classifier": [("broad_clothing_classification", "Broad Clothing")],
            "newassetapp_detailed_clothing_v1": [("detailed_clothing_classification", "Detailed Clothing")],
            "newassetapp_corruption_state_v1": [("corruption_state_classification", "Corruption state")],
        }
        with self.store.connect() as db:
            result = db.execute("""SELECT DISTINCT r.registry_id,r.version,b.manifest_json FROM registries r
                                 JOIN bundles b ON b.id=r.bundle_id ORDER BY r.id DESC""")
            for row in result:
                manifest = json.loads(row["manifest_json"])
                models = [model for model in manifest.get("models", [])
                          if model.get("registry_id") == row["registry_id"]]
                for model in models:
                    for task, label in task_map.get(row["registry_id"], []):
                        rows.append({"task": task, "label": label, "model_id": model["id"],
                                     "registry_id": row["registry_id"],
                                     "registry_version": str(row["version"])})
        unique = {(item["task"], item["model_id"], item["registry_id"], item["registry_version"]): item
                  for item in rows}
        return list(unique.values())

    def _populate_target_tasks(self, row):
        options = self._target_options()
        current = {"task": row["task"], "model_id": row.get("model_id"),
                   "registry_id": row.get("registry_id"),
                   "registry_version": str(row.get("registry_version") or "")}
        if not any(all(item.get(key) == value for key, value in current.items()) for item in options):
            options.insert(0, {**current, "label": row["task"].replace("_", " ").title() + " (source)"})
        self.target_task.blockSignals(True); self.target_task.clear()
        for option in options:
            label = f"{option.get('label', option['task'])} · {option.get('registry_id')}@{option.get('registry_version')}"
            self.target_task.addItem(label, option)
        index = next((i for i in range(self.target_task.count())
                      if self.target_task.itemData(i).get("task") == current["task"]
                      and self.target_task.itemData(i).get("model_id") == current["model_id"]
                      and self.target_task.itemData(i).get("registry_id") == current["registry_id"]), 0)
        self.target_task.setCurrentIndex(index); self.target_task.blockSignals(False)

    def _target_task_changed(self, *_):
        if not self.current_record:
            return
        target = self.target_task.currentData()
        if not target:
            return
        for key in ("task", "model_id", "registry_id", "registry_version"):
            self.current_record[key] = target.get(key)
            self.current_record["annotation"][key] = target.get(key)
        self._populate_class_list(self.current_record)

    def _populate_class_list(self, row: dict):
        self.class_list.clear()
        registry = self._registry_for_record(row)
        if not registry:
            return
        annotation = row["annotation"]
        task, label = row["task"], annotation.get("class_label") or row.get("class_label")
        structured = (row.get("original", {}).get("labels", {}).get("structured", {}))
        group = structured.get("output_group")
        if task == "body_images_classification":
            group = "body_images"
        elif task == "fullbody_state_classification":
            group = "fullbody"
        elif task in {"portrait_classification", "arousal_classification", "corruption_classification"}:
            group = task.removesuffix("_classification")
        if task in {"yolo_detection", "yolo_detector"}:
            rows = registry.get("classes", [])
            options = [(int(c["id"]), str(c["name"])) for c in rows]
        elif task in {"body_images_classification", "fullbody_state_classification",
                      "portrait_classification", "arousal_classification", "corruption_classification"}:
            rows = registry.get("output_groups", {}).get(group, {}).get("classes", [])
            options = [(int(c.get("class_id", i)), str(c["class_name"])) for i,c in enumerate(rows)]
        elif task == "broad_clothing_classification":
            options = [(int(c["class_id"]), str(c["class_name"])) for c in registry.get("classes", [])
                       if c.get("active", True)]
        elif task == "detailed_clothing_classification":
            options = [(int(c.get("class_id", i)), str(c["serialized_value"]))
                       for i,c in enumerate(registry.get("entries", []))
                       if c.get("selectable") and not c.get("requires_review")]
        else:
            options = [(int(c["class_id"]), str(c["class_name"])) for c in registry.get("classes", [])]
        for class_id, name in options:
            item = QListWidgetItem(f"{class_id:>3}  {name}")
            item.setData(Qt.ItemDataRole.UserRole, (class_id, name))
            self.class_list.addItem(item)
            if name == label:
                self.class_list.setCurrentItem(item)

    def _start_box(self):
        if self.current_pixmap.isNull():
            return
        self.preview.drawing = True
        self.preview.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.statusBar().showMessage("Drag across the image to draw a new box.")

    def _box_drawn(self, rect: QRectF):
        rect = rect.intersected(QRectF(self.current_pixmap.rect()))
        if rect.isEmpty():
            return
        if self.box_item and self.box_item.scene():
            self.preview.scene().removeItem(self.box_item)
        self.box_item = BoxItem(rect)
        self.preview.scene().addItem(self.box_item)
        self.preview.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def _delete_box(self):
        if self.box_item and self.box_item.scene():
            self.preview.scene().removeItem(self.box_item)
            self.box_item = None

    def _annotation_from_editor(self):
        if not self.current_record:
            raise ValueError("Select a training record first.")
        annotation = dict(self.current_record["annotation"])
        target = self.target_task.currentData() if hasattr(self, "target_task") else {}
        if target:
            for key in ("task", "model_id", "registry_id", "registry_version"):
                annotation[key] = target.get(key)
        current = self.class_list.currentItem()
        if current:
            class_id, label = current.data(Qt.ItemDataRole.UserRole)
            annotation["class_label"] = label
            annotation["target_class_id"] = class_id
            labels = dict(annotation.get("labels") or {})
            structured = dict(labels.get("structured") or {})
            structured["task"] = target.get("task") if target else annotation.get("task")
            if annotation.get("task") == "body_images_classification":
                structured["output_group"] = "body_images"
            elif annotation.get("task") == "fullbody_state_classification":
                structured["output_group"] = "fullbody"
            elif annotation.get("task") in {"portrait_classification", "arousal_classification",
                                              "corruption_classification"}:
                structured["output_group"] = annotation["task"].removesuffix("_classification")
            labels.update({"class_label": label, "structured": structured})
            annotation["labels"] = labels
        if self.box_item:
            rect = self.box_item.sceneBoundingRect().intersected(QRectF(self.current_pixmap.rect()))
            if rect.width() < 2 or rect.height() < 2:
                raise ValueError("Annotation box must have positive width and height.")
            annotation["bbox_xyxy"] = [rect.left(), rect.top(), rect.right(), rect.bottom()]
        else:
            annotation["bbox_xyxy"] = None
        return annotation

    def _save_correction(self):
        try:
            annotation = self._annotation_from_editor()
            self.store.save_annotation(self.current_record["id"], annotation, note="Saved from annotation review.")
            self.statusBar().showMessage("Correction saved. Original model prediction is preserved separately.")
            self.refresh_records()
        except Exception as error:
            QMessageBox.warning(self, "Could not save correction", str(error))

    def _confirm_record(self):
        try:
            annotation = self._annotation_from_editor()
            if not annotation.get("class_label") or not annotation.get("bbox_xyxy"):
                raise ValueError("Choose a class and a valid box before confirming.")
            if (annotation.get("task") == "body_images_classification"
                    and annotation.get("class_label") in {"face", "boobs", "ass", "pussy", "legs"}):
                raise ValueError("Body-region identity belongs to YOLO. Select YOLO Detection as the target task.")
            self.store.save_annotation(self.current_record["id"], annotation, confirm=True,
                                       note="Human confirmed in Studio.")
            self.statusBar().showMessage("Human correction confirmed for training.")
            self.refresh_records()
        except Exception as error:
            QMessageBox.warning(self, "Could not confirm record", str(error))

    def _reject_record(self):
        if not self.current_record:
            return
        reason, accepted = QInputDialog.getText(self, "Reject record", "Explicit rejection reason:")
        if not accepted:
            return
        if not reason.strip():
            QMessageBox.information(self, "Reason required", "Enter a rejection reason.")
            return
        self.store.save_annotation(self.current_record["id"], self.current_record["annotation"],
                                   reject_reason=reason.strip())
        self.refresh_records()

    def _show_history(self):
        if not self.current_record:
            return
        rows = self.store.annotation_history(self.current_record["id"])
        view = QTextEdit(); view.setReadOnly(True)
        view.setPlainText("\n\n".join(f"{row['occurred_at']} · {row['event_type']} · {row['note'] or ''}\n"
                                      f"Before: {row['before_json']}\nAfter: {row['after_json']}" for row in rows)
                           or "No edits have been recorded.")
        dialog = QMessageBox(self); dialog.setWindowTitle("Correction history")
        dialog.setText(f"{len(rows)} events"); dialog.setDetailedText(view.toPlainText()); dialog.exec()

    def _load_datasets_for_record(self, row):
        if hasattr(self, "dataset_task"):
            if self.dataset_task.findText(row["task"]) < 0:
                self.dataset_task.addItem(row["task"])
            self.dataset_task.setCurrentText(row["task"])
            self.dataset_registry.setText(row.get("registry_id") or "")
            self.dataset_registry_version.setText(row.get("registry_version") or "")

    def _dataset_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        form = QFormLayout()
        self.dataset_name = QLineEdit(); self.dataset_name.setPlaceholderText("Reviewed YOLO faces")
        self.dataset_task = QComboBox(); self.dataset_registry = QLineEdit(); self.dataset_registry_version = QLineEdit()
        form.addRow("Dataset name", self.dataset_name); form.addRow("Task", self.dataset_task)
        form.addRow("Registry ID", self.dataset_registry); form.addRow("Registry version", self.dataset_registry_version)
        self.seed = QSpinBox(); self.seed.setRange(0, 2**31-1); self.seed.setValue(42)
        form.addRow("Reproducible split seed", self.seed)
        layout.addLayout(form)
        actions = QHBoxLayout()
        self.create_dataset_button = QPushButton("Create dataset from selected record")
        self.create_dataset_button.clicked.connect(self._create_dataset)
        self.dataset_combo = QComboBox(); self.dataset_combo.currentIndexChanged.connect(self._dataset_changed)
        self.create_version_button = QPushButton("Create draft version")
        self.create_version_button.clicked.connect(self._create_version)
        actions.addWidget(self.create_dataset_button); actions.addWidget(self.dataset_combo,1); actions.addWidget(self.create_version_button)
        layout.addLayout(actions)
        self.version_combo = QComboBox(); self.version_combo.currentIndexChanged.connect(self._load_version)
        layout.addWidget(self.version_combo)
        self.version_table = QTableWidget(0,5)
        self.version_table.setHorizontalHeaderLabels(["Record", "Include", "Split", "Class", "Exclusion reason"])
        self.version_table.horizontalHeader().setStretchLastSection(True)
        self.version_table.itemChanged.connect(self._version_item_changed)
        layout.addWidget(self.version_table,1)
        bottom = QHBoxLayout()
        self.finalize_version_button = QPushButton("Validate & Finalize immutable version")
        self.finalize_version_button.clicked.connect(self._finalize_version)
        self.export_colab_button = QPushButton("Export for Google Colab")
        self.export_colab_button.clicked.connect(self._export_colab)
        self.export_shared_colab_button = QPushButton("Export shared five-head CNN package")
        self.export_shared_colab_button.clicked.connect(self._export_shared_colab)
        bottom.addWidget(self.finalize_version_button); bottom.addWidget(self.export_colab_button)
        bottom.addWidget(self.export_shared_colab_button)
        layout.addLayout(bottom)
        self.dataset_message = QLabel("Draft splits are source grouped and reproducible; finalized versions cannot be edited.")
        layout.addWidget(self.dataset_message)
        return page

    def refresh_datasets(self):
        if not hasattr(self, "dataset_combo"):
            return
        datasets = self.store.list_datasets()
        selected = self.dataset_combo.currentData()
        self.dataset_combo.blockSignals(True); self.dataset_combo.clear()
        for row in datasets:
            self.dataset_combo.addItem(row["name"], row["id"])
        idx = self.dataset_combo.findData(selected)
        self.dataset_combo.setCurrentIndex(idx if idx >= 0 else (0 if datasets else -1))
        self.dataset_combo.blockSignals(False)
        self._dataset_changed()

    def _create_dataset(self):
        task = self.dataset_task.currentText()
        if not task or not self.dataset_registry.text().strip() or not self.dataset_registry_version.text().strip():
            QMessageBox.information(self, "Choose a reviewed record", "Select a record to set its task and exact registry.")
            return
        try:
            bundle_id = (self.current_record or {}).get("training_bundle_id")
            if bundle_id is None:
                raise DatasetError("Confirm this reviewed record for training first. Studio groups eligible records into model-specific segments capped at 5,000,000,000 bytes.")
            self.datasets.create_dataset(self.dataset_name.text(), task,
                                         self.dataset_registry.text().strip(),
                                         self.dataset_registry_version.text().strip(),
                                         training_bundle_id=int(bundle_id))
            self.refresh_datasets()
            self.dataset_message.setText("Dataset created from the selected model-specific training segment.")
        except Exception as error:
            QMessageBox.warning(self, "Dataset creation failed", str(error))

    def _dataset_changed(self, *_):
        if not hasattr(self, "dataset_combo"):
            return
        selected = self.dataset_combo.currentData()
        datasets = self.store.list_datasets()
        row = next((item for item in datasets if item["id"] == selected), None)
        self.version_combo.blockSignals(True); self.version_combo.clear()
        if row:
            for version in self.store.list_versions(row["id"]):
                label = f"{row['name']} · v{version['version_number']} · {'Final' if version['finalized'] else 'Draft'}"
                self.version_combo.addItem(label, version["id"])
        self.version_combo.blockSignals(False)
        self._load_version()

    def _create_version(self):
        dataset_id = self.dataset_combo.currentData()
        if dataset_id is None:
            QMessageBox.information(self, "Create a dataset", "Create a dataset first.")
            return
        try:
            version_id = self.datasets.create_version(int(dataset_id), seed=self.seed.value())
            self.refresh_datasets()
            self.version_combo.setCurrentIndex(self.version_combo.findData(version_id))
            self.dataset_message.setText("Draft created. Review inclusion and split assignments before finalizing.")
        except Exception as error:
            QMessageBox.warning(self, "Version creation failed", str(error))

    def _load_version(self, *_):
        if not hasattr(self, "version_combo"):
            return
        version_id = self.version_combo.currentData()
        if version_id is None:
            self.version_table.setRowCount(0); return
        version = next((row for row in self.store.list_versions() if row["id"] == version_id), None)
        rows = self.store.version_rows(version_id)
        self._loading_version = True
        self.version_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.version_table.setItem(index, 0, QTableWidgetItem(str(row["record_id"])))
            check = QTableWidgetItem(""); check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if row["included"] else Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, row["record_id"])
            self.version_table.setItem(index, 1, check)
            split = QComboBox()
            for item in ("train", "validation", "test"): split.addItem(item.title(), item)
            split.setCurrentIndex(max(0, split.findData(row["split"])))
            split.setEnabled(not bool(version and version["finalized"]) and bool(row["included"]))
            split.currentIndexChanged.connect(lambda _i, rec=row["record_id"], combo=split: self._version_split_changed(rec, combo))
            self.version_table.setCellWidget(index, 2, split)
            self.version_table.setItem(index, 3, QTableWidgetItem(row.get("class_label") or ""))
            self.version_table.setItem(index, 4, QTableWidgetItem(row.get("exclusion_reason") or ""))
        self._loading_version = False
        locked = bool(version and version["finalized"])
        self.finalize_version_button.setEnabled(not locked and version_id is not None)
        self.version_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dataset_message.setText("Finalized immutable version." if locked else "Draft version. Check source groups when moving a record between splits.")

    def _version_item_changed(self, item):
        if self._loading_version or item.column() != 1:
            return
        version_id = self.version_combo.currentData(); record_id = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Unchecked:
            reason, accepted = QInputDialog.getText(self, "Exclusion reason", "Why exclude this record?")
            if not accepted or not reason.strip():
                self._loading_version = True; item.setCheckState(Qt.CheckState.Checked); self._loading_version = False
                return
            self.datasets.set_record_inclusion(version_id, record_id, False, reason)
        else:
            self.datasets.set_record_inclusion(version_id, record_id, True)
        self._load_version()

    def _version_split_changed(self, record_id, combo):
        if self._loading_version:
            return
        try:
            self.datasets.set_split(self.version_combo.currentData(), record_id, combo.currentData())
        except Exception as error:
            QMessageBox.warning(self, "Split change rejected", str(error)); self._load_version()

    def _finalize_version(self):
        try:
            result = self.datasets.finalize(int(self.version_combo.currentData()))
            self.dataset_message.setText("Immutable version finalized · " + json.dumps(result.get("split_counts", {})))
            self.refresh_datasets(); self.refresh_training_versions()
        except Exception as error:
            QMessageBox.warning(self, "Dataset validation failed", str(error))

    def _export_colab(self):
        version_id = self.version_combo.currentData()
        if version_id is None:
            return
        parent = QFileDialog.getExistingDirectory(self, "Choose package parent folder", str(self.config.output_dir))
        if not parent:
            return
        try:
            version = next(row for row in self.store.list_versions()
                           if int(row["id"]) == int(version_id))
            dataset = next(row for row in self.store.list_datasets()
                           if int(row["id"]) == int(version["dataset_id"]))
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", dataset["name"]).strip("._") or "dataset"
            dest = Path(parent) / f"{safe_name}_v{version['version_number']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            result = self.datasets.export_colab(int(version_id), dest)
            self.dataset_message.setText(f"Package exported · {result['records']} records · {result['package_type']}")
            QMessageBox.information(self, "Colab package ready", result["path"])
        except Exception as error:
            QMessageBox.warning(self, "Colab export failed", str(error))

    def _shared_version_ids(self, selected_version_id: int | None = None) -> dict[str, int]:
        head_tasks = {"body_images": "body_images_classification",
                      "fullbody": "fullbody_state_classification", "portrait": "portrait_classification",
                      "arousal": "arousal_classification", "corruption": "corruption_classification"}
        with self.store.connect() as db:
            rows = db.execute("""SELECT dv.id,d.task,d.registry_version FROM dataset_versions dv
                               JOIN datasets d ON d.id=dv.dataset_id WHERE dv.finalized=1
                               ORDER BY dv.id DESC""").fetchall()
            selected = (db.execute("""SELECT dv.id,d.task,d.registry_version FROM dataset_versions dv
                                  JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=? AND dv.finalized=1""",
                                   (int(selected_version_id),)).fetchone() if selected_version_id else None)
        if selected_version_id and not selected:
            raise ValueError("The selected shared-head dataset version is not finalized.")
        versions = {}
        for head, task in head_tasks.items():
            match = selected if selected and selected["task"] == task else next(
                (row for row in rows if row["task"] == task), None)
            if not match:
                raise ValueError(f"Finalize a dataset version for the {head} head first.")
            versions[head] = int(match["id"])
        return versions

    def _export_shared_colab(self):
        parent = QFileDialog.getExistingDirectory(self, "Choose shared CNN package parent folder",
                                                  str(self.config.output_dir))
        if not parent:
            return
        try:
            versions = self._shared_version_ids()
            dest = Path(parent) / f"shared_five_head_cnn_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            result = self.datasets.export_shared_cnn_colab(versions, dest)
            self.dataset_message.setText(f"Shared CNN package exported · {result['records']} crops · five heads")
            QMessageBox.information(self, "Shared CNN package ready", result["path"])
        except Exception as error:
            QMessageBox.warning(self, "Shared CNN export failed", str(error))

    def _training_page(self):
        page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout()
        self.training_version = QComboBox(); self.training_version.currentIndexChanged.connect(self._check_cpu)
        self.training_model = QComboBox()
        self.training_model.addItems(["newassetapp_yolo_detector_v1", "clothing_classifier",
                                      "unified_body_images_fullbody_cnn", "newassetapp_detailed_clothing_classifier",
                                      "newassetapp_corruption_state_cnn"])
        self.training_checkpoint = QLineEdit(); self.training_checkpoint.setPlaceholderText("Select an existing compatible checkpoint")
        checkpoint_row = QHBoxLayout(); checkpoint_row.addWidget(self.training_checkpoint, 1)
        checkpoint_browse = QPushButton("Browse…"); checkpoint_browse.clicked.connect(self._choose_checkpoint)
        checkpoint_row.addWidget(checkpoint_browse)
        self.epochs = QSpinBox(); self.epochs.setRange(1,1000); self.epochs.setValue(5)
        self.batch = QSpinBox(); self.batch.setRange(1,64); self.batch.setValue(2)
        self.image_size = QSpinBox(); self.image_size.setRange(64,2048); self.image_size.setSingleStep(32); self.image_size.setValue(640)
        self.workers = QSpinBox(); self.workers.setRange(0,32); self.workers.setValue(0)
        self.lr = QDoubleSpinBox(); self.lr.setDecimals(6); self.lr.setRange(.000001,1); self.lr.setValue(.001)
        self.checkpoint_frequency = QSpinBox(); self.checkpoint_frequency.setRange(1,1000); self.checkpoint_frequency.setValue(1)
        self.validation_frequency = QSpinBox(); self.validation_frequency.setRange(1,1000); self.validation_frequency.setValue(1)
        self.resume_check = QCheckBox("Resume from selected checkpoint when supported")
        form.addRow("Finalized dataset version", self.training_version); form.addRow("Model", self.training_model)
        form.addRow("Checkpoint", checkpoint_row); form.addRow("Device", QLabel("CPU (explicit; CUDA is never selected)"))
        form.addRow("Epochs", self.epochs); form.addRow("Batch size", self.batch)
        form.addRow("Image size (YOLO)", self.image_size); form.addRow("Data-loader workers", self.workers)
        form.addRow("Learning rate", self.lr); form.addRow("Checkpoint frequency", self.checkpoint_frequency)
        form.addRow("Validation frequency", self.validation_frequency); form.addRow("Resume", self.resume_check)
        layout.addLayout(form)
        self.compatibility_label = QLabel("Choose a finalized version, architecture and checkpoint to check CPU compatibility.")
        self.compatibility_label.setWordWrap(True); layout.addWidget(self.compatibility_label)
        actions = QHBoxLayout()
        self.cpu_dry_button = QPushButton("CPU dry run")
        self.cpu_dry_button.clicked.connect(lambda: self._start_training(dry_run=True))
        self.cpu_train_button = QPushButton("Train Locally (CPU)")
        self.cpu_train_button.clicked.connect(lambda: self._start_training(dry_run=False))
        self.cancel_training_button = QPushButton("Cancel safely"); self.cancel_training_button.clicked.connect(self._cancel_training)
        self.export_shared_artifact_button = QPushButton("Prepare NewAssetApp shared-model artifact")
        self.export_shared_artifact_button.clicked.connect(self._export_shared_model_artifact)
        actions.addWidget(self.cpu_dry_button); actions.addWidget(self.cpu_train_button)
        actions.addWidget(self.cancel_training_button); actions.addWidget(self.export_shared_artifact_button)
        layout.addLayout(actions)
        self.training_log = QTextEdit(); self.training_log.setReadOnly(True); layout.addWidget(self.training_log,1)
        return page

    def refresh_training_versions(self):
        if not hasattr(self, "training_version"):
            return
        selected = self.training_version.currentData()
        self.training_version.blockSignals(True); self.training_version.clear()
        with self.store.connect() as db:
            rows = db.execute("""SELECT dv.id,d.name,dv.version_number,dv.finalized,d.task FROM dataset_versions dv
                             JOIN datasets d ON d.id=dv.dataset_id WHERE dv.finalized=1 ORDER BY dv.id DESC""").fetchall()
        for row in rows:
            self.training_version.addItem(f"{row['name']} · v{row['version_number']} · {row['task']}", row["id"])
        idx = self.training_version.findData(selected)
        self.training_version.setCurrentIndex(idx if idx >= 0 else (0 if rows else -1))
        self.training_version.blockSignals(False); self._check_cpu()

    def _choose_checkpoint(self):
        path = QFileDialog.getOpenFileName(self, "Choose model checkpoint", str(self.config.root.parent),
                                           "Model checkpoints (*.pt *.pth *.ckpt);;All files (*)")[0]
        if path:
            self.training_checkpoint.setText(path); self._check_cpu()

    def _selected_training_version(self):
        return self.training_version.currentData() if hasattr(self, "training_version") else None

    def _training_task(self):
        value = self._selected_training_version()
        if value is None:
            return None
        with self.store.connect() as db:
            row = db.execute("SELECT d.task FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=?",
                             (int(value),)).fetchone()
        return row["task"] if row else None

    def _prepare_local_package(self, version_id: int) -> Path:
        destination = self.config.output_dir / ("cpu_dataset_" + str(version_id) + "_" + str(time.time_ns()))
        if self.training_model.currentText() == "unified_body_images_fullbody_cnn":
            versions = self._shared_version_ids(version_id)
            self.datasets.export_shared_cnn_colab(versions, destination)
            return destination
        self.datasets.export_colab(version_id, destination)
        return destination

    def _check_cpu(self, *_):
        version_id = self._selected_training_version() if hasattr(self, "training_version") else None
        if version_id is None:
            return
        task = self._training_task()
        model_id = self.training_model.currentText()
        checkpoint = self.training_checkpoint.text().strip()
        with self.store.connect() as db:
            row = db.execute("""SELECT d.task,d.registry_id,r.model_id FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id
                               JOIN dataset_version_records dvr ON dvr.version_id=dv.id AND dvr.included=1
                               JOIN records r ON r.id=dvr.record_id WHERE dv.id=? LIMIT 1""",
                             (int(version_id),)).fetchone()
            version = db.execute("SELECT finalized FROM dataset_versions WHERE id=?", (int(version_id),)).fetchone()
            split_rows = db.execute("SELECT split,COUNT(*) count FROM dataset_version_records "
                                    "WHERE version_id=? AND included=1 GROUP BY split", (int(version_id),)).fetchall()
            dataset_records = db.execute("""SELECT r.media_path FROM dataset_version_records dvr
                                         JOIN records r ON r.id=dvr.record_id
                                         WHERE dvr.version_id=? AND dvr.included=1""", (int(version_id),)).fetchall()
        if row:
            expected = row["model_id"]
            model_id = expected if self.training_model.findText(expected) >= 0 else self.training_model.currentText()
            self.training_model.setCurrentText(model_id)
            package_path = self.config.output_dir / "__compatibility_check__"
            report = cpu_compatibility(task, model_id, checkpoint or None, package_path,
                                       self.config.output_dir, require_dataset=False)
            split_counts = {item["split"]: int(item["count"]) for item in split_rows}
            report["dataset_train_examples"] = split_counts.get("train", 0)
            report["dataset_validation_examples"] = split_counts.get("validation", 0)
            report["dataset_record_count"] = sum(split_counts.values())
            report["dataset_bytes"] = sum(Path(item["media_path"]).stat().st_size
                                           for item in dataset_records
                                           if item["media_path"] and Path(item["media_path"]).is_file())
            report["dataset_layout_valid"] = (report["dataset_train_examples"] > 0 and
                                                report["dataset_validation_examples"] > 0)
            if not report["dataset_layout_valid"]:
                report["reasons"].append("At least one source image is required in both train and validation splits for local training.")
                report["compatible"] = False
            report["dataset_finalized"] = bool(version and version["finalized"])
            self.compatibility_label.setText(json.dumps(report, ensure_ascii=False, indent=2))
            can_run = report["compatible"] and bool(version and version["finalized"])
            self.cpu_train_button.setEnabled(can_run)
            self.cpu_dry_button.setEnabled(can_run)
        else:
            self.compatibility_label.setText("Dataset task not found.")
            self.cpu_train_button.setEnabled(False); self.cpu_dry_button.setEnabled(False)

    def _start_training(self, *, dry_run: bool):
        version_id = self._selected_training_version()
        model_id = self.training_model.currentText()
        checkpoint_text = self.training_checkpoint.text().strip()
        checkpoint = Path(checkpoint_text) if checkpoint_text else None
        if not version_id or (model_id != "unified_body_images_fullbody_cnn"
                              and (checkpoint is None or not checkpoint.is_file())):
            QMessageBox.information(self, "Training inputs required", "Select a finalized dataset version and existing checkpoint.")
            return
        if not dry_run:
            answer = QMessageBox.question(self, "Confirm CPU training",
                "Start a real CPU training run with these settings? It will create a new isolated run and checkpoints.\n\n"
                "The trained model will not replace any production checkpoint.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            package = self._prepare_local_package(int(version_id))
            params = {"epochs": self.epochs.value(), "batch_size": self.batch.value(),
                      "image_size": self.image_size.value(), "workers": self.workers.value(),
                      "learning_rate": self.lr.value(), "checkpoint_frequency": self.checkpoint_frequency.value(),
                      "validation_frequency": self.validation_frequency.value(), "validate": True,
                      "resume": self.resume_check.isChecked()}
            key = self.training.start(int(version_id), package, self.training_model.currentText(),
                                      checkpoint, params, confirmed=not dry_run, dry_run=dry_run,
                                      callback=lambda _key, line: QApplication.instance().postEvent(
                                          self, TrainingLogEvent(_key, line)))
            self.training_log.append(f"Started {'dry-run' if dry_run else 'CPU training'}: {key}")
            self.cpu_dry_button.setEnabled(False); self.cpu_train_button.setEnabled(False)
        except Exception as error:
            QMessageBox.warning(self, "Could not start training", str(error))

    def _cancel_training(self):
        self.training_log.append("Cancellation requested.")
        self.training.cancel()

    def _export_shared_model_artifact(self):
        checkpoint = Path(self.training_checkpoint.text().strip())
        if not checkpoint.is_file():
            QMessageBox.information(self, "Completed checkpoint required",
                                    "Select a completed shared_cnn.pth checkpoint from a successful run.")
            return
        parent = QFileDialog.getExistingDirectory(self, "Choose model artifact parent folder",
                                                  str(self.config.output_dir))
        if not parent:
            return
        try:
            from .shared_training import export_shared_model_artifact
            root = Path(__file__).resolve().parents[2]
            registry_path = root / "data/models/unified_body_images_fullbody/class_registry.json"
            destination = Path(parent) / f"shared_cnn_return_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            result = export_shared_model_artifact(checkpoint, destination, registry_path)
            QMessageBox.information(self, "NewAssetApp model artifact ready", result["path"])
        except Exception as error:
            QMessageBox.warning(self, "Model artifact rejected", str(error))

    def customEvent(self, event):
        if isinstance(event, TrainingLogEvent):
            self.training_log.append(event.line)
            if event.line.startswith("RUN_STATUS:"):
                self.refresh_training_versions()
                self.cpu_train_button.setEnabled(True); self.cpu_dry_button.setEnabled(True)


from PySide6.QtCore import QEvent


class TrainingLogEvent(QEvent):
    TYPE = QEvent.Type(QEvent.registerEventType())
    def __init__(self, run_key: str, line: str):
        super().__init__(self.TYPE)
        self.run_key = run_key
        self.line = line

