import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.core.tag_library import TagLibrary
from validate_tag_library import validate_tag_library


ROOT = Path(__file__).resolve().parents[1]
TAG_DIR = ROOT / "data" / "tags"


class TagLibraryValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp.name) / "tags"
        shutil.copytree(TAG_DIR, self.data_dir)

    def tearDown(self):
        self.temp.cleanup()

    def _load(self, filename):
        return json.loads((self.data_dir / filename).read_text(encoding="utf-8"))

    def _save(self, filename, payload):
        (self.data_dir / filename).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def test_extracted_library_passes_validation(self):
        self.assertEqual(validate_tag_library(self.data_dir), [])

    def test_duplicate_id_is_rejected(self):
        payload = self._load("fullbody_tags.json")
        payload["entries"].append(dict(payload["entries"][0]))
        self._save("fullbody_tags.json", payload)
        self.assertTrue(any("duplicate id" in e for e in validate_tag_library(self.data_dir)))

    def test_case_only_canonical_spelling_collision_is_rejected(self):
        payload = self._load("body_images_tags.json")
        original = next(e for e in payload["entries"] if e.get("serialized_value") == "boobs")
        variant = dict(original)
        variant.update({"id": "test|body_images|BOOBS", "name": "BOOBS",
                        "display_name": "BOOBS", "serialized_value": "BOOBS",
                        "context_path": ["test_variant"]})
        payload["entries"].append(variant)
        self._save("body_images_tags.json", payload)
        self.assertTrue(any("case-insensitive spelling collision" in e
                            for e in validate_tag_library(self.data_dir)))

    def test_one_canonical_token_cannot_be_main_and_subtag(self):
        payload = self._load("body_images_tags.json")
        original = next(e for e in payload["entries"] if e.get("serialized_value") == "boobs")
        variant = dict(original)
        variant.update({"id": "test|body_images|boobs_subtag", "name": "boobs",
                        "tag_type": "subtag", "context_path": ["test_variant"]})
        payload["entries"].append(variant)
        self._save("body_images_tags.json", payload)
        self.assertTrue(any("conflicting tag types" in e
                            for e in validate_tag_library(self.data_dir)))

    def test_wrong_group_is_rejected(self):
        payload = self._load("body_images_tags.json")
        payload["entries"][0]["group"] = "clothing"
        self._save("body_images_tags.json", payload)
        self.assertTrue(any("incorrect group" in e for e in validate_tag_library(self.data_dir)))

    def test_missing_parent_is_rejected(self):
        payload = self._load("fullbody_tags.json")
        next(e for e in payload["entries"] if e["parent_id"] is not None)["parent_id"] = "missing-parent"
        self._save("fullbody_tags.json", payload)
        self.assertTrue(any("missing or cross-group parent" in e for e in validate_tag_library(self.data_dir)))

    def test_parent_cycle_is_rejected(self):
        payload = self._load("fullbody_tags.json")
        entry = next(e for e in payload["entries"] if e["parent_id"] is not None)
        entry["parent_id"] = entry["id"]
        self._save("fullbody_tags.json", payload)
        self.assertTrue(any("circular parent" in e for e in validate_tag_library(self.data_dir)))

    def test_review_flag_requires_review_record(self):
        payload = self._load("fullbody_tags.json")
        entry = next(e for e in payload["entries"] if not e["requires_review"])
        entry["requires_review"] = True
        self._save("fullbody_tags.json", payload)
        self.assertTrue(any("missing ambiguous entry" in e for e in validate_tag_library(self.data_dir)))

    def test_user_additions_are_separate_and_require_explicit_parent(self):
        lib = TagLibrary(self.data_dir)
        before = (self.data_dir / "fullbody_tags.json").read_bytes()
        created = lib.add_user_tag(
            group="clothing", name="Custom cloak", serialized_value="custom_cloak",
            tag_type="main", description="User-defined garment", parent_id=None,
        )
        self.assertEqual(created["source"], "user_created")
        self.assertIsNone(created["parent_id"])
        self.assertEqual((self.data_dir / "fullbody_tags.json").read_bytes(), before)
        self.assertIn(created["id"], [e["id"] for e in lib.search("Custom cloak", group="clothing")])
        lib.deprecate_user_tag(created["id"])
        self.assertNotIn(created["id"], [e["id"] for e in lib.entries(group="clothing")])
        self.assertIn(created["id"], [e["id"] for e in lib.entries(group="clothing", include_deprecated=True)])


if __name__ == "__main__":
    unittest.main()
