import json
import unittest
from pathlib import Path

from TrainingDatasetStudio.studio.importer import _task_validation


ROOT = Path(__file__).resolve().parents[2]


class YoloRegistryGateTests(unittest.TestCase):
    def setUp(self):
        self.registry = json.loads(
            (ROOT / "TrainingDatasetStudio/registries/yolo_detector_v1.json")
            .read_text(encoding="utf-8")
        )
        self.models = {
            "newassetapp_yolo_detector_v1": {
                "registry_id": "newassetapp_yolo_detector_v1",
                "registry_version": "1",
            }
        }

    def record(self):
        return {
            "task": "yolo_detection",
            "model": {
                "id": "newassetapp_yolo_detector_v1",
                "registry_id": "newassetapp_yolo_detector_v1",
                "registry_version": "1",
            },
            "labels": {"class_label": "face", "structured": {}},
            "annotation": {"target_class_id": 1, "coordinate_space": "source_pixels"},
        }

    def test_exact_approved_registry_passes_and_legacy_mismatch_is_quarantined(self):
        valid = _task_validation(self.record(), 4, self.models, {
            "newassetapp_yolo_detector_v1": self.registry,
        })
        self.assertEqual(valid, ("yolo_detection", "newassetapp_yolo_detector_v1", 1, None))

        legacy = json.loads(json.dumps(self.registry))
        legacy["classes"][24]["name"] = "fullbody_swim"
        invalid = _task_validation(self.record(), 4, self.models, {
            "newassetapp_yolo_detector_v1": legacy,
        })
        self.assertEqual(invalid[-1], "approved_yolo_registry_mismatch")

        malformed = json.loads(json.dumps(self.registry))
        malformed["classes"].append(dict(malformed["classes"][0]))
        invalid = _task_validation(self.record(), 4, self.models, {
            "newassetapp_yolo_detector_v1": malformed,
        })
        self.assertEqual(invalid[-1], "approved_yolo_registry_mismatch")


if __name__ == "__main__":
    unittest.main()
