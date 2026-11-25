from __future__ import annotations

# PySide6 exposes these Qt symbols through extension modules that pylint cannot
# always inspect correctly.
# pylint: disable=no-name-in-module

import logging
import json
from collections import OrderedDict
from pathlib import Path
from PIL import Image

import PySide6.QtCore
from PySide6.QtGui import QColor, QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.workers.scan_worker import ScanWorker
from app.workers.dataset_export_worker import DatasetExportWorker
from app.workers.analysis_worker import AnalysisWorker
from app.workers.output_export_worker import OutputExportWorker
from app.core.tag_library import TagLibrary
from app.gui.tag_browser_dialog import TagBrowserDialog
from app.gui.bbox_preview import BoundingBoxPreview
from app.core.output_exporter import build_normal_output_plan
from app.core.crop_rules import BODY_IMAGE_SPECS, prepare_export_crop
from app.core.classification_taxonomy import REGISTRY, location_candidates
from app.core.clothing_taxonomy import clothing_classes, suggested_clothing_tags
from app.core.classification_eligibility import shared_head_eligible
from app.core.confidence_verification import model_verified

logger = logging.getLogger(__name__)

NAV_ITEMS = [
    ("All scanned", "sources"), ("Fullbody", "fullbody"),
    ("Topless", "fullbody_topless"), ("Bottomless", "fullbody_bottomless"),
    ("Body Images", "body_images"), ("Clothing", "clothing"),
    ("Others", "others"), ("Photoshoots", "photoshoots"),
]


