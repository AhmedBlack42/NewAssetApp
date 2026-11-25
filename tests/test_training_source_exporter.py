from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.scanner import scan_folder
from app.core.training_source_exporter import export_training_source_bundle


class TrainingSourceExporterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.image_path = self.sources / "sample.png"
        Image.new("RGB", (100, 80), "teal").save(self.image_path)
        self.database = Database(self.root / "newassetapp.sqlite3")
        self.database.initialize()
        scan_folder(self.sources, self.database)
        with self.database.connect() as connection:
            self.source = dict(connection.execute("SELECT * FROM source_images LIMIT 1").fetchone())

    def tearDown(self):
        self.temp.cleanup()

    def test_explicit_empty_yolo_image_survives_v4_studio_and_colab(self):
        proposal_id = self.database.create_manual_proposal(self.source["id"])
        self.database.save_correction(
            proposal_id, {"category": "others", "no_objects": True, "validity_state": "valid"},
            decision_type="manual_annotation", final_state="confirmed", yolo_training_eligible=True)
        exported = export_training_source_bundle(self.database, self.root / "empty_handoff")
        manifest = json.loads(Path(exported["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["records"]), 1)
        record = manifest["records"][0]
        self.assertTrue(record["annotation"]["empty_image"])
        self.assertIsNone(record["annotation"]["target_bbox_xyxy"])
        self.assertIsNone(record["annotation"]["target_class_id"])

        from TrainingDatasetStudio.studio.config import StudioConfig
        from TrainingDatasetStudio.studio.datasets import DatasetService
        from TrainingDatasetStudio.studio.importer import BundleImporter
        from TrainingDatasetStudio.studio.store import StudioStore
        config = StudioConfig(root=self.root / "empty_studio")
        config.ensure_directories()
        shutil.copytree(Path(__file__).resolve().parents[1] / "TrainingDatasetStudio" / "contracts",
                        config.contract_dir, dirs_exist_ok=True)
        store = StudioStore(config.database_path)
        store.initialize()
        imported = BundleImporter(config, store).import_bundle(exported["directory"])
        self.assertEqual((imported["accepted"], imported["quarantined"]), (1, 0))
        studio_record = store.list_records(task="yolo_detection")[0]
        self.assertEqual(studio_record["training_bundle_id"] is not None, True)
        datasets = DatasetService(store, config.output_dir)
        dataset_id = datasets.create_dataset("empty YOLO", "yolo_detection",
                                             studio_record["registry_id"],
                                             studio_record["registry_version"],
                                             training_bundle_id=studio_record["training_bundle_id"])
        version_id = datasets.create_version(dataset_id)
        datasets.finalize(version_id)
        package_dir = config.output_dir / "empty_yolo_colab"
        datasets.export_colab(version_id, package_dir)
        labels = list((package_dir / "dataset" / "labels").rglob("*.txt"))
        images = list((package_dir / "dataset" / "images").rglob("*"))
        images = [path for path in images if path.is_file()]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].read_bytes(), b"")
        self.assertEqual(len(images), 1)

    def test_v4_preserves_task_identity_geometry_and_excluded_face_record(self):
        detection = self.database.record_yolo_detection(
            self.source["id"], model_id="legacy_yolo", model_digest="model-sha",
            class_id=1, class_name="face", confidence=.91,
            bbox_xyxy=[5, 4, 80, 75])
        registry = json.loads((Path(__file__).resolve().parents[1] /
                               "TrainingDatasetStudio/registries/yolo_detector_v1.json").read_text())
        target = next(row for row in registry["classes"] if row["name"] == "face")
        correction_id = self.database.save_correction(
            detection["proposal_id"],
            {"category": "body_images", "main_tag": "face", "validity_state": "valid",
             "bbox_xyxy": [10, 12, 60, 70],
             "yolo_annotation_registry_id": registry["registry_id"],
             "yolo_annotation_class_id": target["id"],
             "yolo_annotation_class_name": target["name"]},
            decision_type="corrected", final_state="confirmed",
            target_yolo_training_eligible=True)

        normal_detection = self.database.record_yolo_detection(
            self.source["id"], model_id="legacy_yolo", model_digest="model-sha",
            class_id=1, class_name="face", confidence=.91,
            bbox_xyxy=[8, 9, 75, 72])
        normal_proposal_id = int(normal_detection["proposal_id"])
        self.database.save_normal_crop_choice(normal_proposal_id, "body_images", "face", main_tag="face")
        self.database.confirm_normal_crop_classification(normal_proposal_id)

        normal_pussy = self.database.record_yolo_detection(
            self.source["id"], model_id="legacy_yolo", model_digest="model-sha",
            class_id=5, class_name="pussy", confidence=.88,
            bbox_xyxy=[15, 10, 65, 70])
        pussy_proposal_id = int(normal_pussy["proposal_id"])
        self.database.save_normal_crop_choice(pussy_proposal_id, "body_images", "pussy", main_tag="pussy")
        self.database.confirm_normal_crop_classification(pussy_proposal_id)

        normal_body = self.database.record_yolo_detection(
            self.source["id"], model_id="legacy_yolo", model_digest="model-sha",
            class_id=3, class_name="boobs", confidence=.9,
            bbox_xyxy=[20, 12, 70, 74])
        self.database.save_normal_crop_choice(
            normal_body["proposal_id"], "body_images", "boobs", main_tag="boobs",
            subtags=["cum"], body_images_cnn_target="bodypart_cum")
        normal_body_ids = self.database.confirm_normal_crop_classification(normal_body["proposal_id"])
        self.assertEqual(len(normal_body_ids), 1)

        excluded_proposal_id = self.database.create_manual_proposal(self.source["id"])
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO training_examples(source_image_id,proposal_id,detection_id,supersedes_id,
                   source_sha256,crop_bbox_json,task,class_label,taxonomy_id,taxonomy_version,
                   suggestion_provenance_json,workflow,human_confirmed,training_eligible)
                   VALUES (?,?,NULL,NULL,?,?,?,?,?,? ,?,'normal_processing',1,1)""",
                (self.source["id"], excluded_proposal_id, self.source["content_sha256"],
                 json.dumps([12, 8, 70, 72]), "unified_body_images_fullbody", "face",
                 "newassetapp_unified_body_images_fullbody", "1",
                 json.dumps({"yolo": {"class_id": 1, "class_name": "face"}})),
            )

        output_root = self.root / "training_source" / "bundles"
        source_bytes = self.image_path.read_bytes()
        result = export_training_source_bundle(self.database, output_root)
        bundle_dir = Path(result["directory"])
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        accepted = manifest["records"]
        excluded = manifest["excluded_records"]
        self.assertEqual(manifest["schema_version"], 4)
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(excluded), 1)

        record = next(row for row in accepted if row["provenance"]["correction_events"])
        self.assertEqual(record["task"], "yolo_detection")
        self.assertEqual(record["model"]["registry_id"], registry["registry_id"])
        self.assertEqual(record["annotation"]["coordinate_space"], "source_pixels")
        self.assertEqual(record["annotation"]["target_bbox_xyxy"], [10, 12, 60, 70])
        self.assertEqual(record["annotation"]["original_model_bbox_xyxy"], [5, 4, 80, 75])
        self.assertEqual(record["annotation"]["target_class_id"], target["id"])
        self.assertEqual(record["detection"]["bbox_xyxy"], [5, 4, 80, 75])
        self.assertEqual(record["provenance"]["correction_events"][0]["correction_record_id"],
                         str(correction_id))

        self.assertEqual(record["task"], "yolo_detection")
        self.assertEqual(record["labels"]["class_label"], "face")

        quarantined = next(row for row in excluded if row["record_id"] ==
                           f"training_example:{self._example_id(excluded_proposal_id)}")
        self.assertEqual(quarantined["task"], "body_images_classification")
        self.assertEqual(quarantined["reason"],
                         "body_region_identity_is_yolo_provenance_not_cnn_target")
        self.assertEqual(quarantined["labels"]["class_label"], "face")
        self.assertEqual(quarantined["labels"]["structured"]["task"],
                         "body_images")
        self.assertEqual(quarantined["labels"]["structured"]["source_task"],
                         "unified_body_images_fullbody")
        self.assertIsNotNone(quarantined["media"])
        self.assertEqual(quarantined["source"]["sha256"], self.source["content_sha256"])
        self.assertEqual({row["labels"]["class_label"] for row in excluded}, {"face"})
        self.assertTrue(all(row["reason"] ==
                            "body_region_identity_is_yolo_provenance_not_cnn_target"
                            for row in excluded))

        normal_record = next(row for row in accepted if row["record_id"].startswith("training_example:"))
        self.assertEqual(normal_record["task"], "body_images_classification")
        self.assertEqual(normal_record["labels"]["class_label"], "bodypart_cum")
        self.assertEqual(normal_record["labels"]["structured"]["output_group"], "body_images")
        self.assertEqual(normal_record["provenance"]["source_workflow"], "normal_processing")
        self.assertEqual(normal_record["labels"]["structured"]["human_confirmed_labels"], ["cum"])

        for file_record in manifest["files"]:
            path = bundle_dir / file_record["relative_path"]
            self.assertEqual(path.stat().st_size, file_record["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), file_record["sha256"])
        without_hash = dict(manifest)
        expected_hash = without_hash.pop("bundle_sha256")
        payload = json.dumps(without_hash, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")
        self.assertEqual(hashlib.sha256(payload).hexdigest(), expected_hash)
        self.assertEqual(self.image_path.read_bytes(), source_bytes)

        try:
            import jsonschema
        except ImportError:
            return
        contract = json.loads((Path(__file__).resolve().parents[1] /
                               "TrainingDatasetStudio/contracts/newassetapp_import_v4.schema.json").read_text())
        jsonschema.validate(manifest, contract)

        from TrainingDatasetStudio.studio.config import StudioConfig
        from TrainingDatasetStudio.studio.datasets import DatasetService
        from TrainingDatasetStudio.studio.importer import BundleImporter
        from TrainingDatasetStudio.studio.store import StudioStore
        studio_config = StudioConfig(root=self.root / "studio")
        studio_config.ensure_directories()
        shutil.copytree(Path(__file__).resolve().parents[1] / "TrainingDatasetStudio" / "contracts",
                        studio_config.contract_dir, dirs_exist_ok=True)
        studio_store = StudioStore(studio_config.database_path)
        studio_store.initialize()
        importer = BundleImporter(studio_config, studio_store)
        imported = importer.import_bundle(bundle_dir)
        self.assertEqual((imported["accepted"], imported["quarantined"]), (2, 1))
        imported_rows = studio_store.list_records()
        self.assertTrue(all(row["source_project_id"] for row in imported_rows))
        for task in ("yolo_detection", "body_images_classification"):
            record = next(row for row in imported_rows
                          if row["task"] == task and row["status"] == "accepted")
            dataset_service = DatasetService(studio_store, studio_config.output_dir)
            dataset_id = dataset_service.create_dataset(
                f"disposable {task}", task, record["registry_id"], record["registry_version"],
                training_bundle_id=record["training_bundle_id"])
            version_id = dataset_service.create_version(dataset_id)
            dataset_service.finalize(version_id)
            package_path = studio_config.output_dir / f"{task}_package"
            package = dataset_service.export_colab(version_id, package_path)
            self.assertEqual(package["package_type"], "yolo" if task == "yolo_detection" else "cnn")
            self.assertTrue((package_path / "hash_manifest.json").is_file())

        wrong_size_image = self.root / "wrong_size.png"
        Image.new("RGB", (11, 9), "purple").save(wrong_size_image)
        for suffix, replacement in (("invalid", b"not an image"),
                                    ("wrong_size", wrong_size_image.read_bytes())):
            bad_root = self.root / f"bad_{suffix}"
            shutil.copytree(bundle_dir, bad_root)
            bad_manifest_path = bad_root / "manifest.json"
            bad_manifest = json.loads(bad_manifest_path.read_text(encoding="utf-8"))
            image_entry = next(row for row in bad_manifest["files"]
                               if row["relative_path"].startswith("media/"))
            image_payload = bad_root / image_entry["relative_path"]
            image_payload.write_bytes(replacement)
            bad_digest = hashlib.sha256(replacement).hexdigest()
            image_entry.update({"sha256": bad_digest, "bytes": len(replacement)})
            for row in bad_manifest["records"] + bad_manifest["excluded_records"]:
                if row.get("source"):
                    row["source"]["sha256"] = bad_digest
                if row.get("media"):
                    row["media"]["sha256"] = bad_digest
            bad_manifest["bundle_id"] = f"{manifest['bundle_id']}_{suffix}"
            bad_manifest.pop("bundle_sha256", None)
            bad_manifest["bundle_sha256"] = hashlib.sha256(
                json.dumps(bad_manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")).hexdigest()
            bad_manifest_path.write_text(json.dumps(bad_manifest, indent=2), encoding="utf-8")
            bad_result = importer.import_bundle(bad_root)
            self.assertEqual(bad_result["accepted"], 0)
            self.assertGreaterEqual(bad_result["quarantined"], 2)
            bad_rows = [row for row in studio_store.list_records()
                        if row["bundle_id"] == bad_manifest["bundle_id"]]
            self.assertTrue(all(row["status"] == "quarantined" for row in bad_rows))
            self.assertTrue(all(row["reason"] == "source_image_invalid_or_dimensions_mismatch"
                                for row in bad_rows if row["external_id"].startswith("training_example:")))

    def _example_id(self, proposal_id: int) -> int:
        with self.database.connect() as connection:
            row = connection.execute("SELECT id FROM training_examples WHERE proposal_id=?",
                                     (proposal_id,)).fetchone()
            return int(row["id"])


if __name__ == "__main__":
    unittest.main()
