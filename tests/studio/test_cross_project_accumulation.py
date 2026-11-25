import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.training_source_exporter import export_training_source_bundle
from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.importer import BundleImporter
from TrainingDatasetStudio.studio.store import StudioStore


ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "unified_body_images_fullbody_cnn"
REGISTRY_ID = "newassetapp_unified_body_images_fullbody"
REGISTRY_VERSION = "v2_five_head_shared_backbone_untrained"


class CrossProjectAccumulationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="studio_cross_project_")
        self.root = Path(self.temp.name)
        config = StudioConfig(root=self.root / "studio")
        config.ensure_directories()
        shutil.copytree(ROOT / "TrainingDatasetStudio" / "contracts",
                        config.contract_dir, dirs_exist_ok=True)
        self.store = StudioStore(config.database_path)
        self.store.initialize()
        self.importer = BundleImporter(config, self.store)

    def tearDown(self):
        self.temp.cleanup()

    def _project_bundle(self, name, color):
        project = self.root / name
        media_dir = project / "source-images"
        media_dir.mkdir(parents=True)
        source = media_dir / "source.png"
        Image.new("RGB", (120, 100), color).save(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        database = Database(project / "newassetapp.sqlite3")
        database.initialize()
        source_id, _ = database.upsert_source_image({
            "path": str(source.resolve()), "sha256": digest, "width": 120,
            "height": 100, "file_size": source.stat().st_size,
            "modified_ns": source.stat().st_mtime_ns,
        })
        detection = database.record_yolo_detection(
            source_id, model_id="fixture", model_digest="disposable",
            class_id=20, class_name="fullbody_clothed", confidence=.95,
            bbox_xyxy=[10, 10, 110, 90])
        database.ensure_active_detection_crop(int(detection["detection_id"]))
        proposal_id = int(detection["proposal_id"])
        database.save_normal_crop_choice(
            proposal_id, "fullbody", main_tag="clothed", fullbody_state="clothed")
        database.confirm_normal_crop_classification(proposal_id)
        self.assertEqual(len(database.current_training_examples(
            "unified_body_images_fullbody", task_head="fullbody")), 1)
        return export_training_source_bundle(database, project / "handoff")

    def _series(self):
        with self.store.connect() as db:
            row = db.execute(
                """SELECT COUNT(*) AS segments,COALESCE(SUM(record_count),0) AS records,
                          COALESCE(SUM(size_bytes),0) AS bytes
                   FROM training_bundles
                   WHERE task='shared_cnn' AND model_id=? AND registry_id=?
                     AND registry_version=?""",
                (MODEL_ID, REGISTRY_ID, REGISTRY_VERSION),
            ).fetchone()
        return dict(row)

    def test_independent_source_folders_accumulate_and_reimport_is_idempotent(self):
        first_bundle = self._project_bundle("project-one", (20, 90, 150))
        second_bundle = self._project_bundle("project-two", (170, 35, 75))
        self.assertEqual(self._series(), {"segments": 0, "records": 0, "bytes": 0})

        first = self.importer.import_bundle(first_bundle["directory"])
        first_series = self._series()
        self.assertEqual((first["accepted"], first["quarantined"]), (1, 0))
        self.assertEqual(first_series["segments"], 1)
        self.assertEqual(first_series["records"], 1)
        print(f"after project one import: {first_series}", flush=True)

        second = self.importer.import_bundle(second_bundle["directory"])
        second_series = self._series()
        self.assertEqual((second["accepted"], second["quarantined"]), (1, 0))
        self.assertEqual(second_series["segments"], 1)
        self.assertEqual(second_series["records"], 2)
        self.assertEqual(self.store.list_training_bundles()[0]["max_bytes"], 5_000_000_000)
        print(f"after project two import: {second_series}", flush=True)

        duplicate = self.importer.import_bundle(second_bundle["directory"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(self._series(), second_series)
        self.assertEqual(len(self.store.list_records(
            task="fullbody_state_classification")), 2)

        sources = {
            row["source_sha256"]
            for row in self.store.list_records(task="fullbody_state_classification")
        }
        self.assertEqual(len(sources), 2)
        records = self.store.list_records(task="fullbody_state_classification")
        self.assertEqual({row["model_id"] for row in records}, {MODEL_ID})
        self.assertEqual(len({row["source_project_id"] for row in records}), 2)
        for row in records:
            self.assertTrue(row["human_confirmed"])
            self.assertEqual(row["annotation"]["bbox_xyxy"], [10.0, 10.0, 110.0, 90.0])
            detection = row["original"]["detection"]
            self.assertEqual(detection["detection_id"], row["original"]["provenance"]["model_prediction"]["yolo"]["detection_id"])
            self.assertEqual(detection["bbox_xyxy"], [10.0, 10.0, 110.0, 90.0])
            self.assertEqual(detection["class_name"], "fullbody_clothed")
            self.assertEqual(row["original"]["provenance"]["crop_revision"]["bbox_xyxy"],
                             [10.0, 10.0, 110.0, 90.0])
            self.assertTrue(row["original"]["provenance"]["model_prediction"]["yolo"]["model_digest"])
            self.assertEqual(row["original"]["media"]["role"], "authoritative_detection_crop")
            self.assertEqual(row["original"]["media"]["source_sha256"], row["source_sha256"])


if __name__ == "__main__":
    unittest.main()
