from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = APP_ROOT / "data" / "models" / "unified_body_images_fullbody" / "class_registry.json"
EXPECTED_HEADS = {"body_images", "fullbody", "portrait", "arousal", "corruption"}
ARCHITECTURE_ID = "newassetapp.shared_resnet18_five_head"
ARCHITECTURE_VERSION = 1
BACKBONE_ID = "torchvision.resnet18"
INPUT_SIZE = [224, 224]
NORMALIZATION = {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}


def load_head_class_counts(registry_path: Path | str = REGISTRY_PATH) -> dict[str, int]:
    """Load and validate the task-specific output dimensions without importing torch."""
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    groups = registry.get("output_groups")
    if not isinstance(groups, dict) or set(groups) != EXPECTED_HEADS:
        raise ValueError("Shared CNN registry must define exactly the five supported output heads.")
    result: dict[str, int] = {}
    for head, details in groups.items():
        classes = details.get("classes") if isinstance(details, dict) else None
        count = details.get("class_count") if isinstance(details, dict) else None
        if not isinstance(classes, list) or not isinstance(count, int) or count != len(classes):
            raise ValueError(f"Shared CNN head {head!r} has an inconsistent class count.")
        ids = [item.get("class_id") for item in classes]
        names = [item.get("class_name") for item in classes]
        if ids != list(range(count)) or any(not isinstance(name, str) or not name for name in names):
            raise ValueError(f"Shared CNN head {head!r} has invalid or non-contiguous classes.")
        result[head] = count
    return result


def load_head_class_mappings(registry_path: Path | str = REGISTRY_PATH) -> dict[str, list[dict]]:
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    counts = load_head_class_counts(registry_path)
    mappings = {}
    for head in ("body_images", "fullbody", "portrait", "arousal", "corruption"):
        rows = registry["output_groups"][head]["classes"]
        mappings[head] = [{"class_id": int(row["class_id"]),
                           "class_name": str(row["class_name"])} for row in rows]
        if len(mappings[head]) != counts[head]:
            raise ValueError(f"Shared CNN head {head!r} has an inconsistent class mapping.")
    return mappings


def build_shared_task_cnn(registry_path: Path | str = REGISTRY_PATH):
    """Create one ResNet-18 backbone with an independent linear head per task.

    This defines the current shared architecture. An initialization checkpoint is not
    an inference-ready model; callers must validate trained-checkpoint metadata and load
    every tensor strictly before use.
    """
    import torch.nn as nn
    from torchvision import models

    class SharedTaskCNN(nn.Module):
        def __init__(self, head_class_counts: dict[str, int]):
            super().__init__()
            network = models.resnet18(weights=None)
            self.backbone = nn.Sequential(*list(network.children())[:-1])
            feature_count = int(network.fc.in_features)
            self.heads = nn.ModuleDict({
                head: nn.Linear(feature_count, class_count)
                for head, class_count in head_class_counts.items()
            })

        def forward(self, images):
            features = self.backbone(images).flatten(1)
            return {head: classifier(features) for head, classifier in self.heads.items()}

        def classify_task(self, images, task: str):
            if task not in self.heads:
                raise ValueError(f"Unsupported shared CNN task head: {task!r}")
            features = self.backbone(images).flatten(1)
            return self.heads[task](features)

    return SharedTaskCNN(load_head_class_counts(registry_path))
