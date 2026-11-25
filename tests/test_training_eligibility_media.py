import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.scanner import scan_folder


class TrainingEligibilityMediaTests(unittest.TestCase):
    def test_confirmation_is_idempotent_and_missing_media_is_not_current(self):
        with tempfile.TemporaryDirectory(prefix="training_media_") as temporary:
            root = Path(temporary)
            source_dir = root / "sources"
            source_dir.mkdir()
            image_path = source_dir / "sample.png"
            Image.new("RGB", (64, 64), "navy").save(image_path)
            database = Database(root / "disposable.sqlite3")
            database.initialize()
            scan_folder(source_dir, database)
            with database.connect() as connection:
                source_id = int(connection.execute(
                    "SELECT id FROM source_images LIMIT 1").fetchone()["id"])

            detection = database.record_yolo_detection(
                source_id, model_id="fixture", model_digest="fixture-v1",
                class_id=13, class_name="fullbody_maid", confidence=.95,
                bbox_xyxy=[4, 4, 60, 60])
            proposal_id = int(detection["proposal_id"])
            database.save_normal_crop_choice(
                proposal_id, "fullbody", main_tag="maid", fullbody_state="clothed")
            first = database.confirm_normal_crop_classification(proposal_id)
            repeated = database.confirm_normal_crop_classification(proposal_id)
            self.assertEqual(first, repeated)
            self.assertEqual(len(database.current_training_examples()), 1)

            image_path.unlink()
            self.assertEqual(database.current_training_examples(), [])
            with self.assertRaisesRegex(ValueError, "source_image_missing"):
                database.confirm_normal_crop_classification(proposal_id)


if __name__ == "__main__":
    unittest.main()
