from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.training_source_exporter import export_training_source_bundle
from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.datasets import DatasetService
from TrainingDatasetStudio.studio.importer import BundleImporter
from TrainingDatasetStudio.studio.store import StudioStore


ROOT = Path(__file__).resolve().parents[1]


class TrainingHeadsHandoffTests(unittest.TestCase):
    def test_all_heads_and_clothing_tasks_export_import_validate_and_package(self):
        with tempfile.TemporaryDirectory(prefix="all_heads_handoff_") as temp:
            root = Path(temp)
            source_path = root / "source.png"
            Image.new("RGB", (900, 900), "teal").save(source_path)
            source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            database = Database(root / "newasset.sqlite3")
            database.initialize()
            source_id, _ = database.upsert_source_image({
                "path": str(source_path.resolve()), "sha256": source_hash, "width": 900, "height": 900,
                "file_size": source_path.stat().st_size, "modified_ns": source_path.stat().st_mtime_ns,
            })
            source_path_b = root / "source_validation.png"
            Image.new("RGB", (900, 900), "navy").save(source_path_b)
            source_hash_b = hashlib.sha256(source_path_b.read_bytes()).hexdigest()
            source_id_b, _ = database.upsert_source_image({
                "path": str(source_path_b.resolve()), "sha256": source_hash_b,
                "width": 900, "height": 900, "file_size": source_path_b.stat().st_size,
                "modified_ns": source_path_b.stat().st_mtime_ns,
            })

            self._professional_head(database, source_id, 3, "boobs", {
                "category": "body_images", "main_tag": "boobs", "subtags": ["cum"],
                "body_images_cnn_target": "bodypart_cum",
            }, ["body_images"])
            self._professional_head(database, source_id, 20, "fullbody_clothed", {
                "category": "fullbody", "main_tag": "clothed", "state_spec": "clothed",
                "fullbody_output_category": "fullbody", "fullbody_cnn_target": "bra",
            }, ["fullbody"])
            self._professional_head(database, source_id, 2, "portrait_frame", {
                "category": "body_images", "main_tag": "portrait", "arousal_cnn_target": "aroused",
                "corruption_classifier_target": "conservative",
            }, ["portrait", "arousal", "corruption"])
            self._professional_head(database, source_id, 0, "person", {
                "category": "others", "corruption_classifier_target": "slut",
            }, ["corruption"])
            self._professional_head(database, source_id_b, 3, "boobs", {
                "category": "body_images", "main_tag": "boobs", "subtags": ["cum"],
                "body_images_cnn_target": "bodypart_cum",
            }, ["body_images"])
            self._professional_head(database, source_id_b, 20, "fullbody_clothed", {
                "category": "fullbody", "main_tag": "clothed", "state_spec": "clothed",
                "fullbody_output_category": "fullbody", "fullbody_cnn_target": "panty",
            }, ["fullbody"])
            self._professional_head(database, source_id_b, 2, "portrait_frame", {
                "category": "body_images", "main_tag": "portrait", "arousal_cnn_target": "aroused",
                "corruption_classifier_target": "conservative",
            }, ["portrait", "arousal", "corruption"])
            self._professional_head(database, source_id_b, 0, "person", {
                "category": "others", "corruption_classifier_target": "slut",
            }, ["corruption"])

            normal_clothing = database.record_yolo_detection(
                source_id, model_id="fixture", model_digest="source-model", class_id=7,
                class_name="boobs_cover_item", confidence=.9, bbox_xyxy=[250, 150, 650, 550])
            database.save_normal_crop_choice(
                normal_clothing["proposal_id"], "clothing", main_tag="heels",
                clothing_broad_family="footwear", clothing_cover_area="accessory_footwear")
            database.confirm_normal_crop_classification(normal_clothing["proposal_id"])

            detection = database.record_yolo_detection(
                source_id, model_id="fixture", model_digest="source-model", class_id=1,
                class_name="face", confidence=.9, bbox_xyxy=[250, 150, 650, 550])
            database.save_correction(
                detection["proposal_id"], {
                    "category": "body_images", "main_tag": "face", "validity_state": "valid",
                    "bbox_xyxy": [260, 160, 640, 540], "yolo_annotation_registry_id": "newassetapp_yolo_detector_v1",
                    "yolo_annotation_class_id": 1, "yolo_annotation_class_name": "face",
                }, decision_type="corrected", final_state="confirmed", target_yolo_training_eligible=True)

            bundle = export_training_source_bundle(database, root / "handoff")
            from app.core.training_source_exporter import _canonical_sha256
            import json
            manifest = json.loads(Path(bundle["manifest"]).read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 4)
            self.assertEqual(manifest["bundle_sha256"], _canonical_sha256(
                {key: value for key, value in manifest.items() if key != "bundle_sha256"}))
            self.assertEqual(len(manifest["records"]), 17,
                             [(row["task"], row["labels"]["class_label"],
                               row["labels"]["structured"].get("output_group"))
                              for row in manifest["records"]] +
                             [(row["task_head"], row["class_label"])
                              for row in database.current_training_examples()] +
                             [("excluded", row.get("task"), row.get("reason"), row.get("labels"))
                              for row in manifest["excluded_records"]])
            self.assertEqual(len(manifest["excluded_records"]), 0)
            shared_examples = [row for row in database.current_training_examples()
                               if row.get("task_head") in {"portrait", "arousal", "corruption"}]
            frame_ids = {row["detection_id"] for row in shared_examples
                         if row.get("task_head") == "portrait"}
            same_frame_ids = [detection_id for detection_id in frame_ids
                              if {row["task_head"] for row in shared_examples
                                  if row["detection_id"] == detection_id}
                              >= {"portrait", "arousal", "corruption"}]
            self.assertEqual(len(same_frame_ids), 2)
            for detection_id in same_frame_ids:
                self.assertEqual({row["task_head"] for row in shared_examples
                                  if row["detection_id"] == detection_id},
                                 {"portrait", "arousal", "corruption"})
            for head in ("body_images", "fullbody", "portrait", "arousal", "corruption"):
                record = next(row for row in manifest["records"]
                              if row["labels"]["structured"].get("output_group") == head)
                self.assertTrue(record["review"]["human_confirmed"])
                self.assertTrue(record["review"]["eligible"])
            self.assertEqual(len(next(row for row in manifest["records"]
                                      if row["labels"]["class_label"] == "face")["provenance"]["correction_events"]), 1)

            config = StudioConfig(root=root / "studio")
            config.ensure_directories()
            shutil.copytree(ROOT / "TrainingDatasetStudio" / "contracts", config.contract_dir,
                            dirs_exist_ok=True)
            store = StudioStore(config.database_path)
            store.initialize()
            imported = BundleImporter(config, store).import_bundle(bundle["directory"])
            self.assertEqual((imported["accepted"], imported["warning"], imported["quarantined"]),
                             (17, 0, 0))
            shared_task_names = ("body_images_classification", "fullbody_state_classification",
                                 "portrait_classification", "arousal_classification",
                                 "corruption_classification")
            shared_records = [row for task in shared_task_names for row in store.list_records(task=task)
                              if row["status"] == "accepted"]
            self.assertEqual(len({row["training_bundle_id"] for row in shared_records}), 1)
            shared_bundle = next(row for row in store.list_training_bundles()
                                 if row["task"] == "shared_cnn")
            self.assertEqual(shared_bundle["task"], "shared_cnn")
            self.assertEqual(shared_bundle["record_count"], 12)
            self.assertEqual(shared_bundle["max_bytes"], 5_000_000_000)
            datasets = DatasetService(store, config.output_dir)
            tasks = {
                "yolo_detection": "yolo",
                "body_images_classification": "cnn",
                "fullbody_state_classification": "cnn",
                "portrait_classification": "cnn",
                "arousal_classification": "cnn",
                "corruption_classification": "cnn",
                "broad_clothing_classification": "cnn",
                "detailed_clothing_classification": "cnn",
            }
            shared_versions = {}
            for task, package_type in tasks.items():
                record = next(row for row in store.list_records(task=task) if row["status"] == "accepted")
                dataset_id = datasets.create_dataset(
                    f"dataset {task}", task, record["registry_id"], record["registry_version"],
                    training_bundle_id=record["training_bundle_id"])
                records_for_task = [item for item in store.list_records(task=task) if item["status"] == "accepted"]
                split_overrides = ({int(item["id"]): ("train" if item["source_sha256"] == source_hash else "validation")
                                    for item in records_for_task}
                                   if task in {"body_images_classification", "fullbody_state_classification",
                                               "portrait_classification", "arousal_classification",
                                               "corruption_classification"} else None)
                version_id = datasets.create_version(dataset_id, split_overrides=split_overrides)
                datasets.finalize(version_id)
                if split_overrides is not None:
                    shared_versions[{"body_images_classification": "body_images",
                                     "fullbody_state_classification": "fullbody",
                                     "portrait_classification": "portrait",
                                     "arousal_classification": "arousal",
                                     "corruption_classification": "corruption"}[task]] = version_id
                target = config.output_dir / f"package_{task}"
                package = datasets.export_colab(version_id, target)
                self.assertEqual(package["package_type"], package_type)
                self.assertTrue((target / "hash_manifest.json").is_file())
                if task == "yolo_detection":
                    label_files = list((target / "dataset" / "labels").rglob("*.txt"))
                    self.assertEqual(len(label_files), 2)
                    self.assertEqual(sum(len(path.read_text(encoding="utf-8").splitlines())
                                         for path in label_files), 3)
            shared_package_dir = config.output_dir / "shared_cnn_package"
            shared_package = datasets.export_shared_cnn_colab(shared_versions, shared_package_dir)
            self.assertEqual(shared_package["heads"], ["body_images", "fullbody", "portrait", "arousal", "corruption"])
            self.assertEqual(shared_package["records"], 12)
            self.assertTrue((shared_package_dir / "train_shared_cnn.py").is_file())
            from TrainingDatasetStudio.studio.shared_training import validate_shared_dataset
            validation = validate_shared_dataset(shared_package_dir,
                                                 __import__("json").loads((shared_package_dir / "registry.json").read_text()))
            self.assertTrue(validation["valid"])
            from TrainingDatasetStudio.studio.shared_train import run_shared_training
            self.assertEqual(run_shared_training(shared_package_dir, root / "dry_run", root / "cancel.request",
                                                 {"epochs": 1}, dry_run=True), 0)
            from TrainingDatasetStudio.studio.training import TrainingManager, cpu_compatibility
            compatibility = cpu_compatibility(
                "body_images_classification", "unified_body_images_fullbody_cnn", None,
                shared_package_dir, root / "cpu_compatibility", require_dataset=True)
            self.assertTrue(compatibility["compatible"], compatibility["reasons"])
            training = TrainingManager(store, root / "studio_runs")
            run_key = training.start(shared_versions["body_images"], shared_package_dir,
                                     "unified_body_images_fullbody_cnn", None,
                                     {"epochs": 1, "batch_size": 2}, confirmed=False,
                                     dry_run=True)
            training._thread.join(timeout=120)
            self.assertFalse(training._thread.is_alive())
            with store.connect() as connection:
                run = connection.execute("SELECT status,metadata_json,log_path FROM training_runs WHERE run_key=?",
                                         (run_key,)).fetchone()
            self.assertEqual(run["status"], "completed")
            self.assertTrue(__import__("json").loads(run["metadata_json"])["dry_run"])
            self.assertIn("dry_run_ok", Path(run["log_path"]).read_text(encoding="utf-8"))

    @staticmethod
    def _professional_head(database, source_id, class_id, class_name, fields, heads):
        bbox = [240, 160, 660, 740] if class_name == "person" else [200, 120, 700, 780]
        detection = database.record_yolo_detection(
            source_id, model_id="fixture", model_digest="source-model", class_id=class_id,
            class_name=class_name, confidence=.9, bbox_xyxy=bbox)
        payload = {"validity_state": "valid", "bbox_xyxy": bbox, **fields}
        target_yolo = heads == ["body_images"]
        if target_yolo:
            payload.update({"yolo_annotation_registry_id": "newassetapp_yolo_detector_v1",
                            "yolo_annotation_class_id": class_id,
                            "yolo_annotation_class_name": class_name})
        database.save_correction(detection["proposal_id"], payload,
                                 decision_type="corrected", final_state="confirmed",
                                 shared_cnn_training_tasks=heads,
                                 target_yolo_training_eligible=target_yolo)


if __name__ == "__main__":
    unittest.main()
