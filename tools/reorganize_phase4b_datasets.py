from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "train_data"
INVENTORY_PATH = ROOT / "reports" / "PHASE4B_PRE_MIGRATION_INVENTORY.json"
BODY_DATASET = DATA_ROOT / "unified_body_images_fullbody"
CLOTHING_DATASET = DATA_ROOT / "clothing_classifier"
YOLO_DATASET = DATA_ROOT / "yolo"
SEED = 42
RATIOS = (0.8, 0.1, 0.1)
BODY_SOURCE_TO_CLASS = {
    "bodypart_ass": "bodypart_ass", "bodypart_boobs": "bodypart_boobs",
    "bodypart_face": "bodypart_face", "bodypart_legs": "bodypart_legs",
    "bodypart_portrait_clothed": "portrait", "bodypart_portrait_topless": "tportrait",
    "bodypart_pussy": "bodypart_pussy",
}
LEGACY_FULLBODY_CLASSES = ("fullbody_clothed_states", "fullbody_costume_states", "fullbody_nude_states")
BODY_YOLO_CLASS_TO_CANDIDATE = {
    1: "bodypart_face", 2: "unresolved_portrait_type", 3: "bodypart_boobs",
    4: "bodypart_ass", 5: "bodypart_pussy", 6: "bodypart_legs",
}
FULLBODY_YOLO_CANDIDATES = {0: "unclassified_person", **{i: "fullbody_type_candidate" for i in range(19, 28)},
                             29: "candidate_topless", 30: "candidate_bottomless", 31: "unresolved_fullbody_bare"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(f"Refusing to overwrite existing changed dataset metadata: {path}")
        return
    path.write_bytes(data)


def copy_verified(source: Path, destination: Path, expected_sha256: str) -> bool:
    if sha_file(source) != expected_sha256:
        raise ValueError(f"Source changed after inventory: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha_file(destination) != expected_sha256:
            raise FileExistsError(f"Refusing to overwrite existing changed dataset file: {destination}")
        return False
    shutil.copy2(source, destination)
    if sha_file(destination) != expected_sha256:
        raise IOError(f"Copied file hash mismatch: {destination}")
    return True


def stable_split(source_hash: str) -> str:
    number = int(hashlib.sha256(f"{SEED}:{source_hash}".encode()).hexdigest()[:16], 16) / 16**16
    if number < RATIOS[0]:
        return "train"
    if number < RATIOS[0] + RATIOS[1]:
        return "val"
    return "test"


def ensure_split_dirs() -> None:
    body_registry = json.loads((ROOT / "data/models/unified_body_images_fullbody/class_registry.json").read_text(encoding="utf-8"))
    body_classes = [item["class_name"] for item in body_registry["output_groups"]["body_images"]["classes"]]
    state_classes = [item["class_name"] for item in body_registry["output_groups"]["fullbody_state"]["classes"]]
    clothing_registry = json.loads((ROOT / "data/models/clothing_classifier_registry.json").read_text(encoding="utf-8"))
    clothing_classes = [item["class_name"] for item in clothing_registry["classes"]]
    for split in ("train", "val", "test"):
        for name in body_classes:
            (BODY_DATASET / split / "body_images" / name).mkdir(parents=True, exist_ok=True)
        for name in state_classes:
            (BODY_DATASET / split / "fullbody_state" / name).mkdir(parents=True, exist_ok=True)
        for name in clothing_classes:
            (CLOTHING_DATASET / split / name).mkdir(parents=True, exist_ok=True)
        (YOLO_DATASET / "images" / split).mkdir(parents=True, exist_ok=True)
        (YOLO_DATASET / "labels" / split).mkdir(parents=True, exist_ok=True)
    for path in (BODY_DATASET / "review", BODY_DATASET / "manifests", CLOTHING_DATASET / "review",
                 CLOTHING_DATASET / "manifests", YOLO_DATASET / "review_required", YOLO_DATASET / "manifests",
                 DATA_ROOT / "shared" / "provenance", DATA_ROOT / "shared" / "manifests",
                 DATA_ROOT / "backups"):
        path.mkdir(parents=True, exist_ok=True)


def migrate(inventory: dict) -> dict:
    source_index = {row["path"]: row for row in inventory["files"]}
    original_class_map = inventory["cnn_class_map"]
    body_registry = json.loads((ROOT / "data/models/unified_body_images_fullbody/class_registry.json").read_text(encoding="utf-8"))
    clothing_registry = json.loads((ROOT / "data/models/clothing_classifier_registry.json").read_text(encoding="utf-8"))
    model_manifest = json.loads((ROOT / "models/model_manifest.json").read_text(encoding="utf-8"))
    yolo_names = model_manifest["models"]["yolo"]["class_names"]
    if inventory["yolo"]["class_names"] != yolo_names:
        raise ValueError("Legacy YOLO classes.txt differs from the preserved model manifest.")
    for classes, filename in (([x["class_name"] for x in body_registry["output_groups"]["body_images"]["classes"]], "body_images_classes.txt"),
                              ([x["class_name"] for x in body_registry["output_groups"]["fullbody_state"]["classes"]], "fullbody_state_classes.txt")):
        write_once(BODY_DATASET / "classes" / filename, ("\n".join(classes) + "\n").encode())
    clothing_classes = [item["class_name"] for item in clothing_registry["classes"]]
    write_once(CLOTHING_DATASET / "classes" / "classes.txt", ("\n".join(clothing_classes) + "\n").encode())
    write_once(CLOTHING_DATASET / "classes" / "registry.json", json.dumps(clothing_registry, indent=2).encode() + b"\n")
    write_once(BODY_DATASET / "classes" / "registry.json", json.dumps(body_registry, indent=2).encode() + b"\n")
    write_once(YOLO_DATASET / "classes.txt", ("\n".join(yolo_names) + "\n").encode())
    yolo_registry = {"schema_version": 1, "model_id": "yolo_detector", "class_count": 32,
                     "classes": [{"class_id": index, "class_name": name, "original_class_name": name}
                                 for index, name in enumerate(yolo_names)],
                     "source_checkpoint_registry": "models/model_manifest.json#/models/yolo/class_names"}
    write_once(YOLO_DATASET / "class_registry.json", json.dumps(yolo_registry, indent=2).encode() + b"\n")
    yaml = "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnc: 32\nnames:\n" + "".join(
        f"  {class_id}: {name}\n" for class_id, name in enumerate(yolo_names))
    write_once(YOLO_DATASET / "dataset.yaml", yaml.encode())
    write_once(CLOTHING_DATASET / "README.md", b"# Clothing classifier dataset\n\nThe active broad Clothing classifier uses the reviewed 12-class registry. The original 26-class Asset CNN remains historical provenance and is not the active class order.\n")
    write_once(BODY_DATASET / "README.md", b"# Unified Body Images + Fullbody CNN dataset\n\nOne model and one dataset identity use task-specific Body Images (4 classes) and Fullbody State (3 classes) output groups. Existing folder-labeled images and YOLO-derived crops are staged in `review/` only; they are not eligible training labels until a human confirms them. Splits use seed 42 and source SHA-256 grouping (80/10/10). No training occurred.\n")
    write_once(YOLO_DATASET / "README.md", b"# YOLO dataset\n\nOriginal classes and train/val split are preserved. One structurally invalid annotation pair is copied intact to `review_required/` and excluded from active split folders. The source dataset remains untouched. Validate semantic labels before training. No training occurred.\n")

    migration = {"schema_version": 1, "source_inventory": "reports/PHASE4B_PRE_MIGRATION_INVENTORY.json",
                 "backup_verification": "reports/PHASE4B_BACKUP_VERIFICATION.json", "seed": SEED,
                 "split_ratios": {"train": 0.8, "val": 0.1, "test": 0.1},
                 "split_grouping": "sha256 of original image bytes", "copies": [], "crops": [],
                 "review_only_legacy_examples": [], "excluded_from_active_yolo": [],
                 "training_eligible_count": 0, "training_performed": False}

    # Keep legacy Body Images class-folder examples byte-identical in review only.
    for row in inventory["files"]:
        parts = Path(row["path"]).parts
        if row["role"] != "cnn_class_image" or "asset_classifier_data" not in parts:
            continue
        index = parts.index("asset_classifier_data")
        if len(parts) < index + 4:
            continue
        split, old_class = parts[index + 1], parts[index + 2]
        if old_class in BODY_SOURCE_TO_CLASS:
            task, label = "body_images", BODY_SOURCE_TO_CLASS[old_class]
            dest = BODY_DATASET / "review" / "legacy_body_images" / label / f"{row['sha256'][:12]}_{Path(row['path']).name}"
            copy_verified(ROOT / "train_data" / Path(row["path"]), dest, row["sha256"])
            record = {"task": task, "label_candidate": label, "source_relative_path": row["path"],
                      "destination_relative_path": dest.relative_to(ROOT).as_posix(),
                      "source_sha256": row["sha256"], "legacy_split": split, "proposed_split": stable_split(row["sha256"]),
                      "original_class_id": original_class_map[old_class], "original_class_name": old_class,
                      "review_status": "legacy_folder_label_requires_human_confirmation", "training_eligible": False}
            migration["copies"].append(record)
        elif old_class in LEGACY_FULLBODY_CLASSES:
            dest = BODY_DATASET / "review" / "legacy_fullbody_groups" / old_class / f"{row['sha256'][:12]}_{Path(row['path']).name}"
            copy_verified(ROOT / "train_data" / Path(row["path"]), dest, row["sha256"])
            migration["review_only_legacy_examples"].append({"source_relative_path": row["path"],
                "destination_relative_path": dest.relative_to(ROOT).as_posix(), "source_sha256": row["sha256"],
                "original_class_id": original_class_map[old_class], "original_class_name": old_class,
                "state_mapping": None, "reason": "broad legacy group is not equivalent to the three requested states",
                "training_eligible": False})

    yolo_copied, yolo_quarantined = [], []
    crop_counts = Counter()
    for split in ("train", "val"):
        source_images = ROOT / "train_data" / "YOLO_Project" / "dataset" / "images" / split
        source_labels = ROOT / "train_data" / "YOLO_Project" / "dataset" / "labels" / split
        for image_path in sorted(p for p in source_images.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS):
            image_rel = image_path.relative_to(ROOT).as_posix()
            image_row = source_index[image_path.relative_to(DATA_ROOT).as_posix()]
            label_path = source_labels / f"{image_path.stem}.txt"
            label_row = source_index[label_path.relative_to(DATA_ROOT).as_posix()]
            raw_lines = label_path.read_text(encoding="utf-8-sig").splitlines()
            invalid_lines = []
            parsed = []
            for line_number, text in enumerate(raw_lines, 1):
                if not text.strip():
                    continue
                fields = text.split()
                try:
                    class_id = int(fields[0])
                    xc, yc, width, height = map(float, fields[1:])
                    if len(fields) != 5 or not 0 <= class_id < 32 or any(v < 0 or v > 1 for v in (xc, yc, width, height)) or width <= 0 or height <= 0:
                        raise ValueError("invalid class ID or normalized box")
                    parsed.append((line_number, class_id, xc, yc, width, height))
                except Exception as error:
                    invalid_lines.append({"line": line_number, "text": text, "reason": str(error)})
            if invalid_lines:
                image_dst = YOLO_DATASET / "review_required" / split / "images" / image_path.name
                label_dst = YOLO_DATASET / "review_required" / split / "labels" / label_path.name
                image_copied = copy_verified(image_path, image_dst, image_row["sha256"])
                label_copied = copy_verified(label_path, label_dst, label_row["sha256"])
                yolo_quarantined.append({"source_image": image_rel, "source_label": label_path.relative_to(ROOT).as_posix(),
                    "image_sha256": image_row["sha256"], "label_sha256": label_row["sha256"], "source_split": split,
                    "invalid_lines": invalid_lines, "copied_image": image_dst.relative_to(ROOT).as_posix(),
                    "copied_label": label_dst.relative_to(ROOT).as_posix()})
            else:
                image_dst = YOLO_DATASET / "images" / split / image_path.name
                label_dst = YOLO_DATASET / "labels" / split / label_path.name
                image_copied = copy_verified(image_path, image_dst, image_row["sha256"])
                label_copied = copy_verified(label_path, label_dst, label_row["sha256"])
                yolo_copied.append({"source_image": image_rel, "source_label": label_path.relative_to(ROOT).as_posix(),
                    "image_sha256": image_row["sha256"], "label_sha256": label_row["sha256"], "source_split": split,
                    "destination_image": image_dst.relative_to(ROOT).as_posix(),
                    "destination_label": label_dst.relative_to(ROOT).as_posix(),
                    "annotation_count": len(parsed)})
            # Review crops from existing YOLO annotations. These are proposals only, never training labels.
            if invalid_lines:
                continue
            with Image.open(image_path) as original:
                rgb = original.convert("RGB")
                width_px, height_px = rgb.size
                for ordinal, (line_number, class_id, xc, yc, w, h) in enumerate(parsed, 1):
                    candidate = BODY_YOLO_CLASS_TO_CANDIDATE.get(class_id)
                    fullbody_candidate = FULLBODY_YOLO_CANDIDATES.get(class_id)
                    if candidate is None and fullbody_candidate is None:
                        continue
                    x1 = max(0, int((xc - w / 2) * width_px)); y1 = max(0, int((yc - h / 2) * height_px))
                    x2 = min(width_px, int((xc + w / 2) * width_px + 0.999999)); y2 = min(height_px, int((yc + h / 2) * height_px + 0.999999))
                    if x2 <= x1 or y2 <= y1:
                        continue
                    crop_buffer = io.BytesIO()
                    rgb.crop((x1, y1, x2, y2)).save(crop_buffer, format="PNG")
                    crop_bytes = crop_buffer.getvalue(); crop_hash = sha_bytes(crop_bytes)
                    source_hash = image_row["sha256"]
                    task = "body_images" if candidate else "fullbody_state"
                    review_group = candidate or fullbody_candidate
                    dest = BODY_DATASET / "review" / "yolo_candidates" / task / review_group / f"{source_hash[:12]}_y{class_id}_{line_number}.png"
                    write_once(dest, crop_bytes)
                    original_class = yolo_names[class_id]
                    record = {"task": task, "review_group": review_group,
                        "label_candidate": (candidate if candidate and candidate != "unresolved_portrait_type" else
                                            ("topless" if class_id == 29 else "bottomless" if class_id == 30 else None)),
                        "source_path": image_rel, "source_sha256": source_hash,
                        "original_dimensions": [width_px, height_px], "original_yolo_class_id": class_id,
                        "original_yolo_class_name": original_class, "source_label_path": label_path.relative_to(ROOT).as_posix(),
                        "annotation_line": line_number, "bbox_normalized_xywh": [xc, yc, w, h],
                        "crop_bbox_source_xyxy": [x1, y1, x2, y2], "crop_path": dest.relative_to(ROOT).as_posix(),
                        "crop_sha256": crop_hash, "source_dataset_split": split,
                        "stable_proposed_split": stable_split(source_hash),
                        "label_origin": "legacy_yolo_dataset_annotation_no_human-review-provenance",
                        "review_status": "candidate_requires_human_confirmation", "training_eligible": False,
                        "model_confidence": None, "checkpoint_sha256": None}
                    migration["crops"].append(record); crop_counts[task] += 1

    migration["yolo_active_pairs"] = yolo_copied
    migration["excluded_from_active_yolo"] = yolo_quarantined
    write_once(DATA_ROOT / "shared" / "source_inventory.json", INVENTORY_PATH.read_bytes())
    manifest_bytes = json.dumps(migration, indent=2, ensure_ascii=False).encode() + b"\n"
    write_once(DATA_ROOT / "shared" / "manifests" / "migration_manifest.json", manifest_bytes)
    write_once(BODY_DATASET / "manifests" / "migration_manifest.json", manifest_bytes)
    write_once(CLOTHING_DATASET / "manifests" / "migration_manifest.json", json.dumps({
        "status": "manual_user_population_required", "source_data_untouched": "train_data/cnn_train/asset_classifier_data",
        "class_count": 12, "copied_or_relabelled_examples": 0}, indent=2).encode() + b"\n")
    write_once(YOLO_DATASET / "manifests" / "migration_manifest.json", json.dumps({
        "source_dataset": "train_data/YOLO_Project/dataset", "active_pairs": len(yolo_copied),
        "quarantined_pairs": yolo_quarantined, "original_split_preserved": True,
        "class_names": yolo_names, "training_eligible_semantic_review_pending": True}, indent=2).encode() + b"\n")
    return {"legacy_source_files": len(inventory["files"]),
            "unified_body_legacy_examples_in_review": sum(1 for x in migration["copies"] if x["task"] == "body_images"),
            "legacy_fullbody_examples_in_review": len(migration["review_only_legacy_examples"]),
            "yolo_active_pairs": len(yolo_copied), "yolo_quarantined_pairs": len(yolo_quarantined),
            "candidate_crops": dict(crop_counts), "unified_dataset_train_eligible": 0,
            "clothing_examples_copied": 0, "migration_manifest": str((DATA_ROOT / "shared/manifests/migration_manifest.json").relative_to(ROOT)),
            "training_started": False}


def validate_layout() -> list[str]:
    errors = []
    registry_path = ROOT / "data/models/phase4_model_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    models = registry["models"]
    if set(models) != {"yolo_detector", "unified_body_images_fullbody_cnn", "clothing_classifier"}:
        errors.append("model_registry_must_have_yolo_and_exactly_two_cnns")
    unified = json.loads((ROOT / "data/models/unified_body_images_fullbody/class_registry.json").read_text(encoding="utf-8"))
    for key, expected_file in (("body_images", BODY_DATASET / "classes/body_images_classes.txt"),
                               ("fullbody_state", BODY_DATASET / "classes/fullbody_state_classes.txt")):
        group = unified["output_groups"][key]
        names = [entry["class_name"] for entry in group["classes"]]
        if len(names) != group["class_count"] or len(set(names)) != len(names):
            errors.append(f"{key}:registry_count_or_duplicate_name_error")
        if expected_file.read_text(encoding="utf-8").splitlines() != names:
            errors.append(f"{key}:class_file_order_mismatch")
    body_names = [x["class_name"] for x in unified["output_groups"]["body_images"]["classes"]]
    if body_names != ["portrait", "tportrait", "bodypart_cum", "bodypart_acc"]:
        errors.append("body_images_class_order_mismatch")
    if [x["class_name"] for x in unified["output_groups"]["fullbody_state"]["classes"]] != ["clothed", "topless", "bottomless"]:
        errors.append("fullbody_state_class_order_mismatch")
    manifest_path = DATA_ROOT / "shared/manifests/migration_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_splits: dict[str, set[str]] = {}
        for record in manifest.get("copies", []):
            destination = ROOT / record["destination_relative_path"]
            if not destination.is_file() or sha_file(destination) != record["source_sha256"]:
                errors.append(f"legacy_body_copy_hash_mismatch:{record['destination_relative_path']}")
        for record in manifest.get("review_only_legacy_examples", []):
            destination = ROOT / record["destination_relative_path"]
            if not destination.is_file() or sha_file(destination) != record["source_sha256"]:
                errors.append(f"legacy_fullbody_copy_hash_mismatch:{record['destination_relative_path']}")
        for pair in manifest.get("yolo_active_pairs", []) + manifest.get("excluded_from_active_yolo", []):
            for source_key, hash_key in (("destination_image", "image_sha256"), ("copied_image", "image_sha256"),
                                         ("destination_label", "label_sha256"), ("copied_label", "label_sha256")):
                if source_key in pair:
                    copied = ROOT / pair[source_key]
                    if not copied.is_file() or sha_file(copied) != pair[hash_key]:
                        errors.append(f"yolo_copy_hash_mismatch:{pair[source_key]}")
        for crop in manifest.get("crops", []):
            source_splits.setdefault(crop["source_sha256"], set()).add(crop["stable_proposed_split"])
            if crop["training_eligible"]:
                errors.append("unconfirmed_candidate_crop_marked_training_eligible")
            crop_path = ROOT / crop["crop_path"]
            if not crop_path.is_file() or sha_file(crop_path) != crop["crop_sha256"]:
                errors.append(f"candidate_crop_hash_mismatch:{crop['crop_path']}")
        if any(len(splits) > 1 for splits in source_splits.values()):
            errors.append("unified_crop_source_hash_crosses_splits")
    for split in ("train", "val", "test"):
        image_dir = YOLO_DATASET / "images" / split
        label_dir = YOLO_DATASET / "labels" / split
        images = {p.stem for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS}
        labels = {p.stem for p in label_dir.glob("*.txt")}
        if images != labels:
            errors.append(f"yolo_{split}_image_label_pair_mismatch")
        for label in label_dir.glob("*.txt"):
            for line_number, text in enumerate(label.read_text(encoding="utf-8-sig").splitlines(), 1):
                if not text.strip():
                    continue
                values = text.split()
                try:
                    class_id = int(values[0]); coords = [float(v) for v in values[1:]]
                    if len(values) != 5 or not 0 <= class_id < 32 or any(v < 0 or v > 1 for v in coords) or coords[2] <= 0 or coords[3] <= 0:
                        raise ValueError
                except Exception:
                    errors.append(f"invalid_active_yolo_label:{label.name}:{line_number}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        errors = validate_layout()
        print(json.dumps({"errors": errors}, indent=2))
        return int(bool(errors))
    verification = json.loads((ROOT / "reports/PHASE4B_BACKUP_VERIFICATION.json").read_text(encoding="utf-8"))
    if not verification.get("verified"):
        raise RuntimeError("Do not migrate before a fully SHA-verified backup exists.")
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    ensure_split_dirs()
    result = migrate(inventory)
    errors = validate_layout()
    print(json.dumps({**result, "validation_errors": errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
