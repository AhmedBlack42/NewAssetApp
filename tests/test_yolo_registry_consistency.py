import json
import unittest
from pathlib import Path

from app.core.proposals import (
    YOLO_FULLBODY_MAIN_TAGS,
    active_yolo_class_ids,
    valid_normal_cnn_suggestion,
    yolo_detection_disposition,
)
from app.core.training_source_exporter import _registry_class_id
from app.core.yolo_registry import (
    approved_yolo_classes,
    fullbody_final_tag_mapping,
    is_approved_yolo_identity,
)

ROOT = Path(__file__).resolve().parents[1]


class YoloRegistryConsistencyTests(unittest.TestCase):
    def test_active_class_ids_and_mapping_identities_are_exact_registry_entries(self):
        registry = approved_yolo_classes()
        self.assertEqual(active_yolo_class_ids(), set(registry))
        for class_id, class_name in registry.items():
            with self.subTest(class_id=class_id, class_name=class_name):
                self.assertTrue(is_approved_yolo_identity(class_id, class_name))
                self.assertFalse(is_approved_yolo_identity(class_id, class_name + "_legacy"))
                disposition = yolo_detection_disposition(class_id, class_name, .9, [0, 0, 1, 1])
                self.assertFalse(disposition["training_eligible"])

    def test_policy_crosswalk_eligibility_and_exporter_share_canonical_identities(self):
        registry = approved_yolo_classes()
        policy = json.loads((ROOT / "data/models/yolo_class_policy.json").read_text(encoding="utf-8"))
        crosswalk = json.loads((ROOT / "data/models/model_tag_crosswalk.json").read_text(encoding="utf-8"))
        eligibility = json.loads((ROOT / "data/task_eligibility_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {int(row["class_id"]): row["name"] for row in policy["classes"]},
            registry,
        )
        self.assertEqual(
            [(row["class_id"], row["model_label"]) for row in crosswalk["models"]["yolo"]],
            list(registry.items()),
        )
        active_fullbody_crosswalk = {
            row["model_label"]: row for row in crosswalk["models"]["yolo"]
            if row["model_label"].startswith("fullbody_")
        }
        fullbody_mapping = fullbody_final_tag_mapping()
        self.assertEqual(set(active_fullbody_crosswalk), set(fullbody_mapping))
        for class_name, mapping in fullbody_mapping.items():
            with self.subTest(class_name=class_name):
                row = active_fullbody_crosswalk[class_name]
                self.assertEqual(row["application_candidate"], mapping["final_tag"])
                self.assertEqual(
                    row["mapping_type"],
                    "fullbody_final_tag_candidate" if mapping["status"] == "resolved"
                    else "unresolved_fullbody_final_tag",
                )
        self.assertNotIn("fullbody_lingerie", active_fullbody_crosswalk)
        self.assertEqual(crosswalk["source_registries"]["yolo"],
                         "TrainingDatasetStudio/registries/yolo_detector_v1.json")
        for class_name in registry.values():
            self.assertEqual(
                _registry_class_id({"classes": [
                    {"id": class_id, "name": name} for class_id, name in registry.items()
                ]}, "yolo_detector", None, class_name),
                next(class_id for class_id, name in registry.items() if name == class_name),
            )
        self.assertLessEqual(set(eligibility["tasks"]), set(registry.values()))
        self.assertEqual(
            set(eligibility["historical_compatibility_only_classes"]),
            {"action_event", "fullbody_topless", "fullbody_bottomless"},
        )

    def test_every_registry_fullbody_class_has_a_separate_final_tag_disposition(self):
        registry = approved_yolo_classes()
        mapping = fullbody_final_tag_mapping()
        expected = {name for name in registry.values() if name.startswith("fullbody_")}
        self.assertEqual(set(mapping), expected)
        self.assertEqual(
            set(YOLO_FULLBODY_MAIN_TAGS),
            {name for name, row in mapping.items() if row["status"] == "resolved"},
        )
        self.assertEqual(YOLO_FULLBODY_MAIN_TAGS["fullbody_maid"], "maid")
        self.assertEqual(YOLO_FULLBODY_MAIN_TAGS["fullbody_swimsuit"], "swimsuit")
        self.assertEqual(YOLO_FULLBODY_MAIN_TAGS["fullbody_athletic"], "athletic")
        self.assertEqual(mapping["fullbody_athletic"]["status"], "resolved")
        self.assertEqual(mapping["fullbody_athletic"]["final_tag"], "athletic")
        for row in mapping.values():
            self.assertIn(row["status"], {"resolved", "unresolved"})
            if row["status"] == "unresolved":
                self.assertIsNone(row["final_tag"])
                self.assertTrue(row.get("reason", "").strip())
        tags = json.loads((ROOT / "data/tags/fullbody_tags.json").read_text(encoding="utf-8"))
        active_tags = {
            entry["serialized_value"] for entry in tags["entries"]
            if entry.get("tag_type") == "main" and entry.get("selectable")
            and not entry.get("requires_review")
        }
        self.assertTrue(set(YOLO_FULLBODY_MAIN_TAGS.values()).issubset(active_tags))
        historical_spelling = next(
            entry for entry in tags["entries"]
            if entry.get("serialized_value") == "atheletic"
        )
        self.assertTrue(historical_spelling["requires_review"])
        self.assertIn("athletic", active_tags)
        self.assertNotIn("fullbody_swim", mapping)
        self.assertNotIn("fullbody_lingerie", mapping)

    def test_historical_class_names_cannot_create_current_detection_suggestions(self):
        for class_id, class_name in ((24, "fullbody_swim"), (25, "fullbody_lingerie"),
                                     (23, "fullbody_athletic")):
            with self.subTest(class_id=class_id, class_name=class_name):
                self.assertFalse(is_approved_yolo_identity(class_id, class_name))
                decision = yolo_detection_disposition(class_id, class_name, .99, [0, 0, 1, 1])
                self.assertIsNone(decision["asset_type"])
                self.assertEqual(decision["candidate_category"], "others")

    def test_only_supported_current_task_suggestions_are_approvable(self):
        self.assertTrue(valid_normal_cnn_suggestion(
            "clothing_classifier", "ok", "bra", .9, "boobs_cover_item"))
        for args in (
            ("legacy_model", "ok", "bra", .99, "boobs_cover_item"),
            ("clothing_classifier", "error", "bra", .99, "boobs_cover_item"),
            ("clothing_classifier", "ok", "unknown", .99, "boobs_cover_item"),
            ("clothing_classifier", "ok", "bra", .5, "boobs_cover_item"),
            ("clothing_classifier", "ok", "bra", .99, "fullbody_maid"),
        ):
            with self.subTest(args=args):
                self.assertFalse(valid_normal_cnn_suggestion(*args))


if __name__ == "__main__":
    unittest.main()
