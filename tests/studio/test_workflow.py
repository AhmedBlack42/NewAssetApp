from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.datasets import DatasetService
from TrainingDatasetStudio.studio.importer import BundleImporter
from TrainingDatasetStudio.studio.store import StudioStore
from TrainingDatasetStudio.studio.training import TrainingManager


ROOT = Path(__file__).resolve().parents[2]
BUNDLES = ROOT / "training_source" / "bundles"
V2 = BUNDLES / "newassetapp_20261109T014752986366Z_12b7c0dbf0"
V3_ORIGINAL = BUNDLES / "newassetapp_20261109T023555894626Z_a0b1c3669b"
V3_CORRECTED = BUNDLES / "newassetapp_20261109T210802680699Z_b6d7cece21"


class StudioWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tds_workflow_")
        self.root = Path(self.temp.name)
        self.config = StudioConfig(root=self.root / "studio")
        self.config.ensure_directories()
        shutil.copytree(ROOT / "TrainingDatasetStudio" / "contracts", self.config.contract_dir,
                        dirs_exist_ok=True)
        self.store = StudioStore(self.config.database_path)
        self.store.initialize()
        self.importer = BundleImporter(self.config, self.store)

    def tearDown(self):
        self.temp.cleanup()

    def test_imports_preserve_quarantines_and_yolo_region_mapping(self):
        v2 = self.importer.import_bundle(V2)
        original = self.importer.import_bundle(V3_ORIGINAL)
        corrected = self.importer.import_bundle(V3_CORRECTED)
        self.assertFalse(v2["duplicate"])
        self.assertFalse(original["duplicate"])
        self.assertFalse(corrected["duplicate"])
        self.assertEqual(self.importer.import_bundle(V3_CORRECTED)["duplicate"], True)

        rows = self.store.list_records()
        v2_face = next(r for r in rows if r["bundle_id"] == self._bundle_db_id(V2)
                       and r["external_id"] == "training_example:5")
        self.assertEqual(v2_face["task"], "asset_classification")
        self.assertEqual(v2_face["status"], "quarantined")
        self.assertEqual(v2_face["reason"], "label_not_in_current_model_registry")

        old_excluded = [r for r in rows if r["bundle_id"] == self._bundle_db_id(V3_ORIGINAL)
                        and r["status"] == "quarantined"]
        self.assertEqual(len(old_excluded), 2)
        corrected_rows = [r for r in rows if r["bundle_id"] == self._bundle_db_id(V3_CORRECTED)
                          and r["class_label"] in {"face", "pussy"}]
        self.assertEqual({r["class_label"] for r in corrected_rows}, {"face", "pussy"})
        for row in corrected_rows:
            self.assertEqual(row["task"], "yolo_detection")
            self.assertEqual(row["status"], "accepted")
            self.assertEqual(row["registry_id"], "newassetapp_yolo_detector_v1")
            self.assertIsNotNone(row["target_class_id"])
            self.assertTrue(row["human_confirmed"])
            self.assertTrue(row["training_eligible"])
            self.assertTrue(Path(row["media_path"]).is_file())
            original = row["original"]
            self.assertEqual(original["provenance"]["task_mapping"]["mapping"],
                             "human_confirmed_body_region_identity_to_yolo_detection")
            self.assertEqual(original["source"]["sha256"], row["source_sha256"])

    def _bundle_db_id(self, path):
        digest = self.importer.inspect(path)["manifest"]["bundle_sha256"]
        with self.store.connect() as db:
            return db.execute("SELECT id FROM bundles WHERE bundle_sha256=?", (digest,)).fetchone()[0]

    def test_corrections_versions_yolo_and_cnn_packages_and_cpu_dry_run(self):
        self.importer.import_bundle(V3_CORRECTED)
        rows = self.store.list_records(task="yolo_detection")
        row = next(r for r in rows if r["class_label"] == "face")
        annotation = dict(row["annotation"])
        annotation["bbox_xyxy"] = list(annotation["bbox_xyxy"])
        annotation["bbox_xyxy"][0] += 1
        self.store.save_annotation(row["id"], annotation, confirm=True, note="workflow test correction")
        reopened = self.store.get_record(row["id"])
        self.assertEqual(reopened["annotation"]["bbox_xyxy"], annotation["bbox_xyxy"])
        self.assertEqual(len(self.store.annotation_history(row["id"])), 1)

        datasets = DatasetService(self.store, self.config.output_dir)
        yolo_dataset = datasets.create_dataset("reviewed yolo", "yolo_detection",
                                               row["registry_id"], row["registry_version"],
                                               training_bundle_id=row["training_bundle_id"])
        version = datasets.create_version(yolo_dataset, seed=34)
        rows_version = self.store.version_rows(version)
        included = [r for r in rows_version if r["included"]]
        self.assertGreater(len(included), 0, [(r["class_label"], r["status"], r["reason"],
                                              r["registry_id"], r["registry_version"])
                                             for r in rows])
        self.assertGreater(sum(item["split"] == "train" for item in included), 0)
        self.assertGreater(sum(item["split"] == "validation" for item in included), 0)
        split_by_source = {}
        for item in included:
            source = item["source_sha256"]
            split_by_source.setdefault(source, set()).add(item["split"])
        self.assertTrue(all(len(splits) == 1 for splits in split_by_source.values()))
        counts = datasets.finalize(version)
        self.assertEqual(counts["record_count"], len(included))
        package_path = self.config.output_dir / "yolo_colab"
        package = datasets.export_colab(version, package_path)
        self.assertEqual(package["package_type"], "yolo")
        self.assertTrue((package_path / "dataset.yaml").is_file())
        self.assertTrue((package_path / "hash_manifest.json").is_file())
        self.assertTrue((package_path / "metadata.json").is_file())

        checkpoint = ROOT / "models" / "yolo" / "best.pt"
        manager = TrainingManager(self.store, self.config.output_dir, sys.executable)
        run_key = manager.start(version, package_path, "newassetapp_yolo_detector_v1",
                                checkpoint, {"epochs": 1, "batch_size": 1, "image_size": 64,
                                             "workers": 0}, confirmed=False, dry_run=True)
        manager._thread.join(timeout=90)
        self.assertFalse(manager._thread.is_alive(), "CPU dry-run subprocess did not finish")
        with self.store.connect() as db:
            run = db.execute("SELECT * FROM training_runs WHERE run_key=?", (run_key,)).fetchone()
        self.assertEqual(run["status"], "completed", Path(run["log_path"]).read_text(encoding="utf-8"))
        self.assertIn('"status": "dry_run_ok"', Path(run["log_path"]).read_text(encoding="utf-8"))

        clothing = [r for r in self.store.list_records(task="broad_clothing_classification")
                    if r["status"] == "accepted" and r["human_confirmed"] and r["training_eligible"]]
        if clothing:
            cnn_dataset = datasets.create_dataset("reviewed clothing", "broad_clothing_classification",
                                                 clothing[0]["registry_id"], clothing[0]["registry_version"],
                                                 training_bundle_id=clothing[0]["training_bundle_id"])
            cnn_version = datasets.create_version(cnn_dataset, seed=34)
            datasets.finalize(cnn_version)
            cnn_path = self.config.output_dir / "cnn_colab"
            cnn_package = datasets.export_colab(cnn_version, cnn_path)
            self.assertEqual(cnn_package["package_type"], "cnn")
            self.assertTrue((cnn_path / "dataset" / "images" / "train").is_dir())
            self.assertTrue((cnn_path / "hash_manifest.json").is_file())
            self.assertTrue(any((cnn_path / "dataset" / "images" / "validation").rglob("*.jpg")))
            cnn_manager = TrainingManager(self.store, self.config.output_dir, sys.executable)
            cnn_run = cnn_manager.start(
                cnn_version, cnn_path, "clothing_classifier",
                ROOT / "models" / "clothing_classifier" / "clothing_classifier.pth",
                {"epochs": 1, "batch_size": 1, "image_size": 224, "workers": 0},
                confirmed=False, dry_run=True)
            cnn_manager._thread.join(timeout=90)
            self.assertFalse(cnn_manager._thread.is_alive(), "CNN dry-run subprocess did not finish")
            with self.store.connect() as db:
                cnn_run_row = db.execute("SELECT * FROM training_runs WHERE run_key=?", (cnn_run,)).fetchone()
            self.assertEqual(cnn_run_row["status"], "completed",
                             Path(cnn_run_row["log_path"]).read_text(encoding="utf-8"))

    def test_confirmed_records_roll_into_bounded_task_specific_bundles(self):
        self.store = StudioStore(self.config.database_path)
        self.store.initialize()
        self.importer = BundleImporter(self.config, self.store)
        self.importer.import_bundle(V3_CORRECTED)
        bundles = [b for b in self.store.list_training_bundles()
                   if b["task"] == "yolo_detection"]
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0]["record_count"], 5)
        self.assertEqual(bundles[0]["state"], "open")
        self.assertEqual(bundles[0]["max_bytes"], 5_000_000_000)

        row = next(r for r in self.store.list_records(task="yolo_detection")
                   if r["class_label"] == "face")
        original_bundle = row["training_bundle_id"]
        original_count = row["training_bundle_record_count"]
        annotation = dict(row["annotation"])
        self.store.save_annotation(row["id"], annotation, confirm=True, note="reconfirm stays in same bundle")
        reopened = self.store.get_record(row["id"])
        self.assertEqual(reopened["training_bundle_id"], original_bundle)
        with self.store.connect() as db:
            count = db.execute("SELECT record_count FROM training_bundles WHERE id=?",
                               (original_bundle,)).fetchone()[0]
        self.assertEqual(count, original_count)

    def test_cancel_requests_safe_cooperative_stop(self):
        manager = TrainingManager(self.store, self.config.output_dir, sys.executable)
        gate = threading.Event()
        manager._thread = threading.Thread(target=gate.wait, daemon=True)
        manager._thread.start()

        class RunningProcess:
            def __init__(self):
                self.terminated = False
            def poll(self):
                return None
            def terminate(self):
                self.terminated = True

        process = RunningProcess()
        manager._process = process
        manager._cancel_path = self.root / "cancel.request"
        self.assertTrue(manager.cancel())
        self.assertTrue(manager._cancel_path.is_file())
        self.assertFalse(process.terminated)
        gate.set(); manager._thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
