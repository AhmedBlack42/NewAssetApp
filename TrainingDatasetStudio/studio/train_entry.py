from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cancel-file", type=Path, required=True)
    parser.add_argument("--params", default="{}")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _args()
    params = json.loads(args.params)
    is_shared = args.model_id == "unified_body_images_fullbody_cnn"
    if not is_shared and (args.checkpoint is None or not args.checkpoint.is_file()):
        raise FileNotFoundError("Selected checkpoint does not exist.")
    if not args.dataset.is_dir():
        raise FileNotFoundError("Finalized dataset package does not exist.")
    import torch
    if torch.version.cuda is not None:
        raise RuntimeError("Studio CPU trainer requires a CPU-only PyTorch build.")
    if args.task in {"yolo_detection", "yolo_detector"}:
        yaml_path = args.dataset / "dataset.yaml"
        if not yaml_path.is_file():
            raise FileNotFoundError("YOLO dataset.yaml is missing.")
        from ultralytics import YOLO
        model = YOLO(str(args.checkpoint))
        if args.dry_run:
            print(json.dumps({"status": "dry_run_ok", "task": args.task, "device": "cpu",
                              "checkpoint": str(args.checkpoint), "dataset": str(yaml_path),
                              "model_class": type(model).__name__, "params": params}), flush=True)
            return 0
        def cancel_yolo_batch(trainer):
            if args.cancel_file.is_file():
                print("Safe cancellation requested; stopping after the current batch.", flush=True)
                trainer.stop = True
        model.add_callback("on_train_batch_end", cancel_yolo_batch)
        model.train(data=str(yaml_path), device="cpu", epochs=int(params.get("epochs", 5)),
                    batch=int(params.get("batch_size", 2)), imgsz=int(params.get("image_size", 640)),
                    workers=int(params.get("workers", 0)), lr0=float(params.get("learning_rate", .001)),
                    save_period=int(params.get("checkpoint_frequency", 1)),
                    val=bool(params.get("validate", True)), project=str(args.output / "checkpoints"),
                    name="cpu_training", exist_ok=False,
                    resume=bool(params.get("resume", False)))
        return 0
    if is_shared:
        from shared_train import run_shared_training
        return run_shared_training(args.dataset, args.output, args.cancel_file, params,
                                  dry_run=args.dry_run, initialization_checkpoint=args.checkpoint)
    if args.model_id != "clothing_classifier":
        raise RuntimeError("No verified local CPU training implementation is registered for this CNN architecture.")
    images_root = args.dataset / "dataset" / "images"
    train_root, val_root = images_root / "train", images_root / "validation"
    if not train_root.is_dir() or not val_root.is_dir():
        raise FileNotFoundError("CNN package requires train and validation class folders.")
    from torch import nn, optim
    from torch.utils.data import DataLoader
    from torchvision import datasets, models, transforms
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    train_transform = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224),
                                          transforms.RandomHorizontalFlip(), transforms.ToTensor(),
                                          transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    val_transform = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224),
                                         transforms.ToTensor(), transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    train_data = datasets.ImageFolder(str(train_root), train_transform)
    val_data = datasets.ImageFolder(str(val_root), val_transform)
    if not train_data.classes or not train_data.samples or not val_data.samples:
        raise RuntimeError("CNN dry-run requires nonempty train and validation class folders.")
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, len(train_data.classes))
    checkpoint_payload = torch.load(args.checkpoint, map_location="cpu")
    checkpoint_state = checkpoint_payload.get("state_dict", checkpoint_payload) \
        if isinstance(checkpoint_payload, dict) else checkpoint_payload
    if not isinstance(checkpoint_state, dict):
        raise RuntimeError("Selected ResNet-18 checkpoint does not contain a state dictionary.")
    current = model.state_dict()
    compatible = {key.removeprefix("module."): value for key, value in checkpoint_state.items()
                  if key.removeprefix("module.") in current and current[key.removeprefix("module.")].shape == value.shape}
    if not compatible:
        raise RuntimeError("Selected checkpoint has no compatible ResNet-18 parameters.")
    if args.dry_run:
        print(json.dumps({"status": "dry_run_ok", "task": args.task, "device": "cpu",
                          "model_class": "ResNet18", "classes": train_data.classes,
                          "checkpoint_parameters_loaded": len(compatible), "params": params}), flush=True)
        return 0
    model.load_state_dict(compatible, strict=False)
    for parameter in model.parameters():
        parameter.requires_grad = False
    for parameter in model.fc.parameters():
        parameter.requires_grad = True
    model.to(torch.device("cpu"))
    loader_train = DataLoader(train_data, batch_size=int(params.get("batch_size", 2)), shuffle=True,
                              num_workers=int(params.get("workers", 0)))
    loader_val = DataLoader(val_data, batch_size=int(params.get("batch_size", 2)), shuffle=False,
                            num_workers=int(params.get("workers", 0)))
    optimizer = optim.SGD(model.fc.parameters(), lr=float(params.get("learning_rate", .001)), momentum=.9)
    criterion = nn.CrossEntropyLoss()
    epochs = int(params.get("epochs", 5))
    start_epoch = 0
    if params.get("resume"):
        if not isinstance(checkpoint_payload, dict) or "optimizer" not in checkpoint_payload:
            raise RuntimeError("CNN resume needs a Studio checkpoint containing optimizer state and epoch metadata.")
        optimizer.load_state_dict(checkpoint_payload["optimizer"])
        start_epoch = int(checkpoint_payload.get("epoch", 0))
    for epoch in range(start_epoch, start_epoch + epochs):
        model.train()
        for images, labels in loader_train:
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(images.to("cpu")), labels.to("cpu"))
            loss.backward(); optimizer.step()
        if (epoch + 1) % int(params.get("validation_frequency", 1)) == 0:
            model.eval(); correct = total = 0
            with torch.no_grad():
                for images, labels in loader_val:
                    correct += int((model(images.to("cpu")).argmax(1) == labels).sum().item())
                    total += int(labels.numel())
            print(json.dumps({"epoch": epoch + 1, "validation_accuracy": correct / max(1, total)}), flush=True)
        if (epoch + 1) % int(params.get("checkpoint_frequency", 1)) == 0:
            checkpoint_path = args.output / "checkpoints" / ("epoch_" + str(epoch + 1).zfill(4) + ".pth")
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": model.state_dict(), "classes": train_data.classes,
                        "epoch": epoch + 1}, checkpoint_path)
        if args.cancel_file.is_file():
            checkpoint_path = args.output / "checkpoints" / f"cancelled_epoch_{epoch + 1:04d}.pth"
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"state_dict": model.state_dict(), "optimizer": optimizer.state_dict(),
                        "classes": train_data.classes, "epoch": epoch + 1, "cancelled": True},
                       checkpoint_path)
            print(f"Saved cancellation checkpoint: {checkpoint_path}", flush=True)
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

