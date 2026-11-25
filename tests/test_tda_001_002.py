import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.classification_eligibility import eligible_shared_heads, shared_head_eligible
from app.core.training_source_exporter import export_training_source_bundle
from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.importer import BundleImporter
from TrainingDatasetStudio.studio.store import StudioStore
from TrainingDatasetStudio.studio.datasets import DatasetService
from TrainingDatasetStudio.studio.training import TrainingManager


class TDAImplementationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tda_implementation_")
        self.root = Path(self.temp.name)
        self.source = self.root / "source.png"
        Image.new("RGB", (300, 300), "teal").save(self.source)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.db = Database(self.root / "newasset.sqlite3")
        self.db.initialize()
        self.source_id, _ = self.db.upsert_source_image({
            "path": str(self.source.resolve()), "sha256": digest,
            "width": 300, "height": 300, "file_size": self.source.stat().st_size,
            "modified_ns": self.source.stat().st_mtime_ns,
        })

    def tearDown(self):
        self.temp.cleanup()

    def _detection(self, class_id, name):
        return self.db.record_yolo_detection(
            self.source_id, model_id="fixture", model_digest="fixture",
            class_id=class_id, class_name=name, confidence=.9,
            bbox_xyxy=[20, 20, 280, 280])

    def test_body_images_four_completed_combinations_and_pending(self):
        expected = (
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        )
        for index, (cum, accessory) in enumerate(expected):
            with self.subTest(cum=cum, accessory=accessory):
                detection = self._detection(3, "boobs")
                review_id = self.db.save_classification_task_review(
                    detection["proposal_id"], "body_images", "body_images_pending",
                    {
                        "validity_state": "valid",
                        "cum_target": cum,
                        "cum_evaluated": True,
                        "accessory_target": accessory,
                        "accessory_evaluated": True,
                        "body_images_completed": True,
                    },
                    action="confirmed", training_eligible=True)
                status = self.db.classification_task_status(detection["proposal_id"])["body_images"]
                self.assertTrue(status["human_confirmed"])
                self.assertTrue(status["training_eligible"])
                self.assertTrue(status["cum_evaluated"])
                self.assertTrue(status["accessory_evaluated"])
                self.assertEqual(bool(status["cum_target"]), cum)
                self.assertEqual(bool(status["accessory_target"]), accessory)
                self.assertIsInstance(review_id, int)

        pending = self._detection(3, "boobs")
        self.db.save_classification_task_review(
            pending["proposal_id"], "body_images", "body_images_pending",
            {"validity_state": "valid"},
            action="confirmed", training_eligible=True)
        status = self.db.classification_task_status(pending["proposal_id"])["body_images"]
        self.assertTrue(status["human_confirmed"])
        self.assertFalse(status["training_eligible"])
        self.assertFalse(status["cum_evaluated"])
        self.assertFalse(status["accessory_evaluated"])

    def test_body_images_one_target_changed_preserves_the_other(self):
        detection = self._detection(3, "boobs")
        payload = {
            "validity_state": "valid",
            "cum_target": True,
            "cum_evaluated": True,
            "accessory_target": False,
            "accessory_evaluated": True,
            "body_images_completed": True,
        }
        self.db.save_classification_task_review(
            detection["proposal_id"], "body_images", "body_images_pending", payload,
            action="confirmed", training_eligible=True)
        payload["accessory_target"] = True
        self.db.save_classification_task_review(
            detection["proposal_id"], "body_images", "body_images_pending", payload,
            action="confirmed", training_eligible=True)
        status = self.db.classification_task_status(detection["proposal_id"])["body_images"]
        self.assertTrue(status["cum_target"])
        self.assertTrue(status["accessory_target"])
        examples = [row for row in self.db.current_training_examples("unified_body_images_fullbody")
                    if row["proposal_id"] == detection["proposal_id"]]
        self.assertTrue(examples)
        mask = json.loads(examples[-1]["target_mask_json"])
        self.assertEqual(mask["cum"]["target"], True)
        self.assertEqual(mask["accessory"]["target"], True)

    def test_normal_body_images_and_other_head_remain_independent(self):
        detection = self._detection(3, "boobs")
        self.db.save_normal_crop_choice(
            detection["proposal_id"], "body_images", "boobs", main_tag="boobs",
            subtags=["cum"], arousal_cnn_target="aroused",
            corruption_cnn_target="slut",
            body_images_cum_target=True,
            body_images_cum_evaluated=True,
            body_images_accessory_target=True,
            body_images_accessory_evaluated=True,
            body_images_completed=True)
        ids = self.db.confirm_normal_crop_classification(detection["proposal_id"])
        examples = {row["task_head"]: row for row in self.db.current_training_examples()
                    if row["proposal_id"] == detection["proposal_id"]}
        self.assertEqual(set(examples), {"body_images", "arousal", "corruption"})
        mask = json.loads(examples["body_images"]["target_mask_json"])
        self.assertEqual(mask, {
            "cum": {"target": True, "evaluated": True},
            "accessory": {"target": True, "evaluated": True},
        })
        self.assertEqual(len(ids), 3)

    def test_normal_body_images_partial_update_preserves_unedited_target(self):
        detection = self._detection(3, "boobs")
        proposal_id = int(detection["proposal_id"])
        self.db.save_normal_crop_choice(
            proposal_id, "body_images", main_tag="boobs",
            body_images_cum_target=True, body_images_cum_evaluated=True,
            body_images_accessory_target=None, body_images_accessory_evaluated=False)
        self.db.save_normal_crop_choice(
            proposal_id, "body_images", main_tag="boobs",
            body_images_accessory_target=False, body_images_accessory_evaluated=True)
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT body_images_cum_target,body_images_cum_evaluated,
                          body_images_accessory_target,body_images_accessory_evaluated
                   FROM normal_crop_choices WHERE proposal_id=?""", (proposal_id,)
            ).fetchone()
        self.assertEqual(tuple(row), (1, 1, 0, 1))
        self.db.confirm_normal_crop_classification(proposal_id)
        example = next(row for row in self.db.current_training_examples(
            "unified_body_images_fullbody", task_head="body_images")
                       if row["proposal_id"] == proposal_id)
        self.assertEqual(json.loads(example["target_mask_json"]), {
            "cum": {"target": True, "evaluated": True},
            "accessory": {"target": False, "evaluated": True},
        })

    def test_completed_body_images_can_transition_back_to_partial(self):
        detection = self._detection(3, "boobs")
        proposal_id = int(detection["proposal_id"])
        self.db.save_normal_crop_choice(
            proposal_id, "body_images", main_tag="boobs",
            body_images_cum_target=True, body_images_cum_evaluated=True,
            body_images_accessory_target=True, body_images_accessory_evaluated=True,
            body_images_completed=True)
        self.db.save_normal_crop_choice(
            proposal_id, "body_images", main_tag="boobs",
            body_images_cum_target=None, body_images_cum_evaluated=False)
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT body_images_completed,body_images_cum_target,body_images_cum_evaluated,
                          body_images_accessory_target,body_images_accessory_evaluated
                   FROM normal_crop_choices WHERE proposal_id=?""", (proposal_id,)
            ).fetchone()
        self.assertEqual(tuple(row), (0, None, 0, 1, 1))
        self.db.confirm_normal_crop_classification(proposal_id)
        example = next(row for row in self.db.current_training_examples(
            "unified_body_images_fullbody", task_head="body_images")
                       if row["proposal_id"] == proposal_id)
        self.assertEqual(json.loads(example["target_mask_json"]), {
            "cum": {"target": None, "evaluated": False},
            "accessory": {"target": True, "evaluated": True},
        })

    def test_legacy_single_target_keeps_the_other_binary_pending(self):
        detection = self._detection(3, "boobs")
        proposal_id = int(detection["proposal_id"])
        self.db.save_normal_crop_choice(
            proposal_id, "body_images", main_tag="boobs",
            body_images_cnn_target="bodypart_cum")
        with self.db.connect() as connection:
            row = connection.execute(
                """SELECT body_images_cum_target,body_images_cum_evaluated,
                          body_images_accessory_target,body_images_accessory_evaluated
                   FROM normal_crop_choices WHERE proposal_id=?""", (proposal_id,)
            ).fetchone()
        self.assertEqual(tuple(row), (1, 1, None, 0))
        example_ids = self.db.confirm_normal_crop_classification(proposal_id)
        self.assertTrue(example_ids)
        example = next(row for row in self.db.current_training_examples(
            "unified_body_images_fullbody", task_head="body_images")
                       if row["proposal_id"] == proposal_id)
        self.assertEqual(json.loads(example["target_mask_json"]), {
            "cum": {"target": True, "evaluated": True},
            "accessory": {"target": None, "evaluated": False},
        })

    def test_normal_and_professional_eligibility_matrix_agrees(self):
        matrix = {
            "face": {"body_images", "arousal", "corruption"},
            "portrait_frame": {"body_images", "portrait", "arousal", "corruption"},
            "boobs": {"body_images", "arousal", "corruption"},
            "ass": {"body_images", "arousal", "corruption"},
            "pussy": {"body_images", "arousal", "corruption"},
            "legs": {"body_images", "arousal", "corruption"},
            "person": {"arousal", "corruption"},
            "boobs_cover_item": {"clothing_broad", "clothing_fine", "corruption"},
            "fullbody_clothed": {"fullbody", "corruption"},
            "location_home": {"location"},
            "action_event": set(),
            "fullbody_shower": {"fullbody", "corruption"},
        }
        for region, expected in matrix.items():
            with self.subTest(region=region):
                heads = eligible_shared_heads(region)
                if region.startswith("location_"):
                    heads = {"location"}
                elif region in {"action_event", "fullbody_shower"}:
                    heads = expected
                self.assertEqual(heads, expected & {"body_images", "portrait", "arousal", "corruption", "fullbody", "location"})
                for head in ("body_images", "portrait", "arousal", "corruption", "fullbody",
                             "location", "clothing_broad", "clothing_fine"):
                    self.assertEqual(shared_head_eligible(head, region),
                                     head in expected)

    def test_normal_face_accepts_arousal_and_corruption(self):
        for target_head, target in (("arousal", "aroused"), ("corruption", "slut")):
            detection = self._detection(1, "face")
            kwargs = ({ "arousal_cnn_target": target } if target_head == "arousal"
                      else {"corruption_cnn_target": target})
            self.db.save_normal_crop_choice(
                detection["proposal_id"], "body_images", "face", main_tag="face",
                **kwargs)
            ids = self.db.confirm_normal_crop_classification(detection["proposal_id"])
            examples = [row for row in self.db.current_training_examples()
                        if row["proposal_id"] == detection["proposal_id"]
                        and row["task_head"] == target_head]
            self.assertTrue(examples)
            self.assertTrue(ids)

    def test_body_images_handoff_import_and_snapshot_preserve_mask(self):
        detection = self._detection(3, "boobs")
        self.db.save_classification_task_review(
            detection["proposal_id"], "body_images", "body_images_pending",
            {
                "validity_state": "valid",
                "cum_target": True,
                "cum_evaluated": True,
                "accessory_target": False,
                "accessory_evaluated": True,
                "body_images_completed": True,
            },
            action="confirmed", training_eligible=True)
        bundle = export_training_source_bundle(self.db, self.root / "handoff")
        manifest = json.loads(Path(bundle["manifest"]).read_text(encoding="utf-8"))
        record = next(row for row in manifest["records"]
                      if row["task"] == "body_images_classification")
        mask = record["annotation"]["body_images_target_mask"]
        self.assertEqual(mask["cum"]["target"], True)
        self.assertEqual(mask["accessory"]["target"], False)

        config = StudioConfig(root=self.root / "studio")
        config.ensure_directories()
        import shutil
        shutil.copytree(Path(__file__).resolve().parents[1] / "TrainingDatasetStudio" / "contracts",
                        config.contract_dir, dirs_exist_ok=True)
        store = StudioStore(config.database_path)
        store.initialize()
        imported = BundleImporter(config, store).import_bundle(bundle["directory"])
        self.assertEqual(imported["duplicate"], False)
        studio_record = next(row for row in store.list_records(task="body_images_classification")
                             if row["status"] == "accepted")
        imported_mask = studio_record["annotation"]["body_images_target_mask"]
        self.assertEqual(imported_mask, mask)

    def test_body_images_states_survive_confirmation_handoff_split_and_package(self):
        cases = (
            (True, True),
            (True, False),
            (False, True),
            (False, False),
            (True, None),
            (None, False),
            (None, None),
        )
        proposals = {}
        for index, (cum, accessory) in enumerate(cases):
            source = self.root / f"body-source-{index}" / "source.png"
            source.parent.mkdir(parents=True)
            Image.new("RGB", (300, 300), (index * 23, 80, 140)).save(source)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            source_id, _ = self.db.upsert_source_image({
                "path": str(source.resolve()), "sha256": digest, "width": 300,
                "height": 300, "file_size": source.stat().st_size,
                "modified_ns": source.stat().st_mtime_ns,
            })
            detection = self.db.record_yolo_detection(
                source_id, model_id="fixture", model_digest="fixture",
                class_id=3, class_name="boobs", confidence=.9,
                bbox_xyxy=[20, 20, 280, 280])
            proposal_id = int(detection["proposal_id"])
            self.db.save_normal_crop_choice(
                proposal_id, "body_images", main_tag="boobs",
                body_images_cum_target=cum,
                body_images_cum_evaluated=cum is not None,
                body_images_accessory_target=accessory,
                body_images_accessory_evaluated=accessory is not None,
                body_images_completed=cum is not None and accessory is not None,
            )
            example_ids = self.db.confirm_normal_crop_classification(proposal_id)
            proposals[(cum, accessory)] = (proposal_id, example_ids)

        self.assertEqual(proposals[(None, None)][1], [])
        with self.db.connect() as connection:
            pending = connection.execute(
                """SELECT body_images_cum_target,body_images_cum_evaluated,
                          body_images_accessory_target,body_images_accessory_evaluated,
                          body_images_completed
                   FROM normal_crop_choices WHERE proposal_id=?""",
                (proposals[(None, None)][0],),
            ).fetchone()
        self.assertEqual(tuple(pending), (None, 0, None, 0, 0))
        current = [row for row in self.db.current_training_examples(
            "unified_body_images_fullbody", task_head="body_images")]
        self.assertEqual(len(current), 6)
        expected_masks = {
            (cum, accessory): {
                "cum": {"target": cum, "evaluated": cum is not None},
                "accessory": {"target": accessory, "evaluated": accessory is not None},
            }
            for cum, accessory in cases if cum is not None or accessory is not None
        }
        source_masks = {
            row["source_sha256"]: json.loads(row["target_mask_json"])
            for row in current
        }
        self.assertEqual(len(source_masks), 6)
        self.assertEqual(
            {json.dumps(mask, sort_keys=True) for mask in source_masks.values()},
            {json.dumps(mask, sort_keys=True) for mask in expected_masks.values()},
        )

        bundle = export_training_source_bundle(self.db, self.root / "handoff")
        manifest = json.loads(Path(bundle["manifest"]).read_text(encoding="utf-8"))
        body_records = [row for row in manifest["records"]
                        if row["task"] == "body_images_classification"]
        self.assertEqual(len(body_records), 6)
        self.assertEqual(
            {json.dumps(row["annotation"]["body_images_target_mask"], sort_keys=True)
             for row in body_records},
            {json.dumps(mask, sort_keys=True) for mask in expected_masks.values()},
        )

        config = StudioConfig(root=self.root / "studio")
        config.ensure_directories()
        import shutil
        shutil.copytree(Path(__file__).resolve().parents[1] / "TrainingDatasetStudio" / "contracts",
                        config.contract_dir, dirs_exist_ok=True)
        store = StudioStore(config.database_path)
        store.initialize()
        importer = BundleImporter(config, store)
        imported = importer.import_bundle(bundle["directory"])
        self.assertEqual((imported["accepted"], imported["quarantined"]), (6, 0))
        imported_records = [row for row in store.list_records(task="body_images_classification")
                            if row["status"] == "accepted"]
        self.assertEqual(len(imported_records), 6)
        self.assertEqual(
            {json.dumps(row["annotation"]["body_images_target_mask"], sort_keys=True)
             for row in imported_records},
            {json.dumps(mask, sort_keys=True) for mask in expected_masks.values()},
        )

        duplicate = importer.import_bundle(bundle["directory"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(len(store.list_records(task="body_images_classification")), 6)
        first_record = imported_records[0]
        datasets = DatasetService(store, self.root / "studio-output")
        dataset_id = datasets.create_dataset(
            "Body Images states", "body_images_classification",
            first_record["registry_id"], first_record["registry_version"],
            model_id=first_record["model_id"])
        version_id = datasets.create_version(dataset_id, seed=42)
        version_rows = [row for row in store.version_rows(version_id) if row["included"]]
        self.assertEqual(len(version_rows), 6)
        self.assertEqual(len({row["source_sha256"] for row in version_rows}), 6)
        readiness = datasets.version_readiness_report(version_id)
        self.assertEqual(readiness["body_images_target_distribution"], {
            "cum": {"positive": 3, "negative": 2, "pending": 1},
            "accessory": {"positive": 2, "negative": 3, "pending": 1},
        })
        datasets.finalize(version_id)
        self.assertEqual(readiness["state"], "blocked_from_training")
        self.assertEqual(readiness["source_groups"], 6)
        self.assertEqual(readiness["split_source_groups"],
                         {"train": 4, "validation": 1, "test": 1})
        self.assertIn("validation_source_group_minimum_not_met:1/15",
                      readiness["blockers"])
        self.assertIn("test_source_group_minimum_not_met:1/15",
                      readiness["blockers"])
        package = datasets.export_colab(version_id, self.root / "body-package")
        package_metadata = json.loads(
            (Path(package["path"]) / "metadata.json").read_text(encoding="utf-8"))
        packaged_masks = {
            json.dumps(row["body_images_target_mask"], sort_keys=True)
            for row in package_metadata["records"]
        }
        self.assertEqual(packaged_masks,
                         {json.dumps(mask, sort_keys=True) for mask in expected_masks.values()})
        package_manifest = json.loads(
            (Path(package["path"]) / "package_manifest.json").read_text(encoding="utf-8"))
        manager = TrainingManager(store, self.root / "studio-output")
        self.assertTrue(manager._verify_package_files(Path(package["path"]), package_manifest))
        self.assertTrue(manager._verify_dataset_provenance(
            version_id, Path(package["path"]), package_manifest))


class AcceptanceLauncherTests(unittest.TestCase):
    def test_newassetapp_acceptance_database_override_is_isolated(self):
        from main import _acceptance_config
        with tempfile.TemporaryDirectory(prefix="newassetapp_acceptance_launch_") as temp:
            root = Path(temp)
            config = _acceptance_config([
                "--acceptance-root", str(root),
                "--acceptance-db", str(root / "data" / "acceptance.sqlite3"),
                "--acceptance-data", str(root / "data"),
                "--acceptance-output", str(root / "output"),
                "--acceptance-logs", str(root / "logs"),
            ])
            self.assertEqual(config.database_path, (root / "data" / "acceptance.sqlite3").resolve())
            self.assertEqual(config.output_dir, (root / "output").resolve())
            with self.assertRaisesRegex(ValueError, "must not overlap"):
                _acceptance_config([
                    "--acceptance-root", str(Path(__file__).resolve().parents[1]),
                    "--acceptance-db", str(Path(__file__).resolve().parents[1] / "data" / "test.sqlite3"),
                ])

    def test_studio_acceptance_root_override_is_isolated(self):
        with tempfile.TemporaryDirectory(prefix="studio_acceptance_launch_") as temp:
            root = Path(temp)
            sys_path = str((Path(__file__).resolve().parents[1] / "TrainingDatasetStudio").resolve())
            if sys_path not in __import__("sys").path:
                __import__("sys").path.insert(0, sys_path)
            from studio.config import StudioConfig
            config = StudioConfig(root=root)
            self.assertEqual(config.database_path, (root / "data" / "studio.sqlite3").resolve())

    def test_studio_desktop_launcher_batch_exists(self):
        launcher = Path(__file__).resolve().parents[1] / "TrainingDatasetStudio" / "run_app.bat"
        self.assertTrue(launcher.is_file())
        self.assertIn("run_app.ps1", launcher.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
