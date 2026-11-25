from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "models" / "phase4_model_registry.json"
MANIFEST_SCHEMA = ROOT / "data" / "datasets" / "phase4_dataset_manifest.schema.json"
OUTPUT_ROOT = ROOT / "data" / "datasets" / "phase4"
CANONICAL_LOCATIONS = {"bathroom", "bar", "beach", "cafeteria", "class", "clinic", "coffee_shop",
                       "home", "locker_room", "mall", "office", "park", "pier", "shower", "lounge"}


def validate_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    for key in ("schema_version", "dataset_id", "task", "seed", "split_ratios", "samples", "status"):
        if key not in manifest:
            errors.append(f"missing_required_field:{key}")
    by_source: dict[str, set[str]] = defaultdict(set)
    for index, sample in enumerate(manifest.get("samples", [])):
        prefix = f"samples[{index}]"
        digest, split = sample.get("source_sha256"), sample.get("split")
        if not isinstance(digest, str) or len(digest) != 64:
            errors.append(f"{prefix}:invalid_source_sha256")
        elif split in {"train", "validation", "test"}:
            by_source[digest].add(split)
        if sample.get("eligibility") == "trusted_training" and sample.get("review_status") != "human_confirmed":
            errors.append(f"{prefix}:nonhuman_label_in_trusted_dataset")
        if sample.get("review_status") in {"rejected", "uncertain", "ai_candidate", "ai_pseudo_label"} and sample.get("eligibility") == "trusted_training":
            errors.append(f"{prefix}:ineligible_review_status_in_trusted_dataset")
    for digest, splits in by_source.items():
        if len(splits) > 1:
            errors.append(f"source_crosses_splits:{digest}")
    if manifest.get("task") == "location_classifier_v1":
        labels = {sample.get("label") for sample in manifest.get("samples", []) if sample.get("label") is not None}
        if not labels <= CANONICAL_LOCATIONS:
            errors.append("unsupported_location_label")
    return errors


def validate_registry(registry: dict) -> list[str]:
    errors: list[str] = []
    models = registry.get("models", {})
    expected_models = {"yolo_detector", "unified_body_images_fullbody_cnn", "clothing_classifier"}
    if set(models) != expected_models:
        errors.append("phase4b_requires_yolo_and_exactly_two_cnn_models")
    unified = models.get("unified_body_images_fullbody_cnn", {})
    if unified.get("one_model_identity") is not True or unified.get("output_groups") != {
        "body_images": 2, "fullbody": 5, "portrait": 2, "arousal": 2, "corruption": 4
    }:
        errors.append("unified_cnn_output_groups_mismatch")
    clothing = models.get("clothing_classifier", {})
    if clothing.get("class_count") != 12:
        errors.append("clothing_classifier_must_define_12_classes")
    if models.get("yolo_detector", {}).get("class_count") != 32:
        errors.append("yolo_detector_must_preserve_32_classes")
    return errors


def main() -> int:
    errors = validate_registry(json.loads(REGISTRY.read_text(encoding="utf-8")))
    paths = sorted(OUTPUT_ROOT.glob("*/dataset_manifest.json")) if OUTPUT_ROOT.exists() else []
    for path in paths:
        errors.extend(f"{path.relative_to(ROOT)}:{issue}" for issue in validate_manifest(json.loads(path.read_text(encoding="utf-8"))))
    print(json.dumps({"errors": errors, "dataset_manifests_checked": len(paths),
                      "manifest_schema": str(MANIFEST_SCHEMA.relative_to(ROOT)), "dataset_root": str(OUTPUT_ROOT.relative_to(ROOT))}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
