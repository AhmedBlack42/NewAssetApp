import tempfile
import unittest
from pathlib import Path

from TrainingDatasetStudio.studio.store import StudioStore
from TrainingDatasetStudio.studio.datasets import DatasetService


class CnnReadinessTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(prefix="cnn_readiness_")
        root = Path(self.td.name)
        self.store = StudioStore(root / "studio.sqlite3")
        self.store.initialize()
        self.service = DatasetService(self.store, root / "output")

    def tearDown(self):
        self.td.cleanup()

    def test_empty_report_is_insufficient_not_training_ready(self):
        report = self.service.readiness_report()
        self.assertEqual(report["model_status"], "insufficient")
        self.assertIn("fullbody", {entry["head"] for entry in report["single_label"]})
        self.assertIn("body_images", {entry["head"] for entry in report["body_images"]})

    def test_pending_and_invalid_records_are_excluded(self):
        with self.store.connect() as db:
            db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES(?,?,?,?,?)""",
                ("fixture", 1, "a"*64, "fixture", "{}"),
            )
            bundle_id = db.execute("SELECT id FROM bundles").fetchone()["id"]
            db.execute(
                """INSERT INTO records(bundle_id,external_id,task,source_sha256,status,
                   original_json,annotation_json,human_confirmed,training_eligible)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (bundle_id, "pending-1", "shared_cnn", "s1", "accepted",
                 "{}",
                 '{"task_head":"fullbody","target_label":"clothed"}',
                 0, 0),
            )
            db.execute(
                """INSERT INTO records(bundle_id,external_id,task,source_sha256,status,
                   original_json,annotation_json,human_confirmed,training_eligible)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (bundle_id, "invalid-1", "shared_cnn", "s2", "rejected",
                 "{}",
                 '{"task_head":"fullbody","target_label":"clothed"}',
                 1, 0),
            )
        report = self.service.readiness_report()
        clothed = next(
            entry for entry in report["single_label"]
            if entry["head"] == "fullbody" and entry["class"] == "clothed"
        )
        self.assertEqual(clothed["unique_source_groups"], 0)
        self.assertGreater(clothed["pending_unreviewed"], 0)
        self.assertGreater(clothed["invalid_rejected"], 0)

    def test_body_images_positive_negative_are_independent(self):
        with self.store.connect() as db:
            db.execute(
                """INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,source_path,manifest_json)
                   VALUES(?,?,?,?,?)""",
                ("fixture", 1, "b"*64, "fixture", "{}"),
            )
            bundle_id = db.execute("SELECT id FROM bundles").fetchone()["id"]
            for index, (source, mask) in enumerate((
                ("cum-positive", '{"cum":true,"accessory":false}'),
                ("cum-negative", '{"cum":false,"accessory":true}'),
            ), start=1):
                db.execute(
                    """INSERT INTO records(bundle_id,external_id,task,source_sha256,status,
                       original_json,annotation_json,human_confirmed,training_eligible)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (bundle_id, f"body-{index}", "shared_cnn", source, "accepted",
                     "{}", '{"task_head":"body_images","target_mask":' + mask + '}',
                     1, 1),
                )
        report = self.service.readiness_report()
        outcomes = {entry["outcome"]: entry for entry in report["body_images"]}
        self.assertEqual(outcomes["cum_positive"]["unique_source_groups"], 1)
        self.assertEqual(outcomes["cum_negative"]["unique_source_groups"], 1)
        self.assertEqual(outcomes["accessory_positive"]["unique_source_groups"], 1)
        self.assertEqual(outcomes["accessory_negative"]["unique_source_groups"], 1)

    def test_report_has_explicit_split_readiness_thresholds(self):
        report = self.service.readiness_report()
        self.assertEqual(
            report["thresholds"]["minimum_split_groups"],
            {"train": 70, "validation": 15, "test": 15},
        )


if __name__ == "__main__":
    unittest.main()
