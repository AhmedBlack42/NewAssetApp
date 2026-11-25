import unittest
import tempfile
from pathlib import Path

from PIL import Image

from app.core.crop_rules import prepare_export_crop
from app.core.database import Database


class Phase6CropRulesTests(unittest.TestCase):
    def test_classification_edit_confirmation_and_bbox_invalidation_are_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "source.png"
            Image.new("RGB", (100, 100), "white").save(source_path)
            database = Database(root / "review.sqlite3")
            database.initialize()
            source_id, _ = database.upsert_source_image({
                "path": str(source_path.resolve()), "sha256": "b" * 64,
                "width": 100, "height": 100, "file_size": source_path.stat().st_size,
                "modified_ns": source_path.stat().st_mtime_ns,
            })
            detection_id = database.record_yolo_detection(
                source_id, model_id="fixture", model_digest="digest", class_id=1,
                class_name="region", confidence=.9, bbox_xyxy=[10, 10, 60, 60]
            )["detection_id"]
            database.save_classification_edit(detection_id, "fullbody_state", "clothed")
            self.assertEqual(database.classification_review_state(detection_id, "fullbody_state")["status"],
                             "needs_confirmation")
            database.confirm_classification(detection_id, "fullbody_state", "clothed")
            self.assertEqual(database.classification_review_state(detection_id, "fullbody_state")["status"],
                             "confirmed")
            database.save_bbox_edit(detection_id, [12, 12, 62, 62])
            self.assertEqual(database.classification_review_state(detection_id, "fullbody_state")["status"],
                             "needs_confirmation")

    def test_body_images_crop_expands_to_guide_ratio_without_cutting_box(self):
        source = Image.new("RGB", (900, 900), "red")
        crop, policy = prepare_export_crop(source, {
            "category": "body_images", "main_tag": "boobs", "bbox_xyxy": [200, 300, 600, 500]
        })
        try:
            self.assertEqual(crop.width / crop.height, 495 / 240)
            self.assertGreaterEqual(crop.width, 495)
            self.assertEqual(policy["policy"], "body_images_guide_aspect_and_minimum_dimensions")
            left, top, right, bottom = policy["crop_bbox_xyxy_source_pixels"]
            self.assertLessEqual(left, 200)
            self.assertLessEqual(top, 300)
            self.assertGreaterEqual(right, 600)
            self.assertGreaterEqual(bottom, 500)
        finally:
            crop.close()
            source.close()

    def test_fullbody_requires_transparency_and_clothing_preserves_box(self):
        opaque = Image.new("RGB", (100, 200), "blue")
        with self.assertRaisesRegex(ValueError, "transparent background"):
            prepare_export_crop(opaque, {"category": "fullbody", "bbox_xyxy": [5, 5, 95, 195]})
        clothing, policy = prepare_export_crop(opaque, {
            "category": "clothing", "bbox_xyxy": [10, 20, 70, 100]
        })
        try:
            self.assertEqual(clothing.size, (60, 80))
            self.assertEqual(policy["policy"], "clothing_reviewed_box_preserve_source_aspect")
        finally:
            clothing.close()
            opaque.close()


if __name__ == "__main__":
    unittest.main()
