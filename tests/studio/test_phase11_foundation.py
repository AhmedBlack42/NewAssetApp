import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
CLASSES_PATH = REGISTRY_PATH.parent / "classes.txt"
HASH_PATH = REGISTRY_PATH.parent / "classes.sha256"
CONTRACT_PATH = ROOT / "TrainingDatasetStudio" / "contracts" / "newassetapp_import_v1.schema.json"


EXPECTED = [
    "person", "face", "portrait_frame", "boobs", "ass", "pussy", "legs",
    "boobs_cover_item", "pussy_cover_item", "ass_cover_item", "leg_cover_item",
    "accessory_footwear", "fullbody_shower", "fullbody_maid", "fullbody_nurse",
    "fullbody_uniform", "fullbody_athletic", "fullbody_swimsuit", "fullbody_bikini",
    "fullbody_work", "fullbody_clothed", "fullbody_bare", "fullbody_underwear",
    "location_class", "location_office", "location_bathroom", "location_bar",
    "location_park", "location_beach", "location_clinic", "location_home",
]


class Phase11FoundationTests(unittest.TestCase):
    def test_new_registry_has_exact_order_and_ids(self):
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        classes = registry["classes"]
        self.assertEqual(registry["class_count"], 31)
        self.assertEqual([item["id"] for item in classes], list(range(31)))
        self.assertEqual([item["name"] for item in classes], EXPECTED)
        self.assertEqual(len({item["name"] for item in classes}), 31)

    def test_xanylabeling_class_list_and_digest_match_registry(self):
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        names = [item["name"] for item in registry["classes"]]
        class_bytes = ("\n".join(names) + "\n").encode("utf-8")
        self.assertEqual(CLASSES_PATH.read_bytes(), class_bytes)
        digest = hashlib.sha256(class_bytes).hexdigest()
        self.assertEqual(HASH_PATH.read_text(encoding="ascii").strip(), digest)

    def test_import_contract_is_versioned_and_provenance_gated(self):
        schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        record = schema["$defs"]["record"]
        self.assertTrue({"source", "review", "labels", "provenance"}.issubset(record["required"]))
        self.assertEqual(
            schema["properties"]["registry"]["required"], ["id", "version", "sha256"]
        )
        self.assertIn("yolo_detection", record["properties"]["task"]["enum"])


if __name__ == "__main__":
    unittest.main()
