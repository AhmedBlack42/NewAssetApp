from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from app.core.database import Database
from app.core.dataset_exporter import (export_cnn_dataset, export_shared_cnn_head_dataset,
                                      export_unified_cnn_dataset, export_yolo_dataset)
from app.core.training_source_exporter import export_training_source_bundle


class DatasetExportWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, database_path, output_dir, task, source_roots=None, new_split=False,
                 seed=42, proportions=(0.8, 0.1, 0.1)):
        super().__init__()
        self.database_path = database_path
        self.output_dir = output_dir
        self.task = task
        self.source_roots = source_roots
        self.new_split = new_split
        self.seed = seed
        self.proportions = proportions

    def run(self):
        try:
            database = Database(self.database_path)
            if self.task == "studio_bundle":
                result = export_training_source_bundle(database, self.output_dir)
            elif self.task == "yolo":
                result = export_yolo_dataset(database, self.output_dir, source_roots=self.source_roots,
                                             new_split=self.new_split, seed=self.seed,
                                             proportions=self.proportions)
            elif self.task == "unified_cnn":
                result = export_unified_cnn_dataset(database, self.output_dir, source_roots=self.source_roots,
                                                    new_split=self.new_split, seed=self.seed,
                                                    proportions=self.proportions)
            elif self.task in {"body_images", "fullbody", "portrait", "arousal", "corruption"}:
                result = export_shared_cnn_head_dataset(database, self.task, self.output_dir,
                                                        source_roots=self.source_roots,
                                                        new_split=self.new_split, seed=self.seed,
                                                        proportions=self.proportions)
            elif self.task in {"asset_cnn", "clothing_cnn", "broad_clothing"}:
                result = export_cnn_dataset(database, self.task, self.output_dir,
                                            source_roots=self.source_roots, new_split=self.new_split,
                                            seed=self.seed, proportions=self.proportions)
            else:
                raise ValueError(f"Unsupported dataset export task: {self.task}")
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")
