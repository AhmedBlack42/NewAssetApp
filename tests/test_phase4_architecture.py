import json
import hashlib
import unittest
from pathlib import Path

from tools.validate_phase4_dataset import validate_manifest, validate_registry

ROOT = Path(__file__).resolve().parents[1]


class Phase4ArchitectureTests(unittest.TestCase):
    def test_original_yolo_registry_and_asset_class_map_are_preserved(self):
        manifest = json.loads((ROOT / "models/model_manifest.json").read_text(encoding="utf-8"))
        policy = json.loads((ROOT / "data/models/yolo_class_policy.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "TrainingDatasetStudio/registries/yolo_detector_v1.json").read_text(encoding="utf-8"))
        expected = {int(row["id"]): row["name"] for row in registry["classes"]}
        self.assertEqual({int(row["class_id"]): row["name"] for row in policy["classes"]}, expected)
        self.assertEqual(set(policy["active_classes"]), set(expected))
        historical = policy["historical_32_class_checkpoint"]
        self.assertEqual(len(historical["classes"]), 32)
        self.assertEqual(list(manifest["models"]["yolo"]["class_names"]),
                         [row["name"] for row in historical["classes"]])
        class_map = json.loads((ROOT / "models/asset_classifier/asset_class_map.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(class_map.values()), list(range(26)))
        self.assertEqual(len(class_map), 26)

    def test_legacy_26_class_checkpoint_is_preserved_but_not_a_shared_five_head_model(self):
        source = ROOT / "models/asset_classifier/asset_classifier.pth"
        initialization = ROOT / "models/unified_body_images_fullbody/asset_classifier_initialization_26class.pth"
        self.assertTrue(initialization.is_file())
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        expected = "EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2"
        self.assertEqual(digest(source).upper(), expected)
        self.assertEqual(digest(initialization).upper(), expected)
        import torch
        state = torch.load(initialization, map_location="cpu")
        self.assertEqual(tuple(state["fc.weight"].shape), (26, 512))
        self.assertEqual(tuple(state["fc.bias"].shape), (26,))
        self.assertNotIn("heads.body_images.weight", state)

    def test_registry_defines_one_unified_cnn_and_one_clothing_cnn(self):
        registry = json.loads((ROOT / "data/models/phase4_model_registry.json").read_text(encoding="utf-8"))
        self.assertEqual(validate_registry(registry), [])
        self.assertEqual(set(registry["models"]), {"yolo_detector", "unified_body_images_fullbody_cnn", "clothing_classifier"})
        unified = registry["models"]["unified_body_images_fullbody_cnn"]
        self.assertEqual(unified["output_groups"], {
            "body_images": 2, "fullbody": 5, "portrait": 2, "arousal": 2, "corruption": 4
        })
        self.assertTrue(unified["one_model_identity"])
        self.assertEqual(registry["models"]["clothing_classifier"]["class_count"], 12)
        class_registry = json.loads((ROOT / "data/models/unified_body_images_fullbody/class_registry.json").read_text())
        self.assertEqual([item["class_name"] for item in class_registry["output_groups"]["body_images"]["classes"]],
                         ["bodypart_cum", "bodypart_acc"])
        self.assertEqual([item["class_name"] for item in class_registry["output_groups"]["fullbody"]["classes"]],
                         ["clothed", "topless", "bottomless", "bra", "panty"])

    def test_clothing_cnn_keeps_original_class_map_and_yolo_region_routing(self):
        registry = json.loads((ROOT / "data/models/phase4_model_registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["models"]["clothing_classifier"]["class_count"], 12)
        clothing = json.loads((ROOT / "data/models/clothing_classifier_registry.json").read_text(encoding="utf-8"))
        self.assertEqual(len(clothing["classes"]), 12)
        self.assertTrue(all(row["application_role"] == "broad_family_prediction" and
                            row["detailed_tag_selection"] == "human_only" for row in clothing["classes"]))

    def test_retired_portrait_identity_is_metadata_only(self):
        registry = json.loads((ROOT / "data/models/phase4_model_registry.json").read_text(encoding="utf-8"))
        self.assertNotIn("portrait_classifier_v1", registry["models"])
        self.assertEqual(registry["retired_model_identities"]["portrait_classifier_v1"]["status"],
                         "superseded_by_unified_model")

    def test_rejected_uncertain_and_ai_predictions_are_not_trusted(self):
        manifest = {"schema_version": 1, "dataset_id": "fixture", "task": "portrait_classifier_v1", "seed": 42,
                    "split_ratios": {"train": .8, "validation": .1, "test": .1}, "status": "review_queue_only",
                    "samples": [{"source_sha256": "a" * 64, "split": "train", "review_status": "ai_candidate", "eligibility": "trusted_training"}]}
        self.assertTrue(any("nonhuman_label" in error for error in validate_manifest(manifest)))

    def test_source_hash_cannot_cross_splits(self):
        base = {"schema_version": 1, "dataset_id": "fixture", "task": "portrait_classifier_v1", "seed": 42,
                "split_ratios": {}, "status": "review_queue_only"}
        base["samples"] = [{"source_sha256": "b" * 64, "split": "train", "review_status": "human_confirmed", "eligibility": "trusted_training"},
                            {"source_sha256": "b" * 64, "split": "test", "review_status": "human_confirmed", "eligibility": "trusted_training"}]
        self.assertTrue(any("source_crosses_splits" in error for error in validate_manifest(base)))


if __name__ == "__main__":
    unittest.main()
