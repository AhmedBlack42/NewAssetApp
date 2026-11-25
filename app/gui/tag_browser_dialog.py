from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from app.core.tag_library import GROUP_FILES, TagLibrary


class TagBrowserDialog(QDialog):
    """Search and multi-select JSON-backed tags; uncertain entries stay gated."""

    def __init__(self, library: TagLibrary, parent=None, preferred_group: str | None = None):
        super().__init__(parent)
        self.library = library
        self.selected_tags: list[dict] = []
        self.tag_changes: list[dict] = []
        self.setWindowTitle("Tag Library")
        self.resize(900, 650)
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.group = QComboBox()
        for group, filename in GROUP_FILES.items():
            import json
            payload = json.loads((library.data_dir / filename).read_text(encoding="utf-8"))
            self.group.addItem(payload.get("title", group), group)
        index = self.group.findData(preferred_group)
        if index >= 0:
            self.group.setCurrentIndex(index)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search names, serialized values, descriptions, or sources")
        self.show_review = QCheckBox("Show entries requiring review")
        self.show_deprecated = QCheckBox("Show deprecated user tags")
        controls.addWidget(self.group, 1)
        controls.addWidget(self.search, 2)
        controls.addWidget(self.show_review)
        controls.addWidget(self.show_deprecated)
        layout.addLayout(controls)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Tag / context", "Serialized value", "Type"])
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.currentItemChanged.connect(self._show_detail)
        layout.addWidget(self.tree, 1)

        self.detail = QLabel("Select a tag to inspect its description and provenance.")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.detail)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add user tag…")
        self.add_button.clicked.connect(self._add_user_tag)
        actions.addWidget(self.add_button)
        self.edit_button = QPushButton("Edit selected user tag…")
        self.edit_button.clicked.connect(self._edit_user_tag)
        actions.addWidget(self.edit_button)
        self.deprecate_button = QPushButton("Deprecate selected user tag")
        self.deprecate_button.clicked.connect(self._deprecate_user_tag)
        actions.addWidget(self.deprecate_button)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use selected tags")
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.group.currentIndexChanged.connect(self._reload)
        self.search.textChanged.connect(self._reload)
        self.show_review.toggled.connect(self._reload)
        self.show_deprecated.toggled.connect(self._reload)
        self._reload()

    def _reload(self):
        group = self.group.currentData()
        query = self.search.text().strip()
        if query:
            rows = self.library.search(query, group=group, include_review=self.show_review.isChecked())
            if self.show_deprecated.isChecked():
                by_id = {e["id"]: e for e in self.library.entries(
                    group=group, include_metadata=True, include_review=self.show_review.isChecked(),
                    include_deprecated=True,
                )}
                rows.extend(e for e in by_id.values() if e.get("deprecated") and query.casefold() in e.get("name", "").casefold())
        else:
            rows = self.library.entries(
                group=group, include_metadata=True, include_review=self.show_review.isChecked(),
                include_deprecated=self.show_deprecated.isChecked(),
            )
        by_id = {entry["id"]: entry for entry in rows}
        self.tree.clear()
        items: dict[str, QTreeWidgetItem] = {}
        for entry in rows:
            item = QTreeWidgetItem([
                entry.get("display_name", entry.get("name", "")),
                entry.get("serialized_value", ""),
                entry.get("tag_type", ""),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            selectable = bool(entry.get("selectable", True)) and not entry.get("requires_review") and not entry.get("deprecated")
            if not selectable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                item.setForeground(0, QColor("#e2a75f" if entry.get("requires_review") else "#8b93a1"))
            items[entry["id"]] = item
        for entry in rows:
            item = items[entry["id"]]
            parent = items.get(entry.get("parent_id"))
            (parent.addChild(item) if parent else self.tree.addTopLevelItem(item))
        if query:
            self.tree.expandAll()
        else:
            self.tree.collapseAll()
        self.tree.resizeColumnToContents(0)

    def _show_detail(self, current, _previous):
        entry = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        if not entry:
            self.detail.setText("Select a tag to inspect its description and provenance.")
            return
        self.detail.setText(
            f"{entry.get('description', '')}\n"
            f"Source: {entry.get('source', '')} · {entry.get('source_reference', '')}\n"
            f"Examples: {', '.join(entry.get('examples', [])) or 'None recorded'}"
            + ("\nRequires review; this item cannot be selected as a confirmed tag." if entry.get("requires_review") else "")
        )

    def _accept_selected(self):
        self.selected_tags = []
        for item in self.tree.selectedItems():
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            if entry and entry.get("selectable", True) and not entry.get("requires_review") and not entry.get("deprecated"):
                self.selected_tags.append(dict(entry))
        self.accept()

    def _add_user_tag(self):
        # Kept as an explicit form rather than deriving a parent or token from a name.
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        group = self.group.currentData()
        name, ok = QInputDialog.getText(self, "Add a user tag", "Original tag spelling:")
        if not ok:
            return
        value, ok = QInputDialog.getText(self, "Add a user tag", "Serialized value (enter explicitly):")
        if not ok:
            return
        parent_rows = self.library.entries(group=group, include_metadata=True, include_review=False)
        options = ["(no parent)"] + [f"{e['name']}  ·  {e['id']}" for e in parent_rows]
        selected, ok = QInputDialog.getItem(self, "Define parent", "Choose a parent explicitly:", options, 0, False)
        if not ok:
            return
        parent_id = None
        if selected != "(no parent)":
            parent_id = selected.split("  ·  ", 1)[1]
        tag_type, ok = QInputDialog.getItem(self, "Choose tag type", "Tag type:",
                                             ["main", "subtag", "modifier", "compound", "tag"], 0, False)
        if not ok:
            return
        description, ok = QInputDialog.getText(self, "Tag description", "Description (optional):")
        if not ok:
            return
        try:
            created = self.library.add_user_tag(group=group, name=name, serialized_value=value,
                                                parent_id=parent_id, tag_type=tag_type, description=description)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Tag not saved", str(exc))
            return
        self.tag_changes.append({"action": "add", "before": None, "after": created})
        self._reload()

    def _selected_user_entry(self):
        from PySide6.QtWidgets import QMessageBox
        selected = self.tree.selectedItems()
        if len(selected) != 1:
            QMessageBox.information(self, "Select one user tag", "Choose exactly one user-created tag first.")
            return None
        entry = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if not entry or entry.get("source") != "user_created":
            QMessageBox.information(self, "Built-in tag", "Extracted Girl Packer tags are preserved; only user-created tags can be edited or deprecated.")
            return None
        return entry

    def _edit_user_tag(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        entry = self._selected_user_entry()
        if not entry:
            return
        name, ok = QInputDialog.getText(self, "Edit user tag", "Original tag spelling:", text=entry["name"])
        if not ok:
            return
        value, ok = QInputDialog.getText(self, "Edit user tag", "Serialized value:", text=entry["serialized_value"])
        if not ok:
            return
        description, ok = QInputDialog.getText(self, "Edit user tag", "Description:", text=entry.get("description", ""))
        if not ok:
            return
        try:
            updated = self.library.edit_user_tag(entry["id"], name=name, serialized_value=value, description=description)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Tag not updated", str(exc))
            return
        self.tag_changes.append({"action": "edit", "before": entry, "after": updated})
        self._reload()

    def _deprecate_user_tag(self):
        from PySide6.QtWidgets import QMessageBox
        entry = self._selected_user_entry()
        if not entry:
            return
        try:
            updated = self.library.deprecate_user_tag(entry["id"])
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Tag not deprecated", str(exc))
            return
        self.tag_changes.append({"action": "deprecate", "before": entry, "after": updated})
        self._reload()
