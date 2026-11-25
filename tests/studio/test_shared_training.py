from __future__ import annotations

import json
import unittest
from pathlib import Path

from TrainingDatasetStudio.studio.shared_training import (HEADS, SharedTrainingError,
                                                          load_verified_legacy_initialization,
                                                          masked_head_loss,
                                                          validate_shared_checkpoint)
from app.core.shared_cnn import load_head_class_mappings
from app.core.shared_model_artifacts import (SharedModelArtifactError,
                                             activate_shared_candidate)


ROOT = Path(__file__).resolve().parents[2]


class SharedTrainingTests(unittest.TestCase):
    def test_head_mappings_match_authoritative_registry_order(self):
        mappings = load_head_class_mappings()
        self.assertEqual(list(mappings), list(HEADS))
        self.assertEqual([item["class_name"] for item in mappings["body_images"]],
                         ["bodypart_cum", "bodypart_acc"])
        self.assertEqual([item["class_name"] for item in mappings["fullbody"]],
                         ["clothed", "topless", "bottomless", "bra", "panty"])
        self.assertEqual([item["class_name"] for item in mappings["portrait"]],
                         ["portrait", "tportrait"])
        self.assertEqual([item["class_name"] for item in mappings["arousal"]],
                         ["aroused", "edging"])
        self.assertEqual([item["class_name"] for item in mappings["corruption"]],
                         ["slut", "conservative", "whore", "u_whore"])

    def test_masked_loss_only_updates_the_present_task_head(self):
        import torch
        outputs = {head: torch.randn(2, count, requires_grad=True)
                   for head, count in zip(HEADS, (2, 5, 2, 2, 4))}
        loss = masked_head_loss(outputs, torch.tensor([0, 0]), torch.tensor([1, 0]),
                                torch.nn.CrossEntropyLoss())
        loss.backward()
        self.assertIsNotNone(outputs["body_images"].grad)
        for head in HEADS[1:]:
            self.assertIsNone(outputs[head].grad)

    def test_legacy_26_class_checkpoint_is_rejected_as_a_trained_shared_model(self):
        registry_path = ROOT / "data/models/unified_body_images_fullbody/class_registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        legacy = ROOT / "models/unified_body_images_fullbody/asset_classifier_initialization_26class.pth"
        with self.assertRaisesRegex(SharedTrainingError, "partial, untrained"):
            validate_shared_checkpoint(legacy, registry)

    def test_legacy_checkpoint_initializes_only_verified_portrait_rows(self):
        legacy = ROOT / "models/unified_body_images_fullbody/asset_classifier_initialization_26class.pth"
        legacy_model, mapping = load_verified_legacy_initialization(legacy)
        self.assertEqual(mapping["mapped_head"], "portrait")
        self.assertEqual(mapping["mapped_source_rows"], [4, 5])
        self.assertEqual(mapping["mapped_target_classes"], ["portrait", "tportrait"])
        self.assertEqual(len(mapping["unmapped_source_rows"]), 24)
        self.assertEqual(tuple(legacy_model.fc.weight.shape), (26, 512))
        from TrainingDatasetStudio.studio.shared_train import build_shared_training_model
        shared, applied = build_shared_training_model(load_head_class_mappings(), legacy)
        import torch
        self.assertEqual(applied["mapped_source_rows"], [4, 5])
        self.assertTrue(torch.equal(shared.heads["portrait"].weight, legacy_model.fc.weight[[4, 5]]))
        self.assertTrue(torch.equal(shared.heads["portrait"].bias, legacy_model.fc.bias[[4, 5]]))

    def test_activation_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(SharedModelArtifactError, "Explicit user confirmation"):
            activate_shared_candidate("missing_candidate", ROOT / "disposable", confirmed=False)


if __name__ == "__main__":
    unittest.main()
