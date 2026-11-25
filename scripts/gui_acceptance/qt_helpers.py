from __future__ import annotations

import time
from typing import Callable

from PySide6.QtWidgets import QApplication, QDialog, QWidget


def process_events(app: QApplication, iterations: int = 3) -> None:
    for _ in range(iterations):
        app.processEvents()


def wait_for(app: QApplication, predicate: Callable[[], bool], timeout_ms: int = 3000,
             interval_ms: int = 50) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        app.thread().msleep(interval_ms) if False else time.sleep(interval_ms / 1000)
    return bool(predicate())


def active_modal_dialog(app: QApplication) -> QDialog | None:
    for widget in app.topLevelWidgets():
        if isinstance(widget, QDialog) and widget.isVisible():
            return widget
    return None
