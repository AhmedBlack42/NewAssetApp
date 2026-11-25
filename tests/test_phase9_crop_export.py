import hashlib
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image, ImageDraw

from app.core.database import Database
from app.core.crop_rules import clothing_cover_rule
from app.core.output_exporter import (
    _BIREFNET_ALPHA_CACHE,
    _preferred_birefnet_input_size,
    build_normal_output_plan,
    export_normal_output,
)


class Phase9CropExportTests(unittest.TestCase):
    def test_bra_cover_rule_is_explicit_and_leg_cover_stays_excluded_for_skirts_and_shorts(self):
        self.assertEqual(clothing_cover_rule("bra", "boobs_cover"),
                         ("boobs", "boobs_cover/bra"))
        for family in ("shorts", "skirt"):
            with self.assertRaisesRegex(ValueError, "valid guide cover area"):
                clothing_cover_rule(family, "leg_cover")
        with self.assertRaisesRegex(ValueError, "valid guide cover area"):
            clothing_cover_rule("bra", "")

    def test_birefnet_chooses_cpu_input_size_from_available_memory(self):
        gib = 1024 ** 3
        self.assertEqual(_preferred_birefnet_input_size(3 * gib), 384)
        self.assertEqual(_preferred_birefnet_input_size(5 * gib), 512)
        self.assertEqual(_preferred_birefnet_input_size(9 * gib), 768)
        self.assertEqual(_preferred_birefnet_input_size(14 * gib), 1024)
        self.assertEqual(_preferred_birefnet_input_size(None), 512)

    def setUp(self):
        _BIREFNET_ALPHA_CACHE.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        image = Image.new("RGBA", (900, 900), (18, 28, 38, 0))
        ImageDraw.Draw(image).ellipse((210, 100, 690, 800), fill=(220, 90, 120, 255))
        image.save(self.source)
        image.close()
        self.source_bytes = self.source.read_bytes()
        self.digest = hashlib.sha256(self.source_bytes).hexdigest()
        self.db = Database(self.root / "app.sqlite3")
        self.db.initialize()
        self.source_id, _ = self.db.upsert_source_image({
            "path": str(self.source.resolve()), "sha256": self.digest,
            "width": 900, "height": 900, "file_size": self.source.stat().st_size,
            "modified_ns": self.source.stat().st_mtime_ns,
        })

    def tearDown(self):
        _BIREFNET_ALPHA_CACHE.clear()
        self.temp.cleanup()

    def proposal(self, class_id, class_name, bbox=(100, 80, 800, 850)):
        row = self.db.record_yolo_detection(
            self.source_id, model_id="phase9-fixture", model_digest="fixture",
            class_id=class_id, class_name=class_name, confidence=.9,
            bbox_xyxy=list(bbox),
        )
        return int(row["proposal_id"])

    def export_one(self, proposal_id, output, **kwargs):
        plan = build_normal_output_plan(self.db, output, [proposal_id])
        return plan, export_normal_output(self.db, plan, **kwargs)

    def test_all_routes_write_webp_with_source_traceability_and_no_training_records(self):
        fullbody = self.proposal(20, "fullbody_clothed")
        body_image = self.proposal(1, "face", (250, 150, 650, 550))
        clothing = self.proposal(8, "boobs_cover_item", (250, 250, 650, 650))
        self.db.save_normal_crop_choice(fullbody, "fullbody", main_tag="clothed", fullbody_state="clothed")
        self.db.save_normal_crop_choice(body_image, "body_images", "face", main_tag="face")
        self.db.save_normal_crop_choice(clothing, "clothing", main_tag="dress",
                                        clothing_broad_family="dress",
                                        clothing_cover_area="boobs_cover")
        plan = build_normal_output_plan(
            self.db, self.root / "output", [fullbody, body_image, clothing]
        )
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 3)
        self.assertEqual(result["failure_count"], 0)
        for category, rows in (("fullbody", [fullbody]),
                               ("body_images", [body_image]),
                               ("clothing", [clothing])):
            files = list((self.root / "output" / category).rglob("*.webp"))
            self.assertEqual(len(files), 1)
            with Image.open(files[0]) as exported:
                self.assertEqual(exported.format, "WEBP")
                if category == "fullbody":
                    self.assertEqual(exported.mode, "RGBA")
                    self.assertEqual(exported.height, 1500)
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT proposal_id,source_sha256,output_path,processing_json "
                "FROM normal_crop_exports ORDER BY proposal_id"
            ).fetchall()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM training_records").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM final_assets").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM dataset_split_assignments").fetchone()[0], 0)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["source_sha256"], self.digest)
            self.assertTrue(Path(row["output_path"]).is_file())
            self.assertIn("crop_policy", json.loads(row["processing_json"]))
        self.assertEqual(self.db.output_review_records(), [])

    def test_collision_creates_new_name_and_keeps_first_output(self):
        proposal_id = self.proposal(8, "boobs_cover_item")
        self.db.save_normal_crop_choice(proposal_id, "clothing", main_tag="dress",
                                        clothing_broad_family="dress",
                                        clothing_cover_area="boobs_cover")
        first_plan, first = self.export_one(proposal_id, self.root / "collision-output")
        second_plan = build_normal_output_plan(
            self.db, self.root / "collision-output", [proposal_id]
        )
        self.assertEqual(first["written_count"], 1)
        self.assertNotEqual(first_plan["items"][0]["target"], second_plan["items"][0]["target"])
        second = export_normal_output(self.db, second_plan)
        self.assertEqual(second["written_count"], 1)
        self.assertEqual(len(list((self.root / "collision-output" / "clothing").rglob("*.webp"))), 2)

    def test_normal_confirmation_creates_unified_cnn_example_without_export_selection(self):
        proposal_id = self.proposal(2, "portrait_frame", (250, 150, 650, 550))
        self.db.save_normal_crop_choice(proposal_id, "body_images", "portrait", main_tag="portrait",
                                        location="home")
        self.assertEqual(self.db.current_training_examples(), [])
        ids = self.db.confirm_normal_crop_classification(proposal_id)
        self.assertEqual(len(ids), 1)
        record = self.db.current_training_examples("unified_body_images_fullbody")[0]
        self.assertEqual(record["class_label"], "portrait")
        self.assertEqual(record["task_head"], "portrait")
        self.assertEqual(self.db.confirm_normal_crop_classification(proposal_id), ids)
        self.assertEqual(len(self.db.current_training_examples()), 1)
        with self.db.connect() as connection:
            choice = connection.execute(
                "SELECT subtags_json,location_value FROM normal_crop_choices WHERE proposal_id=?",
                (proposal_id,),
            ).fetchone()
        self.assertEqual(json.loads(choice["subtags_json"]), [])
        self.assertEqual(choice["location_value"], "home")

    def test_invalid_normal_crop_is_excluded_until_reclassified(self):
        proposal_id = self.proposal(3, "boobs", (250, 150, 650, 550))
        self.db.save_normal_crop_choice(proposal_id, "body_images", "boobs", main_tag="boobs",
                                        subtags=["cum"], body_images_cnn_target="bodypart_cum")
        self.db.confirm_normal_crop_classification(proposal_id)
        self.assertEqual(len(self.db.current_training_examples()), 1)
        self.db.save_normal_crop_choice(proposal_id, "invalid")
        self.assertEqual(self.db.normal_crop_records()[0]["category"], "invalid")
        self.assertEqual(self.db.current_training_examples(), [])
        with self.assertRaisesRegex(ValueError, "marked invalid"):
            self.db.confirm_normal_crop_classification(proposal_id)
        self.db.save_normal_crop_choice(proposal_id, "body_images", "boobs", main_tag="boobs",
                                        subtags=["cum"], body_images_cnn_target="bodypart_acc")
        self.db.confirm_normal_crop_classification(proposal_id)
        examples = self.db.current_training_examples()
        self.assertEqual([row["class_label"] for row in examples], ["bodypart_acc"])

    def test_invalid_normal_crop_cannot_be_reconfirmed_with_same_class(self):
        proposal_id = self.proposal(3, "boobs", (250, 150, 650, 550))
        self.db.save_normal_crop_choice(proposal_id, "body_images", "boobs", main_tag="boobs",
                                        subtags=["cum"], body_images_cnn_target="bodypart_cum")
        self.db.save_normal_crop_choice(proposal_id, "invalid")
        self.db.save_normal_crop_choice(proposal_id, "body_images", "boobs", main_tag="boobs",
                                        subtags=["cum"], body_images_cnn_target="bodypart_cum")
        with self.assertRaisesRegex(ValueError, "Choose a different class"):
            self.db.confirm_normal_crop_classification(proposal_id)

    def test_clothing_yolo_region_stays_clothing_when_cnn_name_is_unmapped(self):
        detection = self.db.record_yolo_detection(
            self.source_id, model_id="phase9-fixture", model_digest="fixture",
            class_id=8, class_name="boobs_cover_item", confidence=.83,
            bbox_xyxy=[100, 100, 800, 800],
        )
        proposal_id = detection["proposal_id"]
        result = self.db.record_cnn_prediction(
            detection["detection_id"], model_id="fixture-cnn", model_digest="cnn-fixture",
            class_name="boobs_cover_item", confidence=.83,
        )
        self.assertEqual(result["category"], "clothing")
        self.assertEqual(self.db.normal_crop_records()[0]["category"], "clothing")

    def test_normal_clothing_confirmation_creates_separate_broad_and_fine_examples(self):
        proposal_id = self.proposal(8, "boobs_cover_item")
        self.db.save_normal_crop_choice(proposal_id, "clothing", main_tag="heels",
                                        clothing_broad_family="footwear",
                                        clothing_cover_area="accessory_footwear")
        ids = self.db.confirm_normal_crop_classification(proposal_id)
        records = self.db.current_training_examples()
        self.assertEqual(len(ids), 2)
        self.assertEqual({row["task"] for row in records}, {"clothing_broad", "clothing_fine"})
        self.assertEqual({row["class_label"] for row in records}, {"footwear", "heels"})
        self.assertEqual(len({row["source_sha256"] for row in records}), 1)
        self.assertEqual(len({tuple(row["crop_bbox_xyxy"]) for row in records}), 1)

    def test_normal_clothing_requires_human_selected_broad_group(self):
        proposal_id = self.proposal(8, "boobs_cover_item")
        with self.assertRaisesRegex(ValueError, "valid guide cover area"):
            self.db.save_normal_crop_choice(proposal_id, "clothing", main_tag="heels",
                                            clothing_cover_area="accessory_footwear")
        self.assertEqual(self.db.current_training_examples(), [])

    def test_portrait_is_exported_as_transparent_square_webp(self):
        proposal_id = self.proposal(1, "face", (250, 150, 650, 550))
        self.db.save_normal_crop_choice(proposal_id, "body_images", "portrait", main_tag="portrait")
        plan = build_normal_output_plan(self.db, self.root / "portrait-output", [proposal_id])
        self.assertEqual(plan["item_count"], 1)
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 1)
        with Image.open(result["written"][0]) as output:
            self.assertEqual(output.format, "WEBP")
            self.assertEqual(output.size[0], output.size[1])
            self.assertEqual(output.mode, "RGBA")
            self.assertEqual(output.width, 400)

    def test_failed_export_is_separately_marked_and_never_written_as_success(self):
        proposal_id = self.proposal(8, "boobs_cover_item")
        self.db.save_normal_crop_choice(proposal_id, "clothing", main_tag="heels",
                                        clothing_broad_family="footwear",
                                        clothing_cover_area="accessory_footwear")
        plan = build_normal_output_plan(self.db, self.root / "failed-output", [proposal_id])
        Image.new("RGB", (900, 900), "blue").save(self.source)
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 0)
        self.assertEqual(result["failure_count"], 1)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM normal_crop_exports WHERE proposal_id=?", (proposal_id,)
            ).fetchone()[0], 0)
        row = next(item for item in self.db.normal_crop_records() if item["id"] == proposal_id)
        self.assertEqual(row["normal_export_status"], "failed")

    def test_background_removal_failure_never_exports_opaque_fullbody(self):
        opaque = self.root / "opaque.jpg"
        Image.new("RGB", (900, 900), (30, 80, 130)).save(opaque)
        digest = hashlib.sha256(opaque.read_bytes()).hexdigest()
        source_id, _ = self.db.upsert_source_image({
            "path": str(opaque.resolve()), "sha256": digest, "width": 900, "height": 900,
            "file_size": opaque.stat().st_size, "modified_ns": opaque.stat().st_mtime_ns,
        })
        detection = self.db.record_yolo_detection(
            source_id, model_id="phase9-fixture", model_digest="fixture",
            class_id=20, class_name="fullbody_clothed", confidence=.9, bbox_xyxy=[100, 100, 800, 850],
        )
        self.db.save_normal_crop_choice(detection["proposal_id"], "fullbody",
                                        main_tag="clothed", fullbody_state="clothed")

        def failed_removal(_region):
            raise RuntimeError("synthetic segmentation failure")

        plan = build_normal_output_plan(
            self.db, self.root / "fallback-output", [detection["proposal_id"]]
        )
        result = export_normal_output(self.db, plan, background_remover=failed_removal)
        self.assertEqual(result["written_count"], 0)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["fallback_count"], 0)
        self.assertEqual(result["fallbacks"], [])
        self.assertFalse(Path(plan["items"][0]["target"]).exists())
        with self.db.connect() as connection:
            history = connection.execute(
                "SELECT status,message FROM normal_crop_export_attempts WHERE proposal_id=?",
                (detection["proposal_id"],),
            ).fetchone()
            self.assertEqual(history["status"], "failed")
            self.assertIn("synthetic segmentation failure", history["message"])
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM normal_crop_exports WHERE proposal_id=?",
                (detection["proposal_id"],),
            ).fetchone()[0], 0)

    def test_fullbody_resource_preflight_rejects_before_model_allocation(self):
        opaque = self.root / "low_memory_fullbody.jpg"
        Image.new("RGB", (900, 900), "teal").save(opaque)
        digest = hashlib.sha256(opaque.read_bytes()).hexdigest()
        source_id, _ = self.db.upsert_source_image({
            "path": str(opaque.resolve()), "sha256": digest,
            "width": 900, "height": 900, "file_size": opaque.stat().st_size,
            "modified_ns": opaque.stat().st_mtime_ns,
        })
        detection = self.db.record_yolo_detection(
            source_id, model_id="phase9-fixture", model_digest="fixture",
            class_id=20, class_name="fullbody_clothed", confidence=.9,
            bbox_xyxy=[100, 100, 800, 850],
        )
        self.db.save_normal_crop_choice(
            detection["proposal_id"], "fullbody",
            main_tag="clothed", fullbody_state="clothed")
        plan = build_normal_output_plan(
            self.db, self.root / "low_memory_output", [detection["proposal_id"]])
        with patch("app.core.output_exporter._available_physical_memory_bytes",
                   return_value=1024 ** 3), \
             patch("app.core.output_exporter._get_birefnet_runtime") as runtime_load:
            result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 0)
        self.assertEqual(result["failure_count"], 1)
        self.assertIn("at least 2 GiB", result["failures"][0]["reason"])
        runtime_load.assert_not_called()
        self.assertFalse(Path(plan["items"][0]["target"]).exists())

    def test_disabled_background_removal_blocks_opaque_fullbody_export(self):
        opaque = self.root / "disabled.jpg"
        Image.new("RGB", (900, 900), "teal").save(opaque)
        digest = hashlib.sha256(opaque.read_bytes()).hexdigest()
        source_id, _ = self.db.upsert_source_image({
            "path": str(opaque.resolve()), "sha256": digest, "width": 900, "height": 900,
            "file_size": opaque.stat().st_size, "modified_ns": opaque.stat().st_mtime_ns,
        })
        detection = self.db.record_yolo_detection(
            source_id, model_id="phase9-fixture", model_digest="fixture",
            class_id=20, class_name="fullbody_clothed", confidence=.9, bbox_xyxy=[100, 100, 800, 850],
        )
        self.db.save_normal_crop_choice(detection["proposal_id"], "fullbody",
                                        main_tag="clothed", fullbody_state="clothed")
        plan = build_normal_output_plan(self.db, self.root / "disabled-output", [detection["proposal_id"]])
        plan["items"][0]["remove_background"] = False
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 0)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["fallback_count"], 0)
        self.assertIn("enable background removal", result["failures"][0]["reason"].lower())
        self.assertFalse(Path(plan["items"][0]["target"]).exists())

    def test_completed_exports_survive_cancellation_between_items(self):
        ids = [
            self.proposal(8, "boobs_cover_item", (100, 100, 300, 300)),
            self.proposal(9, "ass_cover_item", (300, 300, 500, 500)),
            self.proposal(10, "boobs_cover_item", (500, 500, 700, 700)),
        ]
        for proposal_id in ids:
            self.db.save_normal_crop_choice(proposal_id, "clothing", main_tag="dress",
                                            clothing_broad_family="dress",
                                            clothing_cover_area="boobs_cover")
        plan = build_normal_output_plan(self.db, self.root / "cancel-output", ids)
        cancel = threading.Event()

        def report(_current, _total, _proposal_id, status):
            if status == "exported":
                cancel.set()

        result = export_normal_output(self.db, plan, progress_callback=report,
                                      cancel_event=cancel)
        self.assertTrue(result["cancelled"])
        self.assertEqual(result["written_count"], 1)
        self.assertEqual(len(result["cancelled_ids"]), 2)
        self.assertTrue(Path(result["written"][0]).is_file())
        self.assertEqual(self.db.normal_crop_export_count(), 1)

    def test_alpha_mask_cache_hits_and_evicts_by_byte_limit(self):
        cache = _BIREFNET_ALPHA_CACHE.__class__(max_bytes=10)
        cache.put(("one",), (2, 2), b"1234")
        self.assertEqual(cache.get(("one",)), ((2, 2), b"1234"))
        cache.put(("two",), (2, 2), b"56789012")
        self.assertIsNone(cache.get(("one",)))
        self.assertEqual(cache.get(("two",)), ((2, 2), b"56789012"))

    def test_injected_background_mask_is_reused_for_same_source_and_box(self):
        opaque = self.root / "cache.jpg"
        Image.new("RGB", (900, 900), "slateblue").save(opaque)
        digest = hashlib.sha256(opaque.read_bytes()).hexdigest()
        source_id, _ = self.db.upsert_source_image({
            "path": str(opaque.resolve()), "sha256": digest, "width": 900, "height": 900,
            "file_size": opaque.stat().st_size, "modified_ns": opaque.stat().st_mtime_ns,
        })
        detection = self.db.record_yolo_detection(
            source_id, model_id="phase9-fixture", model_digest="fixture",
            class_id=20, class_name="fullbody_clothed", confidence=.9, bbox_xyxy=[100, 100, 800, 850],
        )
        self.db.save_normal_crop_choice(detection["proposal_id"], "fullbody",
                                        main_tag="clothed", fullbody_state="clothed")
        calls = []

        def segment(region):
            calls.append(1)
            result = region.convert("RGBA")
            alpha = Image.new("L", result.size, 0)
            ImageDraw.Draw(alpha).ellipse((30, 20, result.width - 30, result.height - 20), fill=255)
            result.putalpha(alpha)
            alpha.close()
            return result

        proposal_id = detection["proposal_id"]
        first = build_normal_output_plan(self.db, self.root / "cache-a", [proposal_id])
        second = build_normal_output_plan(self.db, self.root / "cache-b", [proposal_id])
        self.assertEqual(export_normal_output(self.db, first, background_remover=segment,
                                              background_remover_key="phase9-test-model")["written_count"], 1)
        self.assertEqual(export_normal_output(self.db, second, background_remover=segment,
                                              background_remover_key="phase9-test-model")["written_count"], 1)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
