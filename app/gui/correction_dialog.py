from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget, QGroupBox,
)

from app.core.fullbody_classification import fullbody_filename
from app.core.filename_grammar import body_images_filename, clothing_filename
from app.core.clothing_taxonomy import clothing_classes, suggested_clothing_tags, validate_final_clothing_tag
from app.core.classification_taxonomy import (
    REGISTRY, legacy_fullbody_state_candidate, location_candidates,
)
from app.core.classification_eligibility import (
    arousal_eligible, is_fullbody_region, is_location_group, shared_head_eligible,
)


class CorrectionDialog(QDialog):
    """YOLO class and bounding-box correction form.

    CNN classification and filename decisions belong exclusively to Normal
    Processing. This dialog remains append-only and updates only the YOLO
    annotation authority.
    """

    def __init__(self, proposal: dict, tag_library, parent=None):
        super().__init__(parent)
        self.proposal = proposal
        self.tag_library = tag_library
        self.latest = json.loads(proposal["latest_correction_json"]) if proposal.get("latest_correction_json") else {}
        self.task_reviews = proposal.get("task_reviews") or {}
        self._task_action = None
        self._result_payload = None
        self.clothing_tag_input_method = self.latest.get("clothing_tag_input_method")
        self.decision_type = "corrected"
        self.setWindowTitle(f"YOLO/BBox correction · proposal #{proposal['id']}")
        available = self.screen().availableGeometry()
        minimum_width = min(560, max(460, available.width() - 40))
        minimum_height = min(500, max(420, available.height() - 40))
        self.setMinimumSize(minimum_width, minimum_height)
        self.resize(min(760, max(minimum_width, available.width() - 40)),
                    min(760, max(minimum_height, available.height() - 40)))
        layout = QVBoxLayout(self)
        original = QLabel(
            f"Original YOLO class: {proposal.get('yolo_class_name') or 'none'} "
            f"({proposal.get('yolo_confidence') if proposal.get('yolo_confidence') is not None else 'no score'})\n"
            f"Source hash: {proposal.get('content_sha256')}"
        )
        original.setWordWrap(True)
        original.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(original)
        history_lines = [
            f"{item.get('created_at')} · {item.get('event')} · {item.get('label')} · "
            f"{'confirmed' if item.get('human_confirmed') else item.get('status')}"
            + (f" · {item.get('actor')}" if item.get("actor") else "")
            for item in proposal.get("review_history", [])
        ]
        self.history_label = QLabel("Recent review history\n" + ("\n".join(history_lines) if history_lines else "No saved review events yet."))
        self.history_label.setWordWrap(True)
        self.history_label.setObjectName("SuggestionNote")
        layout.addWidget(self.history_label)
        form_widget = QWidget(self)
        form_widget.setMinimumWidth(0)
        form_widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        form_content = QVBoxLayout(form_widget)
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.form = form
        form_content.addLayout(form)
        self.category = QComboBox()
        for value in ("fullbody", "body_images", "clothing", "others"):
            self.category.addItem(value, value)
        reviewed_category = self.latest.get("category", proposal.get("category"))
        self.category.setCurrentIndex(max(0, self.category.findData(reviewed_category)))
        form.addRow("Reviewed category", self.category)

        self.main_tag = QComboBox()
        self.main_tag.addItem("")
        for entry in tag_library.entries(group="fullbody", include_review=False):
            if entry.get("tag_type") == "main" and entry.get("serialized_value") not in {"topless", "bottomless"}:
                self.main_tag.addItem(entry.get("display_name", entry["name"]), entry["serialized_value"])
        self.body_tag = QComboBox()
        self.body_tag.addItem("")
        for entry in tag_library.entries(group="body_images", include_review=False):
            if entry.get("tag_type") == "main":
                self.body_tag.addItem(entry.get("display_name", entry["name"]), entry.get("serialized_value"))
        self.location_tag = QListWidget()
        self.location_tag.setMaximumHeight(80)
        self.location_tag.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.location_tag.setToolTip("Scroll the canonical locations and select one optional value.")
        for value in ("bathroom", "bar", "beach", "cafeteria", "class", "clinic", "coffee_shop",
                      "home", "locker_room", "mall", "office", "park", "pier", "shower", "lounge"):
            item = QListWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.location_tag.addItem(item)
        saved_location = self.latest.get("location_tag")
        if saved_location:
            for index in range(self.location_tag.count()):
                item = self.location_tag.item(index)
                item.setSelected(item.data(Qt.ItemDataRole.UserRole) == saved_location)
        candidate_locations = location_candidates(
            proposal.get("yolo_class_name"), registry_id=proposal.get("yolo_registry_id"),
            model_id=proposal.get("yolo_model_id"), class_id=proposal.get("yolo_class_id"),
            checkpoint_digest=proposal.get("yolo_model_digest"))
        self.location_suggestions_label = QLabel(
            "Detector evidence suggests: " + (", ".join(candidate_locations) if candidate_locations else "no verified location suggestions") +
            ". These are suggestions only; choose the final location yourself."
        )
        self.location_suggestions_label.setWordWrap(True)
        self.clothing_tag = QComboBox()
        self.clothing_tag.addItem("")
        for entry in tag_library.entries(group="clothing", include_review=False):
            if entry.get("tag_type") in {"main", "tag"}:
                self.clothing_tag.addItem(entry.get("display_name", entry["name"]), entry.get("serialized_value"))
        self.asset_cnn_class = QComboBox()
        self.asset_cnn_class.addItem("")
        for class_row in clothing_classes():
            self.asset_cnn_class.addItem(class_row["display_name"], class_row["class_name"])
        saved_clothing_class = self.latest.get("clothing_family_tag")
        if saved_clothing_class:
            index = self.asset_cnn_class.findData(saved_clothing_class)
            if index >= 0:
                self.asset_cnn_class.setCurrentIndex(index)
        self.clothing_suggestions = QComboBox()
        self.clothing_suggestions.addItem("Choose a family suggestion…", None)
        self.clothing_suggestions.currentIndexChanged.connect(self._apply_clothing_suggestion)
        self.asset_cnn_class.currentIndexChanged.connect(self._refresh_clothing_suggestions)
        self._refresh_clothing_suggestions()
        self.state = QComboBox()
        self.state.addItems(["", "clothed", "topless", "bottomless"])
        self.state.setCurrentText({"normal": "clothed"}.get(self.latest.get("state_spec"), self.latest.get("state_spec") or ""))
        legacy_state = legacy_fullbody_state_candidate(
            proposal.get("cnn_class_name"), model_id=proposal.get("cnn_model_id"),
            checkpoint_digest=proposal.get("cnn_model_digest"))
        self.legacy_state_note = QLabel("Legacy Fullbody CNN evidence: " + (
            "candidate: clothed; reviewer confirmation required" if legacy_state and not legacy_state["ambiguous"] else
            "ambiguous nude evidence; choose topless or bottomless" if legacy_state else
            "no legacy Fullbody state candidate"))
        self.legacy_state_note.setWordWrap(True)
        self.legacy_state_note.setObjectName("SuggestionNote")
        self.output_category = QComboBox()
        for value in ("fullbody", "fullbody_topless", "fullbody_bottomless"):
            self.output_category.addItem(value, value)
        if self.latest.get("fullbody_output_category"):
            self.output_category.setCurrentIndex(self.output_category.findData(self.latest["fullbody_output_category"]))
        for combo, field in ((self.main_tag, "main_tag"), (self.body_tag, "main_tag"),
                             (self.clothing_tag, "clothing_tag")):
            value = self.latest.get(field)
            if value:
                index = combo.findData(value)
                if index >= 0:
                    combo.setCurrentIndex(index)
                else:
                    combo.setCurrentText(value)
        self.subtags = QListWidget()
        self.subtags.setMaximumHeight(145)
        self.subtags.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.subtags.setToolTip("Select the exact human tags to serialize after the hyphen.")
        self._saved_subtags = list(self.latest.get("subtags", []))
        self._saved_subtags = [value for value in self._saved_subtags
                               if value not in REGISTRY["corruption_values"]]
        # Older reviewed payloads stored composition-like values separately.
        if self.latest.get("sub_main_tag") and self.category.currentData() == "body_images":
            self._saved_subtags.append(self.latest["sub_main_tag"])
        self._populate_subtags(self.category.currentData())
        if self.latest.get("corruption_subtag"):
            self._saved_subtags.append(self.latest["corruption_subtag"])
            self._populate_subtags(self.category.currentData())
        self.validity_state = QComboBox()
        for value in ("", "valid", "invalid"):
            self.validity_state.addItem(value, value or None)
        self.validity_state.setCurrentIndex(max(0, self.validity_state.findData(self.latest.get("validity_state"))))
        self.validity_state.currentIndexChanged.connect(self._validity_changed)
        self.corruption_cnn_target = QComboBox()
        self.corruption_cnn_target.addItem("Choose one human target…", None)
        for value in REGISTRY["corruption_values"]:
            label = "Ultimate Whore" if value == "u_whore" else value.replace("_", " ").title()
            self.corruption_cnn_target.addItem(label, value)
        saved_corruption_target = self.latest.get("corruption_classifier_target")
        if saved_corruption_target:
            self.corruption_cnn_target.setCurrentIndex(
                max(0, self.corruption_cnn_target.findData(saved_corruption_target)))
        self.body_images_cnn_target = QComboBox()
        self.body_images_cnn_target.addItem("Choose broad evidence target…", None)
        self.body_images_cnn_target.addItem("Cum evidence · bodypart_cum", "bodypart_cum")
        self.body_images_cnn_target.addItem("Accessory evidence · bodypart_acc", "bodypart_acc")
        self.body_images_cnn_target.setCurrentIndex(max(0, self.body_images_cnn_target.findData(
            self.latest.get("body_images_cnn_target"))))
        self.fullbody_cnn_target = QComboBox()
        self.fullbody_cnn_target.addItem("Use confirmed Fullbody state", None)
        for value in ("clothed", "topless", "bottomless", "bra", "panty"):
            self.fullbody_cnn_target.addItem(value, value)
        self.fullbody_cnn_target.setCurrentIndex(max(0, self.fullbody_cnn_target.findData(
            self.latest.get("fullbody_cnn_target"))))
        self.arousal_cnn_target = QComboBox()
        self.arousal_cnn_target.addItem("Choose Arousal target…", None)
        for value in ("aroused", "edging"):
            self.arousal_cnn_target.addItem(value.title(), value)
        self.arousal_cnn_target.setCurrentIndex(max(0, self.arousal_cnn_target.findData(
            self.latest.get("arousal_cnn_target"))))
        self.portrait_cnn_target = QComboBox()
        self.portrait_cnn_target.addItem("Choose portrait target…", None)
        self.portrait_cnn_target.addItem("Portrait", "portrait")
        self.portrait_cnn_target.addItem("Topless portrait", "tportrait")
        self.portrait_cnn_target.setCurrentIndex(max(0, self.portrait_cnn_target.findData(
            self.latest.get("portrait_cnn_target"))))
        self.output_filename = QLineEdit()
        self.output_filename.setPlaceholderText("Required for Others export, e.g. item_name.webp")
        self.output_filename.setText(self.latest.get("output_filename", ""))
        form.addRow("Fullbody main tag", self.main_tag)
        form.addRow("Fullbody state", self.state)
        form.addRow(self.legacy_state_note)
        form.addRow("Fullbody output category", self.output_category)
        form.addRow("Body Images tag", self.body_tag)
        form.addRow("Human-selected subtags", self.subtags)
        form.addRow("Validity state", self.validity_state)
        form.addRow("Others output filename", self.output_filename)
        self.filename_preview = QLabel("Select verified main tags and subtags to preview the export name.")
        self.filename_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Filename preview (sequence 1)", self.filename_preview)

        task_panels_layout = QVBoxLayout()
        task_panels_layout.setContentsMargins(0, 0, 0, 0)
        form_content.addLayout(task_panels_layout)
        self.task_panels = {}
        self.task_status_labels = {}
        self.task_error_labels = {}
        self.task_training_checks = {}
        self.task_action_buttons = {}
        self.task_draft_buttons = {}
        self.task_reject_buttons = {}
        panel_specs = (
            ("body_images", "Body Images", (("Body Images CNN evidence target", self.body_images_cnn_target),),
             "Exact human filename tags remain separate from the broad CNN evidence target."),
            ("fullbody", "Fullbody", (("Fullbody CNN target", self.fullbody_cnn_target),),
             "The CNN target is independent from the filename state and main tag above."),
            ("portrait", "Portrait", (("Portrait CNN target", self.portrait_cnn_target),),
             "portrait_frame result only; Arousal becomes available after this task is confirmed."),
            ("arousal", "Arousal", (("Arousal CNN target", self.arousal_cnn_target),),
             "Arousal head target."),
            ("corruption", "Corruption",
             (("Corruption CNN target (one human-selected class)", self.corruption_cnn_target),),
             "Corruption head target."),
            ("location", "Location",
             (("Human-selected canonical location (optional)", self.location_tag),
              (None, self.location_suggestions_label)),
             "Single-select human location for a dedicated location_group box."),
            ("clothing_broad", "Clothing · broad family",
             (("Human-reviewed Clothing family", self.asset_cnn_class),
              ("Suggestions for this family", self.clothing_suggestions)),
             "Broad Clothing task."),
            ("clothing_fine", "Clothing · detailed tag",
             (("Final Clothing tag (human selected)", self.clothing_tag),),
             "Detailed Clothing task."),
        )
        for head, title, fields, note in panel_specs:
            panel = QGroupBox(title, form_widget)
            panel_layout = QVBoxLayout(panel)
            field_form = QFormLayout()
            field_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            panel_layout.addLayout(field_form)
            for label_text, field in fields:
                if label_text:
                    field_form.addRow(label_text, field)
                else:
                    field_form.addRow(field)
            note_label = QLabel(note, panel)
            note_label.setWordWrap(True)
            note_label.setObjectName("SuggestionNote")
            panel_layout.addWidget(note_label)
            suggestion_label = QLabel(self._task_suggestion_text(head), panel)
            suggestion_label.setWordWrap(True)
            suggestion_label.setObjectName("SuggestionNote")
            panel_layout.addWidget(suggestion_label)
            status = QLabel("Not reviewed", panel)
            panel_layout.addWidget(status)
            error = QLabel("", panel)
            error.setWordWrap(True)
            error.setStyleSheet("color: #d9534f")
            error.hide()
            panel_layout.addWidget(error)
            train_check = QCheckBox("Eligible for training when confirmed", panel)
            train_check.setChecked(self.validity_state.currentData() == "valid")
            train_check.setEnabled(self.validity_state.currentData() == "valid")
            panel_layout.addWidget(train_check)
            actions = QHBoxLayout()
            confirm = QPushButton(f"Confirm {title}", panel)
            draft = QPushButton("Save task draft", panel)
            reject = QPushButton("Reject this task", panel)
            actions.addWidget(confirm)
            actions.addWidget(draft)
            actions.addWidget(reject)
            panel_layout.addLayout(actions)
            confirm.clicked.connect(lambda _checked=False, key=head: self._submit_task_action(key, "confirmed"))
            draft.clicked.connect(lambda _checked=False, key=head: self._submit_task_action(key, "draft"))
            reject.clicked.connect(lambda _checked=False, key=head: self._submit_task_action(key, "rejected"))
            self.task_panels[head] = panel
            self.task_status_labels[head] = status
            self.task_suggestion_labels = getattr(self, "task_suggestion_labels", {})
            self.task_suggestion_labels[head] = suggestion_label
            self.task_error_labels[head] = error
            self.task_training_checks[head] = train_check
            self.task_action_buttons[head] = confirm
            self.task_draft_buttons[head] = draft
            self.task_reject_buttons[head] = reject
            saved = (proposal.get("task_reviews") or {}).get(head)
            if saved:
                status.setText(f"{saved['confirmation_status'].replace('_', ' ').title()} · {saved['target_label']} · {saved['created_at']}")
            task_panels_layout.addWidget(panel)
            panel.setVisible(False)

        technical_form = QFormLayout()
        technical_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.technical_form = technical_form
        form_content.addLayout(technical_form)
        yolo_box = QHBoxLayout()
        coordinates = tuple(self.latest.get("bbox_xyxy") or (
            proposal.get("yolo_x1"), proposal.get("yolo_y1"),
            proposal.get("yolo_x2"), proposal.get("yolo_y2")))
        if proposal.get("detection_id") is None and self.latest.get("bbox_xyxy") is None:
            coordinates = (0, 0, proposal.get("width", 1), proposal.get("height", 1))
        self.boxes = []
        for value, limit in zip(coordinates, (proposal.get("width", 1), proposal.get("height", 1),
                                               proposal.get("width", 1), proposal.get("height", 1))):
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setRange(0, max(float(limit or 1), 1))
            spin.setValue(float(value or 0))
            spin.setPrefix("x1 " if len(self.boxes) == 0 else "y1 " if len(self.boxes) == 1 else
                           "x2 " if len(self.boxes) == 2 else "y2 ")
            spin.setEnabled(value is not None)
            self.boxes.append(spin)
            yolo_box.addWidget(spin)
        yolo_box_widget = QWidget(form_widget)
        yolo_box_widget.setLayout(yolo_box)
        yolo_box_widget.setVisible(proposal.get("detection_id") is not None)
        technical_form.addRow("Effective bbox (source pixels)", yolo_box_widget)
        target_registry_path = Path(__file__).resolve().parents[2] / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
        target_registry = json.loads(target_registry_path.read_text(encoding="utf-8"))
        self._yolo_target_classes = {
            int(row["id"]): str(row["name"]) for row in target_registry["classes"]
        }
        self.yolo_class = QComboBox()
        self.yolo_class.addItem("Choose target class", None)
        for row in target_registry["classes"]:
            self.yolo_class.addItem(f"{row['id']}: {row['name']}", row["id"])
        current_class = self.latest.get("yolo_annotation_class_id")
        index = self.yolo_class.findData(current_class)
        if index >= 0:
            self.yolo_class.setCurrentIndex(index)
        else:
            original_class = str(proposal.get("yolo_class_name") or "")
            index = next(
                (i for i in range(self.yolo_class.count())
                 if str(self.yolo_class.itemText(i)).split(": ", 1)[-1].casefold()
                 == original_class.casefold()),
                -1,
            )
            if index >= 0:
                self.yolo_class.setCurrentIndex(index)
        self.yolo_class.setVisible(proposal.get("detection_id") is not None)
        technical_form.addRow("Effective YOLO class", self.yolo_class)
        self.training_tasks = QListWidget()
        self.training_tasks.setMaximumHeight(190)
        self.training_tasks.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.training_tasks.setToolTip("Select training tasks supported by this human-reviewed record.")
        task_specs = [
            ("yolo_detector", "Target YOLO detector", "target_yolo_training_eligible"),
            ("body_images", "Body Images evidence head", "body_images_cnn_training_eligible"),
            ("fullbody", "Fullbody head", "fullbody_cnn_training_eligible"),
            ("portrait", "Portrait head", "portrait_cnn_training_eligible"),
            ("arousal", "Arousal head", "arousal_cnn_training_eligible"),
            ("clothing_broad", "Broad Clothing family classifier", "broad_clothing_training_eligible"),
            ("clothing_fine", "Fine-grained Clothing classifier", "clothing_cnn_training_eligible"),
            ("corruption", "Corruption head", "corruption_cnn_training_eligible"),
        ]
        self._training_task_items = {}
        saved_training_tasks = set(self.latest.get("requested_training_tasks", []))
        for key, label, saved_key in task_specs:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setSelected(key in saved_training_tasks if saved_training_tasks
                             else bool(self.latest.get(saved_key)))
            self.training_tasks.addItem(item)
            self._training_task_items[key] = item
        # Shared head and Clothing training are confirmed in their own panels below.
        self._training_task_items["body_images"].setHidden(True)
        self._training_task_items["fullbody"].setHidden(True)
        self._training_task_items["portrait"].setHidden(True)
        self._training_task_items["arousal"].setHidden(True)
        self._training_task_items["corruption"].setHidden(True)
        self._training_task_items["clothing_broad"].setHidden(True)
        self._training_task_items["clothing_fine"].setHidden(True)
        self._training_task_items["body_images"].setSelected(False)
        self._training_task_items["fullbody"].setSelected(False)
        self._training_task_items["portrait"].setSelected(False)
        self._training_task_items["arousal"].setSelected(False)
        self._training_task_items["corruption"].setSelected(False)
        self._training_task_items["clothing_broad"].setSelected(False)
        self._training_task_items["clothing_fine"].setSelected(False)
        technical_form.addRow("YOLO annotation training eligibility", self.training_tasks)
        self.exclusion_reason = QComboBox()
        for reason in REGISTRY["exclusion_reasons"]:
            self.exclusion_reason.addItem(reason.replace("_", " ").title() if reason else "No exclusion reason", reason or None)
        saved_reason = self.latest.get("exclusion_reason")
        self.exclusion_reason.setCurrentIndex(max(0, self.exclusion_reason.findData(saved_reason)))
        technical_form.addRow("Training exclusion reason", self.exclusion_reason)
        self.no_objects = QCheckBox("Manually confirm this source image has no active asset objects")
        self.no_objects.setEnabled(proposal.get("detection_id") is None)
        self.no_objects.setChecked(bool(self.latest.get("no_objects")))
        self.no_objects.toggled.connect(self._toggle_no_objects)
        technical_form.addRow(self.no_objects)
        self.notes = QLineEdit()
        self.notes.setPlaceholderText("Review note (optional)")
        technical_form.addRow("Notes", self.notes)
        form_scroll = QScrollArea(self)
        form_scroll.setWidgetResizable(True)
        form_scroll.setWidget(form_widget)
        layout.addWidget(form_scroll, 1)
        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(6)
        self.confirm_button = QPushButton("Confirm human tags")
        self.confirm_button.setToolTip("Confirm filename tags only. Use each task panel to confirm its classifier independently.")
        self.save_button = QPushButton("Save draft")
        self.save_button.setToolTip("Save filename tag edits without confirming a task or making it training eligible.")
        self.reject_button = QPushButton("Reject proposal")
        self.cancel_button = QPushButton("Cancel")
        self.save_class_button = QPushButton("Save class correction")
        self.save_bbox_button = QPushButton("Save bbox correction")
        self.save_combined_button = QPushButton("Save combined correction")
        self.save_class_button.setEnabled(proposal.get("detection_id") is not None)
        self.save_bbox_button.setEnabled(proposal.get("detection_id") is not None)
        self.save_combined_button.setEnabled(proposal.get("detection_id") is not None)
        self.save_class_button.clicked.connect(self._submit_class_correction)
        self.save_bbox_button.clicked.connect(self._submit_bbox_correction)
        self.save_combined_button.clicked.connect(self._submit_combined_correction)
        for column in range(2):
            actions.setColumnStretch(column, 1)
        actions.addWidget(self.confirm_button, 0, 0)
        actions.addWidget(self.save_button, 0, 1)
        actions.addWidget(self.save_class_button, 1, 0)
        actions.addWidget(self.save_bbox_button, 1, 1)
        actions.addWidget(self.save_combined_button, 2, 0)
        actions.addWidget(self.reject_button, 2, 1)
        actions.addWidget(self.cancel_button, 3, 0)
        layout.addLayout(actions)
        self.confirm_button.clicked.connect(self._confirm)
        self.save_button.clicked.connect(self._save)
        self.reject_button.clicked.connect(self._reject)
        self.cancel_button.clicked.connect(self.reject)
        self.category.currentIndexChanged.connect(self._category_changed)
        self.body_tag.currentIndexChanged.connect(self._refresh_task_visibility)
        self.portrait_cnn_target.currentIndexChanged.connect(self._refresh_task_visibility)
        self.yolo_class.currentIndexChanged.connect(self._refresh_task_visibility)
        self.state.currentIndexChanged.connect(self._state_changed)
        for combo in (self.category, self.main_tag, self.body_tag, self.clothing_tag,
                      self.state, self.output_category, self.yolo_class, self.asset_cnn_class):
            combo.currentIndexChanged.connect(self._mark_changed)
            if combo.isEditable():
                combo.lineEdit().textEdited.connect(self._mark_changed)
        self.corruption_cnn_target.currentIndexChanged.connect(self._mark_changed)
        self.body_images_cnn_target.currentIndexChanged.connect(self._mark_changed)
        self.fullbody_cnn_target.currentIndexChanged.connect(self._mark_changed)
        self.arousal_cnn_target.currentIndexChanged.connect(self._mark_changed)
        self.portrait_cnn_target.currentIndexChanged.connect(self._mark_changed)
        for box in self.boxes:
            box.valueChanged.connect(self._mark_changed)
        self.subtags.itemSelectionChanged.connect(self._mark_changed)
        self.validity_state.currentIndexChanged.connect(self._mark_changed)
        self.location_tag.itemSelectionChanged.connect(self._mark_changed)
        self.training_tasks.itemSelectionChanged.connect(self._mark_changed)
        if self.clothing_tag.isEditable():
            self.clothing_tag.lineEdit().textEdited.connect(self._manual_clothing_tag_edited)
        self.output_filename.textEdited.connect(self._mark_changed)
        self.exclusion_reason.currentIndexChanged.connect(self._mark_changed)
        for combo in (self.main_tag, self.body_tag,
                      self.clothing_tag, self.state, self.category):
            combo.currentIndexChanged.connect(self._refresh_filename_preview)
            if combo.isEditable():
                combo.lineEdit().textEdited.connect(self._refresh_filename_preview)
        self.subtags.itemSelectionChanged.connect(self._refresh_filename_preview)
        self.location_tag.itemSelectionChanged.connect(self._refresh_filename_preview)
        self.category.currentIndexChanged.connect(self._refresh_subtags_for_category)
        self.body_tag.currentIndexChanged.connect(self._refresh_subtags_for_category)
        self.main_tag.currentIndexChanged.connect(self._refresh_subtags_for_category)
        self._category_changed()
        self._state_changed()
        self._validity_changed()
        self._refresh_filename_preview()

        # This dialog is a YOLO authority editor, not a classification form.
        # Keep all legacy classification widgets alive for backward-compatible
        # database callers, but do not expose or route them through this dialog.
        yolo_only_hide = [
            self.category, self.main_tag, self.body_tag, self.location_tag,
            self.location_suggestions_label, self.clothing_tag, self.asset_cnn_class,
            self.clothing_suggestions, self.state, self.output_category,
            self.subtags, self.validity_state, self.corruption_cnn_target,
            self.body_images_cnn_target, self.fullbody_cnn_target,
            self.arousal_cnn_target, self.portrait_cnn_target,
            self.output_filename, self.filename_preview, self.training_tasks,
            self.exclusion_reason, self.no_objects, self.notes,
            self.confirm_button, self.save_button, self.reject_button,
        ]
        for widget in yolo_only_hide:
            widget.hide()
            label = self.form.labelForField(widget)
            if label:
                label.hide()
        for panel in self.task_panels.values():
            panel.hide()

    def _task_suggestion_text(self, task: str) -> str:
        saved = self.task_reviews.get(task) or {}
        provenance = saved.get("suggestion_provenance_json")
        if provenance:
            try:
                suggestion = json.loads(provenance)
                cnn = suggestion.get("cnn") or {}
                if cnn.get("class_name"):
                    confidence = cnn.get("confidence")
                    score = f" · {float(confidence):.1%}" if confidence is not None else ""
                    model = f" · {cnn.get('model_id')}" if cnn.get("model_id") else ""
                    return f"CNN evidence: {cnn['class_name']}{score}{model} · unconfirmed"
            except (TypeError, ValueError):
                pass
        if task in {"clothing_broad", "clothing_fine"} and self.proposal.get("cnn_class_name"):
            confidence = self.proposal.get("cnn_confidence")
            score = f" · {float(confidence):.1%}" if confidence is not None else ""
            return f"CNN evidence: {self.proposal['cnn_class_name']}{score} · unconfirmed"
        return "CNN suggestion unavailable · human selection remains unconfirmed"

    def _task_target(self, task: str):
        if task == "body_images":
            return self.body_images_cnn_target.currentData()
        if task == "fullbody":
            return self.fullbody_cnn_target.currentData()
        if task == "portrait":
            return self.portrait_cnn_target.currentData()
        if task == "arousal":
            return self.arousal_cnn_target.currentData()
        if task == "corruption":
            return self.corruption_cnn_target.currentData()
        if task == "location":
            return self._selected_location()
        if task == "clothing_broad":
            return self.asset_cnn_class.currentData()
        if task == "clothing_fine":
            return self.clothing_tag.currentData() or self.clothing_tag.currentText().strip()
        return None

    def _submit_task_action(self, task: str, action: str):
        if self.proposal.get("detection_id") is None:
            manual_person_roi = (
                task == "corruption"
                and str(self.proposal.get("yolo_class_name") or "").casefold() == "person"
                and self.category.currentData() == "others"
            )
            if not manual_person_roi:
                message = "This proposal has no linked Detection. This classification task requires a persisted Detection; use the valid manual-crop workflow instead."
                self.set_task_error(task, message)
                QMessageBox.warning(self, "Detection required", message)
                return
        if not self._task_target(task):
            self.set_task_error(task, "Choose a target for this task before saving.")
            return
        payload = self.result_payload()
        payload["shared_cnn_training_tasks"] = []
        payload["requested_training_tasks"] = ["yolo_detector"] if self._training_task_selected("yolo_detector") else []
        for key in ("target_yolo_training_eligible", "yolo_training_eligible", "cnn_training_eligible",
                    "broad_clothing_training_eligible", "clothing_cnn_training_eligible",
                    "unified_cnn_training_eligible", "corruption_training_eligible"):
            payload[key] = False
        self._result_payload = payload
        self._task_action = {"task_head": task, "target_label": self._task_target(task),
                             "action": action,
                             "training_eligible": action == "confirmed" and
                                 bool(self.task_training_checks[task].isChecked())}
        self.decision_type = "task_classification"
        self.accept()

    def _submit_class_correction(self):
        if self.proposal.get("detection_id") is None:
            QMessageBox.warning(
                self, "Detection required",
                "YOLO class correction requires a proposal linked to a persisted Detection.",
            )
            return
        class_id = self.yolo_class.currentData()
        if class_id is None or int(class_id) not in self._yolo_target_classes:
            QMessageBox.warning(self, "Choose a target YOLO class",
                                "Select the human-corrected class from the approved YOLO registry.")
            return
        self._result_payload = {
            "yolo_annotation_registry_id": "newassetapp_yolo_detector_v1",
            "yolo_annotation_class_id": int(class_id),
            "yolo_annotation_class_name": self._yolo_target_classes[int(class_id)],
        }
        self.decision_type = "class_correction"
        self.accept()

    def _submit_bbox_correction(self):
        if self.proposal.get("detection_id") is None:
            QMessageBox.warning(self, "Cannot correct bounding box",
                                "This proposal does not have a persisted detection.")
            return
        bbox = [float(box.value()) for box in self.boxes]
        width, height = float(self.proposal.get("width") or 0), float(self.proposal.get("height") or 0)
        if not (width > 0 and height > 0 and
                0 <= bbox[0] < bbox[2] <= width and 0 <= bbox[1] < bbox[3] <= height):
            QMessageBox.warning(self, "Invalid bounding box",
                                "The corrected box must have positive area and stay inside the source image.")
            return
        self._result_payload = {"bbox_xyxy": bbox}
        self.decision_type = "bbox_correction"
        self.accept()

    def _submit_combined_correction(self):
        if self.proposal.get("detection_id") is None:
            QMessageBox.warning(
                self, "Detection required",
                "Combined YOLO correction requires a proposal linked to a persisted Detection.",
            )
            return
        class_id = self.yolo_class.currentData()
        if class_id is None or int(class_id) not in self._yolo_target_classes:
            QMessageBox.warning(
                self, "Choose a target YOLO class",
                "Select the human-corrected class from the approved YOLO registry.",
            )
            return
        bbox = [float(box.value()) for box in self.boxes]
        width, height = float(self.proposal.get("width") or 0), float(self.proposal.get("height") or 0)
        if not (width > 0 and height > 0 and
                0 <= bbox[0] < bbox[2] <= width and 0 <= bbox[1] < bbox[3] <= height):
            QMessageBox.warning(
                self, "Invalid bounding box",
                "The corrected box must have positive area and stay inside the source image.",
            )
            return
        self._result_payload = {
            "bbox_xyxy": bbox,
            "yolo_annotation_registry_id": "newassetapp_yolo_detector_v1",
            "yolo_annotation_class_id": int(class_id),
            "yolo_annotation_class_name": self._yolo_target_classes[int(class_id)],
        }
        self.decision_type = "combined_correction"
        self.accept()

    def set_task_error(self, task: str, message: str):
        if task not in self.task_error_labels:
            return
        label = self.task_error_labels[task]
        label.setText(str(message))
        label.show()
        self._result_payload = None
        self._task_action = None

    def _refresh_filename_preview(self, *_):
        category = self.category.currentData()
        tags = self._selected_subtags()
        tags.extend(value for value in self._selected_corruption_values() if value not in tags)
        location = self._selected_location()
        if location and location not in tags:
            tags.append(location)
        try:
            if category == "fullbody":
                filename = fullbody_filename(self.main_tag.currentData() or self.main_tag.currentText().strip(),
                                             self.state.currentText(), 1, tags)
            elif category == "body_images":
                mains = [self.body_tag.currentData() or self.body_tag.currentText().strip()]
                filename = body_images_filename(mains, 1, tags)
            elif category == "clothing":
                filename = clothing_filename(self.clothing_tag.currentData() or self.clothing_tag.currentText().strip(),
                                             1, tags)
            else:
                filename = self.output_filename.text().strip() or "(enter an Others filename)"
            self.filename_preview.setText(filename + " · output planner advances the sequence if occupied")
        except (ValueError, TypeError):
            self.filename_preview.setText("Select a verified tag composition to preview its filename.")

    def _category_changed(self, *_):
        category = self.category.currentData()
        region = (self.yolo_class.currentText().split(": ", 1)[-1]
                  if self.yolo_class.currentData() is not None
                  else str(self.proposal.get("yolo_class_name") or ""))
        is_fullbody = category == "fullbody"
        self.main_tag.setEnabled(is_fullbody)
        self.state.setEnabled(is_fullbody)
        self.output_category.setEnabled(is_fullbody)
        self.body_tag.setEnabled(self.category.currentData() == "body_images")
        self._refresh_task_visibility()
        category_rows = {
            "fullbody": (self.main_tag, self.state, self.output_category, self.legacy_state_note,
                         ),
            "body_images": (self.body_tag,),
            "clothing": (),
            "others": (),
        }
        for widgets in category_rows.values():
            for widget in widgets:
                label = self.form.labelForField(widget)
                visible = widget in category_rows.get(category, ())
                widget.setVisible(visible)
                if label:
                    label.setVisible(visible)
        shared_controls = (self.subtags, self.validity_state, self.training_tasks)
        for widget in shared_controls:
            label = self.form.labelForField(widget)
            visible = category in {"fullbody", "body_images", "clothing"} if widget == self.subtags else True
            widget.setVisible(visible)
            if label:
                label.setVisible(visible)
        self._refresh_filename_preview()

    def _refresh_task_visibility(self, *_):
        """Apply head eligibility to task choices and their human target controls."""
        category = self.category.currentData()
        original_region = str(self.proposal.get("yolo_class_name") or "")
        corrected_region = self.yolo_class.currentText().split(": ", 1)[-1] if self.yolo_class.currentData() is not None else ""
        region = corrected_region or original_region
        portrait_review = self.task_reviews.get("portrait") or {}
        confirmed_portrait = (portrait_review.get("target_label")
                              if portrait_review.get("confirmation_status") == "confirmed"
                              and portrait_review.get("human_confirmed") else None)
        task_availability = {
            "body_images": region in {"face", "boobs", "ass", "pussy", "legs"},
            "fullbody": is_fullbody_region(region),
            "portrait": region == "portrait_frame",
            "arousal": shared_head_eligible("arousal", region, confirmed_portrait=confirmed_portrait),
            "corruption": shared_head_eligible("corruption", region),
            "location": is_location_group(region),
            "clothing_broad": category == "clothing",
            "clothing_fine": category == "clothing",
        }
        task_availability["location"] = task_availability["location"]
        for key, panel in self.task_panels.items():
            panel.setVisible(bool(task_availability.get(key)))
            check = self.task_training_checks[key]
            valid = self.validity_state.currentData() == "valid"
            check.setEnabled(valid and bool(task_availability.get(key)))
            if not valid:
                check.setChecked(False)

    def _refresh_clothing_suggestions(self, *_):
        if not hasattr(self, "clothing_suggestions"):
            return
        selected = self.clothing_suggestions.currentData()
        family = self.asset_cnn_class.currentData()
        self.clothing_suggestions.blockSignals(True)
        self.clothing_suggestions.clear()
        self.clothing_suggestions.addItem("Choose a family suggestion…", None)
        for tag in suggested_clothing_tags(family) if family else []:
            self.clothing_suggestions.addItem(tag, tag)
        self.clothing_suggestions.setCurrentIndex(max(0, self.clothing_suggestions.findData(selected)))
        self.clothing_suggestions.blockSignals(False)

    def _populate_subtags(self, category: str):
        selected = set(getattr(self, "_saved_subtags", []))
        if hasattr(self, "subtags"):
            selected |= set(self._selected_subtags())
        entries = self.tag_library.entries(group=category, include_review=False) if category in {
            "fullbody", "body_images", "clothing"} else []
        values = {entry.get("serialized_value") for entry in entries
                  if entry.get("tag_type") in {"subtag", "tag", "modifier"}
                  and entry.get("serialized_value")}
        values.difference_update(REGISTRY["locations"]["canonical_values"])
        values.difference_update(REGISTRY["corruption_values"])
        if category == "body_images":
            main = self.body_tag.currentData() or self.body_tag.currentText().strip()
            values.update(REGISTRY["body_images"]["supported_main_subtag_pairs"].get(main, []))
        if category == "fullbody":
            policy = json.loads((self.tag_library.data_dir.parent / "models" /
                                 "fullbody_classification_policy.json").read_text(encoding="utf-8"))
            values.update(policy.get("supported_subtags", []))
        values.discard(None)
        values.difference_update(REGISTRY["locations"]["canonical_values"])
        values.difference_update(REGISTRY["corruption_values"])
        values.discard("park")
        self.subtags.blockSignals(True)
        self.subtags.clear()
        for value in sorted(values):
            item = QListWidgetItem(value)
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setSelected(value in selected)
            self.subtags.addItem(item)
        self.subtags.blockSignals(False)
        self._saved_subtags = []

    def _refresh_subtags_for_category(self, *_):
        if hasattr(self, "subtags"):
            self._populate_subtags(self.category.currentData())

    def _selected_subtags(self) -> list[str]:
        if not hasattr(self, "subtags"):
            return []
        return [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.subtags.selectedItems()]

    def _selected_corruption_values(self) -> list[str]:
        target = self.corruption_cnn_target.currentData()
        return [str(target)] if target else []

    def _selected_location(self):
        region = (self.yolo_class.currentText().split(": ", 1)[-1]
                  if self.yolo_class.currentData() is not None
                  else str(self.proposal.get("yolo_class_name") or ""))
        if not is_location_group(region):
            return None
        selected = self.location_tag.selectedItems()
        return selected[0].data(Qt.ItemDataRole.UserRole) if selected else None

    def _apply_clothing_suggestion(self, index: int):
        value = self.clothing_suggestions.itemData(index)
        if value:
            self.clothing_tag_input_method = "family_suggestion_selected"
            tag_index = self.clothing_tag.findData(str(value))
            if tag_index >= 0:
                self.clothing_tag.setCurrentIndex(tag_index)
            self._mark_changed()
            self._refresh_filename_preview()

    def _manual_clothing_tag_edited(self, _text: str):
        self.clothing_tag_input_method = "manual_entry"
        self.clothing_suggestions.blockSignals(True)
        self.clothing_suggestions.setCurrentIndex(0)
        self.clothing_suggestions.blockSignals(False)
        self._mark_changed()

    def _state_changed(self, *_):
        state = self.state.currentText()
        output = {"clothed": "fullbody", "topless": "fullbody_topless",
                  "bottomless": "fullbody_bottomless"}.get(state)
        if output:
            self.output_category.setCurrentIndex(self.output_category.findData(output))

    def _mark_changed(self, *_):
        self.confirm_button.setEnabled(True)

    def _validity_changed(self, *_):
        can_train = self.validity_state.currentData() == "valid"
        if not can_train:
            self.training_tasks.clearSelection()
        self.training_tasks.setEnabled(can_train)
        if hasattr(self, "task_panels"):
            self._refresh_task_visibility()
        self._mark_changed()

    def _toggle_no_objects(self, checked: bool):
        for box in self.boxes:
            box.setEnabled(not checked and (box.value() >= 0))
        if checked:
            self.yolo_class.setCurrentIndex(0)
            self._training_task_items["yolo_detector"].setSelected(True)
            for key in ("body_images", "fullbody", "portrait", "arousal", "clothing_broad",
                        "clothing_fine", "corruption"):
                self._training_task_items[key].setSelected(False)
        self._mark_changed()

    def result_payload(self) -> dict:
        if isinstance(getattr(self, "_result_payload", None), dict):
            return dict(self._result_payload)
        category = self.category.currentData()
        main_value = self.main_tag.currentData() or self.main_tag.currentText().strip()
        body_value = self.body_tag.currentData() or self.body_tag.currentText().strip()
        clothing_value = self.clothing_tag.currentData() or self.clothing_tag.currentText().strip()
        bbox = [float(box.value()) for box in self.boxes] if self.boxes[0].isEnabled() else None
        payload = {"category": category, "bbox_xyxy": bbox,
                   "requested_training_tasks": (["yolo_detector"] if self._training_task_selected("yolo_detector") else []),
                   "output_filename": self.output_filename.text().strip() or None,
                   "class_id": self.latest.get("class_id", self.proposal.get("yolo_class_id")),
                   "subtags": self._selected_subtags(),
                   "validity_state": self.validity_state.currentData(),
                   "corruption_state": next(iter(self._selected_corruption_values()), None),
                   "corruption_values": self._selected_corruption_values(),
                   "corruption_classifier_target": self.corruption_cnn_target.currentData(),
                   "corruption_training_eligible": False,
                   "body_images_cnn_target": self.body_images_cnn_target.currentData(),
                   "fullbody_cnn_target": self.fullbody_cnn_target.currentData(),
                   "arousal_cnn_target": self.arousal_cnn_target.currentData(),
                   "shared_cnn_training_tasks": [],
                   "propagate_corruption_review": False,
                   "notes": self.notes.text().strip(),
                   "yolo_class_id": self.latest.get("class_id", self.proposal.get("yolo_class_id")),
                   "yolo_annotation_registry_id": "newassetapp_yolo_detector_v1",
                   "yolo_annotation_class_id": self.yolo_class.currentData(),
                   "yolo_annotation_class_name": self.yolo_class.currentText().split(": ", 1)[-1]
                       if self.yolo_class.currentData() is not None else None,
                   "target_yolo_training_eligible": self._training_task_selected("yolo_detector"),
                   "yolo_training_eligible": self._training_task_selected("yolo_detector"),
                   "cnn_training_eligible": False,
                   "broad_clothing_training_eligible": False,
                   "clothing_cnn_training_eligible": False,
                   "unified_cnn_training_eligible": False,
                   "asset_cnn_class": self.proposal.get("cnn_class_name"),
                   "clothing_cnn_class": self.proposal.get("cnn_class_name"),
                   "clothing_family_tag": self.asset_cnn_class.currentData(),
                   "clothing_tag": self.clothing_tag.currentData() or self.clothing_tag.currentText().strip(),
                   "clothing_tag_input_method": self.clothing_tag_input_method,
                   "clothing_taxonomy_version": "clothing-broad-v2-12class",
                   "location_tag": self._selected_location(),
                   "location_evidence_class": self.proposal.get("yolo_class_name"),
                   "location_evidence_registry_id": self.proposal.get("yolo_registry_id"),
                   "location_evidence_model_id": self.proposal.get("yolo_model_id"),
                   "location_evidence_class_id": self.proposal.get("yolo_class_id"),
                   "location_evidence_checkpoint_digest": self.proposal.get("yolo_model_digest"),
                   "exclusion_reason": self.exclusion_reason.currentData(),
                   "classification_registry_id": REGISTRY["registry_id"],
                   "taxonomy_version": REGISTRY["version"],
                   "no_objects": self.no_objects.isChecked()}
        payload["corruption_values"] = list(dict.fromkeys(
            payload["corruption_values"] + [value for value in payload["subtags"]
                                             if value in REGISTRY["corruption_values"]]))
        if category == "fullbody":
            payload.update({"main_tag": main_value, "state_spec": self.state.currentText() or None,
                            "fullbody_cnn_target": self.fullbody_cnn_target.currentData() or self.state.currentText() or None,
                            "fullbody_output_category": self.output_category.currentData(),
                            "unified_cnn_task": "fullbody_state",
                            "unified_cnn_class": self.state.currentText() or None})
        elif category == "body_images":
            payload["main_tag"] = body_value
            payload["unified_cnn_task"] = "body_images"
            payload["unified_cnn_class"] = body_value or None
            payload["portrait_cnn_target"] = self.portrait_cnn_target.currentData()
        elif category == "clothing":
            payload["main_tag"] = clothing_value
        elif category == "others" and payload.get("corruption_classifier_target"):
            target = payload["corruption_classifier_target"]
            payload["corruption_state"] = target
            payload["corruption_values"] = list(dict.fromkeys(payload["corruption_values"] + [target]))
        return payload

    def _training_task_selected(self, key: str) -> bool:
        return self._training_task_items[key].isSelected()

    def _confirm(self):
        payload = self.result_payload()
        category = payload.get("category")
        label = ({"fullbody": payload.get("state_spec"),
                  "body_images": payload.get("main_tag"),
                  "clothing": payload.get("clothing_family_tag") or payload.get("clothing_tag"),
                  "others": payload.get("corruption_classifier_target")}.get(category))
        if category == "fullbody" and self.proposal.get("yolo_class_name") == "person":
            QMessageBox.warning(self, "Person region review",
                                "A person detection is a person-region box for Others and corruption-state labeling. "
                                "It cannot be confirmed as Fullbody. Choose Others and a human-selected corruption target.")
            return
        if not self._validate_form(payload):
            return
        payload["shared_cnn_training_tasks"] = []
        self.decision_type = "annotation_confirmation"
        self._result_payload = payload
        self.accept()

    def _save(self):
        payload = self.result_payload()
        if not self._validate_form(payload):
            return
        payload["requested_training_tasks"] = [key for key in self._training_task_items
                                               if self._training_task_selected(key)]
        for field in ("target_yolo_training_eligible", "yolo_training_eligible",
                      "cnn_training_eligible", "broad_clothing_training_eligible",
                      "clothing_cnn_training_eligible", "unified_cnn_training_eligible",
                      "corruption_training_eligible"):
            payload[field] = False
        payload["shared_cnn_training_tasks"] = []
        self._result_payload = payload
        self.decision_type = "manual_annotation" if payload.get("no_objects") else "corrected"
        self.accept()

    def _validate_form(self, payload: dict) -> bool:
        if self._training_task_selected("yolo_detector") and payload.get("yolo_annotation_class_id") is None:
            QMessageBox.warning(self, "Choose a target YOLO class",
                                "Choose the human-selected class from the approved 31-class target registry.")
            return False
        if self._training_task_selected("corruption") and not payload.get("corruption_classifier_target"):
            QMessageBox.warning(self, "Choose a corruption CNN target",
                                "Select one human-confirmed corruption state for this person crop.")
            return False
        required_targets = {
            "body_images": ("body_images_cnn_target", "Choose bodypart_cum or bodypart_acc for the Body Images evidence head."),
            "fullbody": ("fullbody_cnn_target", "Choose a class for the Fullbody head."),
            "portrait": ("portrait_cnn_target", "Choose portrait or tportrait as the Portrait head target."),
            "arousal": ("arousal_cnn_target", "Choose aroused or edging for the Arousal head."),
        }
        for task, (field, message) in required_targets.items():
            if task in payload.get("shared_cnn_training_tasks", []) and not payload.get(field):
                QMessageBox.warning(self, "Choose a CNN target", message)
                return False
        if "body_images" in payload.get("shared_cnn_training_tasks", []) and not payload.get("subtags"):
            QMessageBox.warning(self, "Choose exact Body Images tags",
                                "Select the human-confirmed final tags separately from the broad CNN evidence label.")
            return False
        if self.category.currentData() == "fullbody" and (not payload.get("main_tag") or not payload.get("state_spec")):
            QMessageBox.warning(self, "Complete Fullbody review", "Choose a verified main tag and a normal, topless, or bottomless state.")
            return False
        if self.category.currentData() == "body_images" and not payload.get("main_tag"):
            QMessageBox.warning(self, "Choose a Body Images tag", "Select or enter a reviewed Body Images tag.")
            return False
        if self.category.currentData() == "clothing" and not payload.get("main_tag"):
            QMessageBox.warning(self, "Choose a Clothing tag", "Select or enter a reviewed Clothing tag.")
            return False
        if self.category.currentData() == "clothing":
            family = self.asset_cnn_class.currentData()
            final_tag = payload.get("clothing_tag")
            if not family or not validate_final_clothing_tag(family, final_tag):
                QMessageBox.warning(
                    self, "Review the Clothing family and final tag",
                    "Choose a 12-class family and a selectable detailed tag that belongs to that family.")
                return False
        try:
            from app.core.classification_taxonomy import validate_record
            validate_record(payload["category"], {
                **payload,
                "main_tags": [payload.get("main_tag")] if payload.get("main_tag") else [],
                "human_review_state": "edited_unconfirmed",
            })
        except ValueError as error:
            QMessageBox.warning(self, "Check the structured tags", str(error))
            return False
        return True

    def _reject(self):
        self._result_payload = self.result_payload()
        self._result_payload["shared_cnn_training_tasks"] = []
        self.decision_type = "rejected"
        self.accept()
