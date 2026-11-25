import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core.classification_taxonomy import (
    REGISTRY_ID, REGISTRY_VERSION, legacy_fullbody_state_candidate,
    location_candidates, parse_tag_filename, serialize_filename, validate_record,
)
from app.core.database import Database, MIGRATIONS, SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
LEGACY_YOLO_DIGEST = "57449664aa24427c703770ae155a361da252f26be4840242aae95f3017df58ea"


class StructuredTaxonomyTests(unittest.TestCase):
    def test_universal_filename_grammar_and_source_metadata_parser(self):
        filename = serialize_filename(["boobs", "ass"], ["cum", "bb"], 2)
        self.assertEqual(filename, "boobs,ass-cum,bb2.webp")
        parsed = parse_tag_filename(filename)
        self.assertEqual(parsed["main_tags"], ["boobs", "ass"])
        self.assertEqual(parsed["subtags"], ["cum", "bb"])
        self.assertTrue(parsed["source_metadata_only"])
        self.assertEqual(REGISTRY_ID, "newassetapp_structured_classification")
        self.assertEqual(REGISTRY_VERSION, "1.0.0")

    def test_exact_body_pairs_and_unknown_values_are_rejected(self):
        validate_record("body_images", {"main_tag": "boobs", "subtags": ["cum"], "validity_state": "valid"})
        validate_record("body_images", {"main_tag": "ass", "subtags": ["creampie"], "validity_state": "valid"})
        validate_record("body_images", {"main_tag": "ass", "subtags": ["bb"], "validity_state": "valid"})
        validate_record("body_images", {"main_tag": "boobs", "subtags": ["u_whore"], "validity_state": "valid"})
        with self.assertRaises(ValueError):
            validate_record("body_images", {"main_tag": "ass", "subtags": ["cum"]})
        with self.assertRaises(ValueError):
            validate_record("body_images", {"main_tag": "boobs", "subtags": ["ultimate_whore"]})
        with self.assertRaises(ValueError):
            validate_record("body_images", {"main_tag": "unknown", "subtags": []})

    def test_legacy_fullbody_mapping_is_advisory_and_nude_is_ambiguous(self):
        identity = {"model_id": "asset_cnn", "checkpoint_digest": "eb1251dade9293098e327f3e708bf92f0c5fc09c272c6cddb0f4f04f210ae6d2"}
        clothed = legacy_fullbody_state_candidate("fullbody_clothed_states", **identity)
        costume = legacy_fullbody_state_candidate("fullbody_costume_states", **identity)
        nude = legacy_fullbody_state_candidate("fullbody_nude_states", **identity)
        self.assertEqual(clothed["candidate"], "clothed")
        self.assertEqual(costume["candidate"], "clothed")
        self.assertTrue(clothed["human_decision_required"])
        self.assertEqual(nude["choices"], ["topless", "bottomless"])
        self.assertTrue(nude["ambiguous"])
        self.assertIsNone(nude["candidate"])
        self.assertIsNone(legacy_fullbody_state_candidate("fullbody_nude_states", model_id="other_model",
                                                          checkpoint_digest=identity["checkpoint_digest"]))

    def test_location_suggestions_require_verified_model_identity_and_are_not_aliases(self):
        suggestion = location_candidates("location_bar", model_id="legacy_yolo", class_id=16,
                                          checkpoint_digest=LEGACY_YOLO_DIGEST)
        self.assertEqual(suggestion, ["bar", "coffee_shop", "mall"])
        self.assertEqual(location_candidates("location_park", model_id="legacy_yolo", class_id=17,
                                             checkpoint_digest=LEGACY_YOLO_DIGEST), [])
        self.assertEqual(location_candidates("location_beach", registry_id="newassetapp_yolo_detector_v1"),
                         ["beach", "pier", "park"])
        self.assertEqual(location_candidates("location_bar", model_id="legacy_yolo", class_id=16,
                                             checkpoint_digest="wrong"), [])

    def test_schema_v9_upgrade_preserves_rows_and_adds_current_tables(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "v9.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            for version in range(1, 10):
                connection.executescript("BEGIN IMMEDIATE;\n" + MIGRATIONS[version] +
                                         f"\nINSERT INTO schema_migrations(version) VALUES ({version});\nCOMMIT;")
            connection.execute("INSERT INTO normal_crop_choices(proposal_id,source_image_id,category,body_image_main_tag) "
                               "VALUES(41,7,'body_images','boobs')")
            connection.commit()
            connection.close()
            Database(path).initialize()
            upgraded = sqlite3.connect(path)
            try:
                self.assertEqual(upgraded.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(upgraded.execute("SELECT proposal_id,body_image_main_tag FROM normal_crop_choices").fetchone(), (41, "boobs"))
                columns = {row[1] for row in upgraded.execute("PRAGMA table_info(normal_crop_choices)")}
                self.assertTrue({"main_tag", "fullbody_state", "subtags_json", "location_value", "taxonomy_version"}.issubset(columns))
                self.assertIn("clothing_broad_family", columns)
                self.assertIsNotNone(upgraded.execute("SELECT name FROM sqlite_master WHERE name='structured_classifications'").fetchone())
                self.assertIsNotNone(upgraded.execute("SELECT name FROM sqlite_master WHERE name='training_examples'").fetchone())
            finally:
                upgraded.close()

    def test_schema_v11_migration_rolls_back_on_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conflict.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript("""
                CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO schema_migrations(version) VALUES (10);
                CREATE TABLE normal_crop_choices(proposal_id INTEGER PRIMARY KEY, source_image_id INTEGER,
                  category TEXT, body_image_main_tag TEXT, main_tag TEXT, clothing_broad_family TEXT, updated_at TEXT);
                CREATE TABLE normal_crop_exports(id INTEGER PRIMARY KEY);
                CREATE TABLE source_images(id INTEGER PRIMARY KEY);
                CREATE TABLE asset_proposals(id INTEGER PRIMARY KEY);
                CREATE TABLE yolo_detections(id INTEGER PRIMARY KEY);
            """)
            connection.commit()
            connection.close()
            with self.assertRaises(sqlite3.OperationalError):
                Database(path).initialize()
            rolled_back = sqlite3.connect(path)
            try:
                self.assertEqual(rolled_back.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 10)
                self.assertIsNone(rolled_back.execute("SELECT name FROM sqlite_master WHERE name='structured_classifications'").fetchone())
            finally:
                rolled_back.close()


if __name__ == "__main__":
    unittest.main()