class AspectRatioPreview(QLabel):
    """Display a source pixmap fully inside the current label bounds."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._source_pixmap = QPixmap()
        self.setAlignment(PySide6.QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def set_source_pixmap(self, pixmap: QPixmap):
        self._source_pixmap = pixmap
        self._update_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if self._source_pixmap.isNull():
            self.setPixmap(QPixmap())
            return
        bounds = self.contentsRect().size()
        if bounds.isEmpty():
            return
        fitted = self._source_pixmap.scaled(
            bounds, PySide6.QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            PySide6.QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(fitted)


class MainWindow(QMainWindow):
    def __init__(self, config, database):
        super().__init__()
        self.config = config
        self.database = database
        self.worker = None
        self.export_worker = None
        self.studio_source_worker = None
        self.analysis_worker = None
        self.normal_export_worker = None
        self._normal_drafts: dict[int, dict] = {}
        self._normal_loaded_proposal_id: int | None = None
        self._normal_gallery_crop_cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._normal_gallery_crop_cache_limit = 128
        self._normal_preview_cache: OrderedDict[tuple, tuple[QPixmap, str]] = OrderedDict()
        self._normal_preview_cache_limit = 16
        self._normal_cache_stats = {
            "thumbnail_hits": 0,
            "thumbnail_misses": 0,
            "thumbnail_evictions": 0,
            "preview_hits": 0,
            "preview_misses": 0,
            "preview_evictions": 0,
            "selection_timings_ms": [],
        }
        self._normal_thumbnail_debounce = PySide6.QtCore.QTimer(self)
        self._normal_thumbnail_debounce.setSingleShot(True)
        self._normal_thumbnail_debounce.setInterval(50)
        self._normal_thumbnail_debounce.timeout.connect(self._load_visible_normal_thumbnails)
        self._normal_draft_debounce = PySide6.QtCore.QTimer(self)
        self._normal_draft_debounce.setSingleShot(True)
        self._normal_draft_debounce.setInterval(300)
        self._normal_draft_debounce.timeout.connect(self._flush_normal_draft_autosave)
        self._loading_normal_crop = False
        self.current_category = "sources"
        self.tag_library = TagLibrary(config.data_dir / "tags")
        self.resize(1360, 820)
        self.setMinimumSize(800, 540)
        self.setWindowTitle(f"{config.app_name} — Normal Processing and Professional Review")
        self._build_ui()
        self._apply_style()
        from PySide6.QtGui import QShortcut
        QShortcut("Ctrl+J", self).activated.connect(lambda: self.normal_proposal_search.setFocus())
        QShortcut("Ctrl+S", self).activated.connect(self._flush_normal_draft_autosave)
        QShortcut("Alt+Left", self).activated.connect(lambda: self._move_normal_selection(-1))
        QShortcut("Alt+Right", self).activated.connect(lambda: self._move_normal_selection(1))
        QShortcut("Ctrl+Enter", self).activated.connect(self._confirm_shortcut_normal_crop)
        QShortcut("Escape", self).activated.connect(self._cancel_normal_search)
        self._refresh_navigation()
        self._refresh_gallery()

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 8, 12, 5)
        root_layout.setSpacing(4)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(6)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Choose a source image folder…")
        self.folder_edit.setClearButtonEnabled(True)
        self.folder_edit.setMaximumHeight(32)
        self.folder_edit.setMaximumWidth(560)
        self.browse_button = QPushButton("Choose Folder")
        self.scan_button = QPushButton("Scan Images")
        self.analyze_button = QPushButton("Analyze new / changed")
        for control in (self.browse_button, self.scan_button, self.analyze_button):
            control.setMaximumHeight(32)
        self.analyze_button.clicked.connect(self._start_analysis)
        self.full_rescan_check = QCheckBox("Full rescan")
        self.full_rescan_check.setToolTip("Revalidate every file even when its content hash is unchanged.")
        self.scan_button.setObjectName("PrimaryButton")
        self.browse_button.clicked.connect(self._choose_folder)
        self.scan_button.clicked.connect(self._start_scan)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_button)
        folder_row.addWidget(self.scan_button)
        folder_row.addWidget(self.analyze_button)
        folder_row.addWidget(self.full_rescan_check)
        root_layout.addLayout(folder_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMaximumHeight(18)
        self.progress.setFormat("Ready")
        root_layout.addWidget(self.progress)

        splitter = QSplitter(PySide6.QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        nav_frame = QFrame()
        nav_frame.setObjectName("NavigationPanel")
        nav_frame.setMinimumWidth(110)
        nav_frame.setMaximumWidth(150)
        self.nav_frame = nav_frame
        nav_layout = QVBoxLayout(nav_frame)
        nav_heading = QLabel("LIBRARY")
        nav_heading.setObjectName("SectionHeading")
        nav_layout.addWidget(nav_heading)
        self.nav = QListWidget()
        self.nav.setObjectName("CategoryNavigation")
        self.nav.setSpacing(4)
        self.nav.setHorizontalScrollBarPolicy(PySide6.QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setTextElideMode(PySide6.QtCore.Qt.TextElideMode.ElideRight)
        for label, key in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
        self.nav.currentItemChanged.connect(self._category_changed)
        nav_layout.addWidget(self.nav, 1)
        nav_note = QLabel("Photoshoots are manually managed. AI never assigns proposals to a group.")
        nav_note.setObjectName("QuietNote")
        nav_note.setWordWrap(True)
        self.nav_note = nav_note
        nav_layout.addWidget(nav_note)
        self.tag_library_button = QPushButton("Tags")
        self.tag_library_button.clicked.connect(self._open_tag_library)
        nav_layout.addWidget(self.tag_library_button)
        self.output_export_button = QPushButton("Export assets")
        self.output_export_button.setToolTip("Export assets")
        self.output_export_button.clicked.connect(self._export_output)
        nav_layout.addWidget(self.output_export_button)
        self.dataset_export_button = QPushButton("Prepare dataset")
        self.dataset_export_button.setToolTip("Prepare dataset")
        self.dataset_export_button.clicked.connect(self._prepare_training_dataset)
        nav_layout.addWidget(self.dataset_export_button)
        self.studio_source_button = QPushButton("Export Studio source")
        self.studio_source_button.setToolTip(
            "Create an immutable source bundle from current human-confirmed training records."
        )
        self.studio_source_button.clicked.connect(self._export_studio_source)
        nav_layout.addWidget(self.studio_source_button)

        gallery_frame = QFrame()
        gallery_frame.setObjectName("GalleryPanel")
        gallery_frame.setMinimumWidth(150)
        self.gallery_frame = gallery_frame
        gallery_layout = QVBoxLayout(gallery_frame)
        gallery_header = QHBoxLayout()
        self.gallery_title = QLabel("Scanned images")
        self.gallery_title.setObjectName("SectionTitle")
        self.gallery_count = QLabel("0 items")
        self.gallery_count.setObjectName("QuietNote")
        gallery_header.addWidget(self.gallery_title)
        gallery_header.addStretch()
        gallery_header.addWidget(self.gallery_count)
        gallery_layout.addLayout(gallery_header)

        filter_row = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All statuses", "Pending review", "Accepted", "Rejected"])
        self.status_filter.setEnabled(False)
        filter_row.addWidget(QLabel("Filter"))
        filter_row.addWidget(self.status_filter)
        filter_row.addStretch()
        gallery_layout.addLayout(filter_row)

        self.photoshoot_controls = QWidget()
        photoshoot_layout = QHBoxLayout(self.photoshoot_controls)
        photoshoot_layout.setContentsMargins(0, 0, 0, 0)
        self.group_combo = QComboBox()
        self.group_combo.currentIndexChanged.connect(self._photoshoot_group_changed)
        self.create_group_button = QPushButton("New group")
        self.rename_group_button = QPushButton("Rename")
        self.delete_group_button = QPushButton("Delete group")
        self.remove_members_button = QPushButton("Remove selected")
        self.create_group_button.clicked.connect(self._create_photoshoot_group)
        self.rename_group_button.clicked.connect(self._rename_photoshoot_group)
        self.delete_group_button.clicked.connect(self._delete_photoshoot_group)
        self.remove_members_button.clicked.connect(self._remove_photoshoot_members)
        for widget in (self.group_combo, self.create_group_button, self.rename_group_button,
                       self.delete_group_button, self.remove_members_button):
            photoshoot_layout.addWidget(widget)
        gallery_layout.addWidget(self.photoshoot_controls)
        self.assignment_controls = QWidget()
        assignment_layout = QHBoxLayout(self.assignment_controls)
        assignment_layout.setContentsMargins(0, 0, 0, 0)
        self.assign_group_combo = QComboBox()
        self.assign_group_button = QPushButton("Assign selected to group")
        self.assign_group_label = QLabel("Manual photoshoot assignment")
        self.assign_group_button.clicked.connect(self._assign_selected_to_photoshoot)
        assignment_layout.addWidget(self.assign_group_label)
        assignment_layout.addWidget(self.assign_group_combo, 1)
        assignment_layout.addWidget(self.assign_group_button)
        gallery_layout.addWidget(self.assignment_controls)

        self.gallery = QListWidget()
        self.gallery.setObjectName("ProposalGallery")
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setWrapping(True)
        self.gallery.setSpacing(12)
        self.gallery.setIconSize(PySide6.QtCore.QSize(148, 112))
        self.gallery.setGridSize(PySide6.QtCore.QSize(180, 176))
        self.gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.gallery.currentItemChanged.connect(self._selection_changed)
        self.gallery.itemSelectionChanged.connect(self._selection_state_changed)
        gallery_layout.addWidget(self.gallery, 1)

        detail_frame = QFrame()
        detail_frame.setObjectName("DetailPanel")
        detail_frame.setMinimumWidth(400)
        self.detail_frame = detail_frame
        detail_layout = QVBoxLayout(detail_frame)
        detail_heading = QLabel("PREVIEW & REVIEW")
        detail_heading.setObjectName("SectionHeading")
        detail_layout.addWidget(detail_heading)
        self.preview = BoundingBoxPreview()
        self.preview.setObjectName("ImagePreview")
        self.preview.box_changed.connect(self._bbox_changed)
        self.preview.box_created.connect(self._manual_box_created)
        self.preview.box_selected.connect(self._preview_box_selected)
        self.preview.setMinimumSize(300, 240)
        self.preview.setMaximumSize(16777215, 16777215)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        preview_frame = QWidget()
        preview_frame_layout = QHBoxLayout(preview_frame)
        preview_frame_layout.setContentsMargins(0, 0, 0, 0)
        preview_frame_layout.setSpacing(0)
        preview_frame_layout.addWidget(self.preview, 1)
        self.detection_splitter = QSplitter(PySide6.QtCore.Qt.Orientation.Vertical)
        self.detection_splitter.setChildrenCollapsible(False)
        self.detection_splitter.addWidget(preview_frame)
        self.detection_list = QListWidget()
        self.detection_list.setObjectName("DetectionList")
        self.detection_list.currentItemChanged.connect(self._detection_list_selection_changed)
        self.detection_filter = QComboBox()
        for label, value in (("All detections", "all"), ("Needs Review", "unreviewed"),
                             ("High YOLO confidence", "model_verified"),
                             ("Human Reviewed", "reviewed"), ("Corrected", "corrected"),
                             ("Invalid", "invalid")):
            self.detection_filter.addItem(label, value)
        self.detection_filter.currentIndexChanged.connect(self._refresh_professional_detection_view)
        detection_panel = QWidget()
        detection_panel_layout = QVBoxLayout(detection_panel)
        detection_panel_layout.setContentsMargins(0, 0, 0, 0)
        detection_panel_layout.addWidget(self.detection_filter)
        detection_panel_layout.addWidget(self.detection_list, 1)
        self.detection_splitter.addWidget(detection_panel)
        self.detection_splitter.setSizes([520, 90])
        self.detection_splitter.setStretchFactor(0, 7)
        self.detection_splitter.setStretchFactor(1, 2)
        detail_layout.addWidget(self.detection_splitter, 2)
        box_actions = QHBoxLayout()
        self.add_box_button = QPushButton("Draw box")
        self.add_box_button.clicked.connect(self.preview.start_manual_box)
        self.reject_box_button = QPushButton("Reject box")
        self.reject_box_button.clicked.connect(self._reject_selected_detection)
        self.approve_bbox_button = QPushButton("Approve BBox As-Is")
        self.approve_bbox_button.clicked.connect(self._approve_unchanged_bbox)
        self.box_visibility_mode = QComboBox()
        for label, data in (("All boxes", "all"), ("Selected box", "selected"), ("Hide boxes", "hidden")):
            self.box_visibility_mode.addItem(label, data)
        self.box_visibility_mode.currentIndexChanged.connect(self._apply_box_visibility_mode)
        box_actions.addWidget(self.add_box_button)
        box_actions.addWidget(self.reject_box_button)
        box_actions.addWidget(self.approve_bbox_button)
        box_actions.addWidget(QLabel("Preview"))
        box_actions.addWidget(self.box_visibility_mode)
        self.box_actions = box_actions
        detail_layout.addLayout(box_actions)
        self.details_toggle = QPushButton("Show technical details")
        self.details_toggle.setCheckable(True)
        self.details_toggle.toggled.connect(
            lambda checked: (self.details.setVisible(checked),
                             self.details_toggle.setText("Hide technical details" if checked
                                                         else "Show technical details"))
        )
        detail_layout.addWidget(self.details_toggle)
        self.details = QLabel("Select an image to view details.")
        self.details.setObjectName("DetailsText")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(PySide6.QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setVisible(False)
        detail_layout.addWidget(self.details, 1)
        self.review_hint = QLabel("Select a detection from the list or its box. Drag to move; use the corner handle to resize.")
        self.review_hint.setObjectName("QuietNote")
        self.review_hint.setWordWrap(True)
        detail_layout.addWidget(self.review_hint)
        self.manual_proposal_button = QPushButton("Create manual detection from selected image")
        self.manual_proposal_button.clicked.connect(self._create_manual_proposal)
        self.manual_proposal_button.setEnabled(False)
        detail_layout.addWidget(self.manual_proposal_button)
        self.return_normal_button = QPushButton("Return to Normal Processing")
        self.return_normal_button.clicked.connect(
            lambda: self.workspace_tabs.setCurrentIndex(0))
        detail_layout.addWidget(self.return_normal_button)

        inspector_frame = QFrame()
        inspector_frame.setObjectName("InspectorPanel")
        inspector_frame.setMinimumWidth(300)
        inspector_layout = QVBoxLayout(inspector_frame)
        inspector_layout.setContentsMargins(8, 8, 8, 8)
        inspector_heading = QLabel("DETECTION INSPECTOR")
        inspector_heading.setObjectName("SectionHeading")
        inspector_layout.addWidget(inspector_heading)
        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.setObjectName("InspectorTabs")
        self.inspector_tabs.setUsesScrollButtons(True)

        detection_page = QWidget()
        detection_layout = QVBoxLayout(detection_page)
        detection_layout.setContentsMargins(4, 8, 4, 4)
        self.inspector_original = QLabel("Select a detection")
        self.inspector_corrected = QLabel("Corrected class: none")
        self.inspector_bbox = QLabel("BBox: none")
        self.inspector_validity = QLabel("Validity: unreviewed")
        self.inspector_history = QLabel("Correction history: no events")
        for label in (self.inspector_original, self.inspector_corrected, self.inspector_bbox,
                      self.inspector_validity, self.inspector_history):
            label.setWordWrap(True)
            label.setTextInteractionFlags(PySide6.QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            detection_layout.addWidget(label)
        detection_layout.addWidget(QLabel("Detection class"))
        self.inspector_class_combo = QComboBox()
        self.inspector_class_combo.setMinimumWidth(220)
        self.inspector_class_button = QPushButton("Save Correction")
        self.inspector_class_button.clicked.connect(self._save_inspector_class_correction)
        detection_layout.addWidget(self.inspector_class_combo)
        detection_layout.addWidget(self.inspector_class_button)
        detection_layout.addStretch()
        self.inspector_tabs.addTab(detection_page, "Detection")
        inspector_layout.addWidget(self.inspector_tabs, 1)

        self.professional_splitter = splitter
        splitter.addWidget(nav_frame)
        splitter.addWidget(gallery_frame)
        splitter.addWidget(detail_frame)
        splitter.addWidget(inspector_frame)
        splitter.setSizes([120, 180, 760, 300])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 3)
        splitter.setStretchFactor(3, 1)

        professional_page = QWidget()
        professional_layout = QVBoxLayout(professional_page)
        professional_layout.setContentsMargins(0, 0, 0, 0)
        professional_layout.addWidget(splitter, 1)

        normal_page = QWidget()
        self.normal_page = normal_page
        normal_layout = QVBoxLayout(normal_page)
        normal_layout.setContentsMargins(6, 5, 6, 5)
        normal_layout.setSpacing(6)
        normal_intro = QLabel("Classify one crop at a time. Select crops only when you are ready to export them.")
        normal_intro.setObjectName("Subtitle")
        self.normal_intro = normal_intro
        normal_layout.addWidget(normal_intro)
        normal_filter_row = QHBoxLayout()
        normal_filter_row.setSpacing(8)
        self.normal_category_filter = QComboBox()
        self.normal_category_filter.addItem("All suggestions", None)
        for value, label in (("fullbody", "Fullbody"), ("body_images", "Body Images"),
                             ("clothing", "Clothing"), ("invalid", "Invalid"),
                             ("needs_category", "Choose category")):
            self.normal_category_filter.addItem(label, value)
        self.normal_category_filter.currentIndexChanged.connect(self._refresh_normal_gallery)
        normal_filter_row.addWidget(QLabel("Category"))
        normal_filter_row.addWidget(self.normal_category_filter)
        normal_filter_row.addWidget(QLabel("Proposal ID"))
        self.normal_proposal_search = QLineEdit()
        self.normal_proposal_search.setPlaceholderText("Exact ID")
        self.normal_proposal_search.setMaximumWidth(130)
        self.normal_proposal_search.returnPressed.connect(self._jump_normal_proposal)
        normal_filter_row.addWidget(self.normal_proposal_search)
        self.normal_proposal_jump = QPushButton("Jump")
        self.normal_proposal_jump.clicked.connect(self._jump_normal_proposal)
        normal_filter_row.addWidget(self.normal_proposal_jump)
        self.normal_status_filter = QComboBox()
        for label, value in (
            ("Any status", None),
            ("Pending", "pending"),
            ("Confirmed", "confirmed"),
            ("Invalid", "invalid"),
            ("Exported", "exported"),
            ("Stale Crop", "stale"),
            ("Needs category", "needs_category"),
            ("Draft / Unsaved", "draft"),
        ):
            self.normal_status_filter.addItem(label, value)
        self.normal_status_filter.currentIndexChanged.connect(self._refresh_normal_gallery)
        normal_filter_row.addWidget(QLabel("Status"))
        normal_filter_row.addWidget(self.normal_status_filter)
        normal_filter_row.addWidget(QLabel("Source"))
        self.normal_source_filter = QComboBox()
        self.normal_source_filter.addItem("All sources", None)
        self.normal_source_filter.currentIndexChanged.connect(self._refresh_normal_gallery)
        normal_filter_row.addWidget(self.normal_source_filter)
        normal_filter_row.addStretch()
        self.normal_source_progress = QLabel("Source progress: checking…")
        self.normal_source_progress.setObjectName("QuietNote")
        normal_filter_row.addWidget(self.normal_source_progress)
        self.normal_gallery_count = QLabel("0 suggestions · 0 selected")
        self.normal_gallery_count.setObjectName("QuietNote")
        normal_filter_row.addWidget(self.normal_gallery_count)
        normal_layout.addLayout(normal_filter_row)

        normal_splitter = QSplitter(PySide6.QtCore.Qt.Orientation.Horizontal)
        normal_splitter.setChildrenCollapsible(False)
        self.normal_gallery = QListWidget()
        self.normal_gallery.setObjectName("NormalCropGallery")
        self.normal_gallery.setMinimumWidth(150)
        self.normal_gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.normal_gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.normal_gallery.setMovement(QListWidget.Movement.Static)
        self.normal_gallery.setWrapping(True)
        self.normal_gallery.setSpacing(7)
        self.normal_gallery.setIconSize(PySide6.QtCore.QSize(88, 68))
        self.normal_gallery.setGridSize(PySide6.QtCore.QSize(118, 112))
        self.normal_gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.normal_gallery.currentItemChanged.connect(self._normal_selection_changed)
        self.normal_gallery.itemSelectionChanged.connect(self._normal_item_changed)
        self.normal_gallery.verticalScrollBar().valueChanged.connect(
            self._schedule_visible_normal_thumbnails)
        normal_splitter.addWidget(self.normal_gallery)
        normal_detail = QWidget()
        self.normal_detail_panel = normal_detail
        normal_detail_layout = QVBoxLayout(normal_detail)
        normal_detail_layout.setContentsMargins(8, 4, 4, 4)
        normal_detail_layout.setSpacing(6)
        self.normal_detail_splitter = QSplitter(PySide6.QtCore.Qt.Orientation.Vertical)
        self.normal_detail_splitter.setChildrenCollapsible(False)
        preview_panel = QWidget()
        preview_panel.setMinimumHeight(150)
        preview_panel.setMinimumWidth(400)
        self.normal_preview_panel = preview_panel
        preview_panel_layout = QVBoxLayout(preview_panel)
        preview_panel_layout.setContentsMargins(0, 0, 0, 0)
        preview_panel_layout.setSpacing(4)
        preview_panel_layout.addWidget(QLabel("SELECTED CROP"))
        self.normal_review_card = QFrame()
        self.normal_review_card.setObjectName("NormalReviewCard")
        review_card_layout = QVBoxLayout(self.normal_review_card)
        review_card_layout.setContentsMargins(8, 6, 8, 6)
        review_card_layout.setSpacing(3)
        self.normal_detection_review = QLabel("Detection: select a crop")
        self.normal_detection_review.setObjectName("ReviewCardTitle")
        self.normal_detection_review.setWordWrap(True)
        review_card_layout.addWidget(self.normal_detection_review)
        self.normal_crop_freshness = QLabel("Crop freshness: unavailable")
        self.normal_crop_freshness.setObjectName("QuietNote")
        self.normal_crop_freshness.setWordWrap(True)
        review_card_layout.addWidget(self.normal_crop_freshness)
        suggestion_row = QHBoxLayout()
        suggestion_row.setSpacing(8)
        self.normal_suggestion_label = QLabel("Suggested Final Tag: none")
        self.normal_suggestion_label.setObjectName("SuggestionNote")
        self.normal_suggestion_label.setWordWrap(True)
        suggestion_row.addWidget(self.normal_suggestion_label, 2)
        self.normal_suggestion_approve = QPushButton("Approve")
        self.normal_suggestion_reject = QPushButton("Reject")
        self.normal_suggestion_approve.clicked.connect(self._approve_normal_suggestion)
        self.normal_suggestion_reject.clicked.connect(self._reject_normal_suggestion)
        suggestion_row.addWidget(self.normal_suggestion_approve)
        suggestion_row.addWidget(self.normal_suggestion_reject)
        review_card_layout.addLayout(suggestion_row)
        self.normal_suggestion_status = QLabel("No model suggestion")
        self.normal_suggestion_status.setObjectName("QuietNote")
        self.normal_suggestion_status.setWordWrap(True)
        review_card_layout.addWidget(self.normal_suggestion_status)
        review_action_row = QHBoxLayout()
        self.normal_needs_correction = QPushButton("Needs YOLO Correction")
        self.normal_mark_invalid = QPushButton("Mark Crop Invalid")
        self.normal_source_context = QPushButton("Show Source Context")
        self.normal_needs_correction.clicked.connect(self._open_normal_in_professional_review)
        self.normal_mark_invalid.clicked.connect(self._mark_current_normal_crop_invalid)
        self.normal_source_context.setCheckable(True)
        self.normal_source_context.clicked.connect(self._toggle_normal_source_context)
        review_action_row.addWidget(self.normal_needs_correction)
        review_action_row.addWidget(self.normal_mark_invalid)
        review_action_row.addWidget(self.normal_source_context)
        review_action_row.addStretch()
        review_card_layout.addLayout(review_action_row)
        preview_panel_layout.addWidget(self.normal_review_card)
        self.normal_preview = AspectRatioPreview("Choose a crop suggestion")
        self.normal_preview.setObjectName("NormalImagePreview")
        self.normal_preview.setMinimumSize(0, 0)
        self._normal_crop_pixmap = QPixmap()
        preview_panel_layout.addWidget(self.normal_preview, 1)
        self.normal_detail_splitter.addWidget(preview_panel)

        normal_form_scroll = QScrollArea()
        normal_form_scroll.setObjectName("NormalClassificationScroll")
        normal_form_scroll.setWidgetResizable(True)
        normal_form_scroll.setFrameShape(QFrame.Shape.NoFrame)
        normal_form_scroll.setMinimumHeight(90)
        normal_form_scroll.setMinimumWidth(260)
        normal_form = QWidget()
        normal_form_layout = QVBoxLayout(normal_form)
        normal_form_layout.setContentsMargins(0, 0, 4, 0)
        normal_form_layout.setSpacing(7)
        normal_form_scroll.setWidget(normal_form)
        self.normal_detail_splitter.addWidget(normal_form_scroll)
        self.normal_detail_splitter.setStretchFactor(0, 3)
        self.normal_detail_splitter.setStretchFactor(1, 2)
        self.normal_detail_splitter.setSizes([280, 350])
        normal_detail_layout.addWidget(self.normal_detail_splitter, 1)

        self.normal_details = QLabel("Select a crop to inspect it.")
        self.normal_details.setObjectName("QuietNote")
        self.normal_details.setWordWrap(True)
        normal_form_layout.addWidget(self.normal_details)
        output_heading = QLabel("OUTPUT CATEGORY")
        output_heading.setObjectName("SectionHeading")
        self.normal_output_heading = output_heading
        normal_form_layout.addWidget(output_heading)
        category_row = QVBoxLayout()
        category_row.addWidget(QLabel("Output category"))
        self.normal_assign_category = QComboBox()
        self.normal_assign_category.addItem("Choose category", None)
        for value, label in (("fullbody", "Fullbody"), ("body_images", "Body Images"),
                             ("clothing", "Clothing"), ("invalid", "Invalid · wrong result")):
            self.normal_assign_category.addItem(label, value)
        category_row.addWidget(self.normal_assign_category)
        normal_form_layout.addLayout(category_row)
        self.normal_body_tag_row = QWidget()
        body_tag_layout = QVBoxLayout(self.normal_body_tag_row)
        body_tag_layout.setContentsMargins(0, 0, 0, 0)
        body_tag_layout.addWidget(QLabel("Main tag"))
        self.normal_body_tag = QComboBox()
        self.normal_body_tag.setCurrentIndex(-1)
        self.normal_body_tag.currentIndexChanged.connect(self._normal_category_choice_changed)
        body_tag_layout.addWidget(self.normal_body_tag)
        self.normal_body_tag_row.setVisible(True)
        normal_form_layout.addWidget(self.normal_body_tag_row)
        self.normal_clothing_broad_row = QWidget()
        broad_layout = QVBoxLayout(self.normal_clothing_broad_row)
        broad_layout.setContentsMargins(0, 0, 0, 0)
        broad_layout.addWidget(QLabel("Broad Clothing group"))
        self.normal_clothing_broad = QComboBox()
        self.normal_clothing_broad.addItem("Choose broad group", None)
        for row in clothing_classes():
            self.normal_clothing_broad.addItem(row["display_name"], row["class_name"])
        self.normal_clothing_broad.currentIndexChanged.connect(self._normal_clothing_broad_changed)
        broad_layout.addWidget(self.normal_clothing_broad)
        self.normal_clothing_broad_row.setVisible(False)
        normal_form_layout.addWidget(self.normal_clothing_broad_row)
        self.normal_clothing_cover_row = QWidget()
        cover_layout = QVBoxLayout(self.normal_clothing_cover_row)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.addWidget(QLabel("Guide cover area"))
        self.normal_clothing_cover_area = QComboBox()
        self.normal_clothing_cover_area.addItem("Choose cover area", None)
        self.normal_clothing_cover_area.currentIndexChanged.connect(self._normal_clothing_cover_changed)
        cover_layout.addWidget(self.normal_clothing_cover_area)
        self.normal_clothing_cover_row.setVisible(False)
        normal_form_layout.addWidget(self.normal_clothing_cover_row)
        self.normal_clothing_suggestion = QLabel("Broad model output is a suggestion; confirm the human-selected group.")
        self.normal_clothing_suggestion.setObjectName("SuggestionNote")
        self.normal_clothing_suggestion.setWordWrap(True)
        self.normal_clothing_suggestion.setVisible(False)
        normal_form_layout.addWidget(self.normal_clothing_suggestion)
        tags_heading = QLabel("HUMAN-SELECTED TAGS")
        tags_heading.setObjectName("SectionHeading")
        self.normal_tags_heading = tags_heading
        normal_form_layout.addWidget(tags_heading)
        state_row = QVBoxLayout()
        state_row.addWidget(QLabel("Fullbody state"))
        self.normal_fullbody_state = QComboBox()
        self.normal_fullbody_state.addItem("Choose state", None)
        for state in ("clothed", "topless", "bottomless"):
            self.normal_fullbody_state.addItem(state.title(), state)
        self.normal_fullbody_state.currentIndexChanged.connect(self._normal_category_choice_changed)
        state_row.addWidget(self.normal_fullbody_state)
        self.normal_state_row = QWidget()
        self.normal_state_row.setLayout(state_row)
        self.normal_state_row.setVisible(False)
        normal_form_layout.addWidget(self.normal_state_row)
        self.normal_fullbody_cnn_target = QComboBox()
        self.normal_fullbody_cnn_target.addItem("Use confirmed Fullbody state", None)
        for value in ("clothed", "topless", "bottomless", "bra", "panty"):
            self.normal_fullbody_cnn_target.addItem(value, value)
        self.normal_fullbody_cnn_row = QWidget()
        fullbody_target_layout = QVBoxLayout(self.normal_fullbody_cnn_row)
        fullbody_target_layout.setContentsMargins(0, 0, 0, 0)
        fullbody_target_layout.addWidget(QLabel("Fullbody CNN target"))
        fullbody_target_layout.addWidget(self.normal_fullbody_cnn_target)
        normal_form_layout.addWidget(self.normal_fullbody_cnn_row)
        self.normal_fullbody_cnn_target.currentIndexChanged.connect(self._normal_category_choice_changed)
        self.normal_body_cum = QCheckBox("Cum detected")
        self.normal_body_cum.setTristate(True)
        self.normal_body_cum.setToolTip("Unchecked = evaluated absent; checked = present; partly checked = pending.")
        self.normal_body_accessory = QCheckBox("Accessory detected")
        self.normal_body_accessory.setTristate(True)
        self.normal_body_accessory.setToolTip("Unchecked = evaluated absent; checked = present; partly checked = pending.")
        self.normal_body_completed = QCheckBox("Mark both decisions complete")
        self.normal_body_completed.setToolTip("Do not check for pending; keep partial decisions evaluated independently.")
        self.normal_body_cnn_row = QWidget()
        body_target_layout = QVBoxLayout(self.normal_body_cnn_row)
        body_target_layout.setContentsMargins(0, 0, 0, 0)
        body_target_layout.addWidget(QLabel("Body Images binary targets"))
        body_target_layout.addWidget(self.normal_body_cum)
        body_target_layout.addWidget(self.normal_body_accessory)
        body_target_layout.addWidget(self.normal_body_completed)
        normal_form_layout.addWidget(self.normal_body_cnn_row)
        self.normal_body_cum.stateChanged.connect(self._normal_category_choice_changed)
        self.normal_body_accessory.stateChanged.connect(self._normal_category_choice_changed)
        self.normal_body_completed.stateChanged.connect(self._normal_category_choice_changed)
        self.normal_arousal_target = QComboBox()
        self.normal_arousal_target.addItem("No Arousal target", None)
        for value in ("aroused", "edging"):
            self.normal_arousal_target.addItem(value.title(), value)
        self.normal_corruption_target = QComboBox()
        self.normal_corruption_target.addItem("No Corruption CNN target", None)
        for value in ("conservative", "slut", "whore", "u_whore"):
            label = "Ultimate Whore · u_whore" if value == "u_whore" else value.title()
            self.normal_corruption_target.addItem(label, value)
        shared_target_row = QVBoxLayout()
        shared_target_row.setContentsMargins(0, 0, 0, 0)
        shared_target_row.setSpacing(7)
        self.normal_arousal_target_label = QLabel("Arousal CNN target")
        shared_target_row.addWidget(self.normal_arousal_target_label)
        shared_target_row.addWidget(self.normal_arousal_target)
        self.normal_corruption_target_label = QLabel("Corruption CNN target")
        shared_target_row.addWidget(self.normal_corruption_target_label)
        shared_target_row.addWidget(self.normal_corruption_target)
        self.normal_shared_target_row = QWidget()
        self.normal_shared_target_row.setLayout(shared_target_row)
        normal_form_layout.addWidget(self.normal_shared_target_row)
        self.normal_arousal_target.currentIndexChanged.connect(self._normal_category_choice_changed)
        self.normal_corruption_target.currentIndexChanged.connect(self._normal_category_choice_changed)
        self.normal_subtags = QListWidget()
        self.normal_subtags.setMaximumHeight(88)
        self.normal_subtags.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.normal_subtags.setToolTip("Select one or more human-selected tags. Model output is shown separately as evidence.")
        self.normal_subtags.itemSelectionChanged.connect(self._normal_category_choice_changed)
        subtags_panel = QWidget()
        subtags_layout = QVBoxLayout(subtags_panel)
        subtags_layout.setContentsMargins(0, 0, 0, 0)
        subtags_layout.addWidget(QLabel("Human-selected subtags"))
        subtags_layout.addWidget(self.normal_subtags)
        self.normal_corruption_states = QListWidget()
        self.normal_corruption_states.setObjectName("NormalCorruptionStates")
        self.normal_corruption_states.setMaximumHeight(72)
        self.normal_corruption_states.setVerticalScrollBarPolicy(PySide6.QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.normal_corruption_states.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.normal_corruption_states.setToolTip("Select only the corruption states that apply to this crop.")
        self.normal_corruption_states.itemSelectionChanged.connect(self._normal_category_choice_changed)
        corruption_panel = QWidget()
        corruption_layout = QVBoxLayout(corruption_panel)
        corruption_layout.setContentsMargins(0, 0, 0, 0)
        corruption_layout.addWidget(QLabel("Corruption states"))
        corruption_layout.addWidget(self.normal_corruption_states)
        corruption_panel.setVisible(False)
        tag_selectors = QHBoxLayout()
        tag_selectors.setSpacing(8)
        tag_selectors.addWidget(subtags_panel, 2)
        tag_selectors.addWidget(corruption_panel, 1)
        normal_form_layout.addLayout(tag_selectors)
        location_row = QVBoxLayout()
        location_row.addWidget(QLabel("Location"))
        self.normal_location = QListWidget()
        self.normal_location.setMaximumHeight(70)
        self.normal_location.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.normal_location.setToolTip("Scroll the canonical locations and select one optional value.")
        none_location = QListWidgetItem("No location")
        none_location.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, None)
        self.normal_location.addItem(none_location)
        for value in REGISTRY["locations"]["canonical_values"]:
            item = QListWidgetItem(value)
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, value)
            self.normal_location.addItem(item)
        self.normal_location.itemSelectionChanged.connect(self._normal_category_choice_changed)
        location_row.addWidget(self.normal_location)
        self.normal_location_row = QWidget()
        self.normal_location_row.setLayout(location_row)
        normal_form_layout.addWidget(self.normal_location_row)
        self.normal_location_suggestions = QLabel("Location choices are human-selected.")
        self.normal_location_suggestions.setObjectName("SuggestionNote")
        self.normal_location_suggestions.setWordWrap(True)
        normal_form_layout.addWidget(self.normal_location_suggestions)
        export_heading = QLabel("EXPORT PREVIEW")
        export_heading.setObjectName("SectionHeading")
        self.normal_export_heading = export_heading
        normal_form_layout.addWidget(export_heading)
        self.normal_filename_preview = QLabel("Filename preview: select a crop and category.")
        self.normal_filename_preview.setObjectName("FilenamePreview")
        self.normal_filename_preview.setWordWrap(True)
        normal_form_layout.addWidget(self.normal_filename_preview)
        self.normal_assign_category.currentIndexChanged.connect(self._normal_category_changed)
        self.normal_apply_category_button = QPushButton("Confirm classification & Next")
        self.normal_apply_category_button.setObjectName("PrimaryButton")
        self.normal_apply_category_button.clicked.connect(self._confirm_current_normal_crop)
        self.normal_apply_category_button.setEnabled(False)
        preview_nav = QHBoxLayout()
        self.normal_previous_button = QPushButton("‹ Previous")
        self.normal_next_button = QPushButton("Next ›")
        self.normal_previous_button.clicked.connect(lambda: self._move_normal_selection(-1))
        self.normal_next_button.clicked.connect(lambda: self._move_normal_selection(1))
        preview_nav.addWidget(self.normal_previous_button)
        preview_nav.addWidget(self.normal_apply_category_button)
        preview_nav.addWidget(self.normal_next_button)
        preview_panel_layout.addLayout(preview_nav)
        self.normal_detail_panel = preview_panel
        normal_splitter.addWidget(preview_panel)
        normal_splitter.addWidget(normal_form_scroll)
        self.normal_splitter = normal_splitter
        normal_splitter.setSizes([220, 720, 390])
        normal_splitter.setStretchFactor(0, 1)
        normal_splitter.setStretchFactor(1, 3)
        normal_splitter.setStretchFactor(2, 2)
        normal_layout.addWidget(normal_splitter, 1)

        normal_actions = QHBoxLayout()
        self.normal_select_all_button = QPushButton("Select all visible")
        self.normal_select_all_button.clicked.connect(self._select_all_normal_crops)
        self.normal_remove_background_check = QCheckBox(
            "Background removal required: Fullbody, Portrait, T-Portrait"
        )
        self.normal_remove_background_check.setChecked(True)
        self.normal_remove_background_check.setEnabled(False)
        self.normal_remove_background_check.setToolTip(
            "Opaque Fullbody, Portrait, and T-Portrait crops use bundled BiRefNet. "
            "An export is blocked if removal fails; an opaque original is never written."
        )
        self.normal_export_button = QPushButton("Export selected crops")
        self.normal_export_button.setObjectName("PrimaryButton")
        self.normal_export_button.setEnabled(False)
        self.normal_export_button.clicked.connect(self._export_selected_normal_crops)
        self.normal_cancel_button = QPushButton("Cancel export")
        self.normal_cancel_button.setEnabled(False)
        self.normal_cancel_button.clicked.connect(self._cancel_normal_export)
        self.normal_discard_draft_button = QPushButton("Discard draft")
        self.normal_discard_draft_button.setEnabled(False)
        self.normal_discard_draft_button.clicked.connect(self._discard_current_normal_draft)
        normal_actions.addWidget(self.normal_select_all_button)
        normal_actions.addWidget(self.normal_remove_background_check)
        normal_actions.addStretch()
        normal_actions.addWidget(self.normal_discard_draft_button)
        normal_actions.addWidget(self.normal_cancel_button)
        normal_actions.addWidget(self.normal_export_button)
        normal_layout.addLayout(normal_actions)

        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("WorkspaceTabs")
        self.workspace_tabs.addTab(normal_page, "Normal Processing")
        self.workspace_tabs.addTab(professional_page, "Professional Review")
        self.workspace_tabs.currentChanged.connect(self._workspace_tab_changed)
        root_layout.addWidget(self.workspace_tabs, 1)
        self.setCentralWidget(root)

        status = QStatusBar()
        status.showMessage("Ready · originals are read-only")
        self.setStatusBar(status)
        self.status_label = status

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #11151c; color: #e6e9ef; font-size: 13px; }
            QDialog { background: #11151c; color: #e6e9ef; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: #11151c; border: 0; }
            QScrollBar:vertical { background: #151a22; width: 12px; margin: 0; }
            QScrollBar::handle:vertical { background: #3a4657; min-height: 28px; border-radius: 5px; }
            QScrollBar:horizontal { background: #151a22; height: 12px; margin: 0; }
            QScrollBar::handle:horizontal { background: #3a4657; min-width: 28px; border-radius: 5px; }
            #PageTitle { font-size: 25px; font-weight: 700; color: #f4f6fb; }
            #Subtitle, #QuietNote, #SuggestionNote { color: #aab3c2; }
            #SectionHeading { color: #9aa6b8; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
            #SectionTitle { font-size: 17px; font-weight: 650; }
            #NavigationPanel, #GalleryPanel, #DetailPanel {
                background: #181e28; border: 1px solid #293241; border-radius: 12px;
            }
            QLineEdit, QComboBox {
                background: #0d1117; border: 1px solid #303a49; border-radius: 7px;
                padding: 9px 11px; color: #edf1f7;
            }
            QComboBox QAbstractItemView {
                background: #171d26; color: #edf1f7; selection-background-color: #40557f;
                selection-color: #ffffff; border: 1px solid #526179; outline: 0;
            }
            QGroupBox {
                background: #171d26; border: 1px solid #303a49; border-radius: 8px;
                margin-top: 10px; padding: 10px 8px 8px 8px; font-weight: 700;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px;
                              color: #dfe6f3; }
            QPushButton {
                background: #252e3b; border: 1px solid #394657; border-radius: 7px;
                padding: 9px 14px; font-weight: 600;
            }
            QPushButton:hover { background: #303d4e; }
            #PrimaryButton { background: #4f6df5; border-color: #4f6df5; color: white; }
            #PrimaryButton:hover { background: #6380ff; }
            QListWidget { background: transparent; border: 0; outline: 0; }
            QListWidget::item { padding: 4px; border-radius: 5px; color: #dfe5ef; }
            QListWidget::item:selected { background: #40557f; color: #ffffff; }
            QListWidget::item:hover { background: #252e3b; }
            QSplitter::handle { background: #2a3442; }
            #CategoryNavigation::item { padding: 11px 10px; border-radius: 7px; color: #b7c0ce; }
            #CategoryNavigation::item:selected { background: #303d58; color: #ffffff; }
            #ProposalGallery::item {
                background: #202835; border: 1px solid #303b4a; border-radius: 9px;
                padding: 8px; color: #e6e9ef;
            }
            #ProposalGallery::item:selected { border: 2px solid #728cff; background: #27344a; }
            #ImagePreview { background: #0c1016; border: 1px solid #303a49; border-radius: 8px; }
            #NormalCropGallery::item {
                background: #202835; border: 1px solid #303b4a; border-radius: 8px;
                padding: 5px; color: #e6e9ef;
            }
            #NormalCropGallery::item:selected { border: 2px solid #728cff; background: #27344a; }
            #NormalImagePreview { background: #0c1016; border: 1px solid #303a49; border-radius: 8px; }
            #NormalReviewCard {
                background: #202835; border: 1px solid #394458; border-radius: 8px;
            }
            #ReviewCardTitle { color: #edf1f7; font-weight: 700; }
            #DetailsText { color: #c5ccd7; }
            QProgressBar {
                background: #202835; border: 0; border-radius: 5px; height: 12px;
                text-align: center; color: #e9edff;
            }
            QProgressBar::chunk { background: #617cff; border-radius: 5px; }
            QStatusBar { background: #10141b; color: #9da7b7; }
            QTabWidget::pane { border: 1px solid #303a49; border-radius: 7px; top: -1px; }
            QTabBar::tab { background: #202835; color: #c5ccd7; border: 1px solid #394657;
                           padding: 7px 14px; margin-right: 3px; border-top-left-radius: 6px;
                           border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #35466b; color: #ffffff; border-color: #728cff; }
            QTabBar::tab:!selected:hover { background: #2a3545; color: #ffffff; }
            QTabBar::tab:disabled { background: #171d26; color: #747d8b; border-color: #293241; }
            QTabBar::tab:focus { outline: 2px solid #a6b8ff; outline-offset: -3px; }
        """)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select image folder", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def _open_tag_library(self):
        preferred_group = "fullbody" if self.current_category in {"fullbody_topless", "fullbody_bottomless"} else self.current_category
        preferred = preferred_group if preferred_group in {
            "fullbody", "body_images", "clothing", "photoshoots"
        } else None
        dialog = TagBrowserDialog(self.tag_library, self, preferred_group=preferred)
        result = dialog.exec()
        current = self.gallery.currentItem()
        row = current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if current else None
        source_id = None
        if row:
            source_id = row.get("source_image_id") if "source_image_id" in row else (
                row.get("id") if self.current_category == "sources" else None)
        for change in dialog.tag_changes:
            try:
                self.database.record_tag_change(change["action"], change["before"], change["after"],
                                                source_image_id=source_id)
            except Exception as error:
                QMessageBox.warning(self, "Tag change log failed", str(error))
        if result == dialog.DialogCode.Accepted and dialog.selected_tags:
            self.status_label.showMessage(f"Selected {len(dialog.selected_tags)} tag(s); proposal tagging is not connected yet")

    def _update_normal_source_progress(self, rows: list[dict]) -> None:
        if not hasattr(self, "normal_source_progress"):
            return
        source_ids = {
            int(row["source_id"]) for row in rows
            if row.get("source_id") is not None
        }
        completed = 0
        for source_id in source_ids:
            source_rows = [row for row in rows if int(row.get("source_id") or -1) == source_id]
            relevant = [row for row in source_rows if not row.get("normal_is_invalid")]
            if relevant and all(bool(row.get("normal_confirmed")) for row in relevant):
                completed += 1
        self.normal_source_progress.setText(
            f"Source progress: {completed} of {len(source_ids)} sources fully confirmed"
        )

    def _cancel_normal_search(self) -> None:
        if hasattr(self, "normal_proposal_search"):
            self.normal_proposal_search.clear()
            self.normal_proposal_search.clearFocus()

    def _workspace_tab_changed(self, index: int) -> None:
        if index == 0 and hasattr(self, "normal_gallery"):
            self._normal_preview_cache.clear()
            self._normal_gallery_crop_cache.clear()
            self._refresh_normal_gallery()

    def _confirm_shortcut_normal_crop(self) -> None:
        focus = self.focusWidget()
        if isinstance(focus, (QLineEdit, QComboBox)):
            return
        if self.normal_apply_category_button.isEnabled():
            self._confirm_current_normal_crop()

    def _jump_normal_proposal(self) -> None:
        text = self.normal_proposal_search.text().strip()
        if not text:
            return
        try:
            proposal_id = int(text)
        except ValueError:
            QMessageBox.warning(self, "Proposal ID", "Enter a numeric Proposal ID.")
            return
        for index in range(self.normal_gallery.count()):
            item = self.normal_gallery.item(index)
            row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
            if row and int(row["id"]) == proposal_id:
                self.normal_gallery.setCurrentRow(index)
                self.normal_gallery.scrollToItem(item)
                self.status_label.showMessage(f"Proposal {proposal_id} selected")
                self._update_normal_position()
                return
        QMessageBox.information(
            self,
            "Proposal not visible",
            f"Proposal #{proposal_id} does not exist in the active category/status filters.",
        )

    def _update_normal_position(self) -> None:
        if not hasattr(self, "normal_gallery_count"):
            return
        current = self.normal_gallery.currentRow()
        visible_rows = [
            index for index in range(self.normal_gallery.count())
            if self.normal_gallery.item(index).data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
        ]
        if visible_rows:
            position = visible_rows.index(current) + 1 if current in visible_rows else 0
            self.normal_gallery_count.setText(
                f"Proposal {position} of {len(visible_rows)} · "
                f"{self._selected_normal_crop_count()} selected"
            )
        else:
            self.normal_gallery_count.setText("0 proposals · 0 selected")

    def _refresh_normal_gallery(self, *_):
        if not hasattr(self, "normal_gallery"):
            return
        selected_ids = {
            int(self.normal_gallery.item(index).data(PySide6.QtCore.Qt.ItemDataRole.UserRole)["id"])
            for index in range(self.normal_gallery.count())
            if self.normal_gallery.item(index).data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
            and self.normal_gallery.item(index).isSelected()
        }
        current_item = self.normal_gallery.currentItem()
        current_id = (int(current_item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)["id"])
                      if current_item and current_item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) else None)
        self.normal_gallery.blockSignals(True)
        self.normal_gallery.clear()
        category_filter = self.normal_category_filter.currentData()
        folder_text = self.folder_edit.text().strip()
        folder = Path(folder_text).resolve() if folder_text else None
        rows = self.database.normal_crop_records(folder=folder)
        all_rows = list(rows)
        source_filter_id = self.normal_source_filter.currentData()
        sources = {}
        for row in all_rows:
            source_id = int(row["source_id"])
            source_name = Path(str(row["path"])).name
            sources.setdefault(source_id, source_name)
        self.normal_source_filter.blockSignals(True)
        current_source = source_filter_id
        self.normal_source_filter.clear()
        self.normal_source_filter.addItem("All sources", None)
        for source_id in sorted(sources):
            self.normal_source_filter.addItem(
                f"{sources[source_id]} · {source_id}", source_id)
        source_index = self.normal_source_filter.findData(current_source)
        self.normal_source_filter.setCurrentIndex(source_index if source_index >= 0 else 0)
        self.normal_source_filter.blockSignals(False)
        if source_filter_id is not None:
            rows = [row for row in rows if int(row["source_id"]) == int(source_filter_id)]
        self._update_normal_source_progress(all_rows)
        if category_filter == "needs_category":
            rows = [row for row in rows if not row.get("category")]
        elif category_filter:
            rows = [row for row in rows if row.get("category") == category_filter]
        status_filter = (
            self.normal_status_filter.currentData()
            if hasattr(self, "normal_status_filter") else None
        )
        if status_filter == "confirmed":
            rows = [row for row in rows if bool(row.get("normal_confirmed"))]
        elif status_filter == "pending":
            rows = [row for row in rows if not row.get("normal_confirmed")
                    and not row.get("normal_is_invalid")]
        elif status_filter == "invalid":
            rows = [row for row in rows if bool(row.get("normal_is_invalid"))]
        elif status_filter == "exported":
            rows = [row for row in rows if row.get("normal_export_status") == "exported"]
        elif status_filter == "stale":
            rows = [row for row in rows if row.get("normal_export_status") == "stale"]
        elif status_filter == "draft":
            draft_ids = set(self.database.normal_processing_draft_ids())
            draft_ids.update(int(proposal_id) for proposal_id in self._normal_drafts)
            rows = [row for row in rows if int(row["id"]) in draft_ids]
        elif status_filter == "needs_category":
            rows = [row for row in rows if not row.get("category")]
        for row in rows:
            category = row.get("category")
            label = category.replace("_", " ").title() if category else "Choose category"
            confirmed = bool(row.get("normal_confirmed"))
            classification_status = ("Invalid · excluded from training" if row.get("normal_is_invalid") else
                                     "Confirmed" if confirmed else
                                      "Draft" if int(row["id"]) in self._normal_drafts else "Not confirmed")
            export_status = {"exported": "Exported", "failed": "Export failed",
                             "stale": "Prior export stale after correction"}.get(
                row.get("normal_export_status"))
            suffix = f" · {export_status}" if export_status else ""
            item = QListWidgetItem(f"{label}\n{classification_status}{suffix} · select to export")
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, dict(row))
            item.setToolTip(Path(row["path"]).name)
            self.normal_gallery.addItem(item)
            item.setSelected(int(row["id"]) in selected_ids)
            if current_id == int(row["id"]):
                self.normal_gallery.setCurrentItem(item)

        self.normal_gallery.blockSignals(False)
        confirmed_count = sum(bool(row.get("normal_confirmed")) for row in rows)
        invalid_count = sum(bool(row.get("normal_is_invalid")) for row in rows)
        stale_count = sum(row.get("normal_export_status") == "stale" for row in rows)
        self.normal_gallery_count.setText(
            f"{len(rows)} proposals · {confirmed_count} confirmed · "
            f"{invalid_count} invalid · {stale_count} stale"
        )
        self.normal_export_button.setEnabled(
            self._selected_normal_crop_count() > 0
            and not (self.normal_export_worker and self.normal_export_worker.isRunning())
        )
        PySide6.QtCore.QTimer.singleShot(0, self._load_visible_normal_thumbnails)
        if not rows:
            empty = QListWidgetItem("No crop suggestions here yet.\nScan the folder, then analyze new or changed images.")
            empty.setFlags(PySide6.QtCore.Qt.ItemFlag.NoItemFlags)
            self.normal_gallery.addItem(empty)
            self._normal_crop_pixmap = QPixmap()
            self.normal_preview.set_source_pixmap(QPixmap())
            self.normal_preview.setText("Choose a crop suggestion")
            self.normal_details.setText("Select a crop to inspect it.")
        self._normal_item_changed(None)

    def _load_visible_normal_thumbnails(self) -> None:
        """Load only visible gallery thumbnails using the bounded cache."""
        if not hasattr(self, "normal_gallery"):
            return
        viewport = self.normal_gallery.viewport()
        visible_indexes = []
        for index in range(self.normal_gallery.count()):
            rect = self.normal_gallery.visualItemRect(self.normal_gallery.item(index))
            if rect.intersects(viewport.rect()):
                visible_indexes.append(index)
        if visible_indexes:
            first = visible_indexes[0]
            last = visible_indexes[-1]
        else:
            first = self.normal_gallery.indexAt(viewport.rect().topLeft()).row()
            last = self.normal_gallery.indexAt(viewport.rect().bottomLeft()).row()
        if first < 0:
            first = 0
        if last < 0:
            last = min(first + 30, self.normal_gallery.count() - 1)
        last = min(last, first + 24)
        for index in range(max(0, first - 5), min(self.normal_gallery.count(), last + 5)):
            item = self.normal_gallery.item(index)
            row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
            if not row:
                continue
            if not str(row.get("path") or "").strip():
                item.setToolTip("Thumbnail unavailable: source path is missing.")
                continue
            box = row.get("bbox_xyxy")
            cache_key = (
                int(row["id"]),
                str(row.get("content_sha256") or ""),
                tuple(round(float(value), 3) for value in box) if box and len(box) == 4 else None,
                str(row.get("normal_clothing_broad_family") or ""),
                str(row.get("normal_clothing_cover_area") or ""),
            )
            pixmap = self._normal_gallery_crop_cache.get(cache_key)
            if pixmap is not None:
                self._normal_cache_stats["thumbnail_hits"] += 1
                self._normal_gallery_crop_cache.move_to_end(cache_key)
                item.setIcon(QIcon(pixmap.scaled(
                    PySide6.QtCore.QSize(132, 116),
                    PySide6.QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    PySide6.QtCore.Qt.TransformationMode.SmoothTransformation,
                )))
                continue
            self._normal_cache_stats["thumbnail_misses"] += 1
            pixmap = QPixmap(str(row["path"]))
            if pixmap.isNull():
                item.setToolTip("Thumbnail unavailable: source image decode failed.")
            else:
                item.setToolTip(Path(row["path"]).name)
            if not pixmap.isNull() and box and len(box) == 4:
                x1, y1, x2, y2 = (int(round(float(value))) for value in box)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(pixmap.width(), x2), min(pixmap.height(), y2)
                if x2 > x1 and y2 > y1:
                    pixmap = pixmap.copy(x1, y1, x2 - x1, y2 - y1)
            self._normal_gallery_crop_cache[cache_key] = pixmap
            while len(self._normal_gallery_crop_cache) > self._normal_gallery_crop_cache_limit:
                self._normal_gallery_crop_cache.popitem(last=False)
                self._normal_cache_stats["thumbnail_evictions"] += 1
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap.scaled(
                    PySide6.QtCore.QSize(132, 116),
                    PySide6.QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    PySide6.QtCore.Qt.TransformationMode.SmoothTransformation,
                )))

    def _schedule_visible_normal_thumbnails(self, *_):
        self._normal_thumbnail_debounce.start()

    def _selected_normal_crop_count(self) -> int:
        if not hasattr(self, "normal_gallery"):
            return 0
        return sum(bool(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)) for item in self.normal_gallery.selectedItems())

    def _normal_suggestion_info(self, row: dict) -> dict:
        from app.core.proposals import YOLO_FULLBODY_MAIN_TAGS, valid_normal_cnn_suggestion
        from app.core.yolo_registry import is_approved_yolo_identity
        cnn_name = str(row.get("cnn_class_name") or "").strip()
        region = str(row.get("yolo_class_name") or row.get("asset_type") or "").strip()
        if row.get("cnn_suggestion_stale") or row.get("stale_due_to_revision"):
            return {"value": None, "task_head": None, "origin": "Stale suggestion", "confidence": None}
        if cnn_name:
            if not valid_normal_cnn_suggestion(
                    row.get("cnn_model_id"), row.get("cnn_status"), cnn_name,
                    row.get("cnn_confidence"), region):
                return {"value": None, "task_head": None,
                        "origin": "Unsupported model output", "confidence": None}
            confidence = row.get("cnn_confidence")
            if confidence is not None:
                try:
                    confidence = float(confidence)
                    if not 0.0 <= confidence <= 1.0:
                        confidence = None
                except (TypeError, ValueError):
                    confidence = None
            return {
                "value": cnn_name,
                "task_head": "clothing_broad",
                "origin": "CNN suggestion",
                "confidence": confidence,
            }
        class_id = row.get("yolo_class_id", row.get("yolo_original_class_id"))
        if (is_approved_yolo_identity(class_id, region)
                and region in YOLO_FULLBODY_MAIN_TAGS):
            return {
                "value": YOLO_FULLBODY_MAIN_TAGS[region],
                "task_head": "fullbody",
                "origin": "YOLO-derived final-tag suggestion",
                "confidence": row.get("yolo_confidence"),
            }
        return {"value": None, "task_head": None, "origin": "No verified model suggestion", "confidence": None}

    def _update_normal_review_card(self, row: dict | None) -> None:
        if not row:
            self.normal_review_card.setVisible(False)
            return
        self.normal_review_card.setVisible(True)
        detection_id = row.get("detection_id")
        effective_class = row.get("yolo_class_name") or "none"
        original_class = row.get("yolo_original_class_name") or row.get("yolo_class_name") or "none"
        confidence = row.get("yolo_confidence")
        confidence_text = f"{float(confidence):.1%}" if confidence is not None else "not available"
        original_note = f" · original YOLO: {original_class}" if original_class != effective_class else ""
        bbox_status = str(row.get("bbox_review_status") or "awaiting BBox approval")
        revision = row.get("bbox_revision")
        revision_text = f"revision #{revision}" if revision is not None else "no saved BBox revision"
        box = row.get("bbox_xyxy")
        box_text = ", ".join(str(round(float(value), 1)) for value in box) if box else "unavailable"
        self.normal_detection_review.setText(
            f"Detection #{detection_id} · Proposal #{row['id']} · effective YOLO: {effective_class}{original_note}\n"
            f"YOLO confidence: {confidence_text} · BBox: {box_text}\n"
            f"BBox status: {bbox_status} · {revision_text}"
        )
        if row.get("crop_generation_error"):
            freshness = f"Crop unavailable: {row['crop_generation_error']} · stale preview is not current"
        elif row.get("crop_fresh"):
            freshness = "Fresh: active crop matches the effective BBox"
        elif row.get("active_crop_id"):
            freshness = "Stale crop: active crop does not match the effective BBox"
        else:
            freshness = "Crop freshness: no active cached crop; preview is regenerated from the effective BBox"
        if row.get("stale_due_to_revision") or row.get("cnn_suggestion_stale"):
            freshness += " · stale after Professional Review correction"
        self.normal_crop_freshness.setText(freshness)
        suggestion = self._normal_suggestion_info(row)
        if suggestion["value"]:
            confidence_text = (
                f" · confidence {float(suggestion['confidence']):.1%}"
                if suggestion["confidence"] is not None
                else ""
            )
            human_value = (
                self.normal_assign_category.currentData()
                and self.normal_body_tag.currentData()
            )
            human_text = f"\nHuman-selected value: {human_value}" if human_value else ""
            self.normal_suggestion_label.setText(
                f"Suggested Final Tag: {suggestion['value']} · origin: {suggestion['origin']}{confidence_text}{human_text}"
            )
            self.normal_suggestion_approve.setEnabled(True)
            self.normal_suggestion_reject.setEnabled(True)
        else:
            self.normal_suggestion_label.setText("Suggested Final Tag: none · no verified suggestion")
            self.normal_suggestion_approve.setEnabled(False)
            self.normal_suggestion_reject.setEnabled(False)
        status = "Not confirmed"
        if row.get("normal_is_invalid"):
            status = "Invalid crop · excluded from training"
        elif row.get("normal_confirmed"):
            status = "Confirmed classification"
        elif int(row["id"]) in self._normal_drafts:
            status = "Draft saved · overall confirmation pending"
        try:
            task_status = self.database.classification_task_status(int(row["id"]))
            suggestion_task = suggestion["task_head"]
            if suggestion_task and suggestion_task in task_status:
                review = task_status[suggestion_task]
                review_status = str(review.get("confirmation_status") or "")
                if review_status == "rejected":
                    status = "Suggestion rejected · crop remains usable"
                elif review_status == "draft":
                    status = "Suggestion approved · Confirm classification still required"
        except Exception:
            pass
        self.normal_suggestion_status.setText(f"Review status: {status}")
        invalid = bool(row.get("normal_is_invalid"))
        self.normal_mark_invalid.setText("Restore Crop" if invalid else "Mark Crop Invalid")
        self.normal_mark_invalid.setObjectName("DangerButton" if not invalid else "PrimaryButton")

    def _normal_item_changed(self, _item=None):
        count = self._selected_normal_crop_count()
        available = sum(bool(self.normal_gallery.item(index).data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
                        for index in range(self.normal_gallery.count()))
        self.normal_gallery_count.setText(f"{available} suggestions · {count} selected")
        self.normal_export_button.setEnabled(
            count > 0 and not (self.normal_export_worker and self.normal_export_worker.isRunning())
        )
        self._normal_category_choice_changed()

    def _select_all_normal_crops(self):
        available = [self.normal_gallery.item(index) for index in range(self.normal_gallery.count())
                     if self.normal_gallery.item(index).data(PySide6.QtCore.Qt.ItemDataRole.UserRole)]
        select = self._selected_normal_crop_count() != len(available)
        for item in available:
            item.setSelected(select)
        self._normal_item_changed(None)

    def _normal_selection_changed(self, current, _previous):
        selection_start = PySide6.QtCore.QElapsedTimer()
        selection_start.start()
        if _previous:
            previous_row = _previous.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
            if previous_row:
                previous_id = int(previous_row["id"])
                if self._normal_loaded_proposal_id == previous_id:
                    self._capture_normal_draft(previous_row)
        row = current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if current else None
        if not row:
            self.normal_preview.set_source_pixmap(QPixmap())
            self.normal_preview.setText("Select a crop to inspect it")
            self.normal_details.setText("Select a crop to inspect it.")
            self._update_normal_review_card(None)
            for widget in (
                self.normal_output_heading, self.normal_assign_category,
                self.normal_body_tag_row, self.normal_clothing_broad_row,
                self.normal_clothing_cover_row, self.normal_clothing_suggestion,
                self.normal_state_row, self.normal_fullbody_cnn_row,
                self.normal_body_cnn_row, self.normal_shared_target_row,
                self.normal_tags_heading, self.normal_subtags,
                self.normal_location_row, self.normal_location_suggestions,
                self.normal_export_heading, self.normal_filename_preview,
                self.normal_apply_category_button,
            ):
                widget.setVisible(False)
            return
        self._loading_normal_crop = True
        row = dict(row)
        if int(row["id"]) not in self._normal_drafts:
            try:
                restored = self.database.load_normal_processing_draft(int(row["id"]))
                if restored:
                    self._normal_drafts[int(row["id"])] = restored
                    row["_restored_draft"] = True
                    self.status_label.showMessage("Restored unconfirmed draft")
            except Exception as error:
                self.status_label.showMessage(f"Could not restore draft · {error}")
        draft = self._normal_drafts.get(int(row["id"]))
        self.normal_discard_draft_button.setEnabled(draft is not None)
        if draft and draft.get("category") == row.get("category"):
            row.update(draft)
            current.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, row)
        try:
            active_crop = self.database.ensure_active_detection_crop(int(row["detection_id"]))
            row["active_crop_id"] = active_crop["crop_id"]
            row["active_crop_path"] = active_crop["crop_path"]
            row["crop_fresh"] = True
            row["bbox_revision"] = active_crop["bbox_revision"]
            row["bbox_xyxy"] = active_crop["bbox_xyxy"]
            current.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, row)
        except Exception as crop_error:
            row["crop_fresh"] = False
            row["crop_generation_error"] = str(crop_error)
            current.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, row)
        self._normal_crop_pixmap, crop_note = self._render_normal_crop(row)
        self.normal_preview.setText("" if not self._normal_crop_pixmap.isNull()
                                    else "Preview unavailable")
        self.normal_preview.set_source_pixmap(self._normal_crop_pixmap)
        category = row.get("category")
        category_index = self.normal_assign_category.findData(category)
        self.normal_assign_category.blockSignals(True)
        self.normal_assign_category.setCurrentIndex(category_index)
        self.normal_assign_category.blockSignals(False)
        self._refresh_normal_taxonomy_options(row)
        self._loading_normal_crop = False
        self._normal_category_choice_changed(record_draft=False)
        self._normal_loaded_proposal_id = int(row["id"])
        suggestion = row.get("yolo_class_name") or row.get("cnn_class_name") or "none"
        if row.get("cnn_suggestion_stale"):
            suggestion += " · stale after Professional Review correction"
        classification_status = ("confirmed" if row.get("normal_confirmed") else
                                 "draft saved for this session" if int(row["id"]) in self._normal_drafts
                                 else "not confirmed")
        if row.get("normal_is_invalid"):
            classification_status = "invalid · excluded from training"
        draft_notice = ""
        if row.get("_restored_draft"):
            draft_notice = "\nRestored unconfirmed draft"
        if row.get("stale_due_to_revision"):
            draft_notice += "\nDraft requires review because its source/BBox revision changed"
        self.normal_details.setText(
            f"{category.replace('_', ' ').title() if category else 'Category needed'} · {classification_status}\n"
            f"Model evidence: {suggestion} · suggestion only\n{crop_note}{draft_notice}"
        )
        self._update_normal_review_card(row)
        elapsed = selection_start.elapsed()
        self._normal_cache_stats["selection_timings_ms"].append(float(elapsed))
        if len(self._normal_cache_stats["selection_timings_ms"]) > 200:
            self._normal_cache_stats["selection_timings_ms"].pop(0)
        self._update_normal_position()

    def _approve_normal_suggestion(self) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row:
            return
        suggestion = self._normal_suggestion_info(row)
        if not suggestion["value"]:
            QMessageBox.information(self, "No suggestion", "This crop has no verified task-specific suggestion.")
            return
        try:
            review_id = self.database.save_normal_suggestion_review(int(row["id"]), "draft")
            task_head = suggestion["task_head"]
            value = suggestion["value"]
            if task_head == "fullbody":
                self.normal_assign_category.setCurrentIndex(
                    self.normal_assign_category.findData("fullbody"))
                self.normal_body_tag.setCurrentIndex(self.normal_body_tag.findData(value))
            elif task_head == "body_images":
                self.normal_assign_category.setCurrentIndex(
                    self.normal_assign_category.findData("body_images"))
            elif task_head == "clothing_broad":
                self.normal_assign_category.setCurrentIndex(
                    self.normal_assign_category.findData("clothing"))
                self.normal_clothing_broad.setCurrentIndex(
                    self.normal_clothing_broad.findData(value))
            self._normal_category_choice_changed()
            self._update_normal_review_card(row)
            self.status_label.showMessage(
                f"Suggestion approved for Proposal #{int(row['id'])} · review #{review_id}; Confirm classification is still required"
            )
        except Exception as error:
            logger.exception("Could not approve Normal Processing suggestion")
            QMessageBox.warning(self, "Could not approve suggestion", str(error))

    def _reject_normal_suggestion(self) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row:
            return
        suggestion = self._normal_suggestion_info(row)
        if not suggestion["value"]:
            QMessageBox.information(self, "No suggestion", "This crop has no verified task-specific suggestion.")
            return
        answer = QMessageBox.question(
            self,
            "Reject model suggestion",
            f"Reject {suggestion['value']} for this Proposal only?\n\n"
            "The suggestion is unsuitable. The crop will remain usable and this does not mark it invalid.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            review_id = self.database.save_normal_suggestion_review(int(row["id"]), "rejected")
            self.status_label.showMessage(
                f"Suggestion rejected · crop remains usable · review #{review_id}"
            )
            self._update_normal_review_card(row)
        except Exception as error:
            logger.exception("Could not reject Normal Processing suggestion")
            QMessageBox.warning(self, "Could not reject suggestion", str(error))

    def _mark_current_normal_crop_invalid(self) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row:
            return
        if row.get("normal_is_invalid"):
            try:
                self.database.restore_normal_crop_invalid(int(row["id"]))
                row.update({"normal_is_invalid": 0, "category": row.get("proposed_category")})
                item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, row)
                self.status_label.showMessage("Crop restored · proposal remains independent")
                self._refresh_normal_gallery()
            except Exception as error:
                QMessageBox.warning(self, "Could not restore crop", str(error))
            return
        answer = QMessageBox.question(
            self,
            "Mark this crop invalid",
            f"Mark Proposal #{int(row['id'])} / Detection #{row.get('detection_id')} invalid?\n\n"
            "This affects this crop/Proposal record only. The source image and sibling detections remain intact.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.save_normal_crop_choice(int(row["id"]), "invalid")
            row.update({"category": "invalid", "normal_is_invalid": 1, "normal_confirmed": False})
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, row)
            self.status_label.showMessage("Crop marked invalid · excluded from export and training")
            self._refresh_normal_gallery()
        except Exception as error:
            logger.exception("Could not mark Normal Processing crop invalid")
            QMessageBox.warning(self, "Could not mark crop invalid", str(error))

    def _toggle_normal_source_context(self, checked: bool) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not checked or not row:
            if hasattr(self, "_normal_crop_pixmap"):
                self.normal_preview.set_source_pixmap(self._normal_crop_pixmap)
            self.normal_source_context.setText("Show Source Context")
            return
        try:
            from PIL import ImageDraw
            with Image.open(row["path"]) as opened:
                source = opened.convert("RGBA")
                box = row.get("bbox_xyxy")
                if box and len(box) == 4:
                    draw = ImageDraw.Draw(source)
                    x1, y1, x2, y2 = (int(round(float(value))) for value in box)
                    draw.rectangle((x1, y1, x2, y2), outline=(255, 82, 82, 255), width=5)
                qimage = QImage(
                    source.tobytes(), source.width, source.height,
                    source.width * 4, QImage.Format.Format_RGBA8888,
                ).copy()
                pixmap = QPixmap.fromImage(qimage)
                self.normal_preview.set_source_pixmap(pixmap)
                source.close()
            self.normal_source_context.setText("Show Crop")
        except Exception as error:
            self.normal_source_context.setChecked(False)
            QMessageBox.warning(self, "Source preview unavailable", str(error))

    def _open_normal_in_professional_review(self) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row:
            return
        try:
            if self._normal_loaded_proposal_id == int(row["id"]):
                self._capture_normal_draft(row)
            source_id = int(row["source_id"])
            detection_id = int(row["detection_id"])
            proposal_id = int(row["id"])
            self._professional_keep_source_id = source_id
            self._professional_keep_proposal_id = proposal_id
            self.current_category = "sources"
            self._select_nav_key("sources")
            self._refresh_navigation()
            self._refresh_gallery()
            for index in range(self.gallery.count()):
                candidate = self.gallery.item(index)
                data = candidate.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
                if data and int(data.get("id", -1)) == source_id:
                    self.gallery.setCurrentItem(candidate)
                    break
            self.workspace_tabs.setCurrentIndex(1)
            for index in range(self.detection_list.count()):
                candidate = self.detection_list.item(index)
                if int(candidate.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)) == detection_id:
                    self.detection_list.setCurrentItem(candidate)
                    self.status_label.showMessage(
                        f"Professional Review: Detection #{detection_id} · Proposal #{proposal_id}"
                    )
                    return
            raise ValueError(f"Detection #{detection_id} is not visible for this source.")
        except Exception as error:
            QMessageBox.warning(self, "Could not open Professional Review", str(error))

    def _normal_draft_payload(self, row: dict) -> dict:
        category = self.normal_assign_category.currentData()
        return {
            "proposal_id": int(row["id"]),
            "source_image_id": row.get("source_id") or row.get("source_image_id"),
            "detection_id": row.get("detection_id"),
            "source_sha256": row.get("content_sha256"),
            "bbox_revision": row.get("bbox_revision"),
            "crop_identity": (
                f"{row.get('content_sha256')}:{','.join(str(round(float(value),3)) for value in row.get('bbox_xyxy',[]))}"
                if row.get("bbox_xyxy") else None
            ),
            "category": category,
            "normal_main_tag": self.normal_body_tag.currentData(),
            "normal_fullbody_state": self.normal_fullbody_state.currentData(),
            "normal_fullbody_cnn_target": self.normal_fullbody_cnn_target.currentData(),
            "normal_body_images_cum_target": (
                True if self.normal_body_cum.isChecked()
                else False if self.normal_body_cum.checkState() == PySide6.QtCore.Qt.CheckState.Unchecked
                else None
            ),
            "normal_body_images_cum_evaluated": (
                self.normal_body_cum.checkState() != PySide6.QtCore.Qt.CheckState.PartiallyChecked
            ),
            "normal_body_images_accessory_target": (
                True if self.normal_body_accessory.isChecked()
                else False if self.normal_body_accessory.checkState() == PySide6.QtCore.Qt.CheckState.Unchecked
                else None
            ),
            "normal_body_images_accessory_evaluated": (
                self.normal_body_accessory.checkState() != PySide6.QtCore.Qt.CheckState.PartiallyChecked
            ),
            "normal_body_images_completed": self.normal_body_completed.isChecked(),
            "normal_arousal_cnn_target": self.normal_arousal_target.currentData(),
            "normal_corruption_cnn_target": self.normal_corruption_target.currentData(),
            "normal_clothing_broad_family": self.normal_clothing_broad.currentData(),
            "normal_clothing_cover_area": self.normal_clothing_cover_area.currentData(),
            "normal_subtags": [
                str(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
                for item in self.normal_subtags.selectedItems()
            ],
            "normal_location_value": self._selected_normal_location(),
            "_draft_corruption_states": [
                str(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
                for item in self.normal_corruption_states.selectedItems()
            ],
            "taxonomy_version": row.get("normal_taxonomy_version"),
            "draft_schema_version": 1,
            "stale_due_to_revision": bool(row.get("normal_draft_stale")),
        }

    def _schedule_normal_draft_autosave(self) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row or self._loading_normal_crop:
            return
        self.status_label.showMessage("Saving draft…")
        self._normal_draft_debounce.start()

    def _flush_normal_draft_autosave(self) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row:
            return
        try:
            payload = self._normal_draft_payload(dict(row))
            saved = self.database.save_normal_processing_draft(int(row["id"]), payload)
            self._normal_drafts[int(row["id"])] = saved
            self.status_label.showMessage("Draft saved")
        except Exception as error:
            try:
                self.database.mark_normal_processing_draft_save_failed(int(row["id"]))
            except Exception:
                pass
            self.status_label.showMessage(f"Draft save failed · kept in memory · {error}")

    def _discard_current_normal_draft(self) -> None:
        item = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row:
            return
        answer = QMessageBox.question(
            self,
            "Discard draft",
            f"Discard the unsaved draft for Proposal #{int(row['id'])}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.database.discard_normal_processing_draft(int(row["id"]))
            self._normal_drafts.pop(int(row["id"]), None)
            self.normal_discard_draft_button.setEnabled(False)
            self.status_label.showMessage("Draft discarded")
            self._refresh_normal_gallery()
        except Exception as error:
            QMessageBox.warning(self, "Could not discard draft", str(error))

    def _normal_category_changed(self, *_):
        current = self.normal_gallery.currentItem()
        row = current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if current else None
        selected_category = self.normal_assign_category.currentData()
        if row:
            row = dict(row)
            if "_draft_corruption_states" not in row:
                row["_draft_corruption_states"] = []
            draft = self._normal_drafts.get(int(row["id"]))
            if draft and draft.get("category") == selected_category:
                row.update(draft)
            elif str(row.get("category") or "") != selected_category:
                row["category"] = selected_category
                row["chosen_category"] = selected_category
                row["normal_main_tag"] = None
                row["body_image_main_tag"] = None
                row["normal_fullbody_state"] = None
                row["normal_fullbody_cnn_target"] = None
                row["normal_clothing_broad_family"] = None
                row["normal_clothing_cover_area"] = None
                row["normal_subtags"] = []
                row["_draft_corruption_states"] = []
                row["normal_location_value"] = None
        self._refresh_normal_taxonomy_options(row or {})
        self._normal_category_choice_changed()

    def _refresh_normal_taxonomy_options(self, row: dict):
        category = self.normal_assign_category.currentData()
        from app.core.classification_eligibility import required_tasks
        effective_region = str(row.get("yolo_class_name") or "")
        eligible_tasks = set(required_tasks(effective_region))
        eligible_categories = {
            "fullbody": "fullbody" in eligible_tasks,
            "body_images": "body_images" in eligible_tasks,
            "clothing": bool({"clothing_broad", "clothing_fine"} & eligible_tasks),
        }
        self.normal_assign_category.blockSignals(True)
        saved_category = category
        self.normal_assign_category.clear()
        self.normal_assign_category.addItem("Choose category", None)
        if eligible_categories["fullbody"]:
            self.normal_assign_category.addItem("Fullbody", "fullbody")
        if eligible_categories["body_images"]:
            self.normal_assign_category.addItem("Body Images", "body_images")
        if eligible_categories["clothing"]:
            self.normal_assign_category.addItem("Clothing", "clothing")
        self.normal_assign_category.addItem("Invalid · wrong crop", "invalid")
        if saved_category in {"fullbody", "body_images", "clothing"} and not eligible_categories[saved_category]:
            saved_category = None
        saved_index = self.normal_assign_category.findData(saved_category)
        self.normal_assign_category.setCurrentIndex(saved_index if saved_index >= 0 else 0)
        category = self.normal_assign_category.currentData()
        self.normal_assign_category.blockSignals(False)
        self.normal_output_heading.setVisible(True)
        self.normal_assign_category.setVisible(True)
        self.normal_tags_heading.setVisible(True)
        self.normal_subtags.setVisible(True)
        self.normal_export_heading.setVisible(True)
        self.normal_filename_preview.setVisible(True)
        self.normal_apply_category_button.setVisible(True)
        if category == "invalid":
            self.normal_body_tag_row.setVisible(False)
            self.normal_apply_category_button.setText("Confirm invalid · Next")
            current = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
            has_current_crop = bool(current and current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
            self.normal_apply_category_button.setEnabled(has_current_crop)
            if not self._loading_normal_crop and has_current_crop:
                self._capture_normal_draft(current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
            return
        self.normal_apply_category_button.setText("Confirm classification & Next")
        tag_type = {"fullbody": "fullbody", "body_images": "body_images", "clothing": "clothing"}.get(category)
        entries = self.tag_library.entries(group=tag_type, include_review=False) if tag_type else []
        types = {"main", "tag"} if category == "clothing" else {"main"}
        values = [(entry.get("display_name", entry.get("name", "")), entry.get("serialized_value"))
                  for entry in entries if entry.get("tag_type") in types
                  and entry.get("serialized_value")
                  and not (category == "fullbody" and entry.get("serialized_value") in {"topless", "bottomless"})]
        deduplicated_values = []
        seen_values = set()
        for label, value in values:
            if value in seen_values:
                continue
            seen_values.add(value)
            deduplicated_values.append((label, value))
        values = deduplicated_values
        selected = row.get("normal_main_tag") or row.get("body_image_main_tag")
        self.normal_body_tag.blockSignals(True)
        self.normal_body_tag.clear()
        self.normal_body_tag.addItem("Choose a main tag", None)
        for label, value in values:
            self.normal_body_tag.addItem(label, value)
        self.normal_body_tag.setCurrentIndex(max(0, self.normal_body_tag.findData(selected)))
        self.normal_body_tag.blockSignals(False)
        self.normal_clothing_broad_row.setVisible(category == "clothing")
        self.normal_clothing_suggestion.setVisible(category == "clothing")
        self.normal_clothing_broad.blockSignals(True)
        self.normal_clothing_broad.setCurrentIndex(max(0, self.normal_clothing_broad.findData(
            row.get("normal_clothing_broad_family"))))
        self.normal_clothing_broad.blockSignals(False)
        if category == "clothing":
            family = self.normal_clothing_broad.currentData()
            accepted = set(suggested_clothing_tags(family)) if family else set()
            detail_selected = selected
            self.normal_body_tag.blockSignals(True)
            self.normal_body_tag.clear()
            self.normal_body_tag.addItem("Choose detailed tag", None)
            entry_map = {
                entry.get("serialized_value"): entry
                for entry in entries
                if entry.get("serialized_value")
            }
            for detail in sorted(accepted):
                entry = entry_map.get(detail)
                label = entry.get("display_name", detail) if entry else detail
                self.normal_body_tag.addItem(str(label), detail)
            detail_index = self.normal_body_tag.findData(detail_selected)
            self.normal_body_tag.setCurrentIndex(detail_index if detail_index >= 0 else 0)
            self.normal_body_tag.blockSignals(False)
        self.normal_clothing_cover_row.setVisible(category == "clothing")
        self._set_normal_clothing_cover_options(
            self.normal_clothing_broad.currentData(), row.get("normal_clothing_cover_area")
        )
        cnn_suggestion = row.get("cnn_class_name") or "none"
        if row.get("cnn_suggestion_stale"):
            cnn_suggestion += " · stale after Professional Review correction"
        self.normal_clothing_suggestion.setText(
            f"Broad Clothing model suggestion: {cnn_suggestion}. Choose the correct broad group above; "
            "the detailed type below is a separate label."
        )
        self.normal_state_row.setVisible(category == "fullbody")
        self.normal_fullbody_cnn_row.setVisible(category == "fullbody")
        self.normal_body_cnn_row.setVisible(category == "body_images")
        arousal_eligible = shared_head_eligible(
            "arousal", str(row.get("yolo_class_name") or ""), confirmed_portrait=None)
        self.normal_arousal_target.setVisible(arousal_eligible)
        self.normal_arousal_target_label.setVisible(arousal_eligible)
        corruption_eligible = shared_head_eligible(
            "corruption", str(row.get("yolo_class_name") or ""), confirmed_portrait=None)
        self.normal_corruption_target.setVisible(corruption_eligible)
        self.normal_corruption_target_label.setVisible(corruption_eligible)
        self.normal_shared_target_row.setVisible(category != "invalid" and (
            arousal_eligible or corruption_eligible))
        location_eligible = bool(location_candidates(
            row.get("yolo_class_name"), model_id=row.get("yolo_model_id"),
            class_id=row.get("yolo_class_id"), checkpoint_digest=row.get("yolo_model_digest")))
        self.normal_location_row.setVisible(location_eligible)
        self.normal_location_suggestions.setVisible(location_eligible)
        state = row.get("normal_fullbody_state")
        self.normal_fullbody_state.setCurrentIndex(max(0, self.normal_fullbody_state.findData(state)))
        self.normal_fullbody_cnn_target.setCurrentIndex(max(0, self.normal_fullbody_cnn_target.findData(
            row.get("normal_fullbody_cnn_target"))))
        from PySide6.QtCore import Qt
        self.normal_body_cum.setCheckState(
            Qt.CheckState.Checked if row.get("normal_body_images_cum_evaluated")
            and row.get("normal_body_images_cum_target") else
            Qt.CheckState.Unchecked if row.get("normal_body_images_cum_evaluated") else
            Qt.CheckState.PartiallyChecked
        )
        self.normal_body_accessory.setCheckState(
            Qt.CheckState.Checked if row.get("normal_body_images_accessory_evaluated")
            and row.get("normal_body_images_accessory_target") else
            Qt.CheckState.Unchecked if row.get("normal_body_images_accessory_evaluated") else
            Qt.CheckState.PartiallyChecked
        )
        self.normal_body_completed.setChecked(bool(row.get("normal_body_images_completed")))
        self.normal_arousal_target.setCurrentIndex(max(0, self.normal_arousal_target.findData(
            row.get("normal_arousal_cnn_target"))))
        self.normal_corruption_target.setCurrentIndex(max(0, self.normal_corruption_target.findData(
            row.get("normal_corruption_cnn_target"))))
        location = row.get("normal_location_value")
        self.normal_location.clearSelection()
        for index in range(self.normal_location.count()):
            item = self.normal_location.item(index)
            if item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) == location:
                item.setSelected(True)
                break
        suggested_locations = location_candidates(
            row.get("yolo_class_name"), model_id=row.get("yolo_model_id"),
            class_id=row.get("yolo_class_id"), checkpoint_digest=row.get("yolo_model_digest"))
        self.normal_location_suggestions.setText(
            "Location suggestions (choose one manually): " +
            (", ".join(suggested_locations) if suggested_locations else "no verified suggestion for this model evidence")
        )
        selected_tags = set(row.get("normal_subtags", []))
        selected_corruption = (set(row["_draft_corruption_states"])
                               if "_draft_corruption_states" in row
                               else selected_tags & set(REGISTRY["corruption_values"]))
        selected_tags -= set(REGISTRY["corruption_values"])
        # Existing values are loaded from structured normal-crop choices only.
        tag_values = {entry.get("serialized_value") for entry in entries
                      if entry.get("tag_type") in {"subtag", "modifier"}
                      and entry.get("selectable") and not entry.get("requires_review")}
        main_value = self.normal_body_tag.currentData()
        if category == "body_images":
            tag_values.update(REGISTRY["body_images"]["supported_main_subtag_pairs"].get(main_value, []))
        if category == "fullbody":
            import json
            policy_path = self.config.data_dir / "models" / "fullbody_classification_policy.json"
            tag_values.update(json.loads(policy_path.read_text(encoding="utf-8")).get("supported_subtags", []))
        tag_values.difference_update(REGISTRY["locations"]["canonical_values"])
        tag_values.difference_update(REGISTRY["corruption_values"])
        tag_values.discard("park")
        self.normal_subtags.blockSignals(True)
        self.normal_subtags.clear()
        for value in sorted(tag for tag in tag_values if tag):
            item = QListWidgetItem(value)
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() & ~PySide6.QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setSelected(value in selected_tags)
            self.normal_subtags.addItem(item)
        self.normal_subtags.blockSignals(False)
        self.normal_corruption_states.blockSignals(True)
        self.normal_corruption_states.clear()
        display_names = {"slut": "Slut", "whore": "Whore", "u_whore": "Ultimate Whore",
                         "conservative": "Conservative"}
        ordered_corruption_values = ("slut", "whore", "u_whore", "conservative")
        for value in ordered_corruption_values:
            item = QListWidgetItem(display_names[value])
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() & ~PySide6.QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setSelected(value in selected_corruption)
            self.normal_corruption_states.addItem(item)
        self.normal_corruption_states.blockSignals(False)

    def _render_normal_crop(self, row: dict) -> tuple[QPixmap, str]:
        box = row.get("bbox_xyxy")
        preview_key = (
            int(row["id"]) if row.get("id") is not None else -1,
            str(row.get("content_sha256") or ""),
            str(row.get("path") or ""),
            tuple(round(float(value), 3) for value in box) if box and len(box) == 4 else None,
            str(row.get("category") or row.get("proposed_category") or ""),
            str(row.get("normal_clothing_broad_family") or row.get("clothing_broad_family") or ""),
            str(row.get("normal_clothing_cover_area") or row.get("clothing_cover_area") or ""),
        )
        cached = self._normal_preview_cache.get(preview_key)
        if cached is not None:
            self._normal_cache_stats["preview_hits"] += 1
            self._normal_preview_cache.move_to_end(preview_key)
            return cached
        self._normal_cache_stats["preview_misses"] += 1
        try:
            with Image.open(row["path"]) as original:
                source = original.convert("RGBA" if "A" in original.getbands() else "RGB")
            try:
                item = {
                    "category": row.get("category") or row.get("proposed_category"),
                    "main_tag": row.get("body_image_main_tag") or row.get("asset_type"),
                    "clothing_broad_family": row.get("normal_clothing_broad_family"),
                    "clothing_cover_area": row.get("normal_clothing_cover_area"),
                    "bbox_xyxy": row.get("bbox_xyxy"),
                }
                try:
                    can_remove_portrait_background = (
                        item["category"] == "body_images"
                        and item["main_tag"] in {"portrait", "tportrait"}
                    )
                    crop, crop_policy = prepare_export_crop(
                        source, item, allow_missing_alpha=can_remove_portrait_background
                    )
                    if can_remove_portrait_background:
                        note = "Portrait background removal runs during export when needed."
                    elif crop_policy.get("policy") == "clothing_guide_cover_area_aspect_and_minimum_dimensions":
                        fit = crop_policy.get("fit_mode")
                        note = ("Clothing crop is centered inside the reviewed box to fit the guide ratio."
                                if fit == "centered_within_reviewed_box"
                                else "Clothing crop is expanded around the reviewed box to fit the guide ratio.")
                    else:
                        note = "Preview follows the folder's crop rules."
                except ValueError as error:
                    x1, y1, x2, y2 = (int(round(float(value))) for value in item["bbox_xyxy"])
                    crop = source.crop((max(0, x1), max(0, y1),
                                        min(source.width, x2), min(source.height, y2)))
                    if item["category"] == "fullbody":
                        note = "Detected region shown; background removal runs during export."
                    else:
                        note = f"Detected region shown; export needs attention: {error}"
                try:
                    if "A" in crop.getbands():
                        display = crop.convert("RGBA")
                        qimage = QImage(display.tobytes(), display.width, display.height,
                                        display.width * 4, QImage.Format.Format_RGBA8888).copy()
                    else:
                        display = crop.convert("RGB")
                        qimage = QImage(display.tobytes(), display.width, display.height,
                                        display.width * 3, QImage.Format.Format_RGB888).copy()
                    result = (QPixmap.fromImage(qimage), note)
                    self._normal_preview_cache[preview_key] = result
                    while len(self._normal_preview_cache) > self._normal_preview_cache_limit:
                        self._normal_preview_cache.popitem(last=False)
                        self._normal_cache_stats["preview_evictions"] += 1
                    return result
                finally:
                    crop.close()
            finally:
                source.close()
        except Exception as error:
            logger.exception("Could not render normal crop preview")
            return QPixmap(), f"Preview unavailable: {error}"

    def _normal_category_choice_changed(self, _index=None, *, record_draft: bool = True):
        category = self.normal_assign_category.currentData()
        self.normal_body_tag_row.setVisible(category in {"fullbody", "body_images", "clothing"})
        has_category = category in {"fullbody", "body_images", "clothing", "invalid"}
        has_valid_tag = category == "invalid" or bool(self.normal_body_tag.currentData())
        has_valid_state = category != "fullbody" or bool(self.normal_fullbody_state.currentData())
        has_broad_clothing = category != "clothing" or bool(self.normal_clothing_broad.currentData())
        has_cover_area = category != "clothing" or bool(self.normal_clothing_cover_area.currentData())
        current = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        has_current_crop = bool(current and current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
        self.normal_apply_category_button.setEnabled(
            has_category and has_current_crop and has_valid_tag
            and has_valid_state and has_broad_clothing and has_cover_area
        )
        if record_draft and not self._loading_normal_crop and has_current_crop:
            current_row = current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
            if current_row:
                self._capture_normal_draft(current_row)
        main_tag = self.normal_body_tag.currentData() or ""
        state = self.normal_fullbody_state.currentData() or ""
        location = self._selected_normal_location()
        subtags = [str(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
                   for item in self.normal_subtags.selectedItems()]
        extra = ", ".join([value for value in (location, *subtags) if value])
        category_label = {
            "fullbody": "Fullbody",
            "body_images": "Body Images",
            "clothing": "Clothing",
            "invalid": "Invalid",
        }.get(category, "Choose category")
        preview_text = f"{category_label}"
        if main_tag:
            preview_text += f" · {main_tag}"
        if state:
            preview_text += f" · {state}"
        if extra:
            preview_text += f" · {extra}"
        self.normal_filename_preview.setText(f"Filename preview: {preview_text}")
        self._schedule_normal_draft_autosave()

    def _selected_normal_location(self):
        selected = self.normal_location.selectedItems() if hasattr(self, "normal_location") else []
        return selected[0].data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if selected else None

    def _set_normal_clothing_cover_options(self, family: str | None, selected: str | None = None):
        from app.core.crop_rules import CLOTHING_FAMILY_AREAS
        labels = {"boobs_cover": "Boobs cover", "ass_cover": "Ass cover",
                  "pussy_cover": "Pussy cover", "leg_cover": "Leg cover",
                  "accessory_footwear": "Accessory footwear"}
        self.normal_clothing_cover_area.blockSignals(True)
        self.normal_clothing_cover_area.clear()
        self.normal_clothing_cover_area.addItem("Choose cover area", None)
        for area in CLOTHING_FAMILY_AREAS.get(str(family or ""), ()):
            self.normal_clothing_cover_area.addItem(labels[area], area)
        self.normal_clothing_cover_area.setCurrentIndex(
            max(0, self.normal_clothing_cover_area.findData(selected))
        )
        self.normal_clothing_cover_area.blockSignals(False)

    def _normal_clothing_broad_changed(self, *_):
        family = self.normal_clothing_broad.currentData()
        selected_detail = self.normal_body_tag.currentData()
        accepted = set(suggested_clothing_tags(family)) if family else set()
        self.normal_body_tag.blockSignals(True)
        self.normal_body_tag.clear()
        self.normal_body_tag.addItem("Choose detailed tag", None)
        for detail in sorted(accepted):
            entry = next(
                (row for row in self.tag_library.entries(group="clothing", include_review=False)
                 if row.get("serialized_value") == detail),
                None,
            )
            label = entry.get("display_name", detail) if entry else detail
            self.normal_body_tag.addItem(str(label), detail)
        detail_index = self.normal_body_tag.findData(selected_detail)
        self.normal_body_tag.setCurrentIndex(detail_index if detail_index >= 0 else 0)
        self.normal_body_tag.blockSignals(False)
        self._set_normal_clothing_cover_options(family)
        self._normal_clothing_cover_changed()

    def _normal_clothing_cover_changed(self, *_):
        self._normal_category_choice_changed()
        current = self.normal_gallery.currentItem() if hasattr(self, "normal_gallery") else None
        row = current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if current else None
        if not row or self.normal_assign_category.currentData() != "clothing":
            return
        preview_row = dict(row)
        preview_row.update({
            "category": "clothing",
            "main_tag": self.normal_body_tag.currentData(),
            "clothing_broad_family": self.normal_clothing_broad.currentData(),
            "clothing_cover_area": self.normal_clothing_cover_area.currentData(),
        })
        self._normal_crop_pixmap, crop_note = self._render_normal_crop(preview_row)
        self.normal_preview.setText("" if not self._normal_crop_pixmap.isNull() else "Preview unavailable")
        self.normal_preview.set_source_pixmap(self._normal_crop_pixmap)
        classification_status = ("invalid · excluded from training" if row.get("normal_is_invalid") else
                                 "confirmed" if row.get("normal_confirmed") else
                                 "draft saved for this session" if int(row["id"]) in self._normal_drafts
                                 else "not confirmed")
        suggestion = row.get("yolo_class_name") or row.get("cnn_class_name") or "none"
        self.normal_details.setText(
            f"Clothing · {classification_status}\nModel evidence: {suggestion} · suggestion only\n{crop_note}"
        )

    def _capture_normal_draft(self, row: dict) -> None:
        """Keep unconfirmed Normal Processing edits while the user moves between crops."""
        if self._loading_normal_crop or not row or row.get("id") is None:
            return
        category = self.normal_assign_category.currentData() or row.get("category")
        self._normal_drafts[int(row["id"])] = {
            "category": category,
            "chosen_category": category,
            "normal_main_tag": (self.normal_body_tag.currentData()
                                or row.get("normal_main_tag")
                                or row.get("body_image_main_tag")),
            "normal_fullbody_state": self.normal_fullbody_state.currentData(),
            "normal_fullbody_cnn_target": self.normal_fullbody_cnn_target.currentData(),
            "normal_body_images_cum_target": (True if self.normal_body_cum.isChecked()
                                               else False if self.normal_body_cum.checkState() == PySide6.QtCore.Qt.CheckState.Unchecked
                                               else None),
            "normal_body_images_cum_evaluated": self.normal_body_cum.checkState() != PySide6.QtCore.Qt.CheckState.PartiallyChecked,
            "normal_body_images_accessory_target": (True if self.normal_body_accessory.isChecked()
                                                     else False if self.normal_body_accessory.checkState() == PySide6.QtCore.Qt.CheckState.Unchecked
                                                     else None),
            "normal_body_images_accessory_evaluated": self.normal_body_accessory.checkState() != PySide6.QtCore.Qt.CheckState.PartiallyChecked,
            "normal_body_images_completed": self.normal_body_completed.isChecked(),
            "normal_arousal_cnn_target": self.normal_arousal_target.currentData(),
            "normal_corruption_cnn_target": self.normal_corruption_target.currentData(),
            "normal_clothing_broad_family": (
                self.normal_clothing_broad.currentData()
                or row.get("normal_clothing_broad_family")
            ),
            "normal_clothing_cover_area": (
                self.normal_clothing_cover_area.currentData()
                or row.get("normal_clothing_cover_area")
            ),
            "normal_subtags": [str(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
                               for item in self.normal_subtags.selectedItems()],
            "normal_location_value": self._selected_normal_location(),
            "_draft_corruption_states": [str(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
                                          for item in self.normal_corruption_states.selectedItems()],
        }

    def _confirm_current_normal_crop(self):
        category = self.normal_assign_category.currentData()
        if category not in {"fullbody", "body_images", "clothing", "invalid"}:
            return
        item = self.normal_gallery.currentItem()
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if not row:
            return
        if category == "invalid":
            try:
                self.database.save_normal_crop_choice(int(row["id"]), "invalid")
            except Exception as error:
                QMessageBox.warning(self, "Could not mark crop invalid", str(error))
                return
            self._normal_drafts.pop(int(row["id"]), None)
            row.update({"category": "invalid", "normal_is_invalid": 1, "normal_confirmed": False})
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, row)
            self.status_label.showMessage("Crop marked invalid · excluded from training until assigned a different class")
            self._refresh_normal_gallery()
            self._move_normal_selection(1)
            return
        tag = self.normal_body_tag.currentData()
        state = self.normal_fullbody_state.currentData() if category == "fullbody" else None
        fullbody_cnn_target = self.normal_fullbody_cnn_target.currentData() if category == "fullbody" else None
        body_images_cum_evaluated = (self.normal_body_cum.checkState()
                                     != PySide6.QtCore.Qt.CheckState.PartiallyChecked)
        body_images_cum_target = (True if self.normal_body_cum.isChecked()
                                  else False if body_images_cum_evaluated else None)
        body_images_accessory_evaluated = (self.normal_body_accessory.checkState()
                                           != PySide6.QtCore.Qt.CheckState.PartiallyChecked)
        body_images_accessory_target = (True if self.normal_body_accessory.isChecked()
                                        else False if body_images_accessory_evaluated else None)
        body_images_completed = self.normal_body_completed.isChecked()
        if category == "body_images" and body_images_completed and not (
                body_images_cum_evaluated and body_images_accessory_evaluated):
            QMessageBox.information(
                self, "Complete both decisions",
                "Before confirming none or both targets, evaluate both Cum and Accessory."
            )
            return
        arousal_cnn_target = self.normal_arousal_target.currentData()
        corruption_cnn_target = self.normal_corruption_target.currentData()
        broad_family = self.normal_clothing_broad.currentData() if category == "clothing" else None
        cover_area = self.normal_clothing_cover_area.currentData() if category == "clothing" else None
        subtags = [str(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)) for item in self.normal_subtags.selectedItems()]
        corruption_states = [str(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
                             for item in self.normal_corruption_states.selectedItems()]
        subtags.extend(value for value in corruption_states if value not in subtags)
        location = self._selected_normal_location()
        if (not tag or (category == "fullbody" and not state)
                or (category == "clothing" and (not broad_family or not cover_area))):
            QMessageBox.information(
                self, "Complete crop tags",
                "Choose a main tag, the applicable Fullbody state, and a Clothing cover area when needed."
            )
            return
        try:
            self.database.save_normal_crop_choice(
                int(row["id"]), category, tag if category == "body_images" else None,
                main_tag=tag, fullbody_state=state, subtags=subtags, location=location,
                clothing_broad_family=broad_family, clothing_cover_area=cover_area,
                body_images_cnn_target=None,
                body_images_cum_target=body_images_cum_target,
                body_images_cum_evaluated=body_images_cum_evaluated,
                body_images_accessory_target=body_images_accessory_target,
                body_images_accessory_evaluated=body_images_accessory_evaluated,
                body_images_completed=body_images_completed,
                fullbody_cnn_target=fullbody_cnn_target,
                arousal_cnn_target=arousal_cnn_target,
                corruption_cnn_target=corruption_cnn_target)
            example_ids = self.database.confirm_normal_crop_classification(int(row["id"]))
            self._normal_drafts.pop(int(row["id"]), None)
            self.database.discard_normal_processing_draft(int(row["id"]))
            row.update({"category": category, "chosen_category": category,
                        "body_image_main_tag": tag if category == "body_images" else None,
                        "normal_main_tag": tag, "normal_fullbody_state": state,
                        "normal_fullbody_cnn_target": fullbody_cnn_target,
                        "normal_body_images_cum_target": body_images_cum_target,
                        "normal_body_images_cum_evaluated": body_images_cum_evaluated,
                        "normal_body_images_accessory_target": body_images_accessory_target,
                        "normal_body_images_accessory_evaluated": body_images_accessory_evaluated,
                        "normal_body_images_completed": body_images_completed,
                        "normal_arousal_cnn_target": arousal_cnn_target,
                        "normal_corruption_cnn_target": corruption_cnn_target,
                        "normal_subtags": subtags, "normal_location_value": location,
                        "normal_clothing_broad_family": broad_family,
                        "normal_clothing_cover_area": cover_area,
                        "normal_confirmed": True})
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, row)
            item.setText(f"{category.replace('_', ' ').title()}\nConfirmed · select to export")
            self.status_label.showMessage(
                f"Classification confirmed · {len(example_ids)} task-specific training example(s) recorded"
            )
            self._refresh_normal_gallery()
            self._move_normal_selection(1)
        except Exception as error:
            QMessageBox.warning(self, "Classification not confirmed", str(error))

    def _move_normal_selection(self, direction: int):
        count = self.normal_gallery.count()
        if not count:
            return
        row = max(0, min(count - 1, self.normal_gallery.currentRow() + int(direction)))
        self.normal_gallery.setCurrentRow(row)
        PySide6.QtCore.QTimer.singleShot(0, self._update_normal_position)

    def _export_selected_normal_crops(self):
        if self.normal_export_worker and self.normal_export_worker.isRunning():
            QMessageBox.information(self, "Export in progress", "Wait for the current crop export to finish.")
            return
        proposal_ids = [
            int(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)["id"])
            for index in range(self.normal_gallery.count())
            for item in [self.normal_gallery.item(index)]
            if item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) and item.isSelected()
        ]
        if not proposal_ids:
            return
        output_dir = QFileDialog.getExistingDirectory(self, "Choose crop output parent folder",
                                                       str(self.config.output_dir))
        if not output_dir:
            return
        try:
            plan = build_normal_output_plan(self.database, output_dir, proposal_ids)
        except Exception as error:
            QMessageBox.critical(self, "Crop export preview failed", str(error))
            return
        for item in plan["items"]:
            item["remove_background"] = item.get("category") == "fullbody"
        filenames = "\n".join(Path(item["target"]).relative_to(plan["output_dir"]).as_posix()
                               for item in plan["items"][:10])
        skipped = "\n".join(f"{row['proposal_id']}: {row['reason']}" for row in plan["skipped"][:8])
        summary = f"Export {plan['item_count']} selected crop(s) as WebP to:\n{plan['output_dir']}\n\n{filenames}"
        if any(item.get("category") in {"fullbody", "body_images"} and
               (item.get("category") == "fullbody" or item.get("main_tag") in {"portrait", "tportrait"})
               for item in plan["items"]):
            summary += (
                "\n\nFullbody, Portrait, and T-Portrait outputs require transparent backgrounds. "
                "Opaque crops use background removal; if removal fails, that crop is skipped and reported."
            )
        if plan["skipped_count"]:
            summary += f"\n\nSkipped during preview ({plan['skipped_count']}):\n{skipped}"
        if not plan["items"]:
            QMessageBox.information(self, "No exportable crops", summary)
            return
        answer = QMessageBox.question(self, "Confirm crop export", summary,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.Yes)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.normal_export_button.setEnabled(False)
        self.normal_cancel_button.setEnabled(True)
        self.progress.setRange(0, max(1, plan["item_count"]))
        self.progress.setValue(0)
        self.progress.setFormat("Exporting selected WebP crops…")
        self.normal_export_worker = OutputExportWorker(self.config.database_path, plan)
        self.normal_export_worker.progress.connect(self._normal_export_progress)
        self.normal_export_worker.completed.connect(self._normal_export_completed)
        self.normal_export_worker.failed.connect(self._normal_export_failed)
        self.normal_export_worker.finished.connect(self._normal_export_thread_finished)
        self.normal_export_worker.start()

    def _cancel_normal_export(self):
        if self.normal_export_worker and self.normal_export_worker.isRunning():
            self.normal_export_worker.cancel()
            self.normal_cancel_button.setEnabled(False)
            self.progress.setFormat("Cancellation requested · finishing current crop")

    def _normal_export_progress(self, current, total, message):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(current)
        self.progress.setFormat(f"{current}/{total} · {message}")

    def _normal_export_completed(self, result):
        self.normal_export_button.setEnabled(self._selected_normal_crop_count() > 0)
        self.normal_cancel_button.setEnabled(False)
        finished = result["written_count"] + result["failure_count"]
        self.progress.setRange(0, max(1, result["item_count"]))
        self.progress.setValue(min(result["item_count"], finished))
        self.progress.setFormat("Cancelled · completed crops kept" if result["cancelled"] else "Export complete")
        self._refresh_normal_gallery()
        failure_text = "\n".join(
            f"#{row['proposal_id']}: {row['reason']}" for row in result["failures"][:5]
        )
        QMessageBox.information(
            self, "Crop export summary",
            f"Exported: {result['written_count']}\n"
            f"Failed: {result['failure_count']}\nSkipped: {result['skipped_count']}\n"
            f"Cancelled: {len(result['cancelled_ids'])} remaining crop(s)\n\n"
            f"{failure_text}\n\nFullbody crops are not exported unless they have transparent backgrounds.",
        )

    def _normal_export_failed(self, message):
        self.normal_cancel_button.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setFormat("Export failed")
        self._refresh_normal_gallery()
        QMessageBox.critical(self, "Crop export failed", message)

    def _normal_export_thread_finished(self):
        self.normal_cancel_button.setEnabled(False)
        self.normal_export_button.setEnabled(self._selected_normal_crop_count() > 0)

    def _prepare_training_dataset(self):
        if self._background_work_active():
            QMessageBox.information(self, "Work in progress", "Wait for the current image or export operation to finish.")
            return
        choices = ["YOLO annotations", "Body Images evidence CNN", "Fullbody CNN",
                   "Portrait CNN", "Arousal CNN", "Corruption CNN",
                   "12-class broad Clothing CNN", "Future detailed Clothing CNN"]
        choice, accepted = QInputDialog.getItem(self, "Prepare Training Dataset",
                                                "Export type (reviewed records only)", choices, 0, False)
        if not accepted:
            return
        task = {choices[0]: "yolo", choices[1]: "body_images", choices[2]: "fullbody",
                choices[3]: "portrait", choices[4]: "arousal", choices[5]: "corruption",
                choices[6]: "broad_clothing", choices[7]: "clothing_cnn"}[choice]
        sources = ["All reviewed records", "NewAssetApp samples folder", "Choose another image folder"]
        source_choice, accepted = QInputDialog.getItem(self, "Dataset sources",
                                                       "Include records from", sources, 0, False)
        if not accepted:
            return
        if source_choice == sources[1]:
            source_roots = [str(Path(__file__).resolve().parents[2] / "samples")]
        elif source_choice == sources[2]:
            folder = QFileDialog.getExistingDirectory(self, "Select reviewed source image folder")
            if not folder:
                return
            source_roots = [folder]
        else:
            source_roots = None
        output_dir = QFileDialog.getExistingDirectory(self, "Choose dataset export parent folder",
                                                       str(self.config.output_dir))
        if not output_dir:
            return
        split_text, accepted = QInputDialog.getText(
            self, "Dataset split proportions", "Train, validation, test percentages", text="80,10,10")
        if not accepted:
            return
        try:
            percent = tuple(float(value.strip()) for value in split_text.split(","))
            if len(percent) != 3 or any(value <= 0 for value in percent) or abs(sum(percent) - 100) > 1e-6:
                raise ValueError("Enter three positive percentages that sum to 100.")
            proportions = tuple(value / 100 for value in percent)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid split proportions", str(error))
            return
        seed, accepted = QInputDialog.getInt(self, "Dataset split seed", "Reproducible split seed", 42, 0, 2**31 - 1)
        if not accepted:
            return
        split_answer = QMessageBox.question(
            self, "Dataset split assignments",
            "Reuse saved source-image split assignments? Choose No only to start a new split.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        new_split = split_answer == QMessageBox.StandardButton.No
        if ((self.worker and self.worker.isRunning()) or (self.export_worker and self.export_worker.isRunning())
                or (self.analysis_worker and self.analysis_worker.isRunning())):
            QMessageBox.information(self, "Work in progress", "Wait for the current scan or export to finish.")
            return
        self.dataset_export_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Preparing reviewed dataset package…")
        self.status_label.showMessage("Exporting only explicitly human-confirmed training records")
        self.export_worker = DatasetExportWorker(self.config.database_path, output_dir, task,
                                                 source_roots, new_split=new_split, seed=seed,
                                                 proportions=proportions)
        self.export_worker.completed.connect(self._dataset_export_completed)
        self.export_worker.failed.connect(self._dataset_export_failed)
        self.export_worker.start()

    def _export_studio_source(self):
        if self._background_work_active():
            QMessageBox.information(self, "Work in progress",
                                    "Wait for the current image or export operation to finish.")
            return
        if ((self.worker and self.worker.isRunning()) or (self.export_worker and self.export_worker.isRunning())
                or (self.analysis_worker and self.analysis_worker.isRunning())
                or (self.normal_export_worker and self.normal_export_worker.isRunning())):
            QMessageBox.information(self, "Work in progress", "Wait for the current scan or export to finish.")
            return
        output_dir = Path(__file__).resolve().parents[2] / "training_source" / "bundles"
        self.studio_source_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Building immutable Studio source bundle…")
        self.status_label.showMessage("Copying verified source images and current eligible labels")
        self.studio_source_worker = DatasetExportWorker(
            self.config.database_path, output_dir, "studio_bundle"
        )
        self.studio_source_worker.completed.connect(self._studio_source_completed)
        self.studio_source_worker.failed.connect(self._studio_source_failed)
        self.studio_source_worker.start()

    def _studio_source_completed(self, result):
        self.studio_source_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Studio source bundle ready")
        self.status_label.showMessage(f"Studio source · {result['record_count']} record(s)")
        QMessageBox.information(
            self, "Studio source bundle ready",
            f"Bundle: {result['bundle_id']}\n"
            f"Reviewed records: {result['record_count']}\n"
            f"Excluded records: {result['excluded_count']}\n"
            f"Unique source images: {result['media_file_count']}\n\n"
            f"Manifest:\n{result['manifest']}"
        )

    def _studio_source_failed(self, message):
        self.studio_source_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Studio source export failed")
        self.status_label.showMessage("Studio source export failed")
        QMessageBox.critical(self, "Studio source export failed", message)

    def _export_output(self):
        if self._background_work_active():
            QMessageBox.information(self, "Work in progress", "Wait for the current scan or analysis to finish.")
            return
        output_dir = QFileDialog.getExistingDirectory(self, "Choose normal application output folder",
                                                       str(self.config.output_dir))
        if not output_dir:
            return
        try:
            plan = build_output_plan(self.database, output_dir)
        except Exception as error:
            QMessageBox.critical(self, "Output preview failed", str(error))
            return
        names = "\n".join(Path(item["target"]).relative_to(plan["output_dir"]).as_posix()
                           for item in plan["items"][:12])
        if len(plan["items"]) > 12:
            names += f"\n… and {len(plan['items']) - 12} more"
        skipped = "\n".join(f"#{row['proposal_id']}: {row['reason']}" for row in plan["skipped"][:6])
        summary = (f"Ready to export {plan['item_count']} confirmed asset(s) to:\n{plan['output_dir']}\n\n"
                   f"Preview:\n{names or '(no eligible outputs)'}")
        if plan["skipped_count"]:
            summary += f"\n\nSkipped {plan['skipped_count']} item(s):\n{skipped}"
        if not plan["item_count"]:
            QMessageBox.information(self, "Nothing ready to export", summary)
            return
        answer = QMessageBox.question(self, "Confirm Export Output", summary,
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.output_export_button.setEnabled(False)
        try:
            result = export_reviewed_output(self.database, output_dir, plan)
            self.status_label.showMessage(f"Output export complete · {result['written_count']} file(s)")
            QMessageBox.information(self, "Output export complete",
                                    f"Wrote {result['written_count']} normal output file(s) to:\n{output_dir}")
        except Exception as error:
            QMessageBox.critical(self, "Output export failed", str(error))
        finally:
            self.output_export_button.setEnabled(True)

    def _start_analysis(self):
        if self._background_work_active():
            QMessageBox.information(self, "Work in progress", "Wait for the current scan or export to finish.")
            return
        folder_text = self.folder_edit.text().strip()
        if folder_text and not Path(folder_text).is_dir():
            QMessageBox.information(self, "Choose an image folder",
                                    "Enter an existing source folder or clear the field to analyze all indexed images.")
            return
        folder = folder_text or None
        self.analyze_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Loading YOLO and Clothing CNN checkpoints…")
        self.status_label.showMessage("Analyzing indexed new/changed images; all results require human review")
        self.analysis_worker = AnalysisWorker(self.config.database_path, folder,
                                              self.config.clothing_classifier_checkpoint,
                                              self.config.clothing_classifier_class_map)
        self.analysis_worker.progress.connect(self._analysis_progress)
        self.analysis_worker.completed.connect(self._analysis_completed)
        self.analysis_worker.failed.connect(self._analysis_failed)
        self.analysis_worker.start()

    def _analysis_progress(self, current, total, path):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        self.progress.setFormat(f"Analyzing {current} of {total}")
        self.status_label.showMessage(Path(path).name)

    def _analysis_completed(self, result):
        self.analyze_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat(f"Analyzed {result['processed']} / {result['total']} · {len(result['errors'])} error(s)")
        shared_suggestions = [suggestion for row in result.get("results", [])
                              for suggestion in row.get("shared_cnn_suggestions", [])]
        self.status_label.showMessage(
            f"Analysis complete · {len(shared_suggestions)} shared CNN suggestions; all remain unconfirmed review candidates"
            if shared_suggestions else
            "Analysis complete · detections and CNN outputs remain review candidates")
        self._refresh_navigation()
        self._refresh_normal_gallery()
        self._refresh_gallery()
        if result["errors"]:
            QMessageBox.warning(self, "Analysis finished with errors",
                                "Some indexed images need attention. First error:\n" + result["errors"][0]["error"])
        if shared_suggestions:
            summary = "\n".join(
                f"Detection {item['detection_id']} · {item['task_head']}: {item['class_label']} "
                f"({item['confidence']:.3f}) — review required"
                for item in shared_suggestions[:50])
            detail = "\n".join(json.dumps(item, ensure_ascii=False) for item in shared_suggestions)
            dialog = QMessageBox(self); dialog.setWindowTitle("Shared CNN suggestions")
            dialog.setText(f"{len(shared_suggestions)} model suggestions were produced. None are human-confirmed.")
            dialog.setDetailedText(summary + ("\n…more entries are in the details payload." if len(shared_suggestions) > 50 else "")
                                   + "\n\nFull prediction evidence:\n" + detail)
            dialog.exec()

    def _analysis_failed(self, message):
        self.analyze_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Analysis failed")
        self.status_label.showMessage("Analysis failed")
        QMessageBox.critical(self, "Analysis failed", message)

    def _dataset_export_completed(self, result):
        self.dataset_export_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("Dataset package prepared")
        self.status_label.showMessage(f"Dataset export {result['version']} complete")
        QMessageBox.information(self, "Training dataset prepared",
                                f"Package:\n{result['zip']}\n\n"
                                f"Review the manifest before uploading to Colab.")

    def _dataset_export_failed(self, message):
        self.dataset_export_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Dataset export failed")
        self.status_label.showMessage("Dataset export failed")
        QMessageBox.critical(self, "Dataset export failed", message)

    def _start_scan(self):
        folder_text = self.folder_edit.text().strip()
        if not folder_text or not Path(folder_text).is_dir():
            QMessageBox.information(self, "Choose an image folder",
                                    "Select an existing folder before scanning.")
            return
        if self._background_work_active():
            return
        self.scan_button.setEnabled(False)
        self.browse_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.setFormat("Preparing image scan…")
        self.status_label.showMessage("Scanning images; originals are read only")
        self.worker = ScanWorker(
            self.config.database_path, folder_text,
            recursive=self.config.recursive_scan,
            extensions=self.config.supported_extensions,
            force_full=self.full_rescan_check.isChecked(),
        )
        self.worker.progress.connect(self._scan_progress)
        self.worker.completed.connect(self._scan_completed)
        self.worker.failed.connect(self._scan_failed)
        self.worker.start()

    def _background_work_active(self):
        return any(worker and worker.isRunning() for worker in
                   (self.worker, self.export_worker, self.studio_source_worker,
                    self.analysis_worker, self.normal_export_worker))

    def _scan_progress(self, current, total, path):
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(current)
        self.progress.setFormat(f"Scanning {current} of {total}")
        self.status_label.showMessage(Path(path).name)

    def _scan_completed(self, result):
        self.scan_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat(
            f"Scanned {result['total']} image(s) · "
            f"{result.get('new_or_changed', result['indexed'])} new/changed · "
            f"{result.get('unchanged', 0)} unchanged · "
            f"{result['duplicates']} duplicate(s) · {len(result['errors'])} error(s)"
        )
        self.status_label.showMessage("Scan complete · model inference is not connected")
        self._refresh_navigation()
        self.current_category = "sources"
        self._select_nav_key("sources")
        self._refresh_gallery()

    def _scan_failed(self, message):
        self.scan_button.setEnabled(True)
        self.browse_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Scan failed")
        self.status_label.showMessage("Scan failed")
        logger.error("Image scan failed: %s", message)
        QMessageBox.critical(self, "Image scan failed", message)

    def _select_nav_key(self, key):
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            if item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) == key:
                self.nav.setCurrentItem(item)
                return

    def _refresh_navigation(self):
        counts = self.database.category_counts()
        labels = {
            "sources": ("All", self.database.count_sources()),
            "fullbody": ("Fullbody", counts.get("fullbody", 0)),
            "fullbody_topless": ("Topless", counts.get("fullbody_topless", 0)),
            "fullbody_bottomless": ("Bottomless", counts.get("fullbody_bottomless", 0)),
            "body_images": ("Body", counts.get("body_images", 0)),
            "clothing": ("Clothing", counts.get("clothing", 0)),
            "others": ("Other", counts.get("others", 0)),
            "photoshoots": ("Photoshoots", sum(group["member_count"] for group in self.database.photoshoot_groups())),
        }
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            label, count = labels[item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)]
            item.setText(f"{label}  ·  {count}")
            item.setToolTip(f"{label} proposals: {count}")
        self._refresh_normal_gallery()

    def _category_changed(self, current, previous):
        if current:
            self.current_category = current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
            self._refresh_gallery()

    def _refresh_gallery(self):
        self.gallery.clear()
        self.preview.set_image("")
        self.details.setText("")
        self.photoshoot_controls.setVisible(self.current_category == "photoshoots")
        self.assignment_controls.setVisible(self.current_category in {"fullbody", "fullbody_topless", "fullbody_bottomless", "body_images", "clothing", "others"})
        self.manual_proposal_button.setVisible(self.current_category == "sources")
        self._refresh_group_controls()
        if self.current_category == "sources":
            rows = self.database.source_images(self.folder_edit.text() or None)
            self.gallery_title.setText("Source images")
            for row in rows:
                item = QListWidgetItem()
                item.setText(f"{Path(row['path']).name}\n{row['width']} × {row['height']}")
                item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, dict(row))
                reader = QImageReader(row["path"])
                reader.setAutoTransform(True)
                source_size = reader.size()
                if source_size.isValid():
                    reader.setScaledSize(source_size.scaled(
                        PySide6.QtCore.QSize(148, 112), PySide6.QtCore.Qt.AspectRatioMode.KeepAspectRatio
                    ))
                pixmap = QPixmap.fromImage(reader.read())
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap.scaled(
                        PySide6.QtCore.QSize(148, 112), PySide6.QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        PySide6.QtCore.Qt.TransformationMode.SmoothTransformation,
                    )))
                else:
                    item.setText(f"{Path(row['path']).name}\nPreview unavailable")
                self.gallery.addItem(item)
            count = len(rows)
        elif self.current_category == "photoshoots":
            group_id = self.group_combo.currentData()
            self.gallery_title.setText(f"Photoshoot · {self.group_combo.currentText()}" if group_id is not None else "Photoshoots")
            rows = self.database.photoshoot_members(group_id) if group_id is not None else []
            self._add_proposal_rows(rows)
            count = len(rows)
        else:
            display_name = dict((key, label) for label, key in NAV_ITEMS)[self.current_category]
            self.gallery_title.setText(f"{display_name} proposals")
            rows = self.database.proposals_for_category(self.current_category)
            keep_source_id = getattr(self, "_professional_keep_source_id", None)
            if keep_source_id is not None:
                existing_ids = {int(row["id"]) for row in rows}
                rows.extend(row for row in self.database.proposals_for_source(keep_source_id)
                            if int(row["id"]) not in existing_ids)
            self._add_proposal_rows(rows)
            count = len(rows)
        self.gallery_count.setText(f"{count} item(s)")
        if self.gallery.count() == 0:
            item = QListWidgetItem()
            if self.current_category == "photoshoots":
                item.setText("No images in this group\nSelect proposals and assign them manually")
            elif self.current_category == "sources":
                item.setText("No images indexed\nChoose a folder and scan")
            else:
                item.setText("No proposals yet\nAI processing is not connected in Phase 1")
            item.setFlags(PySide6.QtCore.Qt.ItemFlag.NoItemFlags)
            self.gallery.addItem(item)
        keep_proposal_id = getattr(self, "_professional_keep_proposal_id", None)
        keep_source_id = getattr(self, "_professional_keep_source_id", None)
        if keep_proposal_id is not None or keep_source_id is not None:
            target_item = None
            for index in range(self.gallery.count()):
                item = self.gallery.item(index)
                row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
                if not isinstance(row, dict):
                    continue
                if keep_proposal_id is not None and int(row.get("id", -1)) == int(keep_proposal_id):
                    target_item = item
                    break
                if keep_source_id is not None and int(row.get("source_image_id", -1)) == int(keep_source_id):
                    target_item = target_item or item
            if target_item is not None:
                self.gallery.setCurrentItem(target_item)
            self._professional_keep_proposal_id = None

    def _add_proposal_rows(self, rows):
        for row in rows:
            item = QListWidgetItem()
            item.setText(f"{Path(row['path']).name}\n{row['width']} × {row['height']}")
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, dict(row))
            reader = QImageReader(row["path"])
            reader.setAutoTransform(True)
            size = reader.size()
            if size.isValid():
                reader.setScaledSize(size.scaled(PySide6.QtCore.QSize(148, 112), PySide6.QtCore.Qt.AspectRatioMode.KeepAspectRatio))
            pixmap = QPixmap.fromImage(reader.read())
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap.scaled(PySide6.QtCore.QSize(148, 112), PySide6.QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                                  PySide6.QtCore.Qt.TransformationMode.SmoothTransformation)))
            self.gallery.addItem(item)

    def _refresh_group_controls(self):
        if not hasattr(self, "group_combo"):
            return
        groups = self.database.photoshoot_groups()
        current_id = self.group_combo.currentData()
        for combo in (self.group_combo, self.assign_group_combo):
            combo.blockSignals(True)
            combo.clear()
            for group in groups:
                combo.addItem(group["name"], group["id"])
            if current_id is not None:
                index = combo.findData(current_id)
                if index >= 0:
                    combo.setCurrentIndex(index)
            combo.blockSignals(False)
        has_group = bool(groups)
        for button in (self.rename_group_button, self.delete_group_button, self.remove_members_button):
            button.setEnabled(has_group)
        self.assign_group_button.setEnabled(has_group)

    def _photoshoot_group_changed(self, _index):
        if getattr(self, "current_category", None) == "photoshoots":
            self._refresh_gallery()

    def _create_photoshoot_group(self):
        name, accepted = QInputDialog.getText(self, "Create photoshoot group", "Group name")
        if accepted:
            try:
                group_id = self.database.create_photoshoot_group(name)
                self._refresh_group_controls()
                self.group_combo.setCurrentIndex(self.group_combo.findData(group_id))
                self._refresh_navigation()
                self._refresh_gallery()
            except Exception as error:
                QMessageBox.warning(self, "Could not create group", str(error))

    def _rename_photoshoot_group(self):
        group_id = self.group_combo.currentData()
        if group_id is None:
            return
        name, accepted = QInputDialog.getText(self, "Rename photoshoot group", "Group name",
                                              text=self.group_combo.currentText())
        if accepted:
            try:
                self.database.rename_photoshoot_group(group_id, name)
                self._refresh_group_controls()
                self.group_combo.setCurrentIndex(self.group_combo.findData(group_id))
                self._refresh_gallery()
            except Exception as error:
                QMessageBox.warning(self, "Could not rename group", str(error))

    def _delete_photoshoot_group(self):
        group_id = self.group_combo.currentData()
        if group_id is None:
            return
        answer = QMessageBox.question(
            self, "Delete photoshoot group",
            "Delete this group and its memberships? Proposal categories stay unchanged.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.database.delete_photoshoot_group(group_id)
            self._refresh_group_controls()
            self._refresh_navigation()
            self._refresh_gallery()

    def _selected_proposal_ids(self):
        return [item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)["id"] for item in self.gallery.selectedItems()
                if item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) and "id" in item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)]

    def _assign_selected_to_photoshoot(self):
        group_id = self.assign_group_combo.currentData()
        ids = self._selected_proposal_ids()
        if group_id is None or not ids:
            return
        try:
            changed = self.database.add_proposals_to_photoshoot(group_id, ids)
            self.status_label.showMessage(f"Manually assigned {changed} proposal(s) to {self.assign_group_combo.currentText()}")
            self._refresh_navigation()
        except Exception as error:
            QMessageBox.warning(self, "Could not assign proposals", str(error))

    def _remove_photoshoot_members(self):
        group_id = self.group_combo.currentData()
        ids = self._selected_proposal_ids()
        if group_id is not None and ids:
            self.database.remove_proposals_from_photoshoot(group_id, ids)
            self._refresh_navigation()
            self._refresh_gallery()

    def _selection_state_changed(self):
        if hasattr(self, "assign_group_button"):
            self.assign_group_button.setEnabled(bool(self.assign_group_combo.count() and self._selected_proposal_ids()))
        if hasattr(self, "manual_proposal_button"):
            self.manual_proposal_button.setEnabled(
                self.current_category == "sources" and bool(self.gallery.currentItem())
                and bool(self.gallery.currentItem().data(PySide6.QtCore.Qt.ItemDataRole.UserRole)))

    def _create_manual_proposal(self):
        item = self.gallery.currentItem()
        row = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if item else None
        if self.current_category != "sources" or not row or "id" not in row:
            return
        registry_path = Path(__file__).resolve().parents[2] / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
        import json
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        classes = [(str(entry["name"]), int(entry["id"])) for entry in registry["classes"]]
        class_name, accepted = QInputDialog.getItem(
            self, "Manual Detection Class",
            "Choose the canonical YOLO class for the entire manually drawn region:",
            [name for name, _ in classes], 0, False,
        )
        if not accepted:
            return
        class_id = dict(classes).get(class_name)
        if class_id is None:
            QMessageBox.warning(self, "Invalid class", "Choose a class from the approved YOLO registry.")
            return
        try:
            width = int(row["width"])
            height = int(row["height"])
            default_bbox = [
                max(0.0, width * .05),
                max(0.0, height * .05),
                max(1.0, width * .95),
                max(1.0, height * .95),
            ]
            detection_id = self.database.create_manual_detection(
                row["id"], default_bbox, class_id=class_id,
                registry_id=registry["registry_id"])
            with self.database.connect() as connection:
                proposal = connection.execute(
                    "SELECT id FROM asset_proposals WHERE detection_id=?",
                    (int(detection_id),),
                ).fetchone()
            if not proposal:
                raise ValueError("Manual detection was created without a review proposal.")
            proposal_id = int(proposal["id"])
            source_id = int(row["id"])
            self.current_category = "sources"
            self._professional_keep_source_id = source_id
            self._select_nav_key("sources")
            self._refresh_navigation()
            self._refresh_gallery()
            for index in range(self.gallery.count()):
                candidate = self.gallery.item(index)
                data = candidate.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
                if data and int(data.get("id", -1)) == source_id:
                    self.gallery.setCurrentItem(candidate)
                    break
            for index in range(self.detection_list.count()):
                detection = self.detection_list.item(index)
                if int(detection.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)) == int(detection_id):
                    self.detection_list.setCurrentItem(detection)
                    return
            raise ValueError(f"Created proposal #{proposal_id} has no visible detection row.")
        except Exception as error:
            QMessageBox.warning(self, "Could not create manual proposal", str(error))

    def _selection_changed(self, current, previous):
        if not current or self.current_category not in {"sources", "fullbody", "fullbody_topless", "fullbody_bottomless", "body_images", "clothing", "others", "photoshoots"}:
            return
        row = current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)
        if not row:
            return
        source_id = row.get("source_image_id", row.get("id"))
        keep_source_id = getattr(self, "_professional_keep_source_id", None)
        if (self.current_category != "sources" and keep_source_id is not None
                and int(source_id) != int(keep_source_id)):
            self._professional_keep_source_id = None
            self._professional_keep_proposal_id = None
        self._active_source_id = int(source_id) if source_id is not None else None
        self._all_detection_boxes = self.database.detections_for_source(self._active_source_id) if self._active_source_id else []
        self.preview.set_image(row["path"], [])
        self._refresh_professional_detection_view()
        if self.current_category == "sources":
            description = (f"{row['file_size']:,} bytes<br>SHA-256: {row['content_sha256']}<br><br>"
                           "Indexed source image. Create or inspect YOLO detections here; classify eligible crops in Normal Processing.")
        else:
            description = (f"Proposal #{row['id']} · {row['review_status']}<br>"
                           f"YOLO: {row.get('yolo_class_name') or 'none'} ({row.get('yolo_confidence')})<br>"
                           "Use Normal Processing for crop tagging, classification confirmation, and export.")
        self.details.setText(f"<b>{Path(row['path']).name}</b><br>{row['width']} × {row['height']} px<br>{description}")

    def _preview_box_selected(self, detection_id):
        if not hasattr(self, "detection_list"):
            return
        for index in range(self.detection_list.count()):
            item = self.detection_list.item(index)
            if int(item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole)) == int(detection_id):
                self.detection_list.setCurrentItem(item)
                break

    def _visible_detection_boxes(self):
        boxes = getattr(self, "_all_detection_boxes", [])
        mode = self.detection_filter.currentData() if hasattr(self, "detection_filter") else "all"
        if mode == "invalid":
            boxes = [box for box in boxes if box.get("origin") == "rejected"]
        elif mode == "unreviewed":
            boxes = [box for box in boxes if box.get("status") in {None, "original", "pending", "review_required"}]
        elif mode == "reviewed":
            boxes = [box for box in boxes if box.get("status") in {"confirmed", "rejected"}]
        elif mode == "model_verified":
            boxes = [box for box in boxes
                     if model_verified(box.get("confidence"))]
        elif mode == "corrected":
            boxes = [box for box in boxes
                     if str(box.get("class_name") or "") != str(box.get("original_class_name") or "")
                     or box.get("origin") in {"rejected", "manual"}]
        if mode not in {"invalid", "reviewed"}:
            boxes = [box for box in boxes if box.get("origin") != "rejected"]
        return list(boxes)

    def _refresh_professional_detection_view(self, *_):
        if not hasattr(self, "detection_list"):
            return
        selected = self.detection_list.currentItem()
        selected_id = selected.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if selected else None
        boxes = self._visible_detection_boxes()
        self.preview.set_boxes(boxes)
        self._apply_box_visibility_mode()
        self.detection_list.blockSignals(True)
        self.detection_list.clear()
        class_counts: dict[str, int] = {}
        for box in boxes:
            effective = str(box.get("class_name") or "Unassigned")
            class_counts[effective] = class_counts.get(effective, 0) + 1
        for box in boxes:
            confidence = box.get("confidence")
            score = f" · YOLO {float(confidence):.0%}" if confidence is not None else ""
            status = str(box.get("status") or "unreviewed").replace("_", " ").title()
            effective = str(box.get("class_name") or "Unassigned")
            count = class_counts.get(effective, 1)
            item = QListWidgetItem(
                f"{effective.replace('_', ' ').title()} ×{count} · "
                f"Detection #{int(box['id'])}{score} · {status}"
            )
            ident = int(box["id"])
            digest = __import__("hashlib").sha256(str(ident).encode("ascii")).digest()
            hue = int.from_bytes(digest[:4], "big") % 360
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor.fromHsv(hue, 205 + digest[4] % 46, 225 + digest[5] % 31))
            item.setIcon(QIcon(pixmap))
            item.setToolTip(
                f"Stable detection ID: {int(box['id'])}\n"
                f"Original YOLO class: {box.get('original_class_name') or 'manual'}\n"
                f"Current reviewed class: {box.get('class_name') or 'manual'}\n"
                f"BBox: {box.get('bbox_xyxy')}\nStatus: {status}"
            )
            item.setData(PySide6.QtCore.Qt.ItemDataRole.UserRole, int(box["id"]))
            self.detection_list.addItem(item)
            if selected_id == int(box["id"]):
                self.detection_list.setCurrentItem(item)
        if self.detection_list.currentRow() < 0 and self.detection_list.count():
            self.detection_list.setCurrentRow(0)
        self.detection_list.blockSignals(False)
        current = self.detection_list.currentItem()
        if current:
            detection_id = int(current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
            self.preview.select_box(detection_id)
            row = next((box for box in boxes if int(box["id"]) == detection_id), None)
            self._refresh_professional_inspector(row)

    def _apply_box_visibility_mode(self, *_):
        mode = self.box_visibility_mode.currentData()
        self.preview.set_boxes_visible(mode != "hidden")
        self.preview.set_selected_only(mode == "selected")
        current = self.detection_list.currentItem()
        self.preview.select_box(current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) if current else None)
        selected_box = self.preview.selected_box()
        if selected_box:
            self.reject_box_button.setText("Restore detection" if selected_box.get("origin") == "rejected"
                                           else "Mark invalid")

    def _refresh_professional_inspector(self, box: dict | None):
        if not hasattr(self, "inspector_original"):
            return
        if not box:
            self.inspector_original.setText("Select a detection")
            self.inspector_corrected.setText("Corrected class: none")
            self.inspector_bbox.setText("BBox: none")
            self.inspector_validity.setText("Validity: unreviewed")
            self.inspector_history.setText("Correction history: no events")
            self.inspector_class_combo.clear()
            self.inspector_class_button.setEnabled(False)
            return

        original_class = box.get("original_class_name") or box.get("class_name") or "unassigned"
        corrected_class = box.get("class_name") or original_class
        bbox = box.get("bbox_xyxy")
        bbox_text = ", ".join(f"{float(value):.1f}" for value in bbox) if bbox else "none"
        status = str(box.get("status") or "unreviewed").replace("_", " ").title()
        history = box.get("correction_history") or box.get("review_history") or []
        self.inspector_original.setText(
            f"<b>Detection #{int(box['id'])}</b><br>"
            f"Original YOLO class: {original_class}<br>"
            f"Original confidence: {float(box['confidence']):.1%}" if box.get("confidence") is not None
            else f"<b>Detection #{int(box['id'])}</b><br>Original YOLO class: {original_class}"
        )
        self.inspector_corrected.setText(
            f"Corrected YOLO class: {corrected_class}" if corrected_class != original_class
            else "Corrected YOLO class: unchanged"
        )
        self.inspector_bbox.setText(
            f"Original bbox: {box.get('original_bbox_xyxy') or 'immutable'}<br>"
            f"Corrected bbox: {bbox_text}"
        )
        try:
            with self.database.connect() as connection:
                bbox_review = connection.execute(
                    """SELECT review_status,human_confirmed,confirmed_at
                       FROM yolo_bbox_reviews WHERE detection_id=? ORDER BY id DESC LIMIT 1""",
                    (int(box["id"]),),
                ).fetchone()
            bbox_review_text = ("BBox: human-approved unchanged" if bbox_review and
                                bbox_review["human_confirmed"] else "BBox: awaiting explicit human approval")
            self.inspector_bbox.setText(
                f"Original bbox: {box.get('original_bbox_xyxy') or 'immutable'}<br>"
                f"Corrected bbox: {bbox_text}<br>{bbox_review_text}"
            )
        except Exception:
            pass
        self.inspector_validity.setText(f"Validity: {status}")
        self.inspector_history.setText(
            f"Correction history: {len(history)} saved event(s)"
        )
        self._populate_inspector_class_controls(box)

    def _populate_inspector_class_controls(self, box: dict):
        registry_path = Path(__file__).resolve().parents[2] / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            classes = [(int(row["id"]), str(row["name"])) for row in registry["classes"]
                       if str(row["name"]) != "action_event"]
        except Exception as error:
            logger.exception("Could not load the active YOLO correction registry")
            classes = []
        self.inspector_class_combo.blockSignals(True)
        self.inspector_class_combo.clear()
        self.inspector_class_combo.addItem("Choose approved target class", None)
        for class_id, class_name in classes:
            self.inspector_class_combo.addItem(class_name.replace("_", " ").title(), class_id)
        current = str(box.get("class_name") or "")
        index = next((i for i in range(self.inspector_class_combo.count())
                      if str(self.inspector_class_combo.itemText(i)).replace(" ", "_").casefold()
                      == current.casefold()), -1)
        if index < 0:
            self.inspector_class_combo.setCurrentIndex(0)
            self.inspector_class_combo.setToolTip(
                "No approved 31-class registry value matches this legacy YOLO detection. "
                "Do not infer or silently remap the class."
            )
        else:
            self.inspector_class_combo.setCurrentIndex(index)
            self.inspector_class_combo.setToolTip("")
        self.inspector_class_combo.blockSignals(False)
        self.inspector_class_button.setEnabled(
            box.get("proposal_id") is not None
            and self.inspector_class_combo.currentData() is not None
        )

    def _save_inspector_class_correction(self):
        class_id = self.inspector_class_combo.currentData()
        current = self.detection_list.currentItem()
        if current is None or class_id is None:
            QMessageBox.warning(self, "Choose a detection class", "Select a detection and an approved target class.")
            return
        detection_id = int(current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
        box = next((row for row in getattr(self, "_all_detection_boxes", [])
                    if int(row["id"]) == detection_id), None)
        proposal_id = box.get("proposal_id") if box else None
        if proposal_id is None:
            QMessageBox.warning(self, "Could not correct class", "This region is not linked to a persisted proposal.")
            return
        try:
            effective = self.database.effective_detection_state(int(proposal_id))
            requested_bbox = box.get("bbox_xyxy") or effective["bbox_xyxy"]
            unchanged_bbox = (
                len(requested_bbox) == 4 and len(effective["bbox_xyxy"]) == 4
                and all(abs(float(left) - float(right)) <= 1e-6
                        for left, right in zip(requested_bbox, effective["bbox_xyxy"]))
            )
            if int(class_id) == int(effective["class_id"]) and unchanged_bbox:
                review_id = self.database.approve_unchanged_bbox(detection_id)
                self.status_label.showMessage(
                    f"Annotation unchanged; bbox approval recorded · review #{review_id}")
                self._refresh_navigation()
                if self._active_source_id:
                    self._all_detection_boxes = self.database.detections_for_source(self._active_source_id)
                self._refresh_professional_detection_view()
                self._refresh_normal_gallery()
                if self.normal_gallery.currentItem():
                    self._normal_selection_changed(self.normal_gallery.currentItem(), None)
                return
            self.database.save_yolo_annotation_correction(
                int(proposal_id), int(class_id), "newassetapp_yolo_detector_v1",
                bbox_xyxy=requested_bbox)
            self.status_label.showMessage("YOLO annotation correction saved")
            self._refresh_navigation()
            if self._active_source_id:
                self._all_detection_boxes = self.database.detections_for_source(self._active_source_id)
            self._refresh_professional_detection_view()
            self._refresh_normal_gallery()
            if self.normal_gallery.currentItem():
                self._normal_selection_changed(self.normal_gallery.currentItem(), None)
        except Exception as error:
            logger.exception("Could not save Inspector class correction proposal_id=%s", proposal_id)
            QMessageBox.warning(self, "Could not save class correction",
                                f"Your selection is preserved.\n\n{error}")

    def _detection_list_selection_changed(self, current, _previous):
        if current:
            detection_id = int(current.data(PySide6.QtCore.Qt.ItemDataRole.UserRole))
            self.preview.select_box(detection_id)
            row = next((box for box in getattr(self, "_all_detection_boxes", [])
                        if int(box["id"]) == detection_id), None)
            if row is None and getattr(self, "_active_source_id", None):
                row = next((box for box in self.database.detections_for_source(
                    int(self._active_source_id))
                            if int(box["id"]) == detection_id), None)
                if row is not None:
                    self._all_detection_boxes = self.database.detections_for_source(
                        int(self._active_source_id))
            self._refresh_professional_inspector(row)
            proposal_id = row.get("proposal_id") if row else None
            if self.current_category != "sources" and proposal_id is not None:
                for index in range(self.gallery.count()):
                    item = self.gallery.item(index)
                    proposal = item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole) or {}
                    if int(proposal.get("id", -1)) == int(proposal_id):
                        self.gallery.setCurrentItem(item)
                        item.setSelected(True)
                        break

    def _bbox_changed(self, detection_id, bbox):
        try:
            self.database.save_bbox_edit(detection_id, bbox)
            if self._active_source_id:
                self._all_detection_boxes = self.database.detections_for_source(self._active_source_id)
                self._refresh_professional_detection_view()
                self.preview.select_box(detection_id)
                self._preview_box_selected(detection_id)
                self._refresh_normal_gallery()
                normal_item = self.normal_gallery.currentItem()
                if normal_item and normal_item.data(PySide6.QtCore.Qt.ItemDataRole.UserRole):
                    self._normal_selection_changed(normal_item, None)
            self.status_label.showMessage("Detection geometry saved in source-image coordinates")
        except Exception as error:
            QMessageBox.warning(self, "Could not save box", str(error))

    def _manual_box_created(self, bbox):
        if not self._active_source_id:
            return
        registry_path = Path(__file__).resolve().parents[2] / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        classes = [(str(entry["name"]), int(entry["id"])) for entry in registry["classes"]]
        class_name, accepted = QInputDialog.getItem(
            self, "Manual Detection Class",
            "Choose the canonical YOLO class for this manually drawn region:",
            [name for name, _ in classes], 0, False,
        )
        if not accepted:
            self.status_label.showMessage("Manual box discarded: a canonical YOLO class is required")
            return
        class_id = dict(classes).get(class_name)
        if class_id is None:
            QMessageBox.warning(self, "Invalid class", "Choose a class from the approved YOLO registry.")
            return
        try:
            detection_id = self.database.create_manual_detection(
                self._active_source_id, bbox, class_id=class_id,
                registry_id=registry["registry_id"])
            self._all_detection_boxes = self.database.detections_for_source(self._active_source_id)
            self._refresh_professional_detection_view()
            for box in self._all_detection_boxes:
                if int(box["id"]) == int(detection_id):
                    self.preview.select_box(int(detection_id))
                    self._refresh_professional_inspector(box)
                    break
            self.status_label.showMessage(
                f"Manual Detection #{detection_id} saved as {class_name}")
            self._refresh_navigation()
        except Exception as error:
            QMessageBox.warning(self, "Could not add box", str(error))

    def _approve_unchanged_bbox(self):
        box = self.preview.selected_box()
        if not box:
            QMessageBox.information(self, "Select a detection", "Select a bbox before approving it as unchanged.")
            return
        try:
            review_id = self.database.approve_unchanged_bbox(int(box["id"]))
            self._all_detection_boxes = self.database.detections_for_source(self._active_source_id)
            self._refresh_professional_detection_view()
            self._refresh_normal_gallery()
            if self.normal_gallery.currentItem():
                self._normal_selection_changed(self.normal_gallery.currentItem(), None)
            self.status_label.showMessage(f"BBox approved unchanged · review #{review_id}")
        except Exception as error:
            logger.exception("Could not approve unchanged bbox detection_id=%s", box.get("id"))
            QMessageBox.warning(self, "Could not approve unchanged bbox",
                                f"The bbox was not changed and unsaved state is preserved.\n\n{error}")

    def _reject_selected_detection(self):
        box = self.preview.selected_box()
        if not box:
            QMessageBox.information(self, "Select a detection", "Select a box in the preview first.")
            return
        try:
            if box.get("origin") == "rejected":
                self.database.restore_detection(box["id"])
                message = "Detection restored; its invalidation history was retained"
            else:
                reason, accepted = QInputDialog.getText(
                    self, "Mark detection invalid", "Optional reason (false positive, unusable box, irrelevant object):"
                )
                if not accepted:
                    return
                self.database.invalidate_detection(box["id"], reason)
                message = "Detection marked invalid; other detections on this image are unchanged"
            self._all_detection_boxes = self.database.detections_for_source(self._active_source_id)
            self._refresh_professional_detection_view()
            self.status_label.showMessage(message)
            self._refresh_navigation()
        except Exception as error:
            QMessageBox.warning(self, "Could not reject detection", str(error))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_schedule_visible_normal_thumbnails"):
            self._schedule_visible_normal_thumbnails()
        if hasattr(self, "professional_splitter"):
            width, height = event.size().width(), event.size().height()
            if width < 1000:
                usable = max(760, width - 24)
                self.nav_frame.setMinimumWidth(125)
                self.gallery_frame.setMinimumWidth(170)
                self.detail_frame.setMinimumWidth(300)
                self.professional_splitter.setSizes([130, 180, max(450, usable - 310)])
                self.normal_splitter.setSizes([230, max(400, usable - 230)])
                self.gallery_title.setText("Images")
                self.gallery.setIconSize(PySide6.QtCore.QSize(112, 86))
                self.gallery.setGridSize(PySide6.QtCore.QSize(145, 148))
                self.output_export_button.setText("Export")
                self.dataset_export_button.setText("Dataset")
                self.create_group_button.setText("New")
                self.rename_group_button.setText("Rename")
                self.delete_group_button.setText("Delete")
                self.remove_members_button.setText("Remove")
                self.assign_group_label.setText("Group")
                self.assign_group_button.setText("Assign")
                self.add_box_button.setText("Draw")
                self.reject_box_button.setText("Reject")
                self.approve_bbox_button.setText("Approve")
                self.normal_remove_background_check.setText("Remove background")
                self.normal_export_button.setText("Export crops")
            else:
                self.nav_frame.setMinimumWidth(140)
                self.gallery_frame.setMinimumWidth(220)
                self.detail_frame.setMinimumWidth(360)
                self.professional_splitter.setSizes([150, 270, 890])
                self.normal_splitter.setSizes([330, 930])
                self.gallery_title.setText("Source images")
                self.gallery.setIconSize(PySide6.QtCore.QSize(148, 112))
                self.gallery.setGridSize(PySide6.QtCore.QSize(180, 176))
                self.output_export_button.setText("Export assets")
                self.dataset_export_button.setText("Prepare dataset")
                self.create_group_button.setText("New group")
                self.rename_group_button.setText("Rename")
                self.delete_group_button.setText("Delete group")
                self.remove_members_button.setText("Remove selected")
                self.assign_group_label.setText("Manual photoshoot assignment")
                self.assign_group_button.setText("Assign selected to group")
                self.add_box_button.setText("Draw box")
                self.reject_box_button.setText("Reject box")
                self.normal_remove_background_check.setText(
                    "Background removal required: Fullbody, Portrait, T-Portrait"
                )
                self.normal_export_button.setText("Export selected crops")
            compact_height = height < 650
            self.normal_intro.setVisible(not compact_height)
            self.nav_note.setVisible(not compact_height and width >= 1000)
            self.review_hint.setVisible(height >= 650)
        current = self.gallery.currentItem()
        if current:
            self._selection_changed(current, None)

    def closeEvent(self, event):
        if hasattr(self, "_normal_draft_debounce"):
            self._normal_draft_debounce.stop()
        if hasattr(self, "normal_gallery"):
            self._flush_normal_draft_autosave()
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        if self.export_worker and self.export_worker.isRunning():
            self.export_worker.wait(30000)
        if self.analysis_worker and self.analysis_worker.isRunning():
            self.analysis_worker.requestInterruption()
            self.analysis_worker.wait(30000)
        if self.normal_export_worker and self.normal_export_worker.isRunning():
            self.normal_export_worker.cancel()
            self.status_label.showMessage("Cancelling export after the current crop; close the window again when finished")
            event.ignore()
            return
        event.accept()
