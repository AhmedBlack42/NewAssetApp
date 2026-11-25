from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.output_exporter import build_normal_output_plan, export_normal_output


class CorrectionCropPipelineTests(unittest.TestCase):
    def test_detection_reload_exposes_partial_body_images_decisions(self):
        with tempfile.TemporaryDirectory(prefix="body_task_reload_") as temp:
            root = Path(temp)
            image_path = root / "source.png"
            Image.new("RGB", (900, 900), "teal").save(image_path)
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            database = Database(root / "app.sqlite3")
            database.initialize()
            source_id, _ = database.upsert_source_image({
                "path": str(image_path.resolve()), "sha256": digest, "width": 900, "height": 900,
                "file_size": image_path.stat().st_size, "modified_ns": image_path.stat().st_mtime_ns,
            })
            detection = database.record_yolo_detection(
                source_id, model_id="fixture", model_digest="source-model", class_id=3,
                class_name="boobs", confidence=.9, bbox_xyxy=[250, 150, 650, 550])
            database.save_classification_task_review(
                int(detection["proposal_id"]), "body_images", "body_images_multi_label",
                {
                    "validity_state": "valid",
                    "cum_target": True,
                    "cum_evaluated": True,
                    "accessory_target": None,
                    "accessory_evaluated": False,
                    "body_images_completed": False,
                },
                action="confirmed",
                training_eligible=True,
            )
            detections = database.detections_for_source(source_id)
            status = detections[0]["classification_status"]["body_images"]
            self.assertTrue(status["cum_evaluated"])
            self.assertTrue(status["cum_target"])
            self.assertFalse(status["accessory_evaluated"])
            self.assertIsNone(status["accessory_target"])
            self.assertEqual(status["target_mask"], {
                "cum": {"target": True, "evaluated": True},
                "accessory": {"target": None, "evaluated": False},
            })
    def test_confirmed_correction_rebuilds_normal_crop_geometry_and_invalidates_old_example(self):
        with tempfile.TemporaryDirectory(prefix="correction_crop_pipeline_") as temp:
            root = Path(temp)
            image_path = root / "source.png"
            Image.new("RGB", (900, 900), "teal").save(image_path)
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            database = Database(root / "app.sqlite3")
            database.initialize()
            source_id, _ = database.upsert_source_image({
                "path": str(image_path.resolve()), "sha256": digest, "width": 900, "height": 900,
                "file_size": image_path.stat().st_size, "modified_ns": image_path.stat().st_mtime_ns,
            })
            detection = database.record_yolo_detection(
                source_id, model_id="fixture", model_digest="source-model", class_id=3,
                class_name="boobs", confidence=.9, bbox_xyxy=[250, 150, 650, 550])
            proposal_id = detection["proposal_id"]
            database.save_normal_crop_choice(
                proposal_id, "body_images", main_tag="boobs", subtags=["cum"],
                body_images_cnn_target="bodypart_cum")
            database.confirm_normal_crop_classification(proposal_id)
            self.assertEqual(len(database.current_training_examples()), 1)

            target_registry = "newassetapp_yolo_detector_v1"
            corrected_box = [270, 170, 630, 540]
            database.save_correction(
                proposal_id,
                {"category": "body_images", "main_tag": "boobs", "subtags": ["cum"],
                 "validity_state": "valid", "bbox_xyxy": corrected_box,
                 "yolo_annotation_registry_id": target_registry,
                 "yolo_annotation_class_id": 3, "yolo_annotation_class_name": "boobs"},
                decision_type="bbox_corrected", final_state="confirmed",
                target_yolo_training_eligible=True)

            rows = database.normal_crop_records()
            row = next(item for item in rows if item["id"] == proposal_id)
            self.assertEqual(row["bbox_xyxy"], corrected_box)
            self.assertEqual(row["normal_export_status"], "stale")
            self.assertTrue(row["cnn_suggestion_stale"])
            active_examples = database.current_training_examples()
            self.assertEqual([item["task"] for item in active_examples], ["yolo_detector"])

            plan = build_normal_output_plan(database, root / "normal_output", [proposal_id])
            self.assertEqual(plan["item_count"], 1, plan["skipped"])
            self.assertEqual(plan["items"][0]["bbox_xyxy"], corrected_box)
            result = export_normal_output(database, plan)
            self.assertEqual(result["written_count"], 1, result["failures"])
            with Image.open(result["written"][0]) as crop:
                self.assertGreater(crop.width, 0)
                self.assertGreater(crop.height, 0)


if __name__ == "__main__":
    unittest.main()
