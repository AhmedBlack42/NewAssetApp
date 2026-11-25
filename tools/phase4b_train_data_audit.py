from __future__ import annotations

import collections
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TRAIN_ROOT = ROOT / "train_data"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def role(path: Path) -> str:
    parts = path.relative_to(TRAIN_ROOT).parts
    ext = path.suffix.lower()
    if "YOLO_Project" in parts:
        if "images" in parts:
            return "yolo_image"
        if "labels" in parts:
            return "yolo_label_cache_or_annotation" if ext in {".cache", ".txt"} else "yolo_label_artifact"
        if "runs" in parts:
            return "yolo_run_artifact"
        return "yolo_configuration_or_checkpoint"
    if "asset_classifier_data" in parts:
        return "cnn_class_image" if ext in IMAGE_EXTENSIONS else "cnn_dataset_metadata"
    if ext in {".pt", ".pth"}:
        return "checkpoint"
    if ext in IMAGE_EXTENSIONS:
        return "unclassified_image_or_crop"
    if ext in {".yaml", ".yml", ".json", ".txt", ".csv"}:
        return "metadata_or_annotation"
    if ext == ".py":
        return "source_code"
    return "other"


def validate_yolo() -> dict:
    dataset = TRAIN_ROOT / "YOLO_Project" / "dataset"
    names_path = dataset / "classes.txt"
    names = names_path.read_text(encoding="utf-8-sig").splitlines()
    splits: dict[str, dict] = {}
    class_counts: collections.Counter[int] = collections.Counter()
    image_hashes: dict[str, list[str]] = collections.defaultdict(list)
    invalid_all = []
    for split in ("train", "val", "test"):
        image_dir, label_dir = dataset / "images" / split, dataset / "labels" / split
        images = sorted(p for p in image_dir.glob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS) if image_dir.exists() else []
        labels = sorted(label_dir.glob("*.txt")) if label_dir.exists() else []
        image_stems = {p.stem: p for p in images}
        label_stems = {p.stem: p for p in labels}
        invalid = []
        annotation_count = 0
        for image in images:
            image_hashes[sha256(image)].append(image.relative_to(ROOT).as_posix())
        for stem, label in label_stems.items():
            if stem not in image_stems:
                continue
            for line_number, raw in enumerate(label.read_text(encoding="utf-8-sig").splitlines(), 1):
                if not raw.strip():
                    continue
                annotation_count += 1
                values = raw.split()
                try:
                    if len(values) != 5:
                        raise ValueError("expected 5 fields")
                    class_id = int(values[0])
                    x, y, width, height = map(float, values[1:])
                    if not 0 <= class_id < len(names):
                        raise ValueError(f"class_id_out_of_range:{class_id}")
                    if any(value < 0 or value > 1 for value in (x, y, width, height)) or width <= 0 or height <= 0:
                        raise ValueError("invalid_normalized_xywh")
                    class_counts[class_id] += 1
                except Exception as error:
                    invalid.append({"label_path": label.relative_to(ROOT).as_posix(), "line": line_number,
                                    "reason": str(error), "text": raw})
        invalid_all.extend(invalid)
        splits[split] = {
            "image_count": len(images), "label_file_count": len(labels),
            "missing_label_stems": sorted(set(image_stems) - set(label_stems)),
            "orphan_label_stems": sorted(set(label_stems) - set(image_stems)),
            "annotation_count": annotation_count, "valid_annotation_count": annotation_count - len(invalid),
            "invalid_annotations": invalid,
        }
    return {"class_names": names, "class_count": len(names), "splits": splits,
            "annotation_class_counts": {str(key): value for key, value in sorted(class_counts.items())},
            "duplicate_image_hash_groups": [paths for paths in image_hashes.values() if len(paths) > 1],
            "invalid_annotation_count": len(invalid_all)}


def build_inventory() -> dict:
    if not TRAIN_ROOT.is_dir():
        raise FileNotFoundError(TRAIN_ROOT)
    files = []
    extensions: collections.Counter[str] = collections.Counter()
    roles: collections.Counter[str] = collections.Counter()
    top_levels: collections.Counter[str] = collections.Counter()
    class_counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for path in sorted(item for item in TRAIN_ROOT.rglob("*") if item.is_file()):
        relative = path.relative_to(TRAIN_ROOT).as_posix()
        digest = sha256(path)
        file_role = role(path)
        row = {"path": relative, "size_bytes": path.stat().st_size, "sha256": digest,
               "extension": path.suffix.lower(), "role": file_role}
        files.append(row)
        extensions[row["extension"]] += 1
        roles[file_role] += 1
        top_levels[relative.split("/")[0]] += 1
        parts = Path(relative).parts
        if file_role == "cnn_class_image" and "asset_classifier_data" in parts:
            index = parts.index("asset_classifier_data")
            if len(parts) > index + 2 and parts[index + 1] in {"train", "val", "test"}:
                class_counts[parts[index + 1]][parts[index + 2]] += 1
    return {
        "inventory_version": 1,
        "root": "train_data",
        "files": files,
        "summary": {
            "file_count": len(files),
            "directory_count": sum(1 for path in TRAIN_ROOT.rglob("*") if path.is_dir()),
            "total_bytes": sum(row["size_bytes"] for row in files),
            "by_top_level": dict(top_levels),
            "by_extension": dict(extensions),
            "by_role": dict(roles),
        },
        "cnn_class_counts": {split: dict(sorted(counts.items())) for split, counts in class_counts.items()},
        "cnn_class_map": json.loads((TRAIN_ROOT / "cnn_train" / "asset_class_map.json").read_text(encoding="utf-8")),
        "yolo": validate_yolo(),
    }


