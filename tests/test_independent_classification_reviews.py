from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.training_source_exporter import export_training_source_bundle
from app.core.dataset_exporter import export_yolo_dataset
from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.importer import BundleImporter
from TrainingDatasetStudio.studio.store import StudioStore


ROOT = Path(__file__).resolve().parents[1]


class IndependentClassificationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="independent_task_review_")
        self.root = Path(self.temp.name)
        source = self.root / "source.png"
        Image.new("RGB", (160, 120), "teal").save(source)
        self.database = Database(self.root / "app.sqlite3")
        self.database.initialize()
        self.source_id, _ = self.database.upsert_source_image({
            "path": str(source.resolve()),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "width": 160, "height": 120, "file_size": source.stat().st_size,
            "modified_ns": source.stat().st_mtime_ns,
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_timestamp_migration_preserves_existing_rows_without_backfilling(self):
        path = self.root / "legacy.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            connection.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(19,'legacy-migration')")
            connection.execute(
                """CREATE TABLE classification_task_reviews(
                   id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
                   confirmation_status TEXT NOT NULL,human_confirmed INTEGER NOT NULL)""")
            connection.execute(
                """INSERT INTO classification_task_reviews
                   (id,created_at,confirmation_status,human_confirmed)
                   VALUES(1,'2026-01-02 03:04:05','confirmed',1)""")
        connection.close()
        legacy = Database(path)
        legacy.initialize()
        with legacy.connect() as connection:
            row = connection.execute(
                "SELECT created_at,confirmed_at,staled_at FROM classification_task_reviews WHERE id=1"
            ).fetchone()
            version = connection.execute(
                "SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        from app.core.database import SCHEMA_VERSION
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertEqual(tuple(row), ("2026-01-02 03:04:05", None, None))

    def test_timestamp_migration_rolls_back_partial_ddl_on_failure(self):
        path = self.root / "failed_migration.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            connection.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(19,'legacy-migration')")
            connection.execute(
                """CREATE TABLE classification_task_reviews(
                   id INTEGER PRIMARY KEY, confirmation_status TEXT NOT NULL,
                   staled_at TEXT)""")
        connection.close()
        legacy = Database(path)
        with self.assertRaises(sqlite3.OperationalError):
            legacy.initialize()
        with legacy.connect() as connection:
            columns = {row["name"] for row in connection.execute(
                "PRAGMA table_info(classification_task_reviews)")}
            version = connection.execute(
                "SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        self.assertNotIn("confirmed_at", columns)
        self.assertEqual(version, 19)

    def _detection(self, class_id: int, name: str):
        return self.database.record_yolo_detection(
            self.source_id, model_id="fixture", model_digest="synthetic-yolo-v1",
            class_id=class_id, class_name=name, confidence=.91,
            bbox_xyxy=[10, 12, 145, 112])

    def _confirm(self, proposal, task, label, **payload_overrides):
        return self.database.save_classification_task_review(
            proposal["proposal_id"], task, label,
            {"validity_state": "valid", "subtags": ["slut"], **payload_overrides},
            action="confirmed", training_eligible=True)

    def _heads(self, proposal_id):
        return {(row["task_head"], row["class_label"])
                for row in self.database.current_training_examples()
                if row["proposal_id"] == proposal_id}

    def test_manual_detection_requires_approved_class_and_has_one_proposal_crop(self):
        with self.assertRaisesRegex(ValueError, "Choose a canonical YOLO class"):
            self.database.create_manual_detection(self.source_id, [10, 12, 145, 112])
        with self.assertRaisesRegex(ValueError, "Choose a class"):
            self.database.create_manual_detection(
                self.source_id, [10, 12, 145, 112],
                class_id=999, registry_id="newassetapp_yolo_detector_v1")
        detection_id = self.database.create_manual_detection(
            self.source_id, [10, 12, 145, 112],
            class_id=1, registry_id="newassetapp_yolo_detector_v1")
        first = self.database.ensure_active_detection_crop(detection_id)
        second = self.database.ensure_active_detection_crop(detection_id)
        self.assertEqual(first["crop_id"], second["crop_id"])
        box = next(row for row in self.database.detections_for_source(self.source_id)
                   if row["id"] == detection_id)
        self.assertEqual(box["class_name"], "face")
        self.assertEqual(box["annotation_class_name"], "face")
        with self.database.connect() as connection:
            proposal_count = connection.execute(
                "SELECT COUNT(*) FROM asset_proposals WHERE detection_id=?",
                (detection_id,),
            ).fetchone()[0]
        self.assertEqual(proposal_count, 1)

    def test_person_effective_eligibility_excludes_fullbody(self):
        person = self._detection(0, "person")
        state = self.database.effective_detection_state(person["proposal_id"])
        self.assertEqual(set(state["eligible_tasks"]), {"arousal", "corruption"})
        with self.assertRaisesRegex(ValueError, "person region"):
            self.database.save_normal_crop_choice(
                person["proposal_id"], "fullbody",
                main_tag="maid", fullbody_state="clothed")

    def test_normal_suggestion_approve_and_reject_touch_only_one_task(self):
        face = self._detection(1, "face")
        approve_id = self.database.save_normal_suggestion_review(
            face["proposal_id"], "draft")
        rejected_id = self.database.save_normal_suggestion_review(
            face["proposal_id"], "rejected")
        statuses = self.database.classification_task_status(face["proposal_id"])
        self.assertEqual(statuses["body_images"]["target_label"], "bodypart_face")
        self.assertEqual(statuses["body_images"]["confirmation_status"], "rejected")
        self.assertEqual(statuses["body_images"]["human_confirmed"], 0)
        self.assertEqual(statuses["body_images"]["training_eligible"], 0)
        self.assertNotEqual(approve_id, rejected_id)

    def test_normal_crop_invalid_is_proposal_scoped_and_restorable(self):
        face = self._detection(1, "face")
        sibling_source = self.root / "sibling.png"
        Image.new("RGB", (160, 120), "purple").save(sibling_source)
        sibling_source_id, _ = self.database.upsert_source_image({
            "path": str(sibling_source.resolve()),
            "sha256": hashlib.sha256(sibling_source.read_bytes()).hexdigest(),
            "width": 160, "height": 120, "file_size": sibling_source.stat().st_size,
            "modified_ns": sibling_source.stat().st_mtime_ns,
        })
        sibling = self.database.record_yolo_detection(
            sibling_source_id, model_id="fixture", model_digest="synthetic-yolo-v1",
            class_id=1, class_name="face", confidence=.91,
            bbox_xyxy=[10, 12, 145, 112])
        self.database.save_normal_crop_choice(face["proposal_id"], "invalid")
        face_row = next(row for row in self.database.normal_crop_records()
                        if row["id"] == face["proposal_id"])
        sibling_row = next(row for row in self.database.normal_crop_records()
                           if row["id"] == sibling["proposal_id"])
        self.assertTrue(face_row["normal_is_invalid"])
        self.assertFalse(sibling_row["normal_is_invalid"])
        self.database.restore_normal_crop_invalid(face["proposal_id"])
        face_row = next(row for row in self.database.normal_crop_records()
                        if row["id"] == face["proposal_id"])
        self.assertFalse(face_row["normal_is_invalid"])

    def test_face_corruption_conservative_saves_without_sibling_task_overwrite(self):
        face = self._detection(1, "face")
        self._confirm(face, "body_images", "bodypart_acc")
        self._confirm(face, "corruption", "conservative")
        statuses = self.database.classification_task_status(face["proposal_id"])
        self.assertEqual(statuses["body_images"]["target_label"], "bodypart_acc")
        self.assertEqual(statuses["corruption"]["target_label"], "conservative")
        self.assertIn("model_verified", statuses["corruption"])
        self.assertIn("model_confidence", statuses["corruption"])
        self.assertIn("confidence_threshold", statuses["corruption"])
        self.assertEqual(self._heads(face["proposal_id"]), {
            ("body_images", "bodypart_acc"),
            ("corruption", "conservative"),
        })

    def test_unchanged_bbox_approval_has_no_geometry_revision_and_creates_yolo_example(self):
        face = self._detection(1, "face")
        before = self.database.save_bbox_edit if False else None
        correction_count = 0
        with self.database.connect() as connection:
            correction_count = connection.execute(
                "SELECT COUNT(*) FROM correction_records WHERE detection_id=?",
                (face["detection_id"],),
            ).fetchone()[0]
        review_id = self.database.approve_unchanged_bbox(face["detection_id"])
        with self.database.connect() as connection:
            review = connection.execute(
                "SELECT * FROM yolo_bbox_reviews WHERE id=?", (review_id,)
            ).fetchone()
            after_count = connection.execute(
                "SELECT COUNT(*) FROM correction_records WHERE detection_id=?",
                (face["detection_id"],),
            ).fetchone()[0]
            example = connection.execute(
                "SELECT * FROM training_examples WHERE proposal_id=? AND task='yolo_detector' "
                "ORDER BY id DESC LIMIT 1", (face["proposal_id"],)
            ).fetchone()
        self.assertEqual(tuple(json.loads(review["effective_bbox_xyxy"])),
                         (10.0, 12.0, 145.0, 112.0))
        self.assertEqual(review["review_status"], "approved")
        self.assertEqual(review["human_confirmed"], 1)
        self.assertIsNone(review["bbox_revision"])
        self.assertEqual(after_count, correction_count)
        self.assertIsNotNone(example)
        self.assertEqual(example["bbox_review_id"], review_id)
        canonical = self.database.current_training_examples("yolo_detector")
        self.assertTrue(any(row["proposal_id"] == face["proposal_id"] for row in canonical))
        exported = export_yolo_dataset(
            self.database, self.root / "bbox_yolo_export",
            source_roots=[self.root])
        self.assertEqual(exported["annotation_count"], 1)
        label_file = next((Path(exported["directory"]) / "labels").rglob("*.txt"))
        self.assertEqual(label_file.read_text(encoding="utf-8"),
                         "1 0.48437500 0.51666667 0.84375000 0.83333333\n")
        bundle = export_training_source_bundle(
            self.database, self.root / "bbox_studio_handoff")
        manifest = json.loads(Path(bundle["manifest"]).read_text(encoding="utf-8"))
        yolo_records = [row for row in manifest["records"]
                        if row["task"] == "yolo_detection"]
        self.assertTrue(yolo_records)
        self.assertEqual(yolo_records[0]["provenance"]["bbox_review"]["review_status"], "approved")

    def test_face_body_images_and_arousal_confirm_independently(self):
        face = self._detection(1, "face")
        self._confirm(face, "body_images", "bodypart_acc")
        self.assertEqual(self._heads(face["proposal_id"]), {("body_images", "bodypart_acc")})
        self._confirm(face, "arousal", "edging")
        self.assertEqual(self._heads(face["proposal_id"]), {
            ("body_images", "bodypart_acc"), ("arousal", "edging")})

    def test_portrait_frame_body_images_binary_task_needs_no_body_part_main_tag(self):
        frame = self._detection(2, "portrait_frame")
        self.database.save_classification_task_review(
            frame["proposal_id"], "body_images", "body_images_pending",
            {
                "validity_state": "valid",
                "cum_target": False,
                "cum_evaluated": True,
                "accessory_target": True,
                "accessory_evaluated": True,
                "body_images_completed": True,
            },
            action="confirmed", training_eligible=True,
        )
        status = self.database.classification_task_status(frame["proposal_id"])["body_images"]
        self.assertTrue(status["human_confirmed"])
        self.assertTrue(status["training_eligible"])
        self.assertTrue(status["cum_evaluated"])
        self.assertFalse(status["cum_target"])
        self.assertTrue(status["accessory_evaluated"])
        self.assertTrue(status["accessory_target"])

    def test_body_region_heads_and_arousal_eligibility(self):
        for class_id, region in ((1, "face"), (4, "ass"), (5, "pussy"), (6, "legs")):
            with self.subTest(region=region):
                row = self._detection(class_id, region)
                self._confirm(row, "body_images", "bodypart_cum")
                self._confirm(row, "arousal", "aroused")
                self.assertEqual(self._heads(row["proposal_id"]), {
                    ("body_images", "bodypart_cum"), ("arousal", "aroused")})
        person = self._detection(0, "person")
        self._confirm(person, "corruption", "slut")
        self._confirm(person, "arousal", "aroused")
        self.assertEqual(self._heads(person["proposal_id"]), {
            ("corruption", "slut"), ("arousal", "aroused")})
        for class_id, region in ():
            row = self._detection(class_id, region)
            with self.subTest(ineligible=region), self.assertRaisesRegex(ValueError, "not eligible"):
                self._confirm(row, "arousal", "aroused")

    def test_portrait_arousal_and_corruption_are_separate_task_records(self):
        frame = self._detection(2, "portrait_frame")
        self._confirm(frame, "arousal", "aroused")
        self.assertEqual(self._heads(frame["proposal_id"]), {("arousal", "aroused")})
        self._confirm(frame, "portrait", "portrait")
        self.assertEqual(self._heads(frame["proposal_id"]), {
            ("portrait", "portrait"), ("arousal", "aroused")})
        self._confirm(frame, "arousal", "aroused")
        self._confirm(frame, "corruption", "conservative")
        self.assertEqual(self._heads(frame["proposal_id"]), {
            ("portrait", "portrait"), ("arousal", "aroused"), ("corruption", "conservative")})
        statuses = self.database.classification_task_status(frame["proposal_id"])
        self.assertTrue(all(statuses[head]["human_confirmed"]
                            for head in ("portrait", "arousal", "corruption")))

    def test_corruption_eligibility_follows_detection_class_not_proposal_category(self):
        cases = (
            (0, "person", "others", None, None),
            (2, "portrait_frame", "body_images", "portrait", "portrait"),
            (20, "fullbody_clothed", "fullbody", "fullbody", "clothed"),
        )
        for class_id, region, expected_category, sibling_head, sibling_label in cases:
            with self.subTest(region=region):
                detection = self._detection(class_id, region)
                with self.database.connect() as connection:
                    category = connection.execute(
                        "SELECT category FROM asset_proposals WHERE id=?",
                        (detection["proposal_id"],),
                    ).fetchone()["category"]
                self.assertEqual(category, expected_category)

                if sibling_head:
                    self._confirm(detection, sibling_head, sibling_label)
                self._confirm(detection, "corruption", "slut")
                self._confirm(detection, "corruption", "whore")

                expected_heads = {("corruption", "whore")}
                if sibling_head:
                    expected_heads.add((sibling_head, sibling_label))
                self.assertEqual(self._heads(detection["proposal_id"]), expected_heads)
                statuses = self.database.classification_task_status(detection["proposal_id"])
                self.assertEqual(statuses["corruption"]["target_label"], "whore")
                self.assertTrue(statuses["corruption"]["human_confirmed"])
                if sibling_head:
                    self.assertEqual(statuses[sibling_head]["target_label"], sibling_label)
                    self.assertTrue(statuses[sibling_head]["human_confirmed"])

    def test_corruption_crop_revision_stales_and_replaces_each_eligible_group(self):
        for class_id, region in (
                (0, "person"), (2, "portrait_frame"), (20, "fullbody_clothed")):
            with self.subTest(region=region):
                detection = self._detection(class_id, region)
                self._confirm(detection, "corruption", "slut")
                self.database.save_bbox_edit(detection["detection_id"], [8, 10, 150, 110])

                status = self.database.classification_task_status(
                    detection["proposal_id"])["corruption"]
                self.assertEqual(status["confirmation_status"], "stale")
                self.assertFalse(status["human_confirmed"])
                self.assertEqual(self._heads(detection["proposal_id"]), set())

                self._confirm(detection, "corruption", "conservative")
                row = next(item for item in self.database.current_training_examples()
                           if item["proposal_id"] == detection["proposal_id"]
                           and item["task_head"] == "corruption")
                self.assertEqual(row["crop_bbox_xyxy"], [8.0, 10.0, 150.0, 110.0])
                self.assertEqual(self._heads(detection["proposal_id"]),
                                 {("corruption", "conservative")})

    def test_rejecting_one_head_suppresses_only_its_current_training_example(self):
        face = self._detection(1, "face")
        self._confirm(face, "body_images", "bodypart_acc")
        self._confirm(face, "arousal", "aroused")
        self.database.save_classification_task_review(
            face["proposal_id"], "arousal", "aroused", {"validity_state": "valid"},
            action="rejected", training_eligible=False)
        self.assertEqual(self._heads(face["proposal_id"]), {("body_images", "bodypart_acc")})
        statuses = self.database.classification_task_status(face["proposal_id"])
        self.assertEqual(statuses["arousal"]["confirmation_status"], "rejected")
        self.assertEqual(statuses["body_images"]["confirmation_status"], "confirmed")

    def test_bbox_change_stales_confirmations_and_requires_per_head_reconfirmation(self):
        face = self._detection(1, "face")
        self._confirm(face, "body_images", "bodypart_acc")
        self._confirm(face, "arousal", "edging")
        with self.database.connect() as connection:
            detection_id = connection.execute(
                "SELECT detection_id FROM asset_proposals WHERE id=?", (face["proposal_id"],)
            ).fetchone()[0]
        self.database.save_bbox_edit(detection_id, [5, 5, 155, 115])
        statuses = self.database.classification_task_status(face["proposal_id"])
        self.assertEqual(statuses["body_images"]["confirmation_status"], "stale")
        self.assertEqual(statuses["arousal"]["confirmation_status"], "stale")
        self.assertEqual(self._heads(face["proposal_id"]), set())
        self._confirm(face, "arousal", "edging")
        remaining = self.database.current_training_examples()
        row = next(item for item in remaining if item["proposal_id"] == face["proposal_id"])
        self.assertEqual((row["task_head"], row["crop_bbox_xyxy"]),
                         ("arousal", [5.0, 5.0, 155.0, 115.0]))
        self.assertEqual(self._heads(face["proposal_id"]), {("arousal", "edging")})

    def test_orphan_proposal_detection_actions_fail_without_mutating_state(self):
        proposal_id = self.database.create_manual_proposal(self.source_id)
        with self.database.connect() as connection:
            before_status = connection.execute(
                "SELECT review_status FROM asset_proposals WHERE id=?",
                (proposal_id,),
            ).fetchone()["review_status"]
            before_corrections = connection.execute(
                "SELECT COUNT(*) FROM correction_records WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()[0]
            before_reviews = connection.execute(
                "SELECT COUNT(*) FROM classification_task_reviews WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()[0]

        with self.assertRaisesRegex(ValueError, "proposal with a source detection"):
            self.database.save_classification_task_review(
                proposal_id, "corruption", "slut", {"validity_state": "valid"},
                action="confirmed", training_eligible=True)
        with self.assertRaisesRegex(ValueError, "persisted Detection|persisted detection"):
            self.database.save_yolo_class_correction(
                proposal_id, 2, "newassetapp_yolo_detector_v1")

        with self.database.connect() as connection:
            after_status = connection.execute(
                "SELECT review_status FROM asset_proposals WHERE id=?",
                (proposal_id,),
            ).fetchone()["review_status"]
            after_corrections = connection.execute(
                "SELECT COUNT(*) FROM correction_records WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()[0]
            after_reviews = connection.execute(
                "SELECT COUNT(*) FROM classification_task_reviews WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()[0]
        self.assertEqual(after_status, before_status)
        self.assertEqual(after_corrections, before_corrections)
        self.assertEqual(after_reviews, before_reviews)

    def test_location_requires_its_own_location_group_detection(self):
        face = self._detection(1, "face")
        with self.assertRaisesRegex(ValueError, "location_group"):
            self._confirm(face, "location", "beach")
        location = self._detection(28, "location_beach")
        review_id = self.database.save_classification_task_review(
            location["proposal_id"], "location", "beach", {"validity_state": "valid"},
            action="confirmed", training_eligible=False)
        status = self.database.classification_task_status(location["proposal_id"])["location"]
        self.assertEqual(status["id"], review_id)
        self.assertEqual(status["confirmation_status"], "confirmed")
        self.assertEqual(self._heads(location["proposal_id"]), set())

    def test_body_images_confirmation_does_not_require_corruption_training_fields(self):
        proposal_id = self.database.create_manual_proposal(self.source_id)
        correction_id = self.database.save_correction(
            proposal_id,
            {"category": "body_images", "main_tag": "face", "validity_state": "valid"},
            decision_type="classification_confirmation", final_state="confirmed",
            corruption_training_eligible=False,
        )
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT final_state,corruption_training_eligible,corrected_payload_json "
                "FROM correction_records WHERE id=?", (correction_id,)
            ).fetchone()
        self.assertEqual(row["final_state"], "confirmed")
        self.assertFalse(row["corruption_training_eligible"])
        self.assertEqual(json.loads(row["corrected_payload_json"])["main_tag"], "face")

        face = self._detection(1, "face")
        self._confirm(face, "body_images", "bodypart_acc")
        status = self.database.classification_task_status(face["proposal_id"])
        self.assertEqual(status["body_images"]["confirmation_status"], "confirmed")
        self.assertNotIn("corruption", status)
        self.assertEqual(self._heads(face["proposal_id"]),
                         {("body_images", "bodypart_acc")})

    def test_corruption_training_requires_human_target_and_reviewed_crop(self):
        for missing in ("target", "crop"):
            proposal_id = self.database.create_manual_proposal(self.source_id)
            payload = {
                "category": "others", "validity_state": "valid",
                "corruption_classifier_target": None if missing == "target" else "slut",
                "bbox_xyxy": None if missing == "crop" else [10, 12, 145, 112],
            }
            with self.subTest(missing=missing), self.assertRaisesRegex(
                    ValueError, "Corruption-state training needs one human-selected target"):
                self.database.save_correction(
                    proposal_id, payload,
                    decision_type="classification_confirmation", final_state="confirmed",
                    corruption_training_eligible=True,
                )

    def test_valid_legacy_person_corruption_record_saves_with_required_target_and_crop(self):
        proposal_id = self.database.create_manual_proposal(self.source_id)
        correction_id = self.database.save_correction(
            proposal_id,
            {"category": "others", "validity_state": "valid",
             "corruption_classifier_target": "slut", "bbox_xyxy": [10, 12, 145, 112]},
            decision_type="classification_confirmation", final_state="confirmed",
            corruption_training_eligible=True,
        )
        rows = self.database.current_corruption_training_examples()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["correction_record_id"], correction_id)
        self.assertEqual(rows[0]["class_label"], "slut")
        self.assertEqual(rows[0]["crop_bbox_xyxy"], [10.0, 12.0, 145.0, 112.0])

    def test_clothing_broad_and_detailed_tasks_are_separately_confirmed(self):
        # The installed 32-class YOLO checkpoint uses class 10 for this name.
        clothing = self._detection(10, "boobs_cover_item")
        self._confirm(clothing, "clothing_broad", "footwear")
        self.assertEqual({(row["task"], row["class_label"])
                          for row in self.database.current_training_examples()
                          if row["proposal_id"] == clothing["proposal_id"]},
                         {("clothing_broad", "footwear")})
        self._confirm(clothing, "clothing_fine", "heels", clothing_family_tag="footwear")
        self.assertEqual({(row["task"], row["class_label"])
                          for row in self.database.current_training_examples()
                          if row["proposal_id"] == clothing["proposal_id"]},
                         {("clothing_broad", "footwear"), ("clothing_fine", "heels")})

    def test_task_timestamps_are_independent_and_bbox_staling_preserves_confirmation_time(self):
        face = self._detection(1, "face")
        body_review_id = self._confirm(face, "body_images", "bodypart_acc")
        draft_id = self.database.save_classification_task_review(
            face["proposal_id"], "arousal", "edging", {"validity_state": "valid"},
            action="draft", training_eligible=False)
        person = self._detection(0, "person")
        rejected_id = self.database.save_classification_task_review(
            person["proposal_id"], "corruption", "slut", {"validity_state": "valid"},
            action="rejected", training_eligible=False)

        with self.database.connect() as connection:
            body = connection.execute(
                "SELECT confirmed_at,staled_at FROM classification_task_reviews WHERE id=?",
                (body_review_id,),
            ).fetchone()
            draft = connection.execute(
                "SELECT confirmed_at,staled_at FROM classification_task_reviews WHERE id=?",
                (draft_id,),
            ).fetchone()
            rejected = connection.execute(
                "SELECT confirmed_at,staled_at FROM classification_task_reviews WHERE id=?",
                (rejected_id,),
            ).fetchone()
            detection_id = connection.execute(
                "SELECT detection_id FROM asset_proposals WHERE id=?",
                (face["proposal_id"],),
            ).fetchone()[0]
        self.assertIsNotNone(body["confirmed_at"])
        self.assertIsNone(body["staled_at"])
        self.assertEqual((draft["confirmed_at"], draft["staled_at"]), (None, None))
        self.assertEqual((rejected["confirmed_at"], rejected["staled_at"]), (None, None))

        self.database.save_bbox_edit(detection_id, [5, 5, 155, 115])
        with self.database.connect() as connection:
            stale = connection.execute(
                """SELECT confirmed_at,staled_at FROM classification_task_reviews
                   WHERE supersedes_id=?""", (body_review_id,)
            ).fetchone()
        self.assertEqual(stale["confirmed_at"], body["confirmed_at"])
        self.assertIsNotNone(stale["staled_at"])

    def test_class_correction_preserves_raw_detection_and_stales_task_reviews(self):
        face = self._detection(1, "face")
        review_id = self._confirm(face, "body_images", "bodypart_acc")
        with self.database.connect() as connection:
            detection_id = connection.execute(
                "SELECT detection_id FROM asset_proposals WHERE id=?",
                (face["proposal_id"],),
            ).fetchone()[0]
        correction_id = self.database.save_yolo_class_correction(
            face["proposal_id"], 0, "newassetapp_yolo_detector_v1")
        with self.database.connect() as connection:
            detection = connection.execute(
                "SELECT class_id,class_name,x1,y1,x2,y2 FROM yolo_detections WHERE id=?",
                (detection_id,),
            ).fetchone()
            correction = connection.execute(
                "SELECT original_snapshot_json,corrected_payload_json FROM correction_records WHERE id=?",
                (correction_id,),
            ).fetchone()
            reviews = connection.execute(
                """SELECT id,confirmation_status,supersedes_id
                   FROM classification_task_reviews WHERE proposal_id=? ORDER BY id""",
                (face["proposal_id"],),
            ).fetchall()
            suppressions = connection.execute(
                """SELECT COUNT(*) FROM training_example_suppressions
                   WHERE task_review_id IN (
                     SELECT id FROM classification_task_reviews
                     WHERE proposal_id=? AND confirmation_status='stale')""",
                (face["proposal_id"],),
            ).fetchone()[0]
        self.assertEqual(tuple(detection), (1, "face", 10.0, 12.0, 145.0, 112.0))
        original = json.loads(correction["original_snapshot_json"])
        corrected = json.loads(correction["corrected_payload_json"])
        self.assertEqual(original["yolo"]["class_name"], "face")
        self.assertEqual(corrected["yolo_annotation_class_name"], "person")
        self.assertEqual(corrected["bbox_xyxy"], [10.0, 12.0, 145.0, 112.0])
        self.assertEqual(len(reviews), 2)
        self.assertEqual((reviews[0]["id"], reviews[0]["confirmation_status"],
                          reviews[0]["supersedes_id"]), (review_id, "confirmed", None))
        self.assertGreater(reviews[1]["id"], review_id)
        self.assertEqual((reviews[1]["confirmation_status"], reviews[1]["supersedes_id"]),
                         ("stale", review_id))
        self.assertEqual(suppressions, 1)
        self.assertNotIn(("body_images", "bodypart_acc"), self._heads(face["proposal_id"]))

    def test_corrected_yolo_annotation_exports_and_hands_off_latest_saved_correction(self):
        source_path = self.root / "corrected_yolo_source.png"
        Image.new("RGB", (200, 200), "purple").save(source_path)
        source_id, _ = self.database.upsert_source_image({
            "path": str(source_path.resolve()),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "width": 200, "height": 200, "file_size": source_path.stat().st_size,
            "modified_ns": source_path.stat().st_mtime_ns,
        })
        detection = self.database.record_yolo_detection(
            source_id, model_id="fixture", model_digest="original-model",
            class_id=0, class_name="person", confidence=.91,
            bbox_xyxy=[10, 20, 100, 150])
        registry = json.loads((ROOT / "TrainingDatasetStudio" / "registries" /
                               "yolo_detector_v1.json").read_text(encoding="utf-8"))
        target_class = next(row for row in registry["classes"]
                            if row["name"] == "portrait_frame")

        # The GUI persists geometry edits first, then saves class + effective geometry atomically.
        self.database.save_bbox_edit(detection["detection_id"], [25, 30, 120, 170])
        correction_id = self.database.save_yolo_annotation_correction(
            detection["proposal_id"], target_class["id"], registry["registry_id"],
            bbox_xyxy=[25, 30, 120, 170])

        with self.database.connect() as connection:
            original = connection.execute(
                "SELECT class_name,x1,y1,x2,y2 FROM yolo_detections WHERE id=?",
                (detection["detection_id"],),
            ).fetchone()
            correction = connection.execute(
                "SELECT * FROM correction_records WHERE id=?", (correction_id,)
            ).fetchone()
            first_example = connection.execute(
                "SELECT * FROM training_examples WHERE correction_record_id=?",
                (correction_id,),
            ).fetchone()
        self.assertEqual(tuple(original), ("person", 10.0, 20.0, 100.0, 150.0))
        corrected_payload = json.loads(correction["corrected_payload_json"])
        self.assertEqual(corrected_payload["yolo_annotation_class_name"], "portrait_frame")
        self.assertEqual(corrected_payload["bbox_xyxy"], [25.0, 30.0, 120.0, 170.0])
        self.assertEqual(correction["final_state"], "confirmed")
        self.assertEqual(first_example["class_label"], "portrait_frame")
        self.assertEqual(json.loads(first_example["crop_bbox_json"]),
                         [25.0, 30.0, 120.0, 170.0])
        self.assertEqual(first_example["detection_id"], detection["detection_id"])

        canonical = [row for row in self.database.current_training_examples("yolo_detector")
                     if row["detection_id"] == detection["detection_id"]]
        self.assertEqual(len(canonical), 1)
        self.assertEqual(canonical[0]["class_label"], "portrait_frame")
        self.assertEqual(canonical[0]["crop_bbox_xyxy"], [25.0, 30.0, 120.0, 170.0])

        first_export = export_yolo_dataset(
            self.database, self.root / "corrected_yolo_export",
            source_roots=[self.root])
        repeated_export = export_yolo_dataset(
            self.database, self.root / "corrected_yolo_export_again",
            source_roots=[self.root])
        self.assertEqual(first_export["annotation_count"], 1)
        self.assertEqual(repeated_export["annotation_count"], 1)
        label_file = next((Path(first_export["directory"]) / "labels").rglob("*.txt"))
        self.assertEqual(label_file.read_text(encoding="utf-8"),
                         "2 0.36250000 0.50000000 0.47500000 0.70000000\n")
        class_map = json.loads((Path(first_export["directory"]) / "class_map.json")
                               .read_text(encoding="utf-8"))
        self.assertEqual(class_map["export_to_original_class_id"]["2"], target_class["id"])

        bundle = export_training_source_bundle(
            self.database, self.root / "corrected_studio_handoff")
        manifest = json.loads(Path(bundle["manifest"]).read_text(encoding="utf-8"))
        handoff = next(row for row in manifest["records"] if row["task"] == "yolo_detection")
        self.assertEqual(handoff["annotation"]["target_class_id"], target_class["id"])
        self.assertEqual(handoff["annotation"]["target_bbox_xyxy"], [25.0, 30.0, 120.0, 170.0])
        self.assertTrue(any(event["correction_record_id"] == str(correction_id)
                            for event in handoff["provenance"]["correction_events"]))

        studio_config = StudioConfig(root=self.root / "corrected_studio")
        studio_config.ensure_directories()
        shutil.copytree(ROOT / "TrainingDatasetStudio" / "contracts",
                        studio_config.contract_dir, dirs_exist_ok=True)
        studio_store = StudioStore(studio_config.database_path)
        studio_store.initialize()
        imported = BundleImporter(studio_config, studio_store).import_bundle(bundle["directory"])
        self.assertEqual((imported["accepted"], imported["quarantined"]), (1, 0))
        studio_record = studio_store.list_records(task="yolo_detection")[0]
        self.assertEqual(studio_record["annotation"]["target_class_id"], target_class["id"])
        self.assertEqual(studio_record["annotation"]["bbox_xyxy"],
                         [25.0, 30.0, 120.0, 170.0])
        correction_events = studio_record["original"]["provenance"]["correction_events"]
        self.assertTrue(any(event["correction_record_id"] == str(correction_id)
                            for event in correction_events))
        from TrainingDatasetStudio.studio.datasets import DatasetService
        dataset_service = DatasetService(studio_store, studio_config.output_dir)
        dataset_id = dataset_service.create_dataset(
            "corrected YOLO", "yolo_detection", studio_record["registry_id"],
            studio_record["registry_version"],
            training_bundle_id=studio_record["training_bundle_id"])
        version_id = dataset_service.create_version(dataset_id)
        dataset_service.finalize(version_id)
        studio_package = studio_config.output_dir / "corrected_yolo_package"
        dataset_service.export_colab(version_id, studio_package)
        studio_labels = list((studio_package / "dataset" / "labels").rglob("*.txt"))
        self.assertEqual(len(studio_labels), 1)
        self.assertEqual(studio_labels[0].read_text(encoding="utf-8"),
                         "2 0.36250000 0.50000000 0.47500000 0.70000000\n")

        later_class = next(row for row in registry["classes"] if row["name"] == "face")
        later_correction_id = self.database.save_yolo_annotation_correction(
            detection["proposal_id"], later_class["id"], registry["registry_id"],
            bbox_xyxy=[30, 40, 130, 180])
        with self.database.connect() as connection:
            latest_example = connection.execute(
                "SELECT * FROM training_examples WHERE correction_record_id=?",
                (later_correction_id,),
            ).fetchone()
        self.assertEqual(latest_example["supersedes_id"], first_example["id"])
        latest = [row for row in self.database.current_training_examples("yolo_detector")
                  if row["detection_id"] == detection["detection_id"]]
        self.assertEqual(len(latest), 1)
        self.assertEqual(latest[0]["class_label"], "face")
        self.assertEqual(latest[0]["crop_bbox_xyxy"], [30.0, 40.0, 130.0, 180.0])
        latest_export = export_yolo_dataset(
            self.database, self.root / "latest_yolo_export",
            source_roots=[self.root])
        self.assertEqual(latest_export["annotation_count"], 1)
        latest_label = next((Path(latest_export["directory"]) / "labels").rglob("*.txt"))
        self.assertEqual(latest_label.read_text(encoding="utf-8"),
                         "1 0.40000000 0.55000000 0.50000000 0.70000000\n")
        latest_bundle = export_training_source_bundle(
            self.database, self.root / "latest_studio_handoff")
        latest_manifest = json.loads(Path(latest_bundle["manifest"]).read_text(encoding="utf-8"))
        latest_handoff = next(row for row in latest_manifest["records"]
                              if row["task"] == "yolo_detection")
        self.assertEqual(len([row for row in latest_manifest["records"]
                              if row["task"] == "yolo_detection"]), 1)
        self.assertEqual(latest_handoff["labels"]["class_label"], "face")
        self.assertEqual(latest_handoff["annotation"]["target_class_id"], later_class["id"])
        self.assertEqual(latest_handoff["annotation"]["target_bbox_xyxy"],
                         [30.0, 40.0, 130.0, 180.0])
        latest_events = latest_handoff["provenance"]["correction_events"]
        self.assertTrue(any(event["correction_record_id"] == str(correction_id)
                            for event in latest_events))
        self.assertTrue(any(event["correction_record_id"] == str(later_correction_id)
                            for event in latest_events))

    def test_class_only_and_bbox_only_yolo_corrections_preserve_other_effective_value(self):
        source_path = self.root / "partial_corrections.png"
        Image.new("RGB", (200, 200), "orange").save(source_path)
        source_id, _ = self.database.upsert_source_image({
            "path": str(source_path.resolve()),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            "width": 200, "height": 200, "file_size": source_path.stat().st_size,
            "modified_ns": source_path.stat().st_mtime_ns,
        })
        registry = json.loads((ROOT / "TrainingDatasetStudio" / "registries" /
                               "yolo_detector_v1.json").read_text(encoding="utf-8"))
        portrait_id = next(row["id"] for row in registry["classes"]
                           if row["name"] == "portrait_frame")

        class_only = self.database.record_yolo_detection(
            source_id, model_id="fixture", model_digest="partial-test",
            class_id=0, class_name="person", confidence=.9,
            bbox_xyxy=[10, 10, 90, 90])
        self.database.save_yolo_annotation_correction(
            class_only["proposal_id"], portrait_id, registry["registry_id"])
        class_rows = [row for row in self.database.current_training_examples("yolo_detector")
                      if row["detection_id"] == class_only["detection_id"]]
        self.assertEqual(len(class_rows), 1)
        self.assertEqual(class_rows[0]["class_label"], "portrait_frame")
        self.assertEqual(class_rows[0]["crop_bbox_xyxy"], [10.0, 10.0, 90.0, 90.0])

        bbox_only = self.database.record_yolo_detection(
            source_id, model_id="fixture", model_digest="partial-test",
            class_id=0, class_name="person", confidence=.9,
            bbox_xyxy=[100, 10, 180, 90])
        self.database.save_yolo_annotation_correction(
            bbox_only["proposal_id"], None, registry["registry_id"],
            bbox_xyxy=[100, 20, 180, 100])
        bbox_rows = [row for row in self.database.current_training_examples("yolo_detector")
                     if row["detection_id"] == bbox_only["detection_id"]]
        self.assertEqual(len(bbox_rows), 1)
        self.assertEqual(bbox_rows[0]["class_label"], "person")
        self.assertEqual(bbox_rows[0]["crop_bbox_xyxy"], [100.0, 20.0, 180.0, 100.0])

    def test_failed_yolo_annotation_save_preserves_pending_state_and_authoritative_examples(self):
        detection = self._detection(0, "person")
        with self.database.connect() as connection:
            before_status = connection.execute(
                "SELECT review_status FROM asset_proposals WHERE id=?",
                (detection["proposal_id"],),
            ).fetchone()["review_status"]
        with self.assertRaisesRegex(ValueError, "within source image"):
            self.database.save_yolo_annotation_correction(
                detection["proposal_id"], 2, "newassetapp_yolo_detector_v1",
                bbox_xyxy=[20, 20, 10, 30])
        with self.database.connect() as connection:
            after_status = connection.execute(
                "SELECT review_status FROM asset_proposals WHERE id=?",
                (detection["proposal_id"],),
            ).fetchone()["review_status"]
            correction_count = connection.execute(
                "SELECT COUNT(*) FROM correction_records WHERE proposal_id=?",
                (detection["proposal_id"],),
            ).fetchone()[0]
            example_count = connection.execute(
                "SELECT COUNT(*) FROM training_examples WHERE proposal_id=? AND task='yolo_detector'",
                (detection["proposal_id"],),
            ).fetchone()[0]
        self.assertEqual(after_status, before_status)
        self.assertEqual(correction_count, 0)
        self.assertEqual(example_count, 0)
        self.assertFalse(any(row["detection_id"] == detection["detection_id"]
                             for row in self.database.current_training_examples("yolo_detector")))

    def test_independent_studio_export_excludes_draft_until_its_own_confirmation(self):
        frame = self._detection(2, "portrait_frame")
        self._confirm(frame, "portrait", "tportrait")
        self.database.save_classification_task_review(
            frame["proposal_id"], "arousal", "edging", {"validity_state": "valid"},
            action="draft", training_eligible=False)
        first_bundle = export_training_source_bundle(self.database, self.root / "handoff_one")
        manifest = json.loads(Path(first_bundle["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual({row["task_head"] for row in self.database.current_training_examples()
                          if row["proposal_id"] == frame["proposal_id"]}, {"portrait"})
        config = StudioConfig(root=self.root / "studio")
        config.ensure_directories()
        shutil.copytree(ROOT / "TrainingDatasetStudio" / "contracts", config.contract_dir, dirs_exist_ok=True)
        store = StudioStore(config.database_path)
        store.initialize()
        imported = BundleImporter(config, store).import_bundle(first_bundle["directory"])
        self.assertEqual(imported["quarantined"], 0)
        self.assertEqual(len(store.list_records(task="portrait_classification")), 1)
        self.assertEqual(len(store.list_records(task="arousal_classification")), 0)

        self._confirm(frame, "arousal", "edging")
        second_bundle = export_training_source_bundle(self.database, self.root / "handoff_two")
        imported_second = BundleImporter(config, store).import_bundle(second_bundle["directory"])
        self.assertEqual(imported_second["quarantined"], 0)
        self.assertEqual(len(store.list_records(task="portrait_classification")), 2)
        self.assertEqual(len(store.list_records(task="arousal_classification")), 1)


if __name__ == "__main__":
    unittest.main()
