import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database


class PersistentNormalDraftTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(prefix="persistent_normal_drafts_")
        self.db = Database(Path(self.td.name) / "app.sqlite3")
        self.db.initialize()
        source_dir = Path(self.td.name) / "source"
        source_dir.mkdir()
        source = source_dir / "crop.jpg"
        Image.new("RGB", (200, 200), "gray").save(source)
        source_id, _ = self.db.upsert_source_image({
            "path": str(source),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "width": 200,
            "height": 200,
            "file_size": source.stat().st_size,
            "modified_ns": source.stat().st_mtime_ns,
        })
        raw = self.db.record_yolo_detection(
            source_id,
            model_id="fixture",
            model_digest="fixture",
            class_id=1,
            class_name="face",
            confidence=0.9,
            bbox_xyxy=[10, 10, 180, 180],
        )
        self.proposal_id = int(raw["proposal_id"])

    def tearDown(self):
        self.td.cleanup()

    def test_autosave_payload_reloads_all_independent_fields(self):
        payload = {
            "category": "body_images",
            "normal_main_tag": "boobs",
            "normal_subtags": ["cum"],
            "normal_body_images_cum_target": True,
            "normal_body_images_cum_evaluated": True,
            "normal_body_images_accessory_target": False,
            "normal_body_images_accessory_evaluated": True,
            "normal_body_images_completed": True,
            "normal_arousal_cnn_target": "aroused",
            "normal_corruption_cnn_target": "slut",
            "draft_schema_version": 1,
            "taxonomy_version": "test-v1",
        }
        self.db.save_normal_processing_draft(self.proposal_id, payload)
        reloaded = Database(self.db.path).load_normal_processing_draft(self.proposal_id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["category"], "body_images")
        self.assertTrue(reloaded["normal_body_images_cum_evaluated"])
        self.assertTrue(reloaded["normal_body_images_cum_target"])
        self.assertTrue(reloaded["normal_body_images_accessory_evaluated"])
        self.assertFalse(reloaded["normal_body_images_accessory_target"])
        self.assertEqual(reloaded["normal_arousal_cnn_target"], "aroused")
        self.assertEqual(reloaded["normal_corruption_cnn_target"], "slut")

    def test_pending_partial_and_stale_draft_are_distinct(self):
        payload = {
            "category": "body_images",
            "normal_main_tag": "boobs",
            "normal_body_images_cum_target": True,
            "normal_body_images_cum_evaluated": True,
            "normal_body_images_accessory_target": None,
            "normal_body_images_accessory_evaluated": False,
            "normal_body_images_completed": False,
            "stale_due_to_revision": True,
        }
        self.db.save_normal_processing_draft(self.proposal_id, payload)
        reloaded = self.db.load_normal_processing_draft(self.proposal_id)
        self.assertTrue(reloaded["normal_body_images_cum_evaluated"])
        self.assertTrue(reloaded["normal_body_images_cum_target"])
        self.assertFalse(reloaded["normal_body_images_accessory_evaluated"])
        self.assertIsNone(reloaded["normal_body_images_accessory_target"])
        self.assertTrue(reloaded["stale_due_to_revision"])

    def test_discard_removes_only_the_draft(self):
        self.db.save_normal_processing_draft(
            self.proposal_id,
            {"category": "clothing", "normal_clothing_broad_family": "skirt"},
        )
        self.assertTrue(self.db.discard_normal_processing_draft(self.proposal_id))
        self.assertIsNone(self.db.load_normal_processing_draft(self.proposal_id))
        with self.db.connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM asset_proposals WHERE id=?",
                    (self.proposal_id,),
                ).fetchone()[0],
                1,
            )


if __name__ == "__main__":
    unittest.main()
