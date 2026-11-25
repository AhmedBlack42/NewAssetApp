import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database, SCHEMA_VERSION
from app.core.dataset_exporter import export_cnn_dataset, export_unified_cnn_dataset, export_yolo_dataset
from app.core.fullbody_classification import fullbody_filename
from app.core.proposals import yolo_detection_disposition
from app.core.scanner import scan_folder


class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / "source_set"
        self.folder.mkdir()
        self.image_path = self.folder / "sample.png"
        Image.new("RGB", (100, 80), "orange").save(self.image_path)
        self.db_path = self.root / "app.sqlite3"
        self.db = Database(self.db_path)
        self.db.initialize()
        scan_folder(self.folder, self.db)
        self.source = self.db.source_images(self.folder)[0]

    def tearDown(self):
        self.temp.cleanup()

    def _proposal(self, category="fullbody", class_name="fullbody_clothed_states", confidence=.91,
                  bbox=(10, 8, 90, 75), class_id=1, yolo_class_name=None):
        with self.db.connect() as connection:
            detection_id = connection.execute(
                """INSERT INTO yolo_detections(source_image_id, model_id, model_digest, class_id,
                   class_name, confidence, x1, y1, x2, y2) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (self.source["id"], "legacy_yolo", "digest", class_id,
                 yolo_class_name or ("person" if class_id == 0 else "face"), .83, *bbox),
            ).lastrowid
            prediction_id = connection.execute(
                "INSERT INTO cnn_predictions(detection_id, model_id, model_digest, class_name, confidence, status) "
                "VALUES (?,?,?,?,?,?)",
                (detection_id, "asset_cnn", "cnn_digest", class_name, confidence, "ok"),
            ).lastrowid
            proposal_id = connection.execute(
                """INSERT INTO asset_proposals(source_image_id, detection_id, prediction_id, asset_type,
                   category, confidence, review_status) VALUES (?,?,?,?,?,?,?)""",
                (self.source["id"], detection_id, prediction_id, class_name, category, confidence, "pending"),
            ).lastrowid
        return proposal_id, detection_id

    def test_person_is_review_only_corruption_crop_not_fullbody(self):
        result = yolo_detection_disposition(0, "person", .84, [1, 2, 90, 79])
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(result["candidate_category"], "others")
        self.assertEqual(result["asset_type"], "person")
        self.assertFalse(result["training_eligible"])
        self.assertEqual(result["original_yolo"]["class_id"], 0)

    def test_person_detection_persists_as_corruption_roi_and_legacy_cnn_cannot_confirm_fullbody(self):
        raw = self.db.record_yolo_detection(
            self.source["id"], model_id="legacy", model_digest="sha256:legacy",
            class_id=0, class_name="person", confidence=.84, bbox_xyxy=[5, 4, 95, 78])
        self.assertEqual(raw["status"], "review_required")
        result = self.db.record_cnn_prediction(
            raw["detection_id"], model_id="asset-cnn", model_digest="sha256:cnn",
            class_name="fullbody_nude_states", confidence=.64,
            probabilities={"fullbody_nude_states": .64}, threshold=.75)
        self.assertEqual(result["review_status"], "review_required")
        proposal = self.db.proposals_for_category("others")[0]
        self.assertEqual(proposal["asset_type"], "person")
        self.assertEqual(proposal["review_status"], "review_required")
        self.assertEqual(proposal["yolo_class_id"], 0)
        self.assertEqual((proposal["yolo_x1"], proposal["yolo_y2"]), (5, 78))
        self.assertEqual(self.db.reviewed_training_records("asset_cnn"), [])

    def test_low_confidence_portrait_cnn_routes_to_body_images_for_review(self):
        raw = self.db.record_yolo_detection(
            self.source["id"], model_id="legacy", model_digest="sha256:legacy",
            class_id=2, class_name="portrait_frame", confidence=.55,
            bbox_xyxy=[5, 4, 95, 78])
        result = self.db.record_cnn_prediction(
            raw["detection_id"], model_id="asset-cnn", model_digest="sha256:cnn",
            class_name="bodypart_portrait_topless", confidence=.4,
            probabilities={"bodypart_portrait_topless": .4})
        self.assertEqual(result["category"], "body_images")
        proposal = next(row for row in self.db.proposals_for_category("body_images")
                        if row["id"] == raw["proposal_id"])
        self.assertIsNone(proposal["asset_type"])
        self.assertEqual(proposal["review_status"], "review_required")

    def test_normal_crop_choice_updates_professional_proposal_routing(self):
        raw = self.db.record_yolo_detection(
            self.source["id"], model_id="legacy", model_digest="sha256:legacy",
            class_id=2, class_name="portrait_frame", confidence=.55,
            bbox_xyxy=[5, 4, 95, 78])
        self.db.record_cnn_prediction(
            raw["detection_id"], model_id="asset-cnn", model_digest="sha256:cnn",
            class_name="bodypart_portrait_topless", confidence=.4,
            probabilities={"bodypart_portrait_topless": .4})
        original = next(row for row in self.db.proposals_for_category("body_images")
                        if row["id"] == raw["proposal_id"])
        self.db.save_normal_crop_choice(raw["proposal_id"], "body_images", "tportrait")
        proposal = next(row for row in self.db.proposals_for_category("body_images")
                        if row["id"] == raw["proposal_id"])
        self.assertEqual(proposal["asset_type"], original["asset_type"])

    def test_person_roi_cannot_be_routed_through_normal_processing_as_fullbody(self):
        raw = self.db.record_yolo_detection(
            self.source["id"], model_id="legacy", model_digest="sha256:legacy",
            class_id=0, class_name="person", confidence=.84, bbox_xyxy=[5, 4, 95, 78])
        with self.assertRaisesRegex(ValueError, "person region.*cannot be classified as Fullbody"):
            self.db.save_normal_crop_choice(raw["proposal_id"], "fullbody", "clothed",
                                            fullbody_state="clothed")

    def test_person_detection_cannot_be_confirmed_as_fullbody(self):
        raw = self.db.record_yolo_detection(
            self.source["id"], model_id="legacy", model_digest="sha256:legacy",
            class_id=0, class_name="person", confidence=.84, bbox_xyxy=[5, 4, 95, 78])
        with self.assertRaisesRegex(ValueError, "person region.*cannot be classified as Fullbody"):
            self.db.save_correction(
                raw["proposal_id"],
                {"category": "fullbody", "main_tag": "clothed", "state_spec": "clothed",
                 "fullbody_output_category": "fullbody", "validity_state": "valid",
                 "bbox_xyxy": [5, 4, 95, 78]},
                decision_type="classification_confirmation", final_state="confirmed")

    def test_manual_person_roi_can_confirm_corruption_cnn_training_target(self):
        proposal_id = self.db.create_manual_proposal(self.source["id"])
        correction_id = self.db.save_correction(
            proposal_id,
            {"category": "others", "bbox_xyxy": [10, 8, 90, 75],
             "validity_state": "valid", "corruption_state": "slut",
             "corruption_values": ["slut"], "corruption_classifier_target": "slut"},
            decision_type="classification_confirmation", final_state="confirmed",
            corruption_training_eligible=True,
        )
        records = self.db.current_corruption_training_examples()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["correction_record_id"], correction_id)
        self.assertEqual(records[0]["proposal_id"], proposal_id)
        self.assertEqual(records[0]["class_label"], "slut")
        self.assertEqual(records[0]["task"], "corruption_state")
        self.assertIsNone(records[0]["detection_id"])
        self.assertEqual(records[0]["crop_bbox_xyxy"], [10, 8, 90, 75])
        self.assertTrue(records[0]["human_confirmed"])
        self.assertTrue(records[0]["training_eligible"])

    def test_person_proposal_without_human_validity_cannot_enter_corruption_training(self):
        proposal_id = self.db.create_manual_proposal(self.source["id"])
        with self.assertRaisesRegex(ValueError, "human-confirmed, valid"):
            self.db.save_correction(
                proposal_id,
                {"category": "others", "bbox_xyxy": [10, 8, 90, 75],
                 "validity_state": "unresolved", "corruption_classifier_target": "slut"},
                decision_type="classification_confirmation", final_state="confirmed",
                corruption_training_eligible=True,
            )

    def test_correction_preserves_original_ai_snapshot_and_restarts(self):
        proposal_id, _ = self._proposal()
        record_id = self.db.save_correction(
            proposal_id, {"category": "fullbody", "main_tag": "shower", "state_spec": "clothed",
                         "fullbody_output_category": "fullbody", "validity_state": "valid",
                         "bbox_xyxy": [8, 5, 92, 78],
                         "asset_cnn_class": "fullbody_nude_states"},
            decision_type="corrected", final_state="confirmed", cnn_training_eligible=True,
            model_version="legacy-model-sha", taxonomy_version="taxonomy-v1")
        reopened = Database(self.db_path)
        rows = reopened.reviewed_training_records("asset_cnn")
        self.assertEqual(rows[0]["id"], record_id)
        self.assertEqual(json.loads(rows[0]["original_snapshot_json"])["cnn"]["class_name"],
                         "fullbody_clothed_states")
        self.assertEqual(json.loads(rows[0]["corrected_payload_json"])["main_tag"], "shower")
        self.assertEqual(rows[0]["user_changed_prediction"], 1)
        self.assertEqual(self.db.category_counts()["fullbody"], 1)

    def test_fullbody_state_outputs_require_human_consistent_pair(self):
        proposal_id, _ = self._proposal()
        with self.assertRaises(ValueError):
            self.db.save_correction(proposal_id, {"main_tag": "clothed", "state_spec": "topless",
                                  "fullbody_output_category": "fullbody"}, decision_type="corrected",
                                  final_state="confirmed")
        for state, output in (("normal", "fullbody"), ("topless", "fullbody_topless"),
                              ("bottomless", "fullbody_bottomless")):
            proposal_id, _ = self._proposal()
            self.db.save_correction(proposal_id, {"main_tag": "clothed", "state_spec": state,
                                  "fullbody_output_category": output}, decision_type="corrected",
                                  final_state="confirmed")
        self.assertEqual(len(self.db.proposals_for_category("fullbody")), 2)
        self.assertEqual(len(self.db.proposals_for_category("fullbody_topless")), 1)
        self.assertEqual(len(self.db.proposals_for_category("fullbody_bottomless")), 1)

    def test_guide_documented_fullbody_conservative_subtag_passes_category_validation(self):
        proposal_id, _ = self._proposal()
        self.db.save_correction(proposal_id,
            {"category": "fullbody", "main_tag": "clothed", "state_spec": "bottomless",
             "fullbody_output_category": "fullbody_bottomless", "subtags": ["conservative"]},
            decision_type="corrected", final_state="confirmed")

    def test_fullbody_filename_uses_only_guide_compositions(self):
        self.assertEqual(fullbody_filename("shower", "normal", 1), "shower-normal1.webp")
        self.assertEqual(fullbody_filename("clothed", "topless", 2), "clothed-topless2.webp")
        self.assertEqual(fullbody_filename("bikini", "bottomless", 3), "bikini-bottomless3.webp")
        with self.assertRaises(ValueError):
            fullbody_filename("shower", "topless", 1)

    def test_bare_is_a_valid_guide_fullbody_main_tag(self):
        # Regression: the writer previously rejected the guide's selectable `bare` type.
        from app.core.fullbody_classification import fullbody_classification
        result = fullbody_classification("bare", "normal")
        self.assertEqual(result["serialized_filename_tag"], "bare")
        self.assertEqual(result["output_category"], "fullbody")

    def test_fullbody_parse_tracks_number_as_metadata_and_keeps_allowlist(self):
        from app.core.fullbody_classification import parse_fullbody_filename
        parsed = parse_fullbody_filename("bikini_bottomless3.webp")
        self.assertEqual((parsed["main_tag"], parsed["state_spec"], parsed["sequence"]),
                         ("bikini", "bottomless", 3))
        self.assertEqual(parse_fullbody_filename("bare.webp")["sequence"], None)
        self.assertEqual(parse_fullbody_filename("shower_2.webp")["sequence_format"], "underscore")
        with self.assertRaises(ValueError):
            parse_fullbody_filename("bare0.webp")
        with self.assertRaises(ValueError):
            parse_fullbody_filename("bikini_topless.webp")

    def test_fullbody_three_state_pairs_use_only_verified_compositions(self):
        from app.core.fullbody_classification import fullbody_classification
        for state, expected in (("clothed", "bikini"),
                                ("topless", "clothed_topless"),
                                ("bottomless", "clothed_bottomless")):
            main = "bikini" if state == "clothed" else "clothed"
            self.assertEqual(fullbody_classification(main, state)["serialized_filename_tag"], expected)
        self.assertEqual(fullbody_classification("bikini", "bottomless")["serialized_filename_tag"],
                         "bikini_bottomless")
        with self.assertRaises(ValueError):
            fullbody_classification("bikini", "topless")
        self.assertEqual(fullbody_filename("clothed", "bottomless", 4, ["conservative"]),
                         "clothed-bottomless,conservative4.webp")
        from app.core.fullbody_classification import parse_fullbody_filename
        parsed = parse_fullbody_filename("clothed-bottomless,conservative.webp")
        self.assertEqual(parsed["subtags"], ["conservative"])

    def test_shared_corruption_subtags_are_selectable_and_fullbody_suffix_is_complete_tag(self):
        from app.core.fullbody_classification import parse_fullbody_filename
        from app.core.tag_library import TagLibrary
        expected = {"slut", "conservative", "whore", "u_whore"}
        library = TagLibrary(Path(__file__).resolve().parents[1] / "data" / "tags")
        for category in ("clothing", "fullbody", "body_images"):
            available = {row["serialized_value"] for row in library.entries(group=category)
                         if row.get("tag_type") == "subtag" and
                         row.get("serialized_value") in expected}
            self.assertEqual(available, expected)
        for value in expected:
            filename = fullbody_filename("clothed", "topless", 1, [value])
            self.assertEqual(filename, f"clothed-topless,{value}1.webp")
            parsed = parse_fullbody_filename(filename)
            self.assertEqual(parsed["subtags"], [value])
            self.assertEqual(parsed["sequence"], 1)
        self.assertEqual(parse_fullbody_filename("clothed_topless_1.webp")["sequence_format"], "underscore")
        self.assertEqual(parse_fullbody_filename("clothed-topless1.webp")["sequence"], 1)
        self.assertEqual(parse_fullbody_filename("clothed-bottomless,conservative.webp")["subtags"],
                         ["conservative"])

    def test_corruption_subtag_is_human_confirmed_separately_from_ai_evidence(self):
        proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_face")
        self.db.save_correction(proposal_id,
            {"category": "body_images", "main_tag": "face",
             "subtags": ["u_whore"], "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        with self.db.connect() as connection:
            row = connection.execute("SELECT original_snapshot_json, corrected_payload_json FROM correction_records WHERE proposal_id=?",
                                     (proposal_id,)).fetchone()
        original = json.loads(row["original_snapshot_json"])
        corrected = json.loads(row["corrected_payload_json"])
        self.assertEqual(corrected["subtags"], ["u_whore"])
        self.assertEqual(corrected["main_tag"], "face")
        self.assertNotIn("sub_main_tag", corrected)
        self.assertNotEqual(corrected["subtags"][0], original["cnn"]["class_name"])

    def test_category_specific_corruption_validation_rejects_others(self):
        proposal_id, _ = self._proposal(category="others", class_name="unmapped")
        with self.assertRaisesRegex(ValueError, "unavailable for this category"):
            self.db.save_correction(proposal_id,
                {"category": "others", "corruption_subtag": "u_whore"},
                decision_type="corrected", final_state="confirmed")

    def test_body_images_structured_main_and_subtags_use_export_grammar(self):
        from app.core.output_exporter import build_output_plan
        proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_face")
        self.db.save_correction(proposal_id,
            {"category": "body_images", "main_tag": "face", "subtags": ["u_whore"],
             "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        plan = build_output_plan(self.db, self.root / "output")
        self.assertEqual(Path(plan["items"][0]["filename"]).name,
                         "face-u_whore1.webp")

    def test_body_fluid_composition_is_a_supported_structured_subtag(self):
        from app.core.output_exporter import build_output_plan
        proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_boobs")
        self.db.save_correction(proposal_id,
            {"category": "body_images", "main_tag": "boobs", "subtags": ["cum", "whore"],
             "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        rows = self.db.output_review_records()
        payload = json.loads(rows[0]["confirmed_json"])
        self.assertNotIn("sub_main_tag", payload)
        self.assertEqual(payload["subtags"], ["cum", "whore"])
        plan = build_output_plan(self.db, self.root / "output")
        self.assertEqual(plan["item_count"], 1)
        self.assertEqual(Path(plan["items"][0]["filename"]).name, "boobs-cum,whore1.webp")

    def test_body_fluid_values_are_restricted_to_supported_main_subtag_pairs(self):
        from app.core.output_exporter import build_output_plan
        for main, subtag in (("face", "cum"), ("boobs", "creampie")):
            proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_boobs")
            with self.assertRaises(ValueError):
                self.db.save_correction(proposal_id,
                    {"category": "body_images", "main_tag": main, "subtags": [subtag],
                     "validity_state": "valid"},
                    decision_type="corrected", final_state="confirmed")
        valid_id, _ = self._proposal(category="body_images", class_name="bodypart_ass")
        self.db.save_correction(valid_id, {"category": "body_images", "main_tag": "ass",
                                           "subtags": ["creampie"], "validity_state": "valid"},
                                decision_type="corrected", final_state="confirmed")
        plan = build_output_plan(self.db, self.root / "output")
        self.assertEqual(plan["item_count"], 1)
        self.assertEqual(Path(plan["items"][0]["filename"]).name, "ass-creampie1.webp")

    def test_body_fluid_values_are_stored_as_subtags_not_a_retired_submain_field(self):
        proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_boobs")
        self.db.save_correction(proposal_id,
            {"category": "body_images", "main_tag": "boobs", "subtags": ["cum"],
             "validity_state": "valid"}, decision_type="corrected", final_state="confirmed")
        with self.db.connect() as connection:
            payload = json.loads(connection.execute(
                "SELECT corrected_payload_json FROM correction_records WHERE proposal_id=?", (proposal_id,)
            ).fetchone()[0])
        self.assertEqual(payload["subtags"], ["cum"])
        self.assertNotIn("sub_main_tag", payload)

    def test_phase4_canonical_location_is_human_selected_and_validated(self):
        proposal_id, _ = self._proposal(category="others", class_name="location_beach",
                                        class_id=28, yolo_class_name="location_beach")
        with self.assertRaisesRegex(ValueError, "Unknown canonical location"):
            self.db.save_correction(proposal_id,
                {"category": "others", "location_tag": "outdoor"},
                decision_type="corrected", final_state="confirmed")
        self.db.save_correction(proposal_id,
            {"category": "others", "location_tag": "beach", "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        payload = json.loads(self.db.output_review_records()[0]["confirmed_json"])
        self.assertEqual(payload["location_tag"], "beach")

    def test_clothing_corruption_subtag_is_serialized_with_clothing_separator(self):
        from app.core.output_exporter import build_output_plan
        proposal_id, _ = self._proposal(category="clothing", class_name="clothing")
        self.db.save_correction(proposal_id,
            {"category": "clothing", "main_tag": "mini_skirt", "clothing_tag": "mini_skirt",
             "output_filename": "mini_skirt.webp", "subtags": ["slut"], "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        plan = build_output_plan(self.db, self.root / "output")
        self.assertEqual(Path(plan["items"][0]["filename"]).name, "mini_skirt-slut1.webp")

    def test_fullbody_collision_advances_sequence_after_corruption_tag(self):
        from app.core.output_exporter import build_output_plan
        proposal_id, _ = self._proposal()
        self.db.save_correction(proposal_id,
            {"category": "fullbody", "main_tag": "clothed", "state_spec": "topless",
             "fullbody_output_category": "fullbody_topless", "subtags": ["slut"],
             "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        output = self.root / "output"
        folder = output / "fullbody"
        folder.mkdir(parents=True)
        (folder / "clothed-topless,slut1.webp").write_bytes(b"keep")
        plan = build_output_plan(self.db, output)
        self.assertEqual(Path(plan["items"][0]["filename"]).name, "clothed-topless,slut2.webp")
        self.assertEqual((folder / "clothed-topless,slut1.webp").read_bytes(), b"keep")

    def test_bbox_correction_persists_without_mutating_original_yolo_box(self):
        raw = self.db.record_yolo_detection(self.source["id"], model_id="legacy", model_digest="digest",
                                             class_id=1, class_name="face", confidence=.9,
                                             bbox_xyxy=[5, 4, 95, 78])
        self.db.save_bbox_edit(raw["detection_id"], [10, 12, 80, 70])
        with self.db.connect() as connection:
            stored = connection.execute("SELECT x1,y1,x2,y2 FROM yolo_detections WHERE id=?",
                                        (raw["detection_id"],)).fetchone()
            correction = connection.execute("SELECT original_snapshot_json,corrected_payload_json FROM correction_records WHERE detection_id=?",
                                            (raw["detection_id"],)).fetchone()
        self.assertEqual(tuple(stored), (5, 4, 95, 78))
        view = self.db.detections_for_source(self.source["id"])[0]
        self.assertEqual(view["bbox_xyxy"], [10, 12, 80, 70])
        self.assertTrue(view["edited"])
        self.assertEqual(json.loads(correction["original_snapshot_json"])["yolo"]["x1"], 5)
        self.assertEqual(json.loads(correction["corrected_payload_json"])["bbox_xyxy"][0], 10)

    def test_category_and_yolo_class_correction_remain_separate_from_detection(self):
        raw = self.db.record_yolo_detection(self.source["id"], model_id="legacy", model_digest="digest",
                                             class_id=28, class_name="accessory_footwear", confidence=.9,
                                             bbox_xyxy=[5, 4, 95, 78])
        self.db.save_correction(raw["proposal_id"],
            {"category": "clothing", "main_tag": "hoodie", "clothing_tag": "hoodie",
             "class_id": 1, "bbox_xyxy": [10, 12, 80, 70]},
            decision_type="reclassified", final_state="confirmed")
        with self.db.connect() as connection:
            original = connection.execute("SELECT class_id,class_name,x1 FROM yolo_detections WHERE id=?",
                                          (raw["detection_id"],)).fetchone()
        self.assertEqual(tuple(original), (28, "accessory_footwear", 5))
        review = self.db.detections_for_source(self.source["id"])[0]
        self.assertEqual(review["class_name"], "face")
        self.assertEqual(review["category"], "clothing")
        self.assertEqual(review["bbox_xyxy"], [10, 12, 80, 70])

    def test_target_yolo_annotation_and_box_create_separate_authoritative_training_example(self):
        proposal_id, detection_id = self._proposal(category="body_images", class_name="bodypart_face")
        target = json.loads((Path(__file__).resolve().parents[1] / "TrainingDatasetStudio" /
                             "registries" / "yolo_detector_v1.json").read_text(encoding="utf-8"))
        chosen = target["classes"][13]
        self.db.save_correction(proposal_id,
            {"category": "body_images", "main_tag": "face", "subtags": [],
             "bbox_xyxy": [12, 14, 78, 68], "validity_state": "valid",
             "yolo_annotation_registry_id": target["registry_id"],
             "yolo_annotation_class_id": chosen["id"],
             "yolo_annotation_class_name": chosen["name"]},
            decision_type="corrected", final_state="confirmed",
            target_yolo_training_eligible=True)
        records = self.db.current_training_examples("yolo_detector")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["class_label"], chosen["name"])
        self.assertEqual(records[0]["crop_bbox_xyxy"], [12.0, 14.0, 78.0, 68.0])
        self.assertEqual(records[0]["detection_id"], detection_id)
        self.assertEqual(records[0]["workflow"], "professional_review")
        self.assertEqual(records[0]["suggestion_provenance"]["class_name"], "face")
        self.assertIsNotNone(records[0]["correction_record_id"])
        with self.db.connect() as connection:
            linked = connection.execute(
                "SELECT id FROM correction_records WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
                (proposal_id,),
            ).fetchone()
        self.assertEqual(records[0]["correction_record_id"], linked["id"])
        exported = export_yolo_dataset(self.db, self.root / "target_yolo_export",
                                       source_roots=[self.folder])
        self.assertEqual(exported["class_registry_id"], target["registry_id"])
        self.assertEqual(len(exported["class_names"]), 31)
        self.assertIn(chosen["name"], exported["class_names"])
        label_files = list(Path(exported["directory"]).rglob("*.txt"))
        label_files = [path for path in label_files if path.parent.name in {"train", "val", "test"}]
        self.assertEqual(len(label_files), 1)
        self.assertEqual(int(label_files[0].read_text().split()[0]), chosen["id"])

    def test_confirmed_fullbody_review_saves_classification_and_correction_atomically(self):
        proposal_id, detection_id = self._proposal(category="fullbody")
        correction_id = self.db.save_correction(
            proposal_id,
            {"category": "fullbody", "main_tag": "clothed", "state_spec": "clothed",
             "fullbody_output_category": "fullbody", "validity_state": "valid",
             "unified_cnn_task": "fullbody_state", "unified_cnn_class": "clothed",
             "bbox_xyxy": [10, 8, 90, 75]},
            decision_type="classification_confirmation", final_state="confirmed",
            unified_cnn_training_eligible=True,
        )
        state = self.db.classification_review_state(detection_id, "fullbody_state")
        self.assertEqual(state["status"], "confirmed")
        self.assertEqual(state["reviewed_label"], "clothed")
        records = self.db.current_training_examples("unified_body_images_fullbody")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["class_label"], "clothed")
        self.assertEqual(records[0]["correction_record_id"], correction_id)

    def test_rejection_is_visible_and_retains_original_box(self):
        raw = self.db.record_yolo_detection(self.source["id"], model_id="legacy", model_digest="digest",
                                             class_id=19, class_name="fullbody_shower", confidence=.9,
                                             bbox_xyxy=[5, 4, 95, 78])
        self.db.save_correction(raw["proposal_id"], {}, decision_type="rejected", final_state="rejected")
        box = next(row for row in self.db.detections_for_source(self.source["id"])
                   if row["id"] == raw["detection_id"])
        self.assertEqual(box["origin"], "rejected")
        self.assertEqual(box["bbox_xyxy"], [5, 4, 95, 78])

    def test_manual_detection_is_audited_and_not_training_eligible(self):
        detection_id = self.db.create_manual_detection(
            self.source["id"], [10, 11, 40, 50],
            class_id=1, registry_id="newassetapp_yolo_detector_v1")
        box = next(row for row in self.db.detections_for_source(self.source["id"]) if row["id"] == detection_id)
        self.assertEqual(box["origin"], "manual")
        self.assertEqual(box["class_name"], "face")
        self.assertEqual(box["annotation_class_name"], "face")
        self.assertEqual(box["bbox_xyxy"], [10, 11, 40, 50])
        self.assertEqual(self.db.reviewed_training_records("yolo"), [])
        with self.db.connect() as connection:
            row = connection.execute("SELECT decision_type, human_confirmed FROM correction_records WHERE detection_id=?",
                                     (detection_id,)).fetchone()
        self.assertEqual(tuple(row), ("manual_annotation", 1))

    def test_output_export_is_separate_collision_safe_and_preserves_source(self):
        from app.core.output_exporter import build_output_plan, export_reviewed_output
        proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_face")
        self.db.save_correction(proposal_id,
            {"category": "body_images", "main_tag": "face", "subtags": [],
             "bbox_xyxy": [10, 8, 90, 75], "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        original_hash = hashlib.sha256(self.image_path.read_bytes()).hexdigest()
        output = self.root / "normal_output"
        (output / "body_images").mkdir(parents=True)
        (output / "body_images" / "face1.webp").write_bytes(b"existing")
        plan = build_output_plan(self.db, output)
        self.assertEqual(plan["item_count"], 1)
        self.assertTrue(plan["items"][0]["target"].endswith("face2.webp"))
        result = export_reviewed_output(self.db, output, plan)
        self.assertEqual(result["written_count"], 1)
        self.assertTrue(Path(result["written"][0]).is_file())
        self.assertEqual(hashlib.sha256(self.image_path.read_bytes()).hexdigest(), original_hash)
        self.assertEqual(self.db.reviewed_training_records("asset_cnn"), [])
        with self.db.connect() as connection:
            final_count = connection.execute("SELECT COUNT(*) FROM final_assets").fetchone()[0]
        self.assertEqual(final_count, 1)

    def test_fullbody_output_uses_user_selected_tag1_writer_rule(self):
        from app.core.output_exporter import build_output_plan, export_reviewed_output
        transparent = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
        from PIL import ImageDraw
        ImageDraw.Draw(transparent).rectangle((12, 10, 88, 74), fill=(240, 120, 90, 255))
        transparent.save(self.image_path)
        transparent.close()
        scan_folder(self.folder, self.db)
        proposal_id, _ = self._proposal()
        self.db.save_correction(proposal_id,
            {"category": "fullbody", "main_tag": "shower", "state_spec": "clothed",
             "fullbody_output_category": "fullbody", "bbox_xyxy": [10, 8, 90, 75],
             "validity_state": "valid"},
            decision_type="corrected", final_state="confirmed")
        output = self.root / "normal_output"
        (output / "fullbody").mkdir(parents=True)
        (output / "fullbody" / "shower-clothed1.webp").write_bytes(b"collision")
        plan = build_output_plan(self.db, output)
        self.assertEqual(Path(plan["items"][0]["target"]).name, "shower-clothed2.webp")
        result = export_reviewed_output(self.db, output, plan)
        self.assertTrue(Path(result["written"][0]).is_file())

    def test_all_32_yolo_classes_create_reviewable_proposals(self):
        from app.core.proposals import YOLO_POLICY_PATH
        policy = json.loads(YOLO_POLICY_PATH.read_text(encoding="utf-8"))
        manifest = json.loads((Path(__file__).resolve().parents[1] / "models" / "model_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({int(row["class_id"]) for row in policy["classes"]}, set(range(32)))
        self.assertEqual([row["name"] for row in sorted(policy["classes"], key=lambda item: item["class_id"])],
                         manifest["models"]["yolo"]["class_names"])
        for row in policy["classes"]:
            result = self.db.record_yolo_detection(
                self.source["id"], model_id="yolo-fixture", model_digest="digest-" + str(row["class_id"]),
                class_id=row["class_id"], class_name=row["name"], confidence=.81,
                bbox_xyxy=[1, 2, 90, 70])
            self.assertIsNotNone(result["proposal_id"], row["name"])
            self.assertIn(result["status"], {"review_required", "unclassified_fullbody"})
        # The person class is a review-only corruption-state ROI candidate now.
        self.assertEqual(len(self.db.proposals_for_category("fullbody")), 12)
        person_rows = [proposal for proposal in self.db.proposals_for_category("others")
                       if proposal["yolo_class_id"] == 0]
        self.assertEqual(len(person_rows), 1)

    def test_yolo_export_uses_only_human_boxes_and_keeps_multiple_boxes_together(self):
        proposal_a, _ = self._proposal(bbox=(10, 8, 40, 40), class_id=1)
        proposal_b, _ = self._proposal(category="body_images", class_name="bodypart_face",
                                       bbox=(50, 10, 80, 70), class_id=2)
        for pid, box, cid, classification in (
            (proposal_a, [10, 8, 35, 40], 1,
             {"category": "fullbody", "main_tag": "clothed", "state_spec": "clothed",
              "fullbody_output_category": "fullbody", "validity_state": "valid"}),
            (proposal_b, [50, 10, 80, 70], 2,
             {"category": "body_images", "main_tag": "face", "validity_state": "valid"}),
        ):
            self.db.save_correction(pid, {**classification, "bbox_xyxy": box, "class_id": cid},
                                    decision_type="corrected", final_state="confirmed",
                                    yolo_training_eligible=True)
        rejected, _ = self._proposal(class_id=3)
        self.db.save_correction(rejected, {}, decision_type="rejected", final_state="rejected")
        export = export_yolo_dataset(self.db, self.root / "exports", seed=17)
        root = Path(export["directory"])
        self.assertEqual(export["image_count"], 1)
        self.assertEqual(export["annotation_count"], 2)
        label = next((root / "labels").rglob("*.txt")).read_text().splitlines()
        self.assertEqual(len(label), 2)
        reviewed = self.db.reviewed_training_records("yolo")[0]
        original = json.loads(reviewed["original_snapshot_json"])
        corrected = json.loads(reviewed["corrected_payload_json"])
        self.assertEqual(original["yolo"]["x2"], 40)
        self.assertEqual(corrected["bbox_xyxy"][2], 35)
        values = [float(item) for item in label[0].split()[1:]]
        self.assertTrue(all(0 <= item <= 1 for item in values))
        self.assertTrue(Path(export["zip"]).is_file())
        self.assertIn("0: person", (root / "data.yaml").read_text())

    def test_cnn_crops_from_one_source_share_a_split(self):
        p1, _ = self._proposal(category="clothing", class_name="shirt", bbox=(2, 2, 45, 70))
        p2, _ = self._proposal(category="clothing", class_name="bra", bbox=(50, 2, 95, 70))
        for pid, family, label, box in ((p1, "shirt", "t_shirt", [2, 2, 45, 70]),
                                       (p2, "bra", "bikini_top", [50, 2, 95, 70])):
            self.db.save_correction(pid, {"category": "clothing", "main_tag": label,
                                          "clothing_family_tag": family, "clothing_tag": label,
                                          "validity_state": "valid", "bbox_xyxy": box},
                                    decision_type="corrected", final_state="confirmed",
                                    clothing_cnn_training_eligible=True)
        export = export_cnn_dataset(self.db, "clothing_cnn", self.root / "exports")
        self.assertEqual(export["crop_count"], 2)
        self.assertEqual(len({crop["split"] for crop in export["crops"]}), 1)
        self.assertTrue(Path(export["zip"]).is_file())

    def test_asset_cnn_export_uses_only_existing_model_class_map(self):
        proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_face")
        self.db.save_correction(
            proposal_id, {"category": "body_images", "main_tag": "face",
                          "asset_cnn_class": "bodypart_face", "validity_state": "valid",
                          "bbox_xyxy": [4, 4, 60, 44]},
            decision_type="corrected", final_state="confirmed", cnn_training_eligible=True)
        export = export_cnn_dataset(self.db, "asset_cnn", self.root / "exports")
        self.assertEqual(export["crop_count"], 1)
        self.assertEqual(export["class_names"], ["bodypart_face"])
        self.assertEqual(export["class_map"]["bodypart_face"], 2)

    def test_unified_cnn_export_requires_human_confirmation_and_task_label(self):
        eligible_id, _ = self._proposal(category="body_images", class_name="bodypart_cum")
        self.db.save_correction(
            eligible_id, {"category": "body_images", "main_tag": "boobs", "subtags": ["cum"],
                          "bbox_xyxy": [4, 4, 60, 44],
                          "validity_state": "valid", "unified_cnn_task": "body_images",
                          "unified_cnn_class": "bodypart_cum"},
            decision_type="corrected", final_state="confirmed", unified_cnn_training_eligible=True)
        pending_id, _ = self._proposal(category="body_images", class_name="bodypart_acc")
        self.db.save_correction(
            pending_id, {"category": "body_images", "main_tag": "boobs", "subtags": ["cum"],
                         "bbox_xyxy": [10, 5, 80, 70],
                         "validity_state": "valid", "unified_cnn_task": "body_images",
                         "unified_cnn_class": "bodypart_acc"},
            decision_type="corrected", final_state="confirmed")
        self.assertEqual(len(self.db.reviewed_unified_cnn_records()), 1)
        exported = export_unified_cnn_dataset(self.db, self.root / "unified_exports")
        self.assertEqual(exported["task_counts"]["body_images"], 1)
        self.assertEqual(exported["task_counts"]["fullbody_state"], 0)
        self.assertEqual(exported["class_counts"]["body_images:bodypart_cum"], 1)
        self.assertTrue(exported["human_confirmed_only"])
        self.assertTrue(Path(exported["zip"]).is_file())

    def test_unified_cnn_rejects_label_from_wrong_task_group(self):
        proposal_id, _ = self._proposal(category="body_images", class_name="bodypart_face")
        with self.assertRaisesRegex(ValueError, "not in the selected task output group"):
            self.db.save_correction(
                proposal_id, {"category": "body_images", "main_tag": "face", "validity_state": "valid",
                              "bbox_xyxy": [4, 4, 60, 44],
                              "unified_cnn_task": "body_images", "unified_cnn_class": "clothed"},
                decision_type="corrected", final_state="confirmed", unified_cnn_training_eligible=True)

    def test_incremental_scanning_detects_new_unchanged_and_changed_content(self):
        first = scan_folder(self.folder, self.db)
        second = scan_folder(self.folder, self.db)
        self.assertEqual(first["new_or_changed"], 0)
        self.assertEqual(second["unchanged"], 1)
        Image.new("RGB", (100, 80), "blue").save(self.image_path)
        third = scan_folder(self.folder, self.db)
        self.assertEqual(third["changed"], 1)
        with self.db.connect() as connection:
            versions = connection.execute("SELECT COUNT(*) FROM source_image_versions").fetchone()[0]
        self.assertEqual(versions, 1)
        self.assertEqual(self.db.source_images(self.folder)[0]["source_root"], str(self.folder.resolve()))

    def test_all32_policy_revision_requeues_sources_analyzed_under_old_policy(self):
        source_id = self.source["id"]
        source_hash = self.source["content_sha256"]
        self.db.set_source_inference_status(source_id, source_hash, "completed")
        self.assertEqual(self.db.sources_needing_inference(self.folder), [])
        with self.db.connect() as connection:
            connection.execute("UPDATE source_images SET inference_hash=? WHERE id=?", (source_hash, source_id))
        self.assertEqual([row["id"] for row in self.db.sources_needing_inference(self.folder)], [source_id])

    def test_migration_version_and_manual_rejection_not_training_negative(self):
        proposal_id, _ = self._proposal()
        self.db.save_correction(proposal_id, {"notes": "invalid"}, decision_type="rejected",
                                final_state="rejected")
        self.assertEqual(self.db.reviewed_training_records("yolo"), [])
        with self.db.connect() as connection:
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            columns = {row[1] for row in connection.execute("PRAGMA table_info(asset_proposals)")}
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertIn("fullbody_output_category", columns)

    def test_manual_proposal_and_explicit_background_annotation_export_empty_yolo_label(self):
        proposal_id = self.db.create_manual_proposal(self.source["id"])
        record_id = self.db.save_correction(
            proposal_id, {"category": "others", "no_objects": True, "validity_state": "valid"},
            decision_type="manual_annotation", final_state="confirmed", yolo_training_eligible=True)
        self.assertEqual(record_id, self.db.reviewed_training_records("yolo")[0]["id"])
        export = export_yolo_dataset(self.db, self.root / "negative_export")
        root = Path(export["directory"])
        label = next((root / "labels").rglob("*.txt"))
        self.assertEqual(label.read_text(), "")
        self.assertEqual(export["annotation_count"], 0)

    def test_active_detection_and_cnn_candidate_mapping_stays_reviewable(self):
        raw = self.db.record_yolo_detection(
            self.source["id"], model_id="legacy", model_digest="digest",
            class_id=1, class_name="face", confidence=.88, bbox_xyxy=[4, 4, 40, 40])
        result = self.db.record_cnn_prediction(
            raw["detection_id"], model_id="asset", model_digest="asset-digest",
            class_name="bodypart_face", confidence=.93,
            probabilities={"bodypart_face": .93}, threshold=.75)
        self.assertEqual(result["category"], "body_images")
        self.assertEqual(result["review_status"], "review_required")
        row = self.db.proposals_for_category("body_images")[0]
        self.assertEqual(row["asset_type"], "face")
        self.assertEqual(row["cnn_class_name"], "bodypart_face")

    def test_yolo_and_cnn_packages_share_source_split_assignments(self):
        proposal_id, _ = self._proposal(category="clothing", class_name="shirt")
        self.db.save_correction(
            proposal_id, {"category": "clothing", "clothing_family_tag": "shirt",
                          "main_tag": "t_shirt", "clothing_tag": "t_shirt", "class_id": 1,
                          "validity_state": "valid", "bbox_xyxy": [10, 8, 90, 75]},
            decision_type="corrected", final_state="confirmed", yolo_training_eligible=True,
            clothing_cnn_training_eligible=True)
        yolo = export_yolo_dataset(self.db, self.root / "exports", seed=42)
        clothing = export_cnn_dataset(self.db, "clothing_cnn", self.root / "exports", seed=7)
        self.assertEqual(yolo["source_images"][0]["split"], clothing["crops"][0]["split"])

    def test_external_folder_scan_records_its_root(self):
        external = self.root / "picked_elsewhere"
        external.mkdir()
        Image.new("RGB", (12, 13), "green").save(external / "external.jpg")
        result = scan_folder(external, self.db, recursive=True)
        self.assertEqual(result["new_or_changed"], 1)
        row = next(row for row in self.db.source_images() if Path(row["path"]).parent == external)
        self.assertEqual(row["source_root"], str(external.resolve()))

    def test_user_corrected_category_is_separate_from_original_proposal(self):
        proposal_id, _ = self._proposal(category="others", class_name="shirt")
        record_id = self.db.save_correction(
            proposal_id, {"category": "clothing", "main_tag": "t_shirt", "clothing_tag": "t_shirt",
                          "validity_state": "valid", "bbox_xyxy": [3, 4, 88, 75]},
            decision_type="reclassified", final_state="confirmed")
        row = self.db.proposals_for_category("clothing")[0]
        self.assertEqual(row["id"], proposal_id)
        self.assertEqual(row["review_status"], "confirmed")
        stored = self.db.reviewed_training_records("yolo")
        self.assertEqual(stored, [])
        with self.db.connect() as connection:
            correction = connection.execute("SELECT original_snapshot_json FROM correction_records WHERE id=?",
                                            (record_id,)).fetchone()
        self.assertEqual(json.loads(correction["original_snapshot_json"])["proposal"]["category"], "others")

    def test_user_tag_change_is_logged_with_source_provenance(self):
        after = {"id": "user:tag-1", "group": "clothing", "serialized_value": "new_verified_token"}
        change_id = self.db.record_tag_change("add", None, after, source_image_id=self.source["id"])
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM tag_change_records WHERE id=?", (change_id,)).fetchone()
        self.assertEqual(row["source_path"], str(self.image_path.resolve()))
        self.assertEqual(row["source_sha256"], self.source["content_sha256"])
        self.assertEqual(json.loads(row["after_json"])["serialized_value"], "new_verified_token")


if __name__ == "__main__":
    unittest.main()
