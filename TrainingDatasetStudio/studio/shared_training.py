from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from PIL import Image


HEADS = ("body_images", "fullbody", "portrait", "arousal", "corruption")
MODEL_ID = "unified_body_images_fullbody_cnn"
REGISTRY_ID = "newassetapp_unified_body_images_fullbody"
ARCHITECTURE_ID = "newassetapp.shared_resnet18_five_head"
ARCHITECTURE_VERSION = 1
BACKBONE_ID = "torchvision.resnet18"
INPUT_SIZE = [224, 224]
PREPROCESSING = {"resize_shorter_side": 256, "center_crop": [224, 224],
                 "mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225],
                 "color_mode": "RGB"}


class SharedTrainingError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if root.resolve() not in candidate.parents or not candidate.is_file():
        raise SharedTrainingError(f"Dataset image is missing or escapes the package: {relative}")
    return candidate


def validate_shared_dataset(dataset_dir: Path | str, expected_registry: dict | None = None) -> dict:
    """Validate a Studio shared-head package without starting optimization."""
    root = Path(dataset_dir).resolve()
    manifest_path = root / "shared_dataset.json"
    if not manifest_path.is_file():
        raise SharedTrainingError("Shared CNN package is missing shared_dataset.json.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != 1 or manifest.get("model_id") != MODEL_ID
            or manifest.get("registry_id") != REGISTRY_ID
            or tuple(manifest.get("heads", ())) != HEADS):
        raise SharedTrainingError("Shared CNN package model or head identities are invalid.")
    mappings = manifest.get("class_mappings")
    if not isinstance(mappings, dict) or tuple(mappings) != HEADS:
        raise SharedTrainingError("Shared CNN package must include ordered mappings for all five heads.")
    if expected_registry is not None:
        expected = {head: [{"class_id": int(row["class_id"]), "class_name": row["class_name"]}
                           for row in expected_registry["output_groups"][head]["classes"]]
                    for head in HEADS}
        if mappings != expected or manifest.get("registry_version") != str(expected_registry.get("version")):
            raise SharedTrainingError("Shared CNN package class mappings differ from the authoritative registry.")
    rows = manifest.get("records")
    if not isinstance(rows, list) or not rows:
        raise SharedTrainingError("Shared CNN package has no training records.")
    source_splits: dict[str, str] = {}
    stats = {head: {split: {"count": 0, "classes": {}} for split in ("train", "validation", "test")}
             for head in HEADS}
    mapping_ids = {head: {int(row["class_id"]) for row in mappings[head]} for head in HEADS}
    for row in rows:
        head, split = row.get("task_head"), row.get("split")
        if head not in HEADS or split not in {"train", "validation", "test"}:
            raise SharedTrainingError("A shared CNN record has an unknown head or split.")
        if row.get("human_confirmed") is not True or row.get("training_eligible") is not True:
            raise SharedTrainingError("Shared CNN package contains a non-confirmed training target.")
        if not isinstance(row.get("source_sha256"), str) or len(row["source_sha256"]) != 64:
            raise SharedTrainingError("Shared CNN record is missing source-photo identity.")
        previous = source_splits.setdefault(row["source_sha256"], split)
        if previous != split:
            raise SharedTrainingError("Source-photo leakage detected across shared CNN splits.")
        target = row.get("target_class_id")
        if head == "body_images":
            target_mask = row.get("body_images_target_mask")
            if not isinstance(target_mask, dict):
                raise SharedTrainingError("Body Images shared CNN record is missing its target mask.")
            for name in ("cum", "accessory"):
                state = target_mask.get(name)
                if (not isinstance(state, dict) or set(("target", "evaluated")) - set(state)
                        or state["evaluated"] not in {True, False}
                        or (state["evaluated"] and state["target"] not in {True, False})
                        or (not state["evaluated"] and state["target"] is not None)):
                    raise SharedTrainingError("Body Images target mask is malformed.")
        else:
            if not isinstance(target, int) or target not in mapping_ids[head]:
                raise SharedTrainingError("Shared CNN target is not a class in its task head registry.")
            if row.get("class_label") != next(item["class_name"] for item in mappings[head]
                                                 if item["class_id"] == target):
                raise SharedTrainingError("Shared CNN target name and class ID do not match.")
        path = _safe_file(root, str(row.get("image_path") or ""))
        if sha256_file(path) != row.get("sha256"):
            raise SharedTrainingError("Shared CNN crop hash mismatch.")
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                if image.mode not in {"RGB", "RGBA", "L"} or min(image.size) < 1:
                    raise SharedTrainingError("Shared CNN crop has invalid dimensions or mode.")
        except SharedTrainingError:
            raise
        except Exception as error:
            raise SharedTrainingError("Shared CNN crop cannot be decoded.") from error
        bucket = stats[head][split]
        bucket["count"] += 1
        name = row["class_label"]
        bucket["classes"][name] = bucket["classes"].get(name, 0) + 1
    for head in HEADS:
        if not stats[head]["train"]["count"] or not stats[head]["validation"]["count"]:
            raise SharedTrainingError(f"Head {head!r} needs at least one train and validation example.")
    return {"valid": True, "record_count": len(rows), "stats": stats,
            "registry_id": REGISTRY_ID, "registry_version": manifest["registry_version"],
            "heads": list(HEADS), "input_size": INPUT_SIZE, "preprocessing": PREPROCESSING}


