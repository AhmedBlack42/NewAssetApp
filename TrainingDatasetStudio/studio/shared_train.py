from __future__ import annotations

import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

try:
    from .shared_training import (ARCHITECTURE_ID, ARCHITECTURE_VERSION, BACKBONE_ID,
                                  HEADS, INPUT_SIZE, MODEL_ID, PREPROCESSING, REGISTRY_ID,
                                  SharedTrainingError, load_verified_legacy_initialization,
                                  validate_shared_dataset)
except ImportError:
    from shared_training import (ARCHITECTURE_ID, ARCHITECTURE_VERSION, BACKBONE_ID,
                                 HEADS, INPUT_SIZE, MODEL_ID, PREPROCESSING, REGISTRY_ID,
                                 SharedTrainingError, load_verified_legacy_initialization,
                                 validate_shared_dataset)


def build_shared_training_model(class_mappings: dict, initialization_checkpoint: Path | None = None):
    import torch
    from torch import nn
    from torchvision import models
    initialization_report = None
    if initialization_checkpoint is not None:
        backbone, initialization_report = load_verified_legacy_initialization(initialization_checkpoint)
    else:
        backbone = models.resnet18(weights=None)

    class SharedTrainingNetwork(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = nn.Sequential(*list(backbone.children())[:-1])
            self.heads = nn.ModuleDict({head: nn.Linear(512, len(class_mappings[head]))
                                        for head in HEADS})
            if initialization_checkpoint is not None:
                with torch.no_grad():
                    self.heads["portrait"].weight.copy_(backbone.fc.weight[[4, 5]])
                    self.heads["portrait"].bias.copy_(backbone.fc.bias[[4, 5]])

        def forward(self, images):
            features = self.backbone(images).flatten(1)
            return {head: layer(features) for head, layer in self.heads.items()}

    return SharedTrainingNetwork(), initialization_report


def run_shared_training(dataset_dir: Path, output_dir: Path, cancel_file: Path,
                        params: dict, *, dry_run: bool = False,
                        initialization_checkpoint: Path | None = None) -> int:
    """Train the five-head model; dry-run validates the full input path only."""
    import torch
    from torch import nn, optim
    from torch.utils.data import DataLoader, Dataset
    from torchvision import models, transforms

    if params.get("resume"):
        raise SharedTrainingError("Shared five-head resume is not implemented; start a new confirmed run.")
    seed = int(params.get("seed", 42))
    random.seed(seed)
    torch.manual_seed(seed)

    package = json.loads((dataset_dir / "shared_dataset.json").read_text(encoding="utf-8"))
    registry = json.loads((dataset_dir / "registry.json").read_text(encoding="utf-8"))
    report = validate_shared_dataset(dataset_dir, registry)
    initialization_report = None
    if initialization_checkpoint is not None:
        _, initialization_report = load_verified_legacy_initialization(initialization_checkpoint)
    if dry_run:
        print(json.dumps({"status": "dry_run_ok", "model_id": MODEL_ID,
                          "architecture_id": ARCHITECTURE_ID, "heads": list(HEADS),
                          "dataset_validation": report, "initialization": initialization_report,
                          "seed": seed}, sort_keys=True), flush=True)
        return 0

    class SharedDataset(Dataset):
        def __init__(self, split: str):
            self.rows = [row for row in package["records"] if row["split"] == split]
            self.transform = transforms.Compose([
                transforms.Resize(int(PREPROCESSING["resize_shorter_side"])),
                transforms.CenterCrop(tuple(INPUT_SIZE)), transforms.ToTensor(),
                transforms.Normalize(PREPROCESSING["mean"], PREPROCESSING["std"]),
            ])
            self.head_index = {head: index for index, head in enumerate(HEADS)}

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, index):
            row = self.rows[index]
            with Image.open(dataset_dir / row["image_path"]) as source:
                image = source.convert("RGB")
            head = row["task_head"]
            if head == "body_images":
                mask = row["body_images_target_mask"]
                targets = torch.tensor([
                    1.0 if mask["cum"]["evaluated"] and mask["cum"]["target"] else 0.0,
                    1.0 if mask["accessory"]["evaluated"] and mask["accessory"]["target"] else 0.0,
                ], dtype=torch.float32)
                target_mask = torch.tensor([
                    1.0 if mask["cum"]["evaluated"] else 0.0,
                    1.0 if mask["accessory"]["evaluated"] else 0.0,
                ], dtype=torch.float32)
                return (self.transform(image), torch.tensor(self.head_index[head]),
                        targets, head, row["class_label"], target_mask)
            return (self.transform(image), torch.tensor(self.head_index[head]),
                    torch.tensor(int(row["target_class_id"])), head, row["class_label"],
                    torch.ones(1, dtype=torch.float32))

    datasets = {split: SharedDataset(split) for split in ("train", "validation", "test")}
    if not datasets["train"] or not datasets["validation"]:
        raise SharedTrainingError("Each head requires train and validation records.")
    loaders = {split: DataLoader(data, batch_size=int(params.get("batch_size", 8)),
                                 shuffle=split == "train", num_workers=int(params.get("workers", 0)))
               for split, data in datasets.items() if len(data)}

    model, initialization_report = build_shared_training_model(
        package["class_mappings"], initialization_checkpoint)
    model = model.to("cpu")
    optimizer = optim.AdamW(model.parameters(), lr=float(params.get("learning_rate", .0003)))
    criterion = nn.CrossEntropyLoss()
    epochs = max(1, int(params.get("epochs", 5)))
    metrics: dict[str, dict] = {}
    for epoch in range(epochs):
        model.train()
        for images, head_indices, targets, head_names, _, target_masks in loaders["train"]:
            optimizer.zero_grad(set_to_none=True)
            output = model(images.to("cpu"))
            losses = []
            for index, head in enumerate(HEADS):
                mask = head_indices == index
                if bool(mask.any()):
                    if head == "body_images":
                        logits = output[head][mask]
                        target_values = targets[mask]
                        masks = target_masks[mask]
                        element_loss = nn.BCEWithLogitsLoss(reduction="none")(logits, target_values)
                        masked = element_loss * masks
                        denominator = masks.sum()
                        if not bool(denominator.item() > 0):
                            continue
                        losses.append(masked.sum() / denominator)
                    else:
                        losses.append(criterion(output[head][mask], targets[mask].long().view(-1)))
            if not losses:
                raise SharedTrainingError("Training batch contains no task-specific targets.")
            torch.stack(losses).mean().backward()
            optimizer.step()
        model.eval()
        epoch_metrics = {}
        with torch.inference_mode():
            for split in ("validation", "test"):
                if split not in loaders:
                    continue
                accum = {head: {"correct": 0, "count": 0, "classes": defaultdict(lambda: [0, 0])}
                         for head in HEADS}
                for images, _, targets, head_names, class_names, target_masks in loaders[split]:
                    outputs = model(images.to("cpu"))
                    for index, head in enumerate(HEADS):
                        positions = [i for i, value in enumerate(head_names) if value == head]
                        if not positions:
                            continue
                        indices = torch.tensor(positions, dtype=torch.long)
                        bucket = accum[head]
                        if head == "body_images":
                            predicted = (outputs[head][indices].sigmoid() >= 0.5).float()
                            actual = targets[indices]
                            masks = target_masks[indices]
                            correct = ((predicted == actual) * masks).sum().item()
                            count = masks.sum().item()
                            bucket["correct"] += int(correct)
                            bucket["count"] += int(count)
                        else:
                            predicted = outputs[head][indices].argmax(1)
                            actual = targets[indices].long().view(-1)
                            bucket["correct"] += int((predicted == actual).sum().item())
                            bucket["count"] += len(positions)
                        for local, row_index in enumerate(positions):
                            name = class_names[row_index]
                            bucket["classes"][name][1] += 1
                            if head == "body_images":
                                bucket["classes"][name][0] += int(
                                    ((predicted[local] == actual[local]) * masks[local]).sum().item()
                                )
                            else:
                                bucket["classes"][name][0] += int(predicted[local] == actual[local])
                epoch_metrics[split] = {head: {
                    "accuracy": values["correct"] / max(1, values["count"]),
                    "count": values["count"],
                    "classes": {name: {"correct": counts[0], "count": counts[1],
                                       "accuracy": counts[0] / max(1, counts[1])}
                                for name, counts in values["classes"].items()}}
                    for head, values in accum.items()}
        metrics = epoch_metrics
        print(json.dumps({"epoch": epoch + 1, "metrics": metrics}, sort_keys=True), flush=True)
        if cancel_file.is_file():
            return 0

    mappings = package["class_mappings"]
    checkpoint = {
        "format_version": 1, "complete_model": True, "training_status": "completed",
        "model_id": MODEL_ID, "architecture_id": ARCHITECTURE_ID,
        "architecture_version": ARCHITECTURE_VERSION, "backbone_id": BACKBONE_ID,
        "head_names": list(HEADS), "class_mappings": mappings,
        "registry_id": REGISTRY_ID, "registry_version": str(package["registry_version"]),
        "input_size": INPUT_SIZE, "preprocessing": PREPROCESSING,
        "state_dict": model.cpu().state_dict(), "dataset": package.get("dataset_provenance"),
        "training_config": {**params, "seed": seed}, "metrics": metrics,
        "initialization": initialization_report or {"kind": "random_initialization"},
        "training_run_id": output_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint_path = output_dir / "shared_cnn.pth"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, checkpoint_path)
    print(json.dumps({"status": "completed", "checkpoint": str(checkpoint_path),
                      "metrics": metrics}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit("Invoke via studio.train_entry with a finalized shared CNN package.")
