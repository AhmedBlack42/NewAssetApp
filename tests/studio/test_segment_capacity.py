from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from TrainingDatasetStudio.studio.store import StudioStore, TRAINING_BUNDLE_MAX_BYTES


class SegmentCapacityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="studio_segment_capacity_")
        self.root = Path(self.temp.name)
        self.store = StudioStore(self.root / "studio.sqlite3")
        self.store.initialize()
        self.media = self.root / "source.bin"
        self.media.write_bytes(b"m" * 90)

    def tearDown(self):
        self.temp.cleanup()

    def _insert_record(self, project: str, external_id: str, *,
                       source_identity: str | None = None, label: str = "top",
                       model_id: str = "clothing_model",
                       assign_max_bytes: int | None = None) -> tuple[int, int | None]:
        source_hash = hashlib.sha256(
            (source_identity or f"{project}:{external_id}").encode()).hexdigest()
        class_id = 0 if label == "top" else 1
        registry = {"classes": [
            {"class_id": 0, "class_name": "top", "active": True},
            {"class_id": 1, "class_name": "footwear", "active": True},
        ]}
        with self.store.connect() as db:
            bundle_hash = hashlib.sha256(f"{project}:{external_id}".encode()).hexdigest()
            bundle_id = db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES(?,4,?,?, '{}')""",
                (f"bundle-{project}-{external_id}", bundle_hash, project),
            ).lastrowid
            db.execute(
                """INSERT INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json)
                   VALUES(?,'broad_registry','1','registry-hash','registry.json',?)""",
                (bundle_id, json.dumps(registry)),
            )
            annotation = json.dumps({
                "bbox_xyxy": [0, 0, 10, 10], "class_label": label,
                "target_class_id": class_id,
            }, sort_keys=True)
            original = json.dumps({"project": project}, sort_keys=True)
            record_id = db.execute(
                """INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,
                   registry_version,class_label,target_class_id,status,source_sha256,source_width,
                   source_height,media_path,original_json,annotation_json,human_confirmed,
                   training_eligible,source_project_id)
                   VALUES(?,?,?,?,?,? ,?,?,'accepted',?,10,10,?,?,?,1,1,?)""",
                (bundle_id, external_id, "broad_clothing_classification", model_id,
                 "broad_registry", "1", label, class_id, source_hash, str(self.media),
                 original, annotation, project),
            ).lastrowid
            segment_id = None
            if assign_max_bytes is not None:
                record = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
                segment_id = self.store._assign_training_bundle(
                    db, record, max_bytes=assign_max_bytes)
        return int(record_id), segment_id

    def _record_bytes(self, record_id: int) -> int:
        with self.store.connect() as db:
            row = db.execute(
                "SELECT media_path,annotation_json,original_json FROM records WHERE id=?",
                (record_id,),
            ).fetchone()
        return (Path(row["media_path"]).stat().st_size
                + len(row["annotation_json"].encode("utf-8"))
                + len(row["original_json"].encode("utf-8")))

    def _assign_existing(self, record_id: int, max_bytes: int) -> int | None:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
            return self.store._assign_training_bundle(db, row, max_bytes=max_bytes)

    def test_exact_fit_rollover_and_complete_records_are_not_split(self):
        first_id, _ = self._insert_record("project-a", "record-01")
        second_id, _ = self._insert_record("project-b", "record-02")
        record_bytes = self._record_bytes(first_id)
        self.assertEqual(self._record_bytes(second_id), record_bytes)

        first_segment = self._assign_existing(first_id, record_bytes)
        second_segment = self._assign_existing(second_id, record_bytes)
        self.assertNotEqual(first_segment, second_segment)
        segments = self.store.list_training_bundles()
        self.assertEqual(len(segments), 2)
        self.assertTrue(all(row["record_count"] == 1 and row["size_bytes"] == record_bytes
                            and row["state"] == "full" for row in segments))

        # A complete record larger than the entire segment fails atomically.
        with self.assertRaisesRegex(ValueError, "over the 5,000,000,000-byte segment cap"):
            self._insert_record("project-c", "oversize", assign_max_bytes=record_bytes - 1)
        self.assertEqual(len(self.store.list_training_bundles()), 2)
        with self.store.connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM records WHERE external_id='oversize'").fetchone()[0], 0)
        self.assertEqual(TRAINING_BUNDLE_MAX_BYTES, 5_000_000_000)

    def test_rollover_occurs_only_when_the_next_complete_record_cannot_fit(self):
        rows = [self._insert_record(f"project-{index}", f"record-{index:02d}")[0]
                for index in range(3)]
        record_bytes = self._record_bytes(rows[0])
        self.assertTrue(all(self._record_bytes(record_id) == record_bytes for record_id in rows))
        segment_ids = [self._assign_existing(record_id, record_bytes * 2) for record_id in rows]
        self.assertEqual(segment_ids[0], segment_ids[1])
        self.assertNotEqual(segment_ids[1], segment_ids[2])
        self.assertEqual([row["record_count"] for row in self.store.list_training_bundles()], [2, 1])
        self.assertEqual([row["size_bytes"] for row in self.store.list_training_bundles()],
                         [record_bytes * 2, record_bytes])

    def test_duplicate_identity_does_not_consume_capacity_twice(self):
        first_id, _ = self._insert_record(
            "project-a", "record-01", source_identity="same-image")
        second_id, _ = self._insert_record(
            "project-b", "record-02", source_identity="same-image")
        record_bytes = self._record_bytes(first_id)
        segment = self._assign_existing(first_id, record_bytes * 2)
        self.assertEqual(self._assign_existing(second_id, record_bytes * 2), segment)
        bundles = self.store.list_training_bundles()
        self.assertEqual(len(bundles), 1)
        self.assertEqual((bundles[0]["record_count"], bundles[0]["size_bytes"]),
                         (1, record_bytes))
        self.assertEqual(self.store.get_record(second_id)["status"], "warning")

    def test_conflicting_annotation_for_same_crop_suppresses_both_records(self):
        first_id, _ = self._insert_record(
            "project-a", "record-01", source_identity="same-image", label="top")
        second_id, _ = self._insert_record(
            "project-b", "record-02", source_identity="same-image", label="footwear")
        third_id, _ = self._insert_record(
            "project-c", "record-03", source_identity="same-image", label="top")
        record_bytes = self._record_bytes(first_id)
        self._assign_existing(first_id, record_bytes * 2)

        self.assertIsNone(self._assign_existing(second_id, record_bytes * 2))
        self.assertIsNone(self._assign_existing(third_id, record_bytes * 2))
        self.assertEqual(self.store.get_record(first_id)["status"], "warning")
        self.assertEqual(self.store.get_record(second_id)["status"], "warning")
        self.assertEqual(self.store.get_record(third_id)["status"], "warning")
        self.assertEqual(self.store.list_training_bundles()[0]["record_count"], 0)
        self.assertEqual(self.store.list_training_bundles()[0]["size_bytes"], 0)

    def test_unrelated_models_use_separate_segments(self):
        first_id, _ = self._insert_record("project-a", "record-01", model_id="model-a")
        second_id, _ = self._insert_record("project-b", "record-02", model_id="model-b")
        record_bytes = self._record_bytes(first_id)

        first_segment = self._assign_existing(first_id, record_bytes * 2)
        second_segment = self._assign_existing(second_id, record_bytes * 2)

        self.assertNotEqual(first_segment, second_segment)
        self.assertEqual({row["model_id"] for row in self.store.list_training_bundles()},
                         {"model-a", "model-b"})

    def test_invalid_updated_annotation_removes_old_segment_membership(self):
        record_id, _ = self._insert_record("project-a", "record-01")
        record_bytes = self._record_bytes(record_id)
        segment_id = self._assign_existing(record_id, record_bytes * 2)
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
            annotation = json.loads(row["annotation_json"])
            annotation["bbox_xyxy"] = [0, 0, 11, 10]
            db.execute("UPDATE records SET annotation_json=? WHERE id=?",
                       (json.dumps(annotation), record_id))
            refreshed = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
            self.assertIsNone(self.store._assign_training_bundle(db, refreshed))

        with self.store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT 1 FROM training_bundle_records WHERE record_id=?", (record_id,)).fetchone())
            segment = db.execute("SELECT record_count,size_bytes FROM training_bundles WHERE id=?",
                                 (segment_id,)).fetchone()
        self.assertEqual((segment["record_count"], segment["size_bytes"]), (0, 0))

    def test_import_insert_returns_final_duplicate_status_for_counts(self):
        from TrainingDatasetStudio.studio.config import StudioConfig
        from TrainingDatasetStudio.studio.importer import BundleImporter

        config = StudioConfig.for_acceptance(self.root / "importer")
        importer = BundleImporter(config, self.store)
        statuses = []
        with self.store.connect() as db:
            registry = {"classes": [
                {"class_id": 0, "class_name": "top", "active": True},
                {"class_id": 1, "class_name": "footwear", "active": True},
            ]}
            for index, label in enumerate(("top", "footwear")):
                bundle_id = db.execute(
                    """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                       VALUES(?,4,?,?, '{}')""",
                    (f"import-{index}", hashlib.sha256(f"import-{index}".encode()).hexdigest(),
                     f"project-{index}"),
                ).lastrowid
                db.execute(
                    """INSERT INTO registries(bundle_id,registry_id,version,sha256,relative_path,payload_json)
                       VALUES(?,'broad_registry','1','registry-hash','registry.json',?)""",
                    (bundle_id, json.dumps(registry)),
                )
                prepared = {
                    "external_id": f"external-{index}",
                    "task": "broad_clothing_classification",
                    "model_id": "clothing_model",
                    "registry_id": "broad_registry",
                    "registry_version": "1",
                    "class_label": label,
                    "target_class_id": 0 if label == "top" else 1,
                    "status": "accepted",
                    "reason": None,
                    "source_image_id": "same-source",
                    "source_project_id": f"project-{index}",
                    "source_sha256": hashlib.sha256(b"same-source").hexdigest(),
                    "source_width": 10,
                    "source_height": 10,
                    "media_path": str(self.media),
                    "original_json": {"fixture": True},
                    "annotation": {
                        "bbox_xyxy": [0, 0, 10, 10], "class_label": label,
                        "target_class_id": 0 if label == "top" else 1,
                        "labels": {"structured": {}},
                    },
                    "human_confirmed": True,
                    "training_eligible": True,
                }
                statuses.append(importer._insert_record(db, int(bundle_id), prepared))

        self.assertEqual(statuses, ["accepted", "warning"])
        self.assertEqual(self.store.list_training_bundles()[0]["record_count"], 0)

    def test_failed_assignment_rolls_back_record_and_byte_accounting(self):
        first_id, _ = self._insert_record("project-a", "record-01")
        record_bytes = self._record_bytes(first_id)
        with self.assertRaises(ValueError):
            self._insert_record("project-b", "too-large",
                                assign_max_bytes=record_bytes - 1)
        self.assertEqual(self._record_bytes(first_id), record_bytes)
        self.assertEqual(self._assign_existing(first_id, record_bytes), 1)
        bundle = self.store.list_training_bundles()[0]
        self.assertEqual((bundle["record_count"], bundle["size_bytes"]),
                         (1, record_bytes))

    def test_more_than_512_records_fit_in_one_byte_available_segment(self):
        max_bytes = 1_000_000
        segment_ids = set()
        for index in range(513):
            record_id, segment_id = self._insert_record(
                "project-shared", f"record-{index:04d}",
                assign_max_bytes=max_bytes)
            self.assertEqual(self.store.get_record(record_id)["status"], "accepted")
            segment_ids.add(segment_id)
        self.assertEqual(len(segment_ids), 1)
        segment = self.store.list_training_bundles()[0]
        self.assertEqual(segment["record_count"], 513)
        self.assertLess(segment["size_bytes"], max_bytes)


if __name__ == "__main__":
    unittest.main()
