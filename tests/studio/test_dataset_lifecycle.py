from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from TrainingDatasetStudio.studio.datasets import DatasetError, DatasetService
from TrainingDatasetStudio.studio.store import StudioStore
from TrainingDatasetStudio.studio.training import TrainingManager
from TrainingDatasetStudio.studio.archive import inspect_colab_rar_readiness


class DatasetLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="studio_dataset_lifecycle_")
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root / "studio.sqlite3")
        self.store.initialize()
        self.datasets = DatasetService(self.store, self.root / "output")

    def tearDown(self):
        self.temp.cleanup()

    def _create_dataset_version(self, record_count: int = 1) -> tuple[int, Path]:
        registry = {"classes": [{"class_id": 0, "class_name": "top", "active": True}]}
        media_paths = []
        with self.store.connect() as db:
            bundle_id = db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES('bundle',4,'bundle-hash','fixture','{}')"""
            ).lastrowid
            db.execute(
                """INSERT INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json)
                   VALUES(?,'registry','1','registry-hash','registry.json',?)""",
                (bundle_id, json.dumps(registry)),
            )
            for index in range(record_count):
                media_path = self.root / f"source-{index}.png"
                Image.new("RGB", (10, 10), (index % 256, (index // 256) % 256, 150)).save(media_path)
                media_paths.append(media_path)
                media_digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
                original = {
                    "source": {"sha256": media_digest, "width": 10, "height": 10},
                    "media": {"sha256": media_digest, "role": "source_image"},
                }
                annotation = {"bbox_xyxy": [1, 1, 9, 9], "class_label": "top",
                              "target_class_id": 0}
                db.execute(
                    """INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,
                       registry_version,class_label,target_class_id,status,source_sha256,source_width,
                       source_height,media_path,original_json,annotation_json,human_confirmed,
                       training_eligible)
                       VALUES(?,?,'broad_clothing_classification','model','registry','1',
                              'top',0,'accepted',?,10,10,?,?,?,1,1)""",
                    (bundle_id, f"record-{index}", media_digest, str(media_path),
                     json.dumps(original), json.dumps(annotation)),
                )
        dataset_id = self.datasets.create_dataset(
            "fixture dataset", "broad_clothing_classification", "registry", "1",
            model_id="model")
        return self.datasets.create_version(dataset_id), media_paths[0]

    def test_finalization_rechecks_media_hash_and_seals_version(self):
        version_id, media_path = self._create_dataset_version()
        media_path.write_bytes(media_path.read_bytes() + b"changed")
        readiness = self.datasets.version_readiness_report(version_id)
        self.assertEqual(len(readiness["invalid_media_record_ids"]), 1)
        self.assertIn("missing_or_invalid_media:1", readiness["blockers"])

        with self.assertRaisesRegex(DatasetError, "media hash verification failed"):
            self.datasets.finalize(version_id)
        with self.store.connect() as db:
            self.assertEqual(db.execute(
                "SELECT finalized FROM dataset_versions WHERE id=?", (version_id,)
            ).fetchone()["finalized"], 0)

        media_path.write_bytes(media_path.read_bytes()[:-7])
        result = self.datasets.finalize(version_id)
        self.assertTrue(result["finalized"])
        readiness = self.datasets.version_readiness_report(version_id)
        self.assertEqual(readiness["state"], "blocked_from_training")
        self.assertIn("source_group_minimum_not_met:1/100", readiness["blockers"])
        with self.assertRaisesRegex(DatasetError, "immutable"):
            self.datasets.set_split(version_id, self.store.version_rows(version_id)[0]["record_id"],
                                    "validation")

    def test_yolo_registry_mismatch_blocks_finalization_and_training(self):
        registry_id = "newassetapp_yolo_detector_v1"
        model_id = registry_id
        with self.store.connect() as db:
            bundle_id = db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES('legacy-yolo',4,'legacy-yolo-hash','fixture','{}')"""
            ).lastrowid
            db.execute(
                """INSERT INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json)
                   VALUES(?,?,'1','legacy-registry-hash','registry.json',?)""",
                (bundle_id, registry_id, json.dumps({
                    "classes": [{"id": 0, "name": "legacy_face"}],
                })),
            )
        dataset_id = self.datasets.create_dataset(
            "legacy yolo", "yolo_detection", registry_id, "1", model_id=model_id)
        version_id = self.datasets.create_version(dataset_id)

        with self.assertRaisesRegex(DatasetError, "approved Studio YOLO registry"):
            self.datasets.finalize(version_id)
        with self.store.connect() as db:
            db.execute("UPDATE dataset_versions SET finalized=1 WHERE id=?", (version_id,))
        manager = TrainingManager(self.store, self.root / "output")
        with self.assertRaisesRegex(ValueError, "approved Studio YOLO registry"):
            manager.start(version_id, self.root / "missing-package", model_id, None, {},
                          confirmed=False, dry_run=True)

    def test_authoritative_crop_is_exported_without_applying_source_box_again(self):
        source = self.root / "source.png"
        Image.new("RGB", (100, 100), "navy").save(source)
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        crop = self.root / "crop.png"
        Image.new("RGB", (20, 20), "orange").save(crop)
        crop_digest = hashlib.sha256(crop.read_bytes()).hexdigest()
        with self.store.connect() as db:
            bundle_id = db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES('crop-bundle',4,'crop-bundle-hash','fixture','{}')"""
            ).lastrowid
            db.execute(
                """INSERT INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json)
                   VALUES(?,'registry','1','registry-hash','registry.json',?)""",
                (bundle_id, json.dumps({"classes": [
                    {"class_id": 0, "class_name": "top", "active": True}]})),
            )
            original = {
                "source": {"sha256": source_digest, "width": 100, "height": 100},
                "media": {"sha256": crop_digest, "role": "authoritative_detection_crop",
                          "source_sha256": source_digest, "bbox_xyxy": [50, 50, 70, 70]},
            }
            annotation = {"bbox_xyxy": [50, 50, 70, 70], "class_label": "top",
                          "target_class_id": 0}
            db.execute(
                """INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,
                   registry_version,class_label,target_class_id,status,source_sha256,source_width,
                   source_height,media_path,original_json,annotation_json,human_confirmed,
                   training_eligible)
                   VALUES(?,'crop-record','broad_clothing_classification','model','registry','1',
                          'top',0,'accepted',?,100,100,?,?,?,1,1)""",
                (bundle_id, source_digest, str(crop), json.dumps(original),
                 json.dumps(annotation)),
            )
        dataset_id = self.datasets.create_dataset(
            "crop dataset", "broad_clothing_classification", "registry", "1",
            model_id="model")
        version_id = self.datasets.create_version(dataset_id)
        self.datasets.finalize(version_id)
        package = self.datasets.export_colab(version_id, self.root / "crop-package")
        output = next((Path(package["path"]) / "dataset" / "images" / "train" / "top").glob("*.jpg"))
        with Image.open(output) as exported:
            self.assertEqual(exported.size, (20, 20))

    def test_readiness_uses_nested_body_targets_and_isolates_model_identity(self):
        media_path = self.root / "readiness.bin"
        media_path.write_bytes(b"fixture")
        with self.store.connect() as db:
            bundle_id = db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES('readiness-bundle',4,'readiness-bundle-hash','fixture','{}')"""
            ).lastrowid
            cases = [
                ("positive", "model", "accepted", None, True, 1, "cum"),
                ("negative", "model", "accepted", None, True, 1, "negative"),
                ("pending", "model", "accepted", None, False, 0, "cum"),
                ("duplicate", "model", "warning", "conflicting_task_annotation_identity",
                 True, 1, "cum"),
                ("other-model", "other", "accepted", None, True, 1, "cum"),
            ]
            for name, model, status, reason, confirmed, eligible, outcome in cases:
                target_mask = {
                    "cum": {"target": False if outcome == "negative" else True,
                            "evaluated": True},
                    "accessory": {"target": None, "evaluated": False},
                }
                source_digest = hashlib.sha256(name.encode()).hexdigest()
                annotation = {
                    "class_label": "bodypart_cum",
                    "bbox_xyxy": [1, 1, 9, 9],
                    "body_images_target_mask": target_mask,
                    "labels": {"structured": {"output_group": "body_images"}},
                }
                db.execute(
                    """INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,
                       registry_version,class_label,status,reason,source_sha256,source_width,
                       source_height,media_path,original_json,annotation_json,human_confirmed,
                       training_eligible)
                       VALUES(?,?,?,?,?,'v2','bodypart_cum',?,?,?,10,10,?,?,?, ?,?)""",
                    (bundle_id, name, "body_images_classification", model, "shared_registry",
                     status, reason, source_digest, str(media_path), "{}", json.dumps(annotation),
                     int(confirmed), eligible),
                )
        dataset_id = self.datasets.create_dataset(
            "shared readiness", "body_images_classification", "shared_registry", "v2",
            model_id="model")

        report = self.datasets.readiness_report(dataset_id=dataset_id)
        outcomes = {row["outcome"]: row for row in report["body_images"]}
        self.assertEqual(outcomes["cum_positive"]["eligible_crop_records"], 1)
        self.assertEqual(outcomes["cum_positive"]["pending_unreviewed"], 1)
        self.assertEqual(outcomes["cum_positive"]["duplicates_excluded"], 1)
        self.assertEqual(outcomes["cum_negative"]["eligible_crop_records"], 1)

    def test_split_assignment_keeps_all_crops_from_one_source_together(self):
        source_by_record = {1: "source-a", 2: "source-a", 3: "source-b",
                            4: "source-c", 5: "source-d"}
        ratios = {"train": .7, "validation": .15, "test": .15}
        splits = self.datasets._assign_splits(source_by_record, 42, ratios)
        self.assertEqual(splits[1], splits[2])
        self.datasets._assert_source_grouping(
            set(source_by_record), source_by_record, splits)
        with self.assertRaisesRegex(DatasetError, "would leak"):
            self.datasets._assert_source_grouping(
                set(source_by_record), source_by_record,
                {**splits, 2: "test" if splits[1] != "test" else "train"})

    def test_explicit_negative_body_images_mask_can_be_finalized(self):
        media_path = self.root / "negative.png"
        Image.new("RGB", (10, 10), "teal").save(media_path)
        media_digest = hashlib.sha256(media_path.read_bytes()).hexdigest()
        with self.store.connect() as db:
            bundle_id = db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES('negative-bundle',4,'negative-bundle-hash','fixture','{}')"""
            ).lastrowid
            db.execute(
                """INSERT INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json)
                   VALUES(?,'shared_registry','v2','shared-hash','registry.json',?)""",
                (bundle_id, json.dumps({"output_groups": {"body_images": {"classes": []}}})),
            )
            original = {
                "source": {"sha256": media_digest, "width": 10, "height": 10},
                "media": {"sha256": media_digest, "role": "source_image"},
            }
            annotation = {
                "bbox_xyxy": [1, 1, 9, 9], "class_label": "body_images_none",
                "target_class_id": None,
                "body_images_target_mask": {
                    "cum": {"target": False, "evaluated": True},
                    "accessory": {"target": False, "evaluated": True},
                },
                "labels": {"structured": {"output_group": "body_images"}},
            }
            db.execute(
                """INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,
                   registry_version,class_label,status,source_sha256,source_width,source_height,
                   media_path,original_json,annotation_json,human_confirmed,training_eligible)
                   VALUES(?,'negative','body_images_classification','shared','shared_registry','v2',
                          'body_images_none','accepted',?,10,10,?,?,?,1,1)""",
                (bundle_id, media_digest, str(media_path), json.dumps(original),
                 json.dumps(annotation)),
            )
        dataset_id = self.datasets.create_dataset(
            "negative body labels", "body_images_classification", "shared_registry", "v2",
            model_id="shared")
        version_id = self.datasets.create_version(dataset_id)

        self.assertTrue(self.datasets.finalize(version_id)["finalized"])

    def test_training_gate_requires_exact_version_and_intact_package(self):
        version_id, _ = self._create_dataset_version(record_count=100)
        self.datasets.finalize(version_id)
        readiness = self.datasets.version_readiness_report(version_id)
        self.assertTrue(readiness["ready_for_training"], readiness["blockers"])
        self.assertEqual(readiness["split_source_groups"],
                         {"train": 70, "validation": 15, "test": 15})
        with self.store.connect() as db:
            dataset_id = db.execute(
                "SELECT dataset_id FROM dataset_versions WHERE id=?", (version_id,)
            ).fetchone()["dataset_id"]
        second_version_id = self.datasets.create_version(dataset_id, seed=7)
        self.datasets.finalize(second_version_id)
        package_root = self.root / "training-package"
        self.datasets.export_colab(version_id, package_root)
        manager = TrainingManager(self.store, self.root / "runs")

        with self.assertRaisesRegex(ValueError, "exact finalized dataset version"):
            manager.start(second_version_id, package_root, "model", None, {},
                          confirmed=True, dry_run=True)
        image_path = next((package_root / "dataset" / "images").rglob("*.jpg"))
        image_path.write_bytes(image_path.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValueError, "file hashes"):
            manager.start(version_id, package_root, "model", None, {},
                          confirmed=True, dry_run=True)

    def test_training_gate_accepts_provenance_bound_package_without_running_trainer(self):
        version_id, _ = self._create_dataset_version(record_count=100)
        self.datasets.finalize(version_id)
        readiness = self.datasets.version_readiness_report(version_id)
        self.assertTrue(readiness["ready_for_training"], readiness["blockers"])
        package_root = self.root / "authorized-package"
        self.datasets.export_colab(version_id, package_root)
        manager = TrainingManager(self.store, self.root / "runs")
        with patch("TrainingDatasetStudio.studio.training.cpu_compatibility",
                   return_value={"compatible": True}), patch.object(manager, "_run"):
            run_key = manager.start(version_id, package_root, "model", None, {},
                                     confirmed=False, dry_run=True)
            manager._thread.join(timeout=5)

        self.assertFalse(manager._thread.is_alive())
        with self.store.connect() as db:
            run = db.execute(
                "SELECT version_id,model_id,status FROM training_runs WHERE run_key=?",
                (run_key,),
            ).fetchone()
        self.assertEqual((run["version_id"], run["model_id"]), (version_id, "model"))
        self.assertEqual(run["status"], "queued")

    def test_training_gate_blocks_finalized_package_below_minimum_groups(self):
        version_id, _ = self._create_dataset_version()
        self.datasets.finalize(version_id)
        package_root = self.root / "underfilled-package"
        self.datasets.export_colab(version_id, package_root)
        manager = TrainingManager(self.store, self.root / "runs")
        with self.assertRaisesRegex(ValueError, "source-group coverage"):
            manager.start(version_id, package_root, "model", None, {},
                          confirmed=False, dry_run=True)
        with self.store.connect() as db:
            count = db.execute("SELECT COUNT(*) FROM training_runs").fetchone()[0]
        self.assertEqual(count, 0)

    def test_rar_readiness_does_not_call_small_package_ready(self):
        package_root = self.root / "small-package"
        package_root.mkdir()
        (package_root / "data.bin").write_bytes(b"fixture")
        with patch("TrainingDatasetStudio.studio.archive.find_rar_writer",
                   return_value="existing-rar-writer.exe"):
            readiness = inspect_colab_rar_readiness(package_root)

        self.assertEqual(readiness["status"], "blocked")
        self.assertTrue(readiness["rar_available"])
        self.assertFalse(readiness["minimum_satisfied_by_uncompressed_size"])
        self.assertFalse(readiness["archive_size_verified"])


if __name__ == "__main__":
    unittest.main()
