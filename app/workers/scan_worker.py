from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.core.database import Database
from app.core.scanner import scan_folder


class ScanWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, database_path, folder, *, recursive=True, extensions=(), force_full=False):
        super().__init__()
        self.database_path = database_path
        self.folder = folder
        self.recursive = recursive
        self.extensions = tuple(extensions)
        self.force_full = force_full

    def run(self):
        try:
            result = scan_folder(
                self.folder,
                Database(self.database_path),
                recursive=self.recursive,
                extensions=self.extensions or None,
                force_full=self.force_full,
                progress=lambda current, total, path: self.progress.emit(current, total, path),
                cancelled=self.isInterruptionRequested,
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
