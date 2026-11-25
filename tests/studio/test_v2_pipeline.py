from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if "jsonschema" not in sys.modules:
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        stub = types.ModuleType("jsonschema")
        stub.Draft202012Validator = object
        stub.FormatChecker = object
        sys.modules["jsonschema"] = stub

from TrainingDatasetStudio.studio.importer import _task_validation
from TrainingDatasetStudio.studio.store import StudioStore, TRAINING_BUNDLE_MAX_BYTES


class V2PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="studio_v2_pipeline_")
        self.root = Path(self.temp.name)
        self.media = self.root / "source.png"
        self.media.write_bytes(b"m" * 90)
        self.store = StudioStore(self.root / "studio.sqlite3")
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_shared_heads_resolve_only_to_their_own_registry_group(self):
        registry = {"output_groups": {
            "body_images": {"classes": [{"class_id": 0, "class_name": "bodypart_cum"},
                                          {"class_id": 1, "class_name": "bodypart_acc"}]},
            "fullbody": {"classes": [{"class_id": 0, "class_name": "clothed"}]},
            "portrait": {"classes": [{"class_id": 0, "class_name": "portrait"}]},
            "arousal": {"classes": [{"class_id": 0, "class_name": "aroused"}]},
            "corruption": {"classes": [{"class_id": 0, "class_name": "conservative"}]},
        }}
        tasks = {
            "body_images_classification": ("body_images", "bodypart_cum"),
            "fullbody_state_classification": ("fullbody", "clothed"),
            "portrait_classification": ("portrait", "portrait"),
            "arousal_classification": ("arousal", "aroused"),
            "corruption_classification": ("corruption", "conservative"),
        }
        models = {"shared": {"id": "shared", "registry_id": "shared_registry",
                              "registry_version": "v2"}}
        for task, (head, label) in tasks.items():
            record = {"task": task, "model": {"id": "shared", "registry_id": "shared_registry",
                                                  "registry_version": "v2"},
                      "labels": {"class_label": label, "structured": {"output_group": head}},
                      "annotation": {"target_class_id": 0}}
            result = _task_validation(record, 4, models, {"shared_registry": registry})
            self.assertEqual(result, (task, "shared_registry", 0, None))
            wrong = dict(record)
            wrong["labels"] = {"class_label": label, "structured": {"output_group": "body_images"}}
            if task != "body_images_classification":
                self.assertEqual(_task_validation(wrong, 4, models, {"shared_registry": registry})[3],
                                 "task_output_head_identity_mismatch")

    def test_region_identity_is_never_accepted_as_a_body_images_target(self):
        registry = {"output_groups": {"body_images": {"classes": [
            {"class_id": 0, "class_name": "bodypart_cum"}]}}}
        record = {"task": "body_images_classification",
                  "model": {"id": "shared", "registry_id": "shared_registry", "registry_version": "v2"},
                  "labels": {"class_label": "pussy", "structured": {"output_group": "body_images"}},
                  "annotation": {"target_class_id": 0}}
        result = _task_validation(record, 4, {"shared": {"id": "shared", "registry_id": "shared_registry"}},
                                  {"shared_registry": registry})
        self.assertEqual(result[3], "architecture_body_region_identity_is_yolo_task")

    def test_yolo_and_both_clothing_tasks_validate_against_distinct_registries(self):
        models = {
            "detector": {"id": "detector", "registry_id": "newassetapp_yolo_detector_v1",
                         "registry_version": "1"},
            "broad": {"id": "broad", "registry_id": "broad_registry", "registry_version": "1"},
            "detailed": {"id": "detailed", "registry_id": "detailed_registry", "registry_version": "1"},
        }
        registries = {
            "newassetapp_yolo_detector_v1": json.loads(
                (ROOT / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json")
                .read_text(encoding="utf-8")),
            "broad_registry": {"classes": [{"class_id": 2, "class_name": "footwear", "active": True}]},
            "detailed_registry": {"entries": [{"class_id": 7, "serialized_value": "heels",
                                                    "selectable": True, "requires_review": False}]},
        }
        yolo = {"task": "yolo_detection", "model": {
                    "id": "detector", "registry_id": "newassetapp_yolo_detector_v1",
                    "registry_version": "1"},
                "labels": {"class_label": "boobs", "structured": {}},
                "annotation": {"target_class_id": 3, "coordinate_space": "source_pixels"}}
        self.assertEqual(_task_validation(yolo, 4, models, registries),
                         ("yolo_detection", "newassetapp_yolo_detector_v1", 3, None))
        broad = {"task": "broad_clothing_classification",
                 "model": {"id": "broad", "registry_id": "broad_registry", "registry_version": "1"},
                 "labels": {"class_label": "footwear", "structured": {}},
                 "annotation": {"target_class_id": 2}}
        detailed = {"task": "detailed_clothing_classification",
                    "model": {"id": "detailed", "registry_id": "detailed_registry", "registry_version": "1"},
                    "labels": {"class_label": "heels", "structured": {}},
                    "annotation": {"target_class_id": 7}}
        self.assertEqual(_task_validation(broad, 4, models, registries),
                         ("broad_clothing_classification", "broad_registry", 2, None))
        self.assertEqual(_task_validation(detailed, 4, models, registries),
                         ("detailed_clothing_classification", "detailed_registry", 7, None))

    def test_segments_append_across_projects_and_roll_over_before_byte_cap(self):
        bundle_ids = []
        for index, project in enumerate(("project-a", "project-b")):
            with self.store.connect() as db:
                bundle_id = db.execute("INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json) "
                                       "VALUES(?,4,?,?, '{}')",
                                       (f"bundle-{index}", hashlib.sha256(project.encode()).hexdigest(), project)).lastrowid
                db.execute("INSERT OR IGNORE INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json) "
                           "VALUES(?,'registry','1','hash','registry.json',?)",
                           (bundle_id, json.dumps({"classes": [{"class_id": 0, "class_name": "top"}]})))
                record_id = db.execute("""INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,
                                  registry_version,class_label,target_class_id,status,source_sha256,source_width,
                                  source_height,media_path,original_json,annotation_json,human_confirmed,training_eligible,
                                  source_project_id) VALUES(?,?,?,?,?,?,'top',0,'accepted',?,10,10,?,?,?,1,1,?)""",
                                       (bundle_id, f"record-{index}", "broad_clothing_classification", "model",
                                        "registry", "1", hashlib.sha256(f"source-{index}".encode()).hexdigest(),
                                        str(self.media), json.dumps({"provenance": "x" * 25}),
                                        json.dumps({"bbox_xyxy": [0, 0, 10, 10], "class_label": "top",
                                                    "target_class_id": 0}), project)).lastrowid
                record = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
                # The byte cap is reduced only for this isolated unit boundary check.
                segment_id = self.store._assign_training_bundle(db, record, max_bytes=300)
                bundle_ids.append(segment_id)
        self.assertNotEqual(bundle_ids[0], bundle_ids[1])
        bundles = self.store.list_training_bundles()
        self.assertEqual(len(bundles), 2)
        self.assertTrue(all(row["size_bytes"] <= row["max_bytes"] == 300 for row in bundles))
        self.assertEqual(TRAINING_BUNDLE_MAX_BYTES, 5_000_000_000)

        from TrainingDatasetStudio.studio.datasets import DatasetService
        datasets = DatasetService(self.store, self.root / "output")
        dataset_id = datasets.create_dataset(
            "accumulated model", "broad_clothing_classification",
            "registry", "1", training_bundle_id=bundle_ids[0])
        version_id = datasets.create_version(dataset_id)
        version_records = self.store.version_rows(version_id)
        self.assertEqual(len(version_records), 2)
        self.assertEqual({row["source_sha256"] for row in version_records},
                         {hashlib.sha256(f"source-{index}".encode()).hexdigest()
                          for index in range(2)})

    def test_shared_model_segment_accumulates_different_heads_across_projects(self):
        head_records = [("project-a", "body_images_classification", "body_images", "bodypart_cum"),
                        ("project-b", "fullbody_state_classification", "fullbody", "clothed")]
        segment_ids = []
        for index, (project, task, head, label) in enumerate(head_records):
            with self.store.connect() as db:
                bundle_id = db.execute(
                    "INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json) "
                    "VALUES(?,4,?,?, '{}')",
                    (f"shared-bundle-{index}", hashlib.sha256(project.encode()).hexdigest(), project)).lastrowid
                registry = {"output_groups": {
                    "body_images": {"classes": [{"class_id": 0, "class_name": "bodypart_cum"}]},
                    "fullbody": {"classes": [{"class_id": 0, "class_name": "clothed"}]},
                }}
                db.execute("INSERT INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json) "
                           "VALUES(?,'shared_registry','v2','registry-hash','registry.json',?)",
                           (bundle_id, json.dumps(registry)))
                source_hash = hashlib.sha256(f"shared-source-{index}".encode()).hexdigest()
                annotation = {"bbox_xyxy": [0, 0, 10, 10], "class_label": label,
                              "target_class_id": 0,
                              "labels": {"structured": {"output_group": head}}}
                record_id = db.execute("""INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,
                                      registry_version,class_label,target_class_id,status,source_sha256,source_width,
                                      source_height,media_path,original_json,annotation_json,human_confirmed,
                                      training_eligible,source_project_id)
                                      VALUES(?,?,?,?,?,?,?,0,'accepted',?,10,10,?,?,?,1,1,?)""",
                                       (bundle_id, f"shared-record-{index}", task,
                                        "unified_body_images_fullbody_cnn", "shared_registry", "v2", label,
                                        source_hash, str(self.media), "{}", json.dumps(annotation), project)).lastrowid
                row = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
                segment_ids.append(self.store._assign_training_bundle(
                    db, row, max_bytes=100_000))
        self.assertEqual(segment_ids[0], segment_ids[1])
        shared_segment = next(row for row in self.store.list_training_bundles()
                              if row["task"] == "shared_cnn")
        self.assertEqual(shared_segment["record_count"], 2)
        self.assertEqual(shared_segment["max_bytes"], 100_000)
        self.assertEqual(TRAINING_BUNDLE_MAX_BYTES, 5_000_000_000)


if __name__ == "__main__":
    unittest.main()
