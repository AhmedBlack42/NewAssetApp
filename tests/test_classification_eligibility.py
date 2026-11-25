import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.classification_eligibility import (
    arousal_eligible, eligible_shared_heads, is_location_group, shared_head_eligible,
)
from app.core.database import Database
from app.core.inference import eligible_shared_heads_for_detection


class ClassificationEligibilityTests(unittest.TestCase):
    def test_arousal_regions_are_exact_and_portrait_frame_is_always_eligible(self):
        for region in ("face", "ass", "pussy", "legs"):
            self.assertTrue(arousal_eligible(region), region)
        for region in ("boobs", "ass", "pussy", "legs", "face"):
            self.assertTrue(arousal_eligible(region), region)
        for region in ("fullbody_maid", "clothing", "location_home"):
            self.assertFalse(arousal_eligible(region), region)
        self.assertTrue(arousal_eligible("person"))
        self.assertTrue(arousal_eligible("portrait_frame"))
        self.assertTrue(arousal_eligible("portrait_frame", confirmed_portrait="portrait"))
        self.assertTrue(arousal_eligible("portrait_frame", confirmed_portrait="tportrait"))

    def test_inference_uses_central_arousal_rules_and_confirmed_portrait_state(self):
        class ReviewDatabase:
            def __init__(self, portrait=None):
                self.portrait = portrait

            def classification_task_status(self, _proposal_id):
                if self.portrait is None:
                    return {}
                return {"portrait": {
                    "target_label": self.portrait,
                    "confirmation_status": "confirmed",
                    "human_confirmed": True,
                }}

        expected = {
            "face": {"body_images", "arousal", "corruption"},
            "ass": {"body_images", "arousal", "corruption"},
            "pussy": {"body_images", "arousal", "corruption"},
            "legs": {"body_images", "arousal", "corruption"},
            "boobs": {"body_images", "arousal", "corruption"},
            "person": {"corruption", "arousal"},
            "fullbody_maid": {"fullbody", "corruption"},
            "portrait_frame": {"body_images", "portrait", "arousal", "corruption"},
        }
        for region, heads in expected.items():
            with self.subTest(region=region):
                self.assertEqual(eligible_shared_heads(region), heads)
                self.assertEqual(
                    eligible_shared_heads_for_detection(
                        ReviewDatabase(), {"proposal_id": 1}, region),
                    heads,
                )
        for portrait in ("portrait", "tportrait"):
            self.assertEqual(
                eligible_shared_heads_for_detection(
                    ReviewDatabase(portrait), {"proposal_id": 1}, "portrait_frame"),
                {"body_images", "portrait", "arousal", "corruption"},
            )

    def test_independent_head_region_rules(self):
        for region in ("face", "boobs", "ass", "pussy", "legs"):
            self.assertTrue(shared_head_eligible("body_images", region), region)
        self.assertTrue(shared_head_eligible("body_images", "portrait_frame"))
        self.assertTrue(shared_head_eligible("fullbody", "fullbody_maid"))
        self.assertFalse(shared_head_eligible("fullbody", "person"))
        self.assertTrue(shared_head_eligible("portrait", "portrait_frame"))
        self.assertTrue(shared_head_eligible("corruption", "person"))
        self.assertTrue(shared_head_eligible("corruption", "portrait_frame"))
        self.assertTrue(shared_head_eligible("corruption", "face"))
        self.assertTrue(shared_head_eligible("corruption", "fullbody_underwear"))

    def test_registry_exposes_five_fullbody_cnn_labels_without_remapping(self):
        registry = json.loads((Path(__file__).resolve().parents[1] /
                               "data/models/unified_body_images_fullbody/class_registry.json").read_text())
        labels = [row["class_name"] for row in registry["output_heads"]["fullbody"]["classes"]]
        self.assertEqual(labels, ["clothed", "topless", "bottomless", "bra", "panty"])
        arousal = registry["output_heads"]["arousal"]
        self.assertEqual(arousal["input_regions"],
                         ["person", "face", "boobs", "ass", "pussy", "legs", "portrait_frame"])
        self.assertNotIn("conditional_input_regions", arousal)
        self.assertEqual(registry["output_heads"]["corruption"]["input_regions"],
                         ["person", "face", "portrait_frame", "boobs", "ass", "pussy", "legs",
                          "pussy_cover_item", "ass_cover_item", "boobs_cover_item",
                          "leg_cover_item", "accessory_footwear", "fullbody_*"])

    def test_task_status_summary_keeps_independent_labels_separate(self):
        payload = json.dumps({
            "shared_cnn_training_tasks": ["portrait", "arousal", "corruption"],
            "main_tag": "portrait", "arousal_cnn_target": "edging",
            "corruption_classifier_target": "conservative",
        })
        status = Database._detection_classification_status(payload)
        self.assertEqual(set(status), {"portrait", "arousal", "corruption"})
        self.assertEqual(status["portrait"], {"label": "portrait", "status": "human_confirmed"})
        self.assertEqual(status["arousal"]["label"], "edging")
        self.assertEqual(status["corruption"]["label"], "conservative")

    def test_location_group_is_only_location_detection_family(self):
        self.assertTrue(is_location_group("location_home"))
        self.assertTrue(is_location_group("location_beach"))
        for region in ("face", "boobs", "ass", "pussy", "legs", "portrait_frame",
                       "person", "fullbody_maid", "boobs_cover_item"):
            self.assertFalse(is_location_group(region), region)

    def test_database_rejects_ineligible_arousal_for_fullbody_and_location(self):
        with tempfile.TemporaryDirectory(prefix="eligibility_db_") as directory:
            root = Path(directory)
            image_path = root / "source.png"
            Image.new("RGB", (100, 100), "navy").save(image_path)
            database = Database(root / "review.sqlite3")
            database.initialize()
            source_id, _ = database.upsert_source_image({
                "path": str(image_path.resolve()),
                "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                "width": 100, "height": 100, "file_size": image_path.stat().st_size,
                "modified_ns": image_path.stat().st_mtime_ns,
            })
            cases = (
                (20, "fullbody_maid", {"category": "fullbody", "main_tag": "clothed",
                                       "state_spec": "clothed"}),
                (24, "location_office", {"category": "others", "main_tag": None}),
            )
            for class_id, class_name, fields in cases:
                detection = database.record_yolo_detection(
                    source_id, model_id="fixture", model_digest="fixture", class_id=class_id,
                    class_name=class_name, confidence=.9, bbox_xyxy=[10, 10, 90, 90])
                with self.subTest(region=class_name), self.assertRaisesRegex(ValueError, "Arousal targets"):
                    database.save_correction(
                        detection["proposal_id"], {
                            **fields, "validity_state": "valid", "bbox_xyxy": [10, 10, 90, 90],
                            "arousal_cnn_target": "aroused",
                        }, decision_type="corrected", final_state="confirmed",
                        shared_cnn_training_tasks=["arousal"])


if __name__ == "__main__":
    unittest.main()
