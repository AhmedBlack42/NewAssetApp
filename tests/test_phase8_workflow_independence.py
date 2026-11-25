import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PIL import ImageDraw

from app.core.database import Database
from app.core.output_exporter import build_normal_output_plan, export_normal_output


class Phase8WorkflowIndependenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source_path = self.root / "source.png"
        image = Image.new("RGBA", (900, 900), (0, 0, 0, 0))
        for x in range(220, 680):
            for y in range(180, 760):
                image.putpixel((x, y), (220, 80, 120, 255))
        image.save(self.source_path)
        self.db = Database(self.root / "app.sqlite3")
        self.db.initialize()
        digest = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        self.source_id, _ = self.db.upsert_source_image({
            "path": str(self.source_path.resolve()), "sha256": digest,
            "width": 900, "height": 900, "file_size": self.source_path.stat().st_size,
            "modified_ns": self.source_path.stat().st_mtime_ns,
        })

    def tearDown(self):
        self.temp.cleanup()

    def _proposal(self, category, class_id, class_name, bbox=(100, 100, 800, 850), asset_type=None):
        return self.db.record_yolo_detection(
            self.source_id, model_id="phase8-fixture", model_digest="fixture-digest",
            class_id=class_id, class_name=class_name, confidence=.9, bbox_xyxy=list(bbox),
        )

    def _choose_normal_classification(self, proposal_id, category, main_tag, fullbody_state=None, **kwargs):
        self.db.save_normal_crop_choice(
            proposal_id, category, main_tag=main_tag, fullbody_state=fullbody_state, **kwargs
        )

    def test_normal_export_uses_unconfirmed_proposal_and_separate_history(self):
        proposal = self._proposal("clothing", 8, "boobs_cover_item")
        self._choose_normal_classification(proposal["proposal_id"], "clothing", "heels",
                                           clothing_broad_family="footwear",
                                           clothing_cover_area="accessory_footwear")
        plan = build_normal_output_plan(self.db, self.root / "output", [proposal["proposal_id"]])
        self.assertEqual(plan["item_count"], 1)
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 1)
        self.assertTrue((self.root / "output" / "clothing").is_dir())
        self.assertEqual(self.db.output_review_records(), [])
        self.assertEqual(self.db.normal_crop_export_count(), 1)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM training_records").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM dataset_split_assignments").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM final_assets").fetchone()[0], 0)
            self.assertEqual(connection.execute(
                "SELECT review_status FROM asset_proposals WHERE id=?", (proposal["proposal_id"],)
            ).fetchone()[0], "review_required")

    def test_normal_category_choice_does_not_change_professional_proposal_state(self):
        proposal = self._proposal("others", 12, "location_home")
        proposal_id = proposal["proposal_id"]
        self.db.save_normal_crop_choice(proposal_id, "body_images", "face")
        candidate = next(row for row in self.db.normal_crop_records() if row["id"] == proposal_id)
        self.assertEqual(candidate["category"], "body_images")
        plan = build_normal_output_plan(self.db, self.root / "output", [proposal_id])
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 1)
        self.assertTrue((self.root / "output" / "body_images").is_dir())
        with self.db.connect() as connection:
            state = connection.execute(
                "SELECT category,review_status FROM asset_proposals WHERE id=?", (proposal_id,)
            ).fetchone()
        self.assertEqual(state["category"], "others")
        self.assertEqual(state["review_status"], "review_required")
        self.assertEqual(self.db.output_review_records(), [])

    def test_fullbody_normal_route_uses_existing_alpha_crop_rule(self):
        proposal = self._proposal("fullbody", 20, "fullbody_clothed")
        self._choose_normal_classification(proposal["proposal_id"], "fullbody", "clothed", "clothed")
        plan = build_normal_output_plan(self.db, self.root / "output", [proposal["proposal_id"]])
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 1)
        self.assertTrue((self.root / "output" / "fullbody").is_dir())

    def test_fullbody_opaque_source_uses_normal_background_removal_without_review_confirmation(self):
        opaque_path = self.root / "opaque.jpg"
        Image.new("RGB", (900, 900), "teal").save(opaque_path)
        digest = hashlib.sha256(opaque_path.read_bytes()).hexdigest()
        source_id, _ = self.db.upsert_source_image({
            "path": str(opaque_path.resolve()), "sha256": digest,
            "width": 900, "height": 900, "file_size": opaque_path.stat().st_size,
            "modified_ns": opaque_path.stat().st_mtime_ns,
        })
        proposal = self.db.record_yolo_detection(
            source_id, model_id="fixture", model_digest="fixture-digest",
            class_id=20, class_name="fullbody_clothed", confidence=.91, bbox_xyxy=[100, 100, 800, 850],
        )
        self._choose_normal_classification(proposal["proposal_id"], "fullbody", "clothed", "clothed")

        def segment(region):
            result = region.convert("RGBA")
            alpha = Image.new("L", result.size, 0)
            ImageDraw.Draw(alpha).rectangle(
                (12, 12, result.width - 13, result.height - 13), fill=255
            )
            result.putalpha(alpha)
            return result

        plan = build_normal_output_plan(self.db, self.root / "output", [proposal["proposal_id"]])
        result = export_normal_output(self.db, plan, background_remover=segment)
        self.assertEqual(result["written_count"], 1)
        self.assertTrue((self.root / "output" / "fullbody").is_dir())
        with self.db.connect() as connection:
            proposal_state = connection.execute(
                "SELECT review_status FROM asset_proposals WHERE id=?", (proposal["proposal_id"],)
            ).fetchone()[0]
            history = connection.execute(
                "SELECT processing_json FROM normal_crop_exports WHERE proposal_id=?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM training_records").fetchone()[0], 0)
        self.assertEqual(proposal_state, "review_required")
        self.assertIn("background_removal", history)

    def test_body_images_normal_route_uses_human_crop_rule_tag(self):
        proposal = self._proposal("body_images", 2, "portrait_frame")
        self._choose_normal_classification(proposal["proposal_id"], "body_images", "face")
        plan = build_normal_output_plan(self.db, self.root / "output", [proposal["proposal_id"]])
        self.assertEqual(plan["item_count"], 1)
        result = export_normal_output(self.db, plan)
        self.assertEqual(result["written_count"], 1)
        self.assertTrue((self.root / "output" / "body_images").is_dir())


if __name__ == "__main__":
    unittest.main()
