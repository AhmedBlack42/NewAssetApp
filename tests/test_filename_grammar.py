import unittest
import json
from pathlib import Path

from app.core.filename_grammar import (
    body_images_filename, clothing_filename, parse_body_images_filename,
    parse_clothing_filename,
)
from app.core.fullbody_classification import fullbody_filename, parse_fullbody_filename
from app.core.tag_library import TagLibrary


ROOT = Path(__file__).resolve().parents[1]


class FilenameGrammarTests(unittest.TestCase):
    def test_fullbody_uses_universal_main_subtag_grammar(self):
        examples = (
            ("clothed", "topless", ["slut"], "clothed-topless,slut1.webp"),
            ("clothed", "topless", ["slut", "park"], "clothed-topless,slut,park1.webp"),
            ("bikini", "clothed", ["slut"], "bikini-clothed,slut1.webp"),
        )
        for main, state, tags, expected in examples:
            with self.subTest(expected=expected):
                filename = fullbody_filename(main, state, 1, tags)
                self.assertEqual(filename, expected)
                parsed = parse_fullbody_filename(filename)
                self.assertEqual(parsed["main_tag"], main)
                self.assertEqual(parsed["subtags"], tags)
                self.assertTrue(parsed["source_metadata_only"])
                self.assertEqual(parsed["sequence"], 1)
        self.assertIsNone(parse_fullbody_filename(examples[0][3])["sub_main_tag"])
        legacy = parse_fullbody_filename("clothed_topless_slut1.webp")
        self.assertEqual(legacy["subtags"], ["slut"])
        self.assertEqual(legacy["legacy_separator"], "legacy_underscore_subtag")
        legacy_comma = parse_fullbody_filename("clothed_bottomless4,conservative.webp")
        self.assertEqual((legacy_comma["sequence"], legacy_comma["subtags"]),
                         (4, ["conservative"]))
        with self.assertRaises(ValueError):
            fullbody_filename("bikini", "topless", 1, ["slut"])

    def test_clothing_uses_universal_main_subtag_grammar(self):
        examples = (
            ("mini_skirt", ["slut"], "mini_skirt-slut1.webp"),
            ("mini_skirt", ["slut", "conservative"], "mini_skirt-slut,conservative1.webp"),
            ("pantyhose", ["u_whore"], "pantyhose-u_whore1.webp"),
        )
        for main, tags, expected in examples:
            with self.subTest(expected=expected):
                filename = clothing_filename(main, 1, tags)
                self.assertEqual(filename, expected)
                self.assertEqual(parse_clothing_filename(filename)["main_tag"], main)
                self.assertEqual(parse_clothing_filename(filename)["subtags"], tags)
        with self.assertRaises(ValueError):
            clothing_filename("panty", 1, ["u_whore"])
        with self.assertRaises(ValueError):
            clothing_filename("mini_skirt", 1, ["u_whore", "u_whore"])

    def test_body_images_composition_values_are_subtags(self):
        library = TagLibrary(ROOT / "data" / "tags")
        canonical_mains = {row["serialized_value"] for row in library.entries(group="body_images")
                           if row.get("tag_type") == "main"}
        self.assertIn("boobs", canonical_mains)
        self.assertNotIn("bobbs", canonical_mains)
        single = body_images_filename(["boobs"], 1, ["whore", "cum"])
        self.assertEqual(single, "boobs-whore,cum1.webp")
        parsed_single = parse_body_images_filename(single)
        self.assertEqual((parsed_single["main_tags"], parsed_single["sub_main_tag"], parsed_single["subtags"], parsed_single["sequence"]),
                         (["boobs"], None, ["whore", "cum"], 1))
        grouped = body_images_filename(["ass"], 3, ["creampie"])
        self.assertEqual(grouped, "ass-creampie3.webp")
        parsed = parse_body_images_filename(grouped)
        self.assertEqual(parsed["main_tags"], ["ass"])
        self.assertIsNone(parsed["sub_main_tag"])
        self.assertEqual(parsed["sequence"], 3)
        corrected = body_images_filename(["ass"], 1, ["bb"])
        self.assertEqual(corrected, "ass-bb1.webp")
        parsed_corrected = parse_body_images_filename(corrected)
        self.assertEqual((parsed_corrected["main_tags"], parsed_corrected["sub_main_tag"],
                          parsed_corrected["subtags"], parsed_corrected["sequence"]),
                         (["ass"], None, ["bb"], 1))
        self.assertEqual(body_images_filename(["boobs"], 1, ["cum"]), "boobs-cum1.webp")
        with self.assertRaises(ValueError):
            body_images_filename(["ass"], 1, ["cum"])
        with self.assertRaises(ValueError):
            body_images_filename(["bobbs"], 1, ["cum"])
        with self.assertRaises(ValueError):
            parse_body_images_filename("bobbs-cum1.webp")

    def test_all_application_category_registries_load_and_keep_exact_tokens(self):
        library = TagLibrary(ROOT / "data" / "tags")
        for category in ("clothing", "fullbody", "body_images", "photoshoots"):
            with self.subTest(category=category):
                self.assertTrue(library.entries(group=category))
        self.assertIn("u_whore", {row.get("serialized_value") for row in
                                   library.entries(group="body_images", include_review=True)})
        u_whore_rows = [row for row in library.entries(group="body_images", include_review=True)
                        if row.get("serialized_value") == "u_whore"]
        self.assertEqual(len(u_whore_rows), 1)
        u_whore = u_whore_rows[0]
        self.assertFalse(u_whore.get("requires_review"))
        self.assertIn("coffee_shop", {row.get("serialized_value") for row in
                                      library.entries(group="body_images", include_review=True)})

    def test_model_registries_match_manifest_and_crosswalk_without_renaming(self):
        manifest = json.loads((ROOT / "models" / "model_manifest.json").read_text(encoding="utf-8"))["models"]
        yolo_policy = json.loads((ROOT / "data" / "models" / "yolo_class_policy.json").read_text(encoding="utf-8"))
        asset_map = json.loads((ROOT / "models" / "asset_classifier" / "asset_class_map.json").read_text(encoding="utf-8"))
        crosswalk = json.loads((ROOT / "data" / "models" / "model_tag_crosswalk.json").read_text(encoding="utf-8"))
        yolo_registry = json.loads((ROOT / "TrainingDatasetStudio" / "registries" /
                                    "yolo_detector_v1.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["yolo"]["class_names"]), 32)
        expected = {int(row["id"]): row["name"] for row in yolo_registry["classes"]}
        self.assertEqual({int(row["class_id"]): row["name"] for row in yolo_policy["classes"]}, expected)
        self.assertEqual(set(yolo_policy["active_classes"]), set(expected))
        self.assertEqual([row["model_label"] for row in crosswalk["models"]["yolo"]],
                         [expected[index] for index in range(len(expected))])
        self.assertEqual(
            [row["model_label"] for row in crosswalk["models"]["historical_legacy_yolo"]],
            manifest["yolo"]["class_names"],
        )
        asset_rows = crosswalk["models"]["asset_classifier"]
        self.assertEqual({row["class_id"]: row["model_label"] for row in asset_rows},
                         {class_id: label for label, class_id in asset_map.items()})
        self.assertEqual([row["model_label"] for row in asset_rows],
                         manifest["asset_classifier"]["class_names"])
        self.assertEqual(next(row for row in crosswalk["models"]["yolo"] if row["class_id"] == 3)["model_label"],
                         "boobs")
        self.assertEqual(next(row for row in asset_rows if row["model_label"] == "bodypart_boobs")["application_candidate"],
                         "boobs")
        for model_label, candidate in (("footwear", "shoes"), ("outerwear", "outer"), ("panty", "panties")):
            row = next(row for row in asset_rows if row["model_label"] == model_label)
            self.assertEqual(row["application_candidate"], candidate)
            self.assertTrue(row["human_confirmation_required"])
        self.assertNotEqual(crosswalk["source_registries"]["yolo"],
                            "models/model_manifest.json + data/models/yolo_class_policy.json")


if __name__ == "__main__":
    unittest.main()
