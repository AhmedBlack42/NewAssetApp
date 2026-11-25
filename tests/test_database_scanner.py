import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database, SCHEMA_VERSION
from app.core.scanner import scan_folder


class DatabaseScannerTests(unittest.TestCase):
    def test_proposals_and_invalid_state_belong_to_individual_detections(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "multi.png"
            Image.new("RGB", (100, 80), "purple").save(source)
            db = Database(root / "app.sqlite3")
            db.initialize()
            source_id, _ = db.upsert_source_image({
                "path": str(source.resolve()), "sha256": "b" * 64,
                "width": 100, "height": 80, "file_size": source.stat().st_size,
                "modified_ns": source.stat().st_mtime_ns,
            })
            with db.connect() as connection:
                first = connection.execute(
                    """INSERT INTO yolo_detections(source_image_id,class_id,class_name,confidence,x1,y1,x2,y2)
                       VALUES (?,0,'person',0.9,1,2,40,70)""", (source_id,),
                ).lastrowid
                second = connection.execute(
                    """INSERT INTO yolo_detections(source_image_id,class_id,class_name,confidence,x1,y1,x2,y2)
                       VALUES (?,1,'face',0.8,5,5,30,30)""", (source_id,),
                ).lastrowid
                first_proposal = connection.execute(
                    "INSERT INTO asset_proposals(source_image_id,detection_id,category) VALUES (?,?,'fullbody')",
                    (source_id, first),
                ).lastrowid
                connection.execute(
                    "INSERT INTO asset_proposals(source_image_id,detection_id,category) VALUES (?,?,'body_images')",
                    (source_id, second),
                )
            rows = db.detections_for_source(source_id)
            self.assertEqual([row["category"] for row in rows], ["fullbody", "body_images"])
            proposals = db.proposals_for_source(source_id)
            self.assertEqual(len(proposals), 2)
            self.assertEqual({row["category"] for row in proposals}, {"fullbody", "body_images"})
            db.invalidate_detection(first, "False positive")
            rows = db.detections_for_source(source_id)
            invalid = next(row for row in rows if row["id"] == first)
            other = next(row for row in rows if row["id"] == second)
            self.assertEqual(invalid["origin"], "rejected")
            self.assertEqual(invalid["invalid_reason"], "False positive")
            self.assertEqual(other["category"], "body_images")
            with db.connect() as connection:
                self.assertEqual(connection.execute(
                    "SELECT category FROM asset_proposals WHERE id=?", (first_proposal,)
                ).fetchone()[0], "fullbody")
            db.restore_detection(first)
            restored = next(row for row in db.detections_for_source(source_id) if row["id"] == first)
            self.assertNotEqual(restored["origin"], "rejected")
            with db.connect() as connection:
                events = connection.execute(
                    "SELECT decision_type FROM correction_records WHERE detection_id=? ORDER BY id", (first,)
                ).fetchall()
            self.assertEqual([event[0] for event in events], ["rejected", "corrected"])

    def test_photoshoot_groups_are_manual_memberships_not_category_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "proposal.png"
            Image.new("RGB", (20, 30), "purple").save(source)
            db = Database(root / "app.sqlite3")
            db.initialize()
            source_id, _ = db.upsert_source_image({
                "path": str(source.resolve()), "sha256": "a" * 64,
                "width": 20, "height": 30, "file_size": source.stat().st_size,
                "modified_ns": source.stat().st_mtime_ns,
            })
            with db.connect() as connection:
                proposal_id = connection.execute(
                    "INSERT INTO asset_proposals(source_image_id, category) VALUES (?, 'fullbody')",
                    (source_id,),
                ).lastrowid
            group_id = db.create_photoshoot_group("Summer")
            self.assertEqual(db.add_proposals_to_photoshoot(group_id, [proposal_id]), 1)
            self.assertEqual(db.add_proposals_to_photoshoot(group_id, [proposal_id]), 0)
            self.assertEqual(len(db.photoshoot_members(group_id)), 1)
            self.assertEqual(db.proposals_for_category("fullbody")[0]["id"], proposal_id)
            db.rename_photoshoot_group(group_id, "Summer 2026")
            self.assertEqual(db.photoshoot_groups()[0]["name"], "Summer 2026")
            self.assertEqual(db.remove_proposals_from_photoshoot(group_id, [proposal_id]), 1)
            self.assertEqual(db.photoshoot_members(group_id), [])
            self.assertEqual(db.proposals_for_category("fullbody")[0]["category"], "fullbody")

    def test_database_migrates_and_scans_images_without_video(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "pics"
            folder.mkdir()
            Image.new("RGB", (80, 60), "red").save(folder / "one.png")
            (folder / "copy.png").write_bytes((folder / "one.png").read_bytes())
            (folder / "clip.mp4").write_bytes(b"not an image")

            db = Database(root / "data" / "app.sqlite3")
            db.initialize()
            result = scan_folder(folder, db, recursive=True)

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["total"], 2)
            self.assertEqual(result["indexed"], 2)
            self.assertEqual(result["duplicates"], 1)
            self.assertEqual(len(db.source_images(folder)), 2)
            with db.connect() as connection:
                version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertTrue({
                "source_images", "yolo_detections", "cnn_predictions",
                "asset_proposals", "user_decisions", "processing_jobs",
                "final_assets", "training_records", "photoshoot_groups",
                "photoshoot_memberships",
            }.issubset(tables))

    def test_images_can_be_scanned_non_recursively(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested = root / "nested"
            nested.mkdir()
            Image.new("RGB", (12, 15), "blue").save(root / "top.webp")
            Image.new("RGB", (12, 15), "green").save(nested / "inner.webp")
            db = Database(root / "app.sqlite3")
            db.initialize()

            result = scan_folder(root, db, recursive=False)
            self.assertEqual(result["indexed"], 1)
            self.assertEqual(Path(db.source_images(root)[0]["path"]).name, "top.webp")


if __name__ == "__main__":
    unittest.main()
