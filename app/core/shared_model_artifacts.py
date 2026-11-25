from __future__ import annotations

import hashlib
import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.core.shared_cnn import (ARCHITECTURE_ID, ARCHITECTURE_VERSION, APP_ROOT,
                                 BACKBONE_ID, EXPECTED_HEADS, INPUT_SIZE,
                                 NORMALIZATION, REGISTRY_PATH, build_shared_task_cnn,
                                 load_head_class_mappings)


class SharedModelArtifactError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_shared_artifact(artifact_dir: Path | str) -> dict:
    """Verify package hashes, exact registry identity, all tensors, and image inference."""
    from TrainingDatasetStudio.studio.shared_training import validate_shared_checkpoint
    root = Path(artifact_dir).resolve()
    manifest_path = root / "artifact_manifest.json"
    if not manifest_path.is_file():
        raise SharedModelArtifactError("Artifact manifest is missing.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hash = manifest.pop("manifest_sha256", None)
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if not expected_hash or hashlib.sha256(canonical).hexdigest() != expected_hash:
        raise SharedModelArtifactError("Artifact manifest hash is invalid.")
    if manifest.get("artifact_type") != "newassetapp_shared_cnn" or manifest.get("schema_version") != 1:
        raise SharedModelArtifactError("Unsupported shared CNN artifact type or version.")
    for relative, entry in manifest.get("files", {}).items():
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise SharedModelArtifactError("Artifact contains a missing or unsafe file path.")
        if path.stat().st_size != int(entry["bytes"]) or _sha256(path) != entry["sha256"]:
            raise SharedModelArtifactError(f"Artifact file hash/size mismatch: {relative}")
    metadata = manifest.get("metadata") or {}
    registry_path = (root / str(metadata.get("registry_path") or "")).resolve()
    checkpoint_path = (root / str(metadata.get("checkpoint_path") or "")).resolve()
    if root not in registry_path.parents or root not in checkpoint_path.parents:
        raise SharedModelArtifactError("Artifact metadata contains an unsafe registry or checkpoint path.")
    if not registry_path.is_file() or not checkpoint_path.is_file():
        raise SharedModelArtifactError("Artifact checkpoint or registry payload is missing.")
    app_registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    package_registry = json.loads(registry_path.read_text(encoding="utf-8"))
    expected_mappings = load_head_class_mappings(REGISTRY_PATH)
    packaged_mappings = {head: [{"class_id": int(row["class_id"]), "class_name": row["class_name"]}
                                 for row in package_registry["output_groups"][head]["classes"]]
                         for head in sorted(EXPECTED_HEADS, key=("body_images", "fullbody", "portrait", "arousal", "corruption").index)}
    if packaged_mappings != expected_mappings or package_registry.get("version") != app_registry.get("version"):
        raise SharedModelArtifactError("Artifact task class mappings or registry version differ from NewAssetApp.")
    if metadata.get("class_mappings") != expected_mappings:
        raise SharedModelArtifactError("Artifact metadata class mappings differ from the current registry.")
    report = validate_shared_checkpoint(checkpoint_path, app_registry)
    if (metadata.get("architecture_id") != ARCHITECTURE_ID
            or metadata.get("architecture_version") != ARCHITECTURE_VERSION
            or metadata.get("backbone_id") != BACKBONE_ID
            or metadata.get("head_names") != ["body_images", "fullbody", "portrait", "arousal", "corruption"]
            or metadata.get("input_size") != INPUT_SIZE
            or metadata.get("preprocessing", {}).get("mean") != NORMALIZATION["mean"]
            or metadata.get("preprocessing", {}).get("std") != NORMALIZATION["std"]):
        raise SharedModelArtifactError("Artifact architecture or preprocessing is incompatible with NewAssetApp.")
    report.update({"artifact_dir": str(root), "model_id": metadata.get("model_id"),
                   "training_run_id": metadata.get("training_run_id"), "metrics": metadata.get("metrics")})
    return report


def stage_shared_artifact(artifact_dir: Path | str, app_root: Path | str = APP_ROOT) -> dict:
    report = inspect_shared_artifact(artifact_dir)
    app_root = Path(app_root).resolve()
    candidate_root = app_root / "models" / "shared_cnn_candidates"
    candidate_root.mkdir(parents=True, exist_ok=True)
    candidate_id = report["checkpoint_sha256"]
    destination = candidate_root / candidate_id
    if not destination.exists():
        staging = Path(tempfile.mkdtemp(prefix=".candidate_", dir=candidate_root))
        try:
            shutil.copytree(Path(artifact_dir).resolve(), staging / "artifact")
            os.replace(staging / "artifact", destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    # Recheck the copied bytes before returning a reviewable candidate.
    copied = inspect_shared_artifact(destination)
    return {"candidate_id": candidate_id, "candidate_path": str(destination),
            "compatible": copied["compatible"], "checkpoint_sha256": copied["checkpoint_sha256"],
            "architecture_id": copied["architecture_id"], "head_names": copied["head_names"],
            "smoke_test": copied["smoke_test"], "training_run_id": copied["training_run_id"]}


def activate_shared_candidate(candidate_path: Path | str, app_root: Path | str = APP_ROOT,
                              *, confirmed: bool = False) -> dict:
    if not confirmed:
        raise SharedModelArtifactError("Explicit user confirmation is required to activate a model candidate.")
    app_root = Path(app_root).resolve()
    candidate = Path(candidate_path).resolve()
    candidate_root = (app_root / "models" / "shared_cnn_candidates").resolve()
    if candidate_root not in candidate.parents:
        raise SharedModelArtifactError("Stage the returned artifact inside this NewAssetApp before activation.")
    report = inspect_shared_artifact(candidate_path)
    pointer = app_root / "data" / "models" / "active_shared_cnn.json"
    backup_dir = app_root / "models" / "shared_cnn_rollback"
    backup_dir.mkdir(parents=True, exist_ok=True)
    previous = None
    if pointer.is_file():
        previous = json.loads(pointer.read_text(encoding="utf-8"))
        backup = backup_dir / (datetime.now(timezone.utc).strftime("active_%Y%m%dT%H%M%S%fZ") + ".json")
        shutil.copy2(pointer, backup)
    payload = {"schema_version": 1, "model_id": report["model_id"],
               "candidate_path": str(candidate), "checkpoint_sha256": report["checkpoint_sha256"],
               "architecture_id": report["architecture_id"],
               "training_run_id": report["training_run_id"],
               "activated_at": datetime.now(timezone.utc).isoformat(),
               "previous_checkpoint_sha256": previous.get("checkpoint_sha256") if previous else None}
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temp = pointer.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, pointer)
    return {"activated": True, "pointer": str(pointer), "checkpoint_sha256": report["checkpoint_sha256"],
            "previous_checkpoint_sha256": payload["previous_checkpoint_sha256"]}


def rollback_shared_candidate(app_root: Path | str = APP_ROOT) -> dict:
    app_root = Path(app_root).resolve()
    pointer = app_root / "data" / "models" / "active_shared_cnn.json"
    backups = sorted((app_root / "models" / "shared_cnn_rollback").glob("active_*.json"), reverse=True)
    if not backups:
        raise SharedModelArtifactError("No previous active shared CNN pointer is available for rollback.")
    if pointer.is_file():
        current_backup = backups[0].parent / ("rolled_back_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        shutil.copy2(pointer, current_backup)
    previous = json.loads(backups[0].read_text(encoding="utf-8"))
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temp = pointer.with_suffix(".tmp")
    temp.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, pointer)
    return {"rolled_back": True, "pointer": str(pointer),
            "checkpoint_sha256": previous.get("checkpoint_sha256")}


def load_active_shared_model(app_root: Path | str = APP_ROOT):
    app_root = Path(app_root).resolve()
    pointer = app_root / "data" / "models" / "active_shared_cnn.json"
    if not pointer.is_file():
        return None, None
    state = json.loads(pointer.read_text(encoding="utf-8"))
    report = inspect_shared_artifact(state["candidate_path"])
    if report["checkpoint_sha256"] != state.get("checkpoint_sha256"):
        raise SharedModelArtifactError("Active checkpoint changed after activation; refusing to load it.")
    import torch
    import torchvision.transforms as transforms
    payload = torch.load(Path(state["candidate_path"]) / "shared_cnn.pth", map_location="cpu")
    model = build_shared_task_cnn()
    model.load_state_dict(payload["state_dict"], strict=True)
    model.eval()
    transform = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(tuple(INPUT_SIZE)),
                                    transforms.ToTensor(), transforms.Normalize(
                                        NORMALIZATION["mean"], NORMALIZATION["std"])])
    return model, {**state, "transform": transform, "report": report}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and manage returned NewAssetApp shared CNN model artifacts.")
    actions = parser.add_subparsers(dest="action", required=True)
    inspect = actions.add_parser("inspect"); inspect.add_argument("artifact", type=Path)
    stage = actions.add_parser("stage"); stage.add_argument("artifact", type=Path)
    activate = actions.add_parser("activate"); activate.add_argument("candidate", type=Path)
    activate.add_argument("--confirm", action="store_true", help="Confirm that this compatible candidate should become active.")
    rollback = actions.add_parser("rollback")
    args = parser.parse_args()
    if args.action == "inspect":
        result = inspect_shared_artifact(args.artifact)
    elif args.action == "stage":
        result = stage_shared_artifact(args.artifact)
    elif args.action == "activate":
        result = activate_shared_candidate(args.candidate, confirmed=args.confirm)
    else:
        result = rollback_shared_candidate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
