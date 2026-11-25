from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.core.database import Database
from app.core.inference import ImageAssetAnalyzer


class AnalysisWorker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, database_path, folder=None, clothing_checkpoint=None, clothing_class_map=None):
        super().__init__()
        self.database_path = database_path
        self.folder = folder
        self.clothing_checkpoint = clothing_checkpoint
        self.clothing_class_map = clothing_class_map

    def run(self):
        database = Database(self.database_path)
        try:
            pending = database.sources_needing_inference(self.folder)
            if not pending:
                self.completed.emit({"total": 0, "processed": 0, "errors": [],
                                     "status": "completed", "results": []})
                return
            analyzer = ImageAssetAnalyzer(cnn_path=self.clothing_checkpoint,
                                          class_map_path=self.clothing_class_map)
            results, errors = [], []
            total = len(pending)
            for index, row in enumerate(pending, 1):
                if self.isInterruptionRequested():
                    break
                database.set_source_inference_status(row["id"], row["content_sha256"], "processing")
                try:
                    results.append(analyzer.analyze(database, dict(row)))
                except Exception as exc:
                    database.set_source_inference_status(row["id"], row["content_sha256"], "failed")
                    errors.append({"source": row["path"], "error": f"{type(exc).__name__}: {exc}"})
                self.progress.emit(index, total, row["path"])
            self.completed.emit({"total": total, "processed": len(results), "errors": errors,
                                 "status": "cancelled" if self.isInterruptionRequested() else "completed",
                                 "results": results})
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
