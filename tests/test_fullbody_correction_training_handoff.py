from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.core.database import Database
from app.core.output_exporter import build_normal_output_plan, export_normal_output
from app.core.training_source_exporter import export_training_source_bundle
from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.importer import BundleImporter
from TrainingDatasetStudio.studio.store import StudioStore


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_ID = "newassetapp_yolo_detector_v1"


class FullbodyCorrectionTrainingHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fullbody_training_handoff_")
        self.root = Path(self.temp.name)
        self.source_path = self.root / "source.png"
        image = Image.new("RGBA", (500, 240), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for index, left in enumerate((10, 130, 250, 370)):
            draw.rectangle((left + 8, 48, left + 82, 190),
                           fill=(40 + index * 30, 120, 180, 255))
        image.save(self.source_path)
        image.close()
        self.source_hash = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        self.database = Database(self.root / "app.sqlite3")
        self.database.initialize()
        self.source_id, _ = self.database.upsert_source_image({
            "path": str(self.source_path.resolve()),
            "sha256": self.source_hash,
            "width": 500,
            "height": 240,
            "file_size": self.source_path.stat().st_size,
            "modified_ns": self.source_path.stat().st_mtime_ns,
        })
        registry_path = ROOT / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
        self.registry = json.loads(registry_path.read_text(encoding="utf-8"))
        self.class_ids = {row["name"]: int(row["id"]) for row in self.registry["classes"]}

    def tearDown(self):
        self.temp.cleanup()

    def _four_confirmed_fullbody_crops(self):
        proposals = []
        targets = ("clothed", "bra", "panty", "topless")
        for index, left in enumerate((0, 120, 240, 360)):
            detection = self.database.record_yolo_detection(
                self.source_id,
                model_id="fixture",
                model_digest="disposable-fullbody-fixture",
                class_id=self.class_ids["fullbody_clothed"],
                class_name="fullbody_clothed",
                confidence=.9,
                bbox_xyxy=[left, 40, left + 100, 200],
            )
            proposal_id = int(detection["proposal_id"])
            self.database.save_normal_crop_choice(
                proposal_id, "fullbody", main_tag="clothed", fullbody_state="clothed",
                fullbody_cnn_target=targets[index])
            self.database.confirm_normal_crop_classification(proposal_id)
            proposals.append(proposal_id)
        return proposals

    def test_fullbody_class_only_and_combined_corrections(self):
        cases = (
            ("fullbody_topless", "fullbody_maid", [20, 20, 120, 170]),
            ("fullbody_bottomless", "fullbody_underwear", [30, 30, 130, 180]),
        )
        for source_name, target_name, original_bbox in cases:
            detection = self.database.record_yolo_detection(
                self.source_id, model_id="legacy-fixture", model_digest="legacy",
                class_id=31, class_name=source_name, confidence=.8, bbox_xyxy=original_bbox)
            correction_id = self.database.save_yolo_annotation_correction(
                detection["proposal_id"], self.class_ids[target_name], REGISTRY_ID)
            effective = self.database.effective_detection_state(detection["proposal_id"])
            self.assertEqual((effective["class_id"], effective["class_name"]),
                             (self.class_ids[target_name], target_name))
            self.assertEqual(effective["bbox_xyxy"], [float(value) for value in original_bbox])
            with self.database.connect() as connection:
                original = connection.execute(
                    "SELECT class_id,class_name,x1,y1,x2,y2 FROM yolo_detections WHERE id=?",
                    (detection["detection_id"],),
                ).fetchone()
                correction = connection.execute(
                    "SELECT corrected_payload_json FROM correction_records WHERE id=?",
                    (correction_id,),
                ).fetchone()
            self.assertEqual(tuple(original), (31, source_name, *map(float, original_bbox)))
            payload = json.loads(correction["corrected_payload_json"])
            self.assertTrue(payload["class_correction"])
            self.assertFalse(payload["bbox_correction"])

        combined = self.database.record_yolo_detection(
            self.source_id, model_id="legacy-fixture", model_digest="legacy",
            class_id=32, class_name="fullbody_bottomless", confidence=.8,
            bbox_xyxy=[40, 35, 140, 185])
        corrected_bbox = [45, 30, 150, 190]
        correction_id = self.database.save_yolo_annotation_correction(
            combined["proposal_id"], self.class_ids["fullbody_bare"], REGISTRY_ID,
            bbox_xyxy=corrected_bbox)
        effective = self.database.effective_detection_state(combined["proposal_id"])
        self.assertEqual(effective["class_name"], "fullbody_bare")
        self.assertEqual(effective["bbox_xyxy"], corrected_bbox)
        with self.database.connect() as connection:
            original = connection.execute(
                "SELECT class_id,class_name,x1,y1,x2,y2 FROM yolo_detections WHERE id=?",
                (combined["detection_id"],),
            ).fetchone()
            correction = connection.execute(
                "SELECT corrected_payload_json FROM correction_records WHERE id=?",
                (correction_id,),
            ).fetchone()
        self.assertEqual(tuple(original), (32, "fullbody_bottomless", 40.0, 35.0, 140.0, 185.0))
        payload = json.loads(correction["corrected_payload_json"])
        self.assertTrue(payload["class_correction"])
        self.assertTrue(payload["bbox_correction"])

        invalid = self.database.record_yolo_detection(
            self.source_id, model_id="legacy-fixture", model_digest="legacy",
            class_id=32, class_name="fullbody_bottomless", confidence=.8,
            bbox_xyxy=[10, 10, 100, 100])
        with self.assertRaisesRegex(ValueError, "within source image"):
            self.database.save_yolo_annotation_correction(
                invalid["proposal_id"], self.class_ids["fullbody_clothed"], REGISTRY_ID,
                bbox_xyxy=[20, 20, 10, 30])
        with self.database.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM correction_records WHERE proposal_id=?",
                (invalid["proposal_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_four_confirmed_cnn_crops_exist_without_user_facing_export(self):
        proposals = self._four_confirmed_fullbody_crops()
        examples = [row for row in self.database.current_training_examples(
            "unified_body_images_fullbody", task_head="fullbody")
                    if row["proposal_id"] in proposals]
        self.assertEqual(len(examples), 4)
        self.assertEqual(self.database.normal_crop_export_count(), 0)
        self.assertFalse((self.root / "normal_output").exists())

    def test_four_confirmed_cnn_crops_with_user_facing_export(self):
        proposals = self._four_confirmed_fullbody_crops()
        output_root = self.root / "normal_output"
        plan = build_normal_output_plan(self.database, output_root, proposals)
        self.assertEqual(plan["item_count"], 4, plan["skipped"])
        result = export_normal_output(self.database, plan)
        self.assertEqual((result["written_count"], result["failure_count"]), (4, 0),
                         result["failures"])
        files = list(output_root.rglob("*.webp"))
        self.assertEqual(len(files), 4)
        examples = [row for row in self.database.current_training_examples(
            "unified_body_images_fullbody", task_head="fullbody")
                    if row["proposal_id"] in proposals]
        self.assertEqual(len(examples), 4)

    def test_four_crops_import_into_studio_idempotently(self):
        proposals = self._four_confirmed_fullbody_crops()
        examples = [row for row in self.database.current_training_examples(
            "unified_body_images_fullbody", task_head="fullbody")
                    if row["proposal_id"] in proposals]
        self.assertEqual(len(examples), 4)

        bundle = export_training_source_bundle(self.database, self.root / "bundles")
        manifest = json.loads(Path(bundle["manifest"]).read_text(encoding="utf-8"))
        cnn_records = [row for row in manifest["records"]
                       if row["task"] == "fullbody_state_classification"]
        self.assertEqual(len(cnn_records), 4)
        self.assertTrue(all(row["media"]["role"] == "authoritative_detection_crop"
                            for row in cnn_records))
        self.assertEqual({row["labels"]["class_label"] for row in cnn_records},
                         {"clothed", "bra", "panty", "topless"})

        config = StudioConfig(root=self.root / "studio")
        config.ensure_directories()
        shutil.copytree(ROOT / "TrainingDatasetStudio" / "contracts",
                        config.contract_dir, dirs_exist_ok=True)
        store = StudioStore(config.database_path)
        store.initialize()
        importer = BundleImporter(config, store)
        imported = importer.import_bundle(bundle["directory"])
        self.assertEqual((imported["accepted"], imported["quarantined"]), (4, 0))
        records = [row for row in store.list_records(task="fullbody_state_classification")
                   if row["status"] == "accepted"]
        self.assertEqual(len(records), 4)
        self.assertTrue(all(Path(row["media_path"]).is_file() for row in records))
        duplicate = importer.import_bundle(bundle["directory"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual((duplicate["record_count"], duplicate["accepted"]), (0, 0))
        self.assertEqual(len(store.list_records(task="fullbody_state_classification")), 4)


if __name__ == "__main__":
    unittest.main()
