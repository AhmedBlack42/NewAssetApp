import unittest

from app.core.proposals import suggest_proposal


class ProposalMappingTests(unittest.TestCase):
    def test_known_class_routes_to_body_images(self):
        result = suggest_proposal("bodypart_face", 0.91)
        self.assertEqual((result.category, result.asset_type), ("body_images", "face"))

    def test_legacy_fullbody_asset_cnn_class_stays_raw_for_review(self):
        result = suggest_proposal("fullbody_nude_states", 0.91)
        self.assertEqual(result.category, "others")
        self.assertEqual(result.review_status, "review_required")
        self.assertEqual(result.asset_type, "fullbody_nude_states")

    def test_source_defined_category_crosswalks_remain_review_only(self):
        expected = {
            "footwear": "footwear", "outerwear": "outerwear", "panty": "panty",
            "lingerie": "lingerie", "bra": "bra", "shirt": "shirt", "top": "top",
            "pantyhose": "socks", "vest": "upper",
        }
        for label, category_tag in expected.items():
            result = suggest_proposal(label, .91)
            if label == "vest":
                self.assertEqual(result.category, "clothing")
                self.assertEqual(result.asset_type, category_tag)
            else:
                self.assertEqual(result.category, "clothing")
                self.assertEqual(result.asset_type, category_tag)
                self.assertEqual(result.review_status, "pending")
                self.assertIn("specific garment tag", result.reason)

    def test_inactive_sweater_is_not_routed_as_a_clothing_class(self):
        self.assertEqual(suggest_proposal("sweater", .99).category, "others")

    def test_unknown_classes_go_to_others_and_low_confidence_keeps_its_task_group(self):
        self.assertEqual(suggest_proposal("unknown", 0.99).category, "others")
        low_portrait = suggest_proposal("bodypart_portrait_clothed", 0.4)
        self.assertEqual((low_portrait.category, low_portrait.asset_type, low_portrait.review_status),
                         ("body_images", "portrait", "review_required"))
        low_tportrait = suggest_proposal("bodypart_portrait_topless", None)
        self.assertEqual((low_tportrait.category, low_tportrait.asset_type, low_tportrait.review_status),
                         ("body_images", "tportrait", "review_required"))
        low_bra = suggest_proposal("bra", 0.4)
        self.assertEqual((low_bra.category, low_bra.asset_type, low_bra.review_status),
                         ("clothing", "bra", "review_required"))
        self.assertEqual(suggest_proposal("bra", None).category, "clothing")

    def test_photoshoots_are_never_an_ai_destination(self):
        for label in ("bodypart_face", "fullbody_clothed_states", "dress", "unknown"):
            self.assertNotEqual(suggest_proposal(label, 0.99).category, "photoshoots")


if __name__ == "__main__":
    unittest.main()