def masked_head_loss(outputs: dict, head_indices, targets, criterion):
    """Sum per-head losses only for examples that have that head's target."""
    import torch
    losses = []
    for head_index, head in enumerate(HEADS):
        mask = head_indices == head_index
        if bool(mask.any()):
            losses.append(criterion(outputs[head][mask], targets[mask]))
    if not losses:
        raise SharedTrainingError("Batch contains no valid task-specific target.")
    return torch.stack(losses).mean()


def load_verified_legacy_initialization(path: Path | str):
    """Strictly load the preserved 26-class ResNet and resolve only portrait rows 4/5."""
    import sys
    import torch
    from torchvision import models
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    map_path = repo_root / "models/asset_classifier/asset_class_map.json"
    manifest_path = repo_root / "models/model_manifest.json"
    registry_path = repo_root / "data/models/unified_body_images_fullbody/class_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    class_map = json.loads(map_path.read_text(encoding="utf-8"))
    class_names = json.loads(manifest_path.read_text(encoding="utf-8"))["models"]["asset_classifier"]["class_names"]
    checkpoint = Path(path).resolve()
    expected_digest = registry.get("source_checkpoint_sha256")
    if not expected_digest or sha256_file(checkpoint).casefold() != expected_digest.casefold():
        raise SharedTrainingError("Legacy initialization must match the preserved Asset CNN checkpoint digest.")
    if (len(class_names) != 26 or len(class_map) != 26
            or {name: int(index) for name, index in class_map.items()} !=
               {name: index for index, name in enumerate(class_names)}):
        raise SharedTrainingError("Legacy Asset CNN class order does not match its preserved class map.")
    state = torch.load(checkpoint, map_location="cpu")
    if (not isinstance(state, dict)
            or tuple(state.get("fc.weight", torch.empty(0)).shape) != (26, 512)
            or tuple(state.get("fc.bias", torch.empty(0)).shape) != (26,)):
        raise SharedTrainingError("Legacy initialization must contain a 26-output ResNet-18 state dictionary.")
    resnet = models.resnet18(weights=None)
    resnet.fc = torch.nn.Linear(resnet.fc.in_features, 26)
    try:
        resnet.load_state_dict(state, strict=True)
    except Exception as error:
        raise SharedTrainingError("Legacy checkpoint tensors do not strictly match ResNet-18.") from error
    portrait_targets = registry.get("legacy_source_output_groups", {}).get("body_images", {}).get("classes", [])
    portrait_targets = [item for item in portrait_targets if item.get("canonical_application_mapping") in {"portrait", "tportrait"}]
    portrait_targets.sort(key=lambda item: int(item["class_id"]))
    if [(row.get("class_name"), int(row.get("original_class_id", -1))) for row in portrait_targets] != [
            ("portrait", 4), ("tportrait", 5)]:
        raise SharedTrainingError("The registry does not provide an exact two-class legacy-to-Portrait mapping.")
    return resnet, {"kind": "verified_legacy_initialization", "source_sha256": expected_digest,
                    "source_model_id": "asset_classifier", "source_class_count": 26,
                    "mapped_head": "portrait", "mapped_source_rows": [4, 5],
                    "mapped_source_classes": ["bodypart_portrait_clothed", "bodypart_portrait_topless"],
                    "mapped_target_classes": ["portrait", "tportrait"],
                    "unmapped_source_rows": [index for index in range(26) if index not in {4, 5}],
                    "unmapped_policy": "retained as provenance; no other old classifier outputs copied"}


