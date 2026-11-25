from __future__ import annotations

import threading
import logging

from PySide6.QtCore import QThread, Signal

from app.core.database import Database
from app.core.output_exporter import export_normal_output

logger = logging.getLogger(__name__)


class OutputExportWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, database_path, plan):
        super().__init__()
        self.database_path = database_path
        self.plan = plan
        self.cancel_event = threading.Event()

    def cancel(self):
        """Stop after the current crop; keep every crop already written."""
        self.cancel_event.set()

    def run(self):
        try:
            logger.info("Starting normal export items=%d", len(self.plan.get("items", [])))
            database = Database(self.database_path)
            result = export_normal_output(
                database, self.plan,
                progress_callback=lambda current, total, proposal_id, status:
                    self.progress.emit(current, total, f"Crop {current}/{total}: {status}"),
                cancel_event=self.cancel_event,
            )
            logger.info("Normal export finished written=%d failed=%d skipped=%d cancelled=%s",
                        result.get("written_count", 0), result.get("failure_count", 0),
                        result.get("skipped_count", 0), result.get("cancelled", False))
            self.completed.emit(result)
        except Exception as error:
            logger.exception("Normal export worker crashed")
            self.failed.emit(f"{type(error).__name__}: {error}")
