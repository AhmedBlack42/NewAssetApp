from __future__ import annotations

import time
from dataclasses import dataclass

from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton


@dataclass
class DialogResult:
    title: str
    text: str
    screenshot_path: str | None
    response: str


class DialogHelper:
    def __init__(self, app: QApplication, timeout_ms: int = 3000):
        self.app = app
        self.timeout_ms = timeout_ms

    def wait_for_modal(self) -> QDialog | None:
        deadline = time.monotonic() + self.timeout_ms / 1000
        while time.monotonic() < deadline:
            self.app.processEvents()
            for widget in self.app.topLevelWidgets():
                if isinstance(widget, QDialog) and widget.isVisible():
                    return widget
            time.sleep(.02)
        return None

    def dismiss_expected(self, title: str | None = None, text_contains: str | None = None,
                         response: str = "OK") -> DialogResult:
        dialog = self.wait_for_modal()
        if dialog is None:
            raise AssertionError("Expected modal dialog, but no dialog appeared.")
        dialog_title = dialog.windowTitle()
        dialog_text = " ".join(
            label.text() for label in dialog.findChildren(QLabel)
            if label.text()
        )
        if title and title.lower() not in dialog_title.lower():
            raise AssertionError(f"Unexpected dialog title: {dialog_title}")
        if text_contains and text_contains.lower() not in dialog_text.lower():
            raise AssertionError(f"Unexpected dialog text: {dialog_text}")
        button = dialog.findChild(QPushButton, "")
        candidates = [item for item in dialog.findChildren(QPushButton)
                      if item.text().lower() in {response.lower(), "ok", "close", "accept", "yes"}]
        if not candidates:
            raise AssertionError(f"Could not find response button {response!r}")
        candidates[0].click()
        self.app.processEvents()
        return DialogResult(dialog_title, dialog_text, None, candidates[0].text())