def verify_tree(tree_root: Path, inventory_path: Path, output_name: str, tree_label: str) -> dict:
    tree_root = tree_root.resolve()
    inventory_path = inventory_path.resolve()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    checked = 0
    missing = []
    mismatches = []
    expected_paths = {row["path"] for row in inventory["files"]}
    source_roots = {Path(path).parts[0] for path in expected_paths}
    for row in inventory["files"]:
        copied = tree_root / Path(row["path"])
        if not copied.is_file():
            missing.append(row["path"])
            continue
        checked += 1
        digest = sha256(copied)
        if digest != row["sha256"]:
            mismatches.append({"path": row["path"], "expected": row["sha256"], "actual": digest})
    actual_paths = {path.relative_to(tree_root).as_posix() for path in tree_root.rglob("*") if path.is_file()}
    unexpected = sorted(path for path in actual_paths - expected_paths
                        if Path(path).parts and Path(path).parts[0] in source_roots)
    generated_count = len(actual_paths - expected_paths) - len(unexpected)
    result = {"tree_root": str(tree_root.relative_to(ROOT)), "tree_label": tree_label, "source_inventory": str(inventory_path.relative_to(ROOT)),
              "expected_files": len(inventory["files"]), "checked_files": checked,
              "missing_files": missing, "unexpected_source_files": unexpected,
              "generated_or_migrated_files_ignored": generated_count, "hash_mismatches": mismatches,
              "verified": not missing and not unexpected and not mismatches and checked == len(inventory["files"])}
    (ROOT / "reports" / output_name).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def audit_images(inventory_path: Path) -> dict:
    inventory_path = inventory_path.resolve()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    rows = [row for row in inventory["files"] if row["role"] in {"cnn_class_image", "yolo_image"}]
    unreadable = []
    for row in rows:
        path = TRAIN_ROOT / Path(row["path"])
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as error:
            unreadable.append({"path": row["path"], "error": str(error)})
    grouped: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        parts = Path(row["path"]).parts
        if "asset_classifier_data" in parts:
            index = parts.index("asset_classifier_data")
            if len(parts) >= index + 4 and parts[index + 1] in {"train", "val", "test"}:
                grouped[row["sha256"]].append({"path": row["path"], "split": parts[index + 1], "class": parts[index + 2]})
    duplicate_groups = [items for items in grouped.values() if len(items) > 1]
    cross_split = [items for items in duplicate_groups if len({item["split"] for item in items}) > 1]
    body_names = {"bodypart_ass", "bodypart_boobs", "bodypart_face", "bodypart_legs",
                  "bodypart_portrait_clothed", "bodypart_portrait_topless", "bodypart_pussy"}
    body_groups = [items for items in duplicate_groups if any(item["class"] in body_names for item in items)]
    result = {"image_file_count": len(rows), "readable_count": len(rows) - len(unreadable),
              "unreadable": unreadable, "cnn_duplicate_hash_groups": duplicate_groups,
              "cnn_cross_split_duplicate_groups": cross_split,
              "body_images_duplicate_groups": body_groups,
              "body_images_cross_split_duplicate_groups": [items for items in body_groups if len({item["split"] for item in items}) > 1]}
    (ROOT / "reports" / "PHASE4B_IMAGE_QUALITY.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-backup", type=Path)
    parser.add_argument("--verify-source", action="store_true")
    parser.add_argument("--audit-images", action="store_true")
    args = parser.parse_args()
    if args.audit_images:
        result = audit_images(ROOT / "reports" / "PHASE4B_PRE_MIGRATION_INVENTORY.json")
        print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in result.items()}, indent=2))
        raise SystemExit(1 if result["unreadable"] else 0)
    if args.verify_backup:
        result = verify_tree(args.verify_backup, ROOT / "reports" / "PHASE4B_PRE_MIGRATION_INVENTORY.json", "PHASE4B_BACKUP_VERIFICATION.json", "backup")
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["verified"] else 1)
    if args.verify_source:
        result = verify_tree(TRAIN_ROOT, ROOT / "reports" / "PHASE4B_PRE_MIGRATION_INVENTORY.json", "PHASE4B_SOURCE_PRESERVATION_VERIFICATION.json", "original_source")
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["verified"] else 1)
    inventory = build_inventory()
    output = ROOT / "reports" / "PHASE4B_PRE_MIGRATION_INVENTORY.json"
    output.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(json.dumps({"summary": inventory["summary"], "cnn_class_counts": inventory["cnn_class_counts"],
                      "yolo": {"class_count": inventory["yolo"]["class_count"],
                               "splits": inventory["yolo"]["splits"],
                               "annotation_class_counts": inventory["yolo"]["annotation_class_counts"],
                               "duplicate_image_hash_groups": len(inventory["yolo"]["duplicate_image_hash_groups"]),
                               "invalid_annotation_count": inventory["yolo"]["invalid_annotation_count"]}}, indent=2))