def validate_shared_checkpoint(path: Path | str, registry: dict) -> dict:
    """Strictly load every tensor and compare all declared compatibility metadata."""
    import torch
    import sys
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from app.core.shared_cnn import (ARCHITECTURE_ID as APP_ARCHITECTURE_ID,
                                     ARCHITECTURE_VERSION as APP_ARCHITECTURE_VERSION,
                                     BACKBONE_ID as APP_BACKBONE_ID,
                                     build_shared_task_cnn, load_head_class_mappings)
    checkpoint_path = Path(path).resolve()
    payload = torch.load(checkpoint_path, map_location="cpu")
    if not isinstance(payload, dict) or payload.get("complete_model") is not True:
        raise SharedTrainingError("Checkpoint is partial, untrained, or missing complete-model metadata.")
    expected_mappings = load_head_class_mappings(
        Path(__file__).resolve().parents[2] / "data/models/unified_body_images_fullbody/class_registry.json")
    expected_registry_version = str(registry.get("version"))
    if (payload.get("model_id") != MODEL_ID or payload.get("architecture_id") != APP_ARCHITECTURE_ID
            or payload.get("architecture_version") != APP_ARCHITECTURE_VERSION
            or payload.get("backbone_id") != APP_BACKBONE_ID
            or payload.get("head_names") != list(HEADS)
            or payload.get("class_mappings") != expected_mappings
            or payload.get("registry_id") != REGISTRY_ID
            or payload.get("registry_version") != expected_registry_version
            or payload.get("input_size") != INPUT_SIZE
            or payload.get("preprocessing") != PREPROCESSING
            or payload.get("training_status") != "completed"):
        raise SharedTrainingError("Checkpoint compatibility metadata does not match the current shared model.")
    if (not isinstance(payload.get("training_run_id"), str) or not payload["training_run_id"]
            or not isinstance(payload.get("dataset"), dict)
            or not isinstance(payload.get("training_config"), dict)
            or not isinstance(payload.get("created_at"), str)):
        raise SharedTrainingError("Checkpoint is missing its run, dataset, configuration, or timestamp provenance.")
    metrics = payload.get("metrics")
    validation_metrics = metrics.get("validation") if isinstance(metrics, dict) else None
    if not isinstance(validation_metrics, dict) or set(validation_metrics) != set(HEADS):
        raise SharedTrainingError("Checkpoint must include validation metrics for all five task heads.")
    for head, values in validation_metrics.items():
        if int(values.get("count", 0)) < 1 or not isinstance(values.get("classes"), dict):
            raise SharedTrainingError(f"Checkpoint validation metrics are incomplete for head {head!r}.")
    state = payload.get("state_dict")
    if not isinstance(state, dict):
        raise SharedTrainingError("Checkpoint has no state dictionary.")
    model = build_shared_task_cnn()
    try:
        model.load_state_dict(state, strict=True)
    except Exception as error:
        raise SharedTrainingError("Checkpoint tensors do not strictly match the shared five-head architecture.") from error
    model.eval()
    with torch.inference_mode():
        smoke_image = Image.new("RGB", tuple(INPUT_SIZE), color=(32, 96, 160))
        transform = __import__("torchvision").transforms.Compose([
            __import__("torchvision").transforms.Resize(256),
            __import__("torchvision").transforms.CenterCrop(tuple(INPUT_SIZE)),
            __import__("torchvision").transforms.ToTensor(),
            __import__("torchvision").transforms.Normalize([.485, .456, .406], [.229, .224, .225])])
        output = model(transform(smoke_image).unsqueeze(0))
    for head in HEADS:
        if tuple(output[head].shape) != (1, len(expected_mappings[head])):
            raise SharedTrainingError(f"Checkpoint head {head!r} returned the wrong output shape.")
    return {"compatible": True, "checkpoint_sha256": sha256_file(checkpoint_path),
            "architecture_id": APP_ARCHITECTURE_ID, "architecture_version": APP_ARCHITECTURE_VERSION,
            "head_names": list(HEADS), "registry_version": expected_registry_version,
            "smoke_test": "passed"}


def export_shared_model_artifact(checkpoint_path: Path | str, destination: Path | str,
                                 registry_path: Path | str) -> dict:
    """Prepare a completed checkpoint and provenance for NewAssetApp review/import."""
    import hashlib
    registry_path = Path(registry_path).resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    compatibility = validate_shared_checkpoint(checkpoint_path, registry)
    destination = Path(destination).resolve()
    if destination.exists():
        raise SharedTrainingError("Model artifact output already exists; export never overwrites artifacts.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".shared_model_artifact_", dir=destination.parent))
    try:
        checkpoint_target = staging / "shared_cnn.pth"
        registry_target = staging / "registry.json"
        shutil.copy2(checkpoint_path, checkpoint_target)
        shutil.copy2(registry_path, registry_target)
        payload = json.loads("{}")
        import torch
        checkpoint = torch.load(checkpoint_target, map_location="cpu")
        payload = {key: checkpoint.get(key) for key in (
            "model_id", "architecture_id", "architecture_version", "backbone_id", "head_names",
            "class_mappings", "registry_id", "registry_version", "input_size", "preprocessing",
            "dataset", "training_config", "metrics", "initialization", "training_run_id", "created_at")}
        payload.update({"schema_version": 1, "checkpoint_path": "shared_cnn.pth",
                        "registry_path": "registry.json", "checkpoint_sha256": compatibility["checkpoint_sha256"],
                        "registry_sha256": sha256_file(registry_target), "training_status": "completed"})
        artifact_files = {name: {"sha256": sha256_file(staging / name),
                                 "bytes": (staging / name).stat().st_size}
                          for name in ("shared_cnn.pth", "registry.json")}
        manifest = {"schema_version": 1, "artifact_type": "newassetapp_shared_cnn",
                    "compatibility": compatibility, "metadata": payload, "files": artifact_files}
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
        (staging / "artifact_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                                        encoding="utf-8")
        os.replace(staging, destination)
        return {"path": str(destination), "checkpoint_sha256": compatibility["checkpoint_sha256"],
                "architecture_id": compatibility["architecture_id"], "head_names": compatibility["head_names"]}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
