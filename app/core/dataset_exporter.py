from __future__ import annotations

import csv
import hashlib
import json
import shutil
import zipfile
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.core.database import Database


POLICY_PATH = Path(__file__).resolve().parents[2] / "data" / "models" / "yolo_class_policy.json"
TAXONOMY_VERSION = "newassetapp-phase3-review-v1"
DEFAULT_PROPORTIONS = (0.8, 0.1, 0.1)
GLOBAL_SPLIT_FAMILY = "source_split_v1"


def _version() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _load_policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def _export_root(root: Path, family: str, version: str) -> Path:
    target = root / f"{family}_{version}"
    target.mkdir(parents=True, exist_ok=False)
    return target


def _copy_verified(source: Path, destination: Path, expected_hash: str):
    if not source.is_file():
        raise FileNotFoundError(source)
    digest = _file_hash(source)
    if digest != expected_hash:
        raise ValueError(f"Source image changed since human review: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _zip_dataset(root: Path) -> Path:
    archive = root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(root.parent))
    return archive


def export_yolo_dataset(database: Database, output_dir: Path | str, *, seed: int = 42,
                        proportions: tuple[float, float, float] = DEFAULT_PROPORTIONS,
                        source_roots: list[Path | str] | None = None,
                        new_split: bool = False) -> dict:
    target_records = database.current_training_examples("yolo_detector")
    target_registry = None
    if target_records:
        registry_path = Path(__file__).resolve().parents[2] / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
        target_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        classes = target_registry["classes"]
        class_ids = [int(row["id"]) for row in classes]
        id_map = {class_id: index for index, class_id in enumerate(class_ids)}
        names = [row["name"] for row in classes]
        records = target_records
    else:
        policy = _load_policy()
        active = [row for row in policy["classes"] if row["status"] == "active"]
        class_ids = [int(row["class_id"]) for row in active]
        id_map = {legacy_id: new_id for new_id, legacy_id in enumerate(class_ids)}
        names = [row["name"] for row in active]
        records = database.reviewed_training_records("yolo")
    if new_split:
        database.clear_split_assignments(GLOBAL_SPLIT_FAMILY)
    selected_roots = [Path(item).resolve() for item in source_roots or []]
    version = _version()
    root = _export_root(Path(output_dir), "yolo_dataset", version)
    for split_name in ("train", "val", "test"):
        (root / "images" / split_name).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split_name).mkdir(parents=True, exist_ok=True)
    grouped: dict[str, dict] = {}
    rejected = []
    for record in records:
        is_target_record = target_registry is not None
        payload = (None if is_target_record else json.loads(record["corrected_payload_json"]))
        source = Path(record["source_path"])
        if selected_roots and not any(source == base or base in source.parents for base in selected_roots):
            rejected.append({"record_id": record["id"], "reason": "outside_selected_source_roots"})
            continue
        key = record["source_sha256"]
        if payload and payload.get("no_objects") is True:
            group = grouped.setdefault(key, {"source": source, "hash": key, "boxes": [], "record_ids": []})
            group["record_ids"].append(record["id"])
            continue
        bbox = record.get("crop_bbox_xyxy") if is_target_record else payload.get("bbox_xyxy")
        label_id = (next((int(row["id"]) for row in target_registry["classes"]
                          if row["name"] == record["class_label"]), None)
                    if is_target_record else payload.get("class_id"))
        if not isinstance(bbox, list) or len(bbox) != 4 or label_id not in id_map:
            rejected.append({"record_id": record["id"], "reason": "missing_or_unapproved_class_or_box"})
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in bbox)
        except (TypeError, ValueError):
            rejected.append({"record_id": record["id"], "reason": "invalid_box_values"})
            continue
        width, height = int(record["width"] or 0), int(record["height"] or 0)
        if width <= 0 or height <= 0 or not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            rejected.append({"record_id": record["id"], "reason": "box_outside_source_image"})
            continue
        group = grouped.setdefault(key, {"source": source, "hash": key, "boxes": [], "record_ids": []})
        group["boxes"].append((id_map[label_id], x1, y1, x2, y2))
        group["record_ids"].append(record["id"])
    counts = {split: 0 for split in ("train", "val", "test")}
    image_count = annotation_count = 0
    class_distribution = {name: 0 for name in names}
    manifest_rows = []
    for source_hash, item in sorted(grouped.items()):
        source = item["source"]
        split = database.assign_split(GLOBAL_SPLIT_FAMILY, source_hash, seed=seed, proportions=proportions)
        basename = source_hash[:16] + source.suffix.lower()
        image_rel = Path("images") / split / basename
        label_rel = Path("labels") / split / f"{source_hash[:16]}.txt"
        try:
            _copy_verified(source, root / image_rel, source_hash)
        except (OSError, ValueError) as error:
            rejected.extend({"record_id": record_id, "reason": f"source_hash_verification_failed: {error}"}
                            for record_id in item["record_ids"])
            continue
        label_path = root / label_rel
        label_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        with Image.open(source) as image:
            width, height = image.size
        for class_id, x1, y1, x2, y2 in item["boxes"]:
            xc, yc = ((x1 + x2) / 2 / width, (y1 + y2) / 2 / height)
            bw, bh = ((x2 - x1) / width, (y2 - y1) / height)
            lines.append(f"{class_id} {xc:.8f} {yc:.8f} {bw:.8f} {bh:.8f}")
            class_distribution[names[class_id]] += 1
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        counts[split] += 1
        image_count += 1
        annotation_count += len(lines)
        manifest_rows.append({"source_path": str(source), "source_sha256": source_hash,
                              "image": image_rel.as_posix(), "label": label_rel.as_posix(),
                              "split": split, "record_ids": item["record_ids"]})
    (root / "data.yaml").write_text(
        "path: .\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n" +
        "".join(f"  {index}: {name}\n" for index, name in enumerate(names)), encoding="utf-8")
    (root / "class_map.json").write_text(json.dumps({"export_to_original_class_id": {
        str(index): class_ids[index] for index in range(len(class_ids))}, "names": names}, indent=2), encoding="utf-8")
    manifest = {"dataset_type": "yolo", "dataset_version": version,
                "exported_at_utc": datetime.now(timezone.utc).isoformat(), "seed": seed,
                "proportions": proportions, "split_counts": counts, "image_count": image_count,
                "annotation_count": annotation_count, "class_distribution": class_distribution,
                "taxonomy_version": TAXONOMY_VERSION,
                "class_names": names, "source_images": manifest_rows,
                "model_versions": sorted({str(row["model_version"]) for row in records
                                           if "model_version" in row.keys() and row["model_version"]}),
                "class_registry_id": target_registry["registry_id"] if target_registry else None,
                "excluded_records": rejected,
                "human_confirmed_only": True, "source_selection": [str(x) for x in selected_roots] or "all_reviewed_records"}
    (root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "export_report.json").write_text(json.dumps({"included_images": image_count,
        "annotations": annotation_count, "excluded": len(rejected), "split_distribution": counts}, indent=2), encoding="utf-8")
    (root / "README_COLAB.md").write_text(
        "# YOLO dataset for Google Colab\n\n"
        "Upload or mount this ZIP in Colab and unzip it. Install the training library with `pip install ultralytics`.\n"
        "The dataset root contains `data.yaml`, `images/{train,val,test}`, `labels/{train,val,test}`, `class_map.json`, and provenance manifests.\n"
        "The YAML names use dense export IDs; `class_map.json` records each mapping to the original checkpoint class ID.\n"
        "Labels are normalized YOLO xywh. Only explicitly human-confirmed records are present. Inspect `dataset_manifest.json` before training.\n",
        encoding="utf-8")
    archive = _zip_dataset(root)
    return {"version": version, "directory": str(root), "zip": str(archive), **manifest}


def export_cnn_dataset(database: Database, task: str, output_dir: Path | str, *, seed: int = 42,
                       proportions: tuple[float, float, float] = DEFAULT_PROPORTIONS,
                       source_roots: list[Path | str] | None = None,
                       new_split: bool = False) -> dict:
    if task not in {"asset_cnn", "clothing_cnn", "broad_clothing"}:
        raise ValueError("CNN dataset task must be asset_cnn, broad_clothing, or clothing_cnn.")
    family = task
    if task == "asset_cnn":
        records = database.reviewed_training_records(task)
    elif task == "broad_clothing":
        records = database.current_training_examples("clothing_broad")
    else:
        records = database.current_training_examples("clothing_fine")
    records = [dict(record) for record in records]
    if new_split:
        database.clear_split_assignments(GLOBAL_SPLIT_FAMILY)
    if task == "asset_cnn":
        class_map = json.loads((POLICY_PATH.parents[1] / ".." / "models" / "asset_classifier" /
                                "asset_class_map.json").resolve().read_text(encoding="utf-8"))
        allowed_labels = set(class_map)
    elif task == "broad_clothing":
        registry_path = POLICY_PATH.parents[1] / "models" / "clothing_classifier_registry.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        class_names = [row["class_name"] for row in registry.get("classes", []) if row.get("active")]
        class_map_path = POLICY_PATH.parents[1] / "models" / "clothing_classifier_12class_map.json"
        class_map = json.loads(class_map_path.read_text(encoding="utf-8"))
        if len(class_names) != 12 or list(class_map) != class_names or list(class_map.values()) != list(range(12)):
            raise ValueError("Broad Clothing registry and 12-class output mapping disagree.")
        allowed_labels = set(class_names)
    else:
        tags_path = POLICY_PATH.parents[1] / "tags" / "clothing_tags.json"
        tags = json.loads(tags_path.read_text(encoding="utf-8"))
        allowed_labels = {entry.get("serialized_value") for entry in tags.get("entries", [])
                          if entry.get("selectable", False) and not entry.get("requires_review", False)}
        user_tags_path = POLICY_PATH.parents[1] / "tags" / "user_tags.json"
        if user_tags_path.exists():
            user_tags = json.loads(user_tags_path.read_text(encoding="utf-8"))
            allowed_labels.update(entry.get("serialized_value") for entry in user_tags.get("entries", [])
                                  if entry.get("group") == "clothing" and not entry.get("deprecated"))
    selected_roots = [Path(item).resolve() for item in source_roots or []]
    version = _version()
    root = _export_root(Path(output_dir), f"{family}_dataset", version)
    for split_name in ("train", "val", "test"):
        (root / split_name).mkdir(parents=True, exist_ok=True)
    rows, excluded, split_counts, classes, class_distribution = [], [], {s: 0 for s in ("train", "val", "test")}, set(), {}
    for record in records:
        payload = json.loads(record["corrected_payload_json"]) if task == "asset_cnn" else {}
        source = Path(record["source_path"])
        if selected_roots and not any(source == base or base in source.parents for base in selected_roots):
            excluded.append({"record_id": record["id"], "reason": "outside_selected_source_roots"})
            continue
        label = (payload.get("asset_cnn_class") if task == "asset_cnn" else
                 record["class_label"])
        bbox = payload.get("bbox_xyxy") if task == "asset_cnn" else record.get("crop_bbox_xyxy")
        if not label or not isinstance(bbox, list) or len(bbox) != 4:
            excluded.append({"record_id": record["id"], "reason": "missing_reviewed_label_or_box"})
            continue
        if label not in allowed_labels:
            excluded.append({"record_id": record["id"], "reason": "label_not_in_task_taxonomy"})
            continue
        label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(label).strip())
        if not label or label in {".", ".."}:
            excluded.append({"record_id": record["id"], "reason": "invalid_label"})
            continue
        classes.add(label)
        split = database.assign_split(GLOBAL_SPLIT_FAMILY, record["source_sha256"], seed=seed, proportions=proportions)
        width, height = int(record["width"] or 0), int(record["height"] or 0)
        x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
        if width <= 0 or height <= 0 or not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            excluded.append({"record_id": record["id"], "reason": "invalid_crop_box"})
            continue
        crop_rel = Path(split) / label / f"{record['source_sha256'][:12]}_r{record['id']}.png"
        destination = root / crop_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            if _file_hash(source) != record["source_sha256"]:
                excluded.append({"record_id": record["id"], "reason": "source_hash_changed_since_review"})
                continue
            with Image.open(source) as image:
                image.convert("RGB").crop((x1, y1, x2, y2)).save(destination, format="PNG")
        split_counts[split] += 1
        class_distribution[label] = class_distribution.get(label, 0) + 1
        rows.append({"record_id": record["id"], "source_image_id": record["source_image_id"],
                     "source_path": str(source), "source_sha256": record["source_sha256"],
                     "crop": crop_rel.as_posix(), "label": label, "split": split,
                     "bbox_xyxy_source_pixels": [x1, y1, x2, y2],
                     "workflow": record.get("workflow", "professional_review"),
                     "human_confirmed_labels": record.get("human_confirmed_labels", [])})
    with (root / "labels.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["record_id", "source_image_id", "source_path", "source_sha256",
                                                    "crop", "label", "split", "bbox_xyxy_source_pixels",
                                                    "workflow", "human_confirmed_labels"])
        writer.writeheader()
        writer.writerows({**row, "human_confirmed_labels": json.dumps(
            row.get("human_confirmed_labels", []), ensure_ascii=False)} for row in rows)
    if task == "asset_cnn":
        output_class_map = class_map
    elif task == "broad_clothing":
        output_class_map = class_map
    else:
        output_class_map = {name: index for index, name in enumerate(sorted(classes))}
    taxonomy_version = ("clothing-broad-v2-12class" if task == "broad_clothing" else TAXONOMY_VERSION)
    manifest = {"dataset_type": family, "dataset_version": version,
                "exported_at_utc": datetime.now(timezone.utc).isoformat(), "seed": seed,
                "proportions": proportions, "split_counts": split_counts,
                "crop_count": len(rows), "class_names": sorted(classes), "class_map": output_class_map,
                "class_distribution": class_distribution, "taxonomy_version": taxonomy_version,
                "preprocessing": "PIL RGB crop in source-pixel coordinates; model-specific resizing/normalization is deferred to Colab training code.",
                 "model_versions": sorted({str(row.get("taxonomy_version") or row.get("model_version"))
                                            for row in records
                                            if row.get("taxonomy_version") or row.get("model_version")}),
                "human_confirmed_only": True, "source_selection": [str(x) for x in selected_roots] or "all_reviewed_records",
                "crops": rows, "excluded_records": excluded}
    (root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "class_map.json").write_text(json.dumps(output_class_map, indent=2), encoding="utf-8")
    (root / "README_COLAB.md").write_text(
        f"# {family} dataset\n\nUpload or mount the ZIP, unzip it, and read `dataset_manifest.json` and `labels.csv`.\n"
        "All crops are RGB PNG files. Keep source-image hashes together when creating any new split.\n"
        "No NewAssetApp or Girl Packer installation is required. This package contains reviewed records only.\n",
        encoding="utf-8")
    (root / "export_report.json").write_text(json.dumps({
        "crop_count": len(rows), "excluded_record_count": len(excluded),
        "split_distribution": split_counts, "class_distribution": class_distribution,
        "dataset_version": version,
    }, indent=2), encoding="utf-8")
    archive = _zip_dataset(root)
    return {"version": version, "directory": str(root), "zip": str(archive), **manifest}


def export_unified_cnn_dataset(database: Database, output_dir: Path | str, *, seed: int = 42,
                               proportions: tuple[float, float, float] = DEFAULT_PROPORTIONS,
                               source_roots: list[Path | str] | None = None,
                               new_split: bool = False) -> dict:
    """Export only human-confirmed, explicitly eligible labels for the unified model."""
    registry_path = Path(__file__).resolve().parents[2] / "data" / "models" / "unified_body_images_fullbody" / "class_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    records = database.reviewed_unified_cnn_records()
    family = "unified_body_images_fullbody"
    if new_split:
        database.clear_split_assignments(family)
    roots = [Path(item).resolve() for item in source_roots or []]
    version = _version()
    root = _export_root(Path(output_dir), f"{family}_dataset", version)
    for split in ("train", "val", "test"):
        for task in ("body_images", "fullbody_state"):
            (root / split / task).mkdir(parents=True, exist_ok=True)
    rows, excluded = [], []
    split_counts = {split: 0 for split in ("train", "val", "test")}
    class_counts: dict[str, int] = {}
    task_counts = {task: 0 for task in ("body_images", "fullbody_state")}
    groups = {key: {row["class_name"]: row["class_id"] for row in value["classes"]}
              for key, value in registry["output_groups"].items()}
    for record in records:
        payload = json.loads(record["corrected_payload_json"])
        task, label = payload.get("unified_cnn_task"), payload.get("unified_cnn_class")
        source = Path(record["source_path"])
        if roots and not any(source == base or base in source.parents for base in roots):
            excluded.append({"record_id": record["id"], "reason": "outside_selected_source_roots"})
            continue
        if task not in groups or label not in groups.get(task, {}):
            excluded.append({"record_id": record["id"], "reason": "task_label_not_in_unified_registry"})
            continue
        box = payload.get("bbox_xyxy")
        width, height = int(record["width"] or 0), int(record["height"] or 0)
        if not isinstance(box, list) or len(box) != 4 or width <= 0 or height <= 0:
            excluded.append({"record_id": record["id"], "reason": "missing_crop_or_source_dimensions"})
            continue
        x1, y1, x2, y2 = (int(round(float(value))) for value in box)
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            excluded.append({"record_id": record["id"], "reason": "invalid_reviewed_crop_box"})
            continue
        source_hash = str(record["source_sha256"])
        if _file_hash(source) != source_hash:
            excluded.append({"record_id": record["id"], "reason": "source_hash_changed_since_review"})
            continue
        split = database.assign_split(family, source_hash, seed=seed, proportions=proportions)
        relative = Path(split) / task / label / f"{source_hash[:12]}_r{record['id']}.png"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            with Image.open(source) as image:
                image.convert("RGB").crop((x1, y1, x2, y2)).save(destination, format="PNG")
        snapshot = json.loads(record["original_snapshot_json"])
        yolo = snapshot.get("yolo") or {}
        rows.append({"record_id": record["id"], "task": task, "class_id": groups[task][label],
                     "label": label, "source_image_id": record["source_image_id"],
                     "source_path": str(source), "source_sha256": source_hash,
                     "crop": relative.as_posix(), "crop_sha256": _file_hash(destination),
                     "corrected_bbox_xyxy_source_pixels": [x1, y1, x2, y2],
                     "original_yolo_class_id": yolo.get("class_id"),
                     "original_yolo_class_name": yolo.get("class_name"),
                     "original_yolo_bbox_xyxy": [yolo.get(key) for key in ("x1", "y1", "x2", "y2")]
                     if yolo else None,
                     "original_snapshot_json": record["original_snapshot_json"],
                     "human_confirmed": bool(record["human_confirmed"]),
                     "training_eligible": True, "split": split,
                     "taxonomy_version": record["taxonomy_version"], "model_version": record["model_version"]})
        split_counts[split] += 1
        task_counts[task] += 1
        class_key = f"{task}:{label}"
        class_counts[class_key] = class_counts.get(class_key, 0) + 1
    class_maps = {key: {row["class_name"]: row["class_id"] for row in value["classes"]}
                  for key, value in registry["output_groups"].items()}
    manifest = {"dataset_type": family, "dataset_version": version,
                "model_id": registry["model_id"], "checkpoint_identity": registry["checkpoint_identity"],
                "seed": seed, "proportions": proportions, "split_counts": split_counts,
                "task_counts": task_counts, "class_counts": class_counts, "class_maps": class_maps,
                "human_confirmed_only": True, "task_labels_are_separate": True,
                "source_grouping": "source_image_sha256", "crops": rows, "excluded_records": excluded,
                "training_performed": False}
    (root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (root / "class_registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    archive = _zip_dataset(root)
    return {"version": version, "directory": str(root), "zip": str(archive), **manifest}


def export_shared_cnn_head_dataset(database: Database, task_head: str,
                                   output_dir: Path | str, *, seed: int = 42,
                                   proportions: tuple[float, float, float] = DEFAULT_PROPORTIONS,
                                   source_roots: list[Path | str] | None = None,
                                   new_split: bool = False) -> dict:
    """Export current Normal Processing and Professional Review records for one head."""
    registry_path = (Path(__file__).resolve().parents[2] / "data" / "models" /
                     "unified_body_images_fullbody" / "class_registry.json")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    groups = registry.get("output_groups", {})
    if task_head not in {"body_images", "fullbody", "portrait", "arousal", "corruption"}:
        raise ValueError(f"Unsupported shared CNN head: {task_head}")
    group = groups.get(task_head)
    if not group or len(group.get("classes", [])) != int(group.get("class_count", -1)):
        raise ValueError(f"Shared CNN registry is invalid for head {task_head}.")
    classes = {str(row["class_name"]): int(row["class_id"]) for row in group["classes"]}
    task_family = "shared_cnn_source_split_v2"
    if new_split:
        database.clear_split_assignments(task_family)
    roots = [Path(value).resolve() for value in source_roots or []]
    examples = database.current_training_examples(
        task="unified_body_images_fullbody", task_head=task_head)
    excluded: list[dict] = []

    # Explicitly accept only safe legacy Portrait/Fullbody rows whose linked YOLO
    # region proves the task head. Other legacy rows retain their source history
    # and are listed as exclusions instead of being reinterpreted.
    legacy_rows = [row for row in database.current_training_examples(
        task="unified_body_images_fullbody") if row.get("task_head") is None]
    for row in legacy_rows:
        provenance = row.get("suggestion_provenance") or {}
        region = str(provenance.get("reviewed_yolo_class_name")
                     or (provenance.get("yolo") or {}).get("class_name") or "")
        label = str(row.get("class_label") or "")
        eligible_legacy_head = (
            task_head == "portrait" and region == "portrait_frame" and label in {"portrait", "tportrait"}
        ) or (
            task_head == "fullbody" and (region == "fullbody" or region.startswith("fullbody_"))
            and label in classes
        )
        if eligible_legacy_head:
            row = dict(row)
            row["task_head"] = task_head
            row["human_confirmed_labels"] = [label] if task_head == "portrait" else []
            row["legacy_head_mapping"] = True
            examples.append(row)
        elif task_head == "body_images" and label in {"face", "boobs", "ass", "pussy", "legs"}:
            excluded.append({"record_id": f"training_example:{row['id']}",
                             "reason": "body_region_identity_is_yolo_provenance_not_cnn_target",
                             "source_task": row.get("task"), "label": label})

    if task_head == "corruption":
        for row in database.current_corruption_training_examples():
            value = dict(row)
            value["task_head"] = "corruption"
            value["human_confirmed_labels"] = []
            examples.append(value)
    selected: dict[tuple, dict] = {}
    for row in examples:
        source = Path(row["source_path"])
        label = str(row.get("class_label") or "")
        provenance = row.get("suggestion_provenance") or {}
        region = str(provenance.get("reviewed_yolo_class_name")
                     or (provenance.get("yolo") or {}).get("class_name") or "")
        if roots and not any(source == root or root in source.parents for root in roots):
            excluded.append({"record_id": str(row["id"]), "reason": "outside_selected_source_roots"})
            continue
        if label not in classes:
            excluded.append({"record_id": str(row["id"]), "reason": "label_not_in_task_head_registry",
                             "label": label})
            continue
        if task_head == "body_images" and region not in {"face", "boobs", "ass", "pussy", "legs"}:
            excluded.append({"record_id": str(row["id"]), "reason": "body_images_head_requires_yolo_body_region"})
            continue
        if task_head == "portrait" and region != "portrait_frame":
            excluded.append({"record_id": str(row["id"]), "reason": "portrait_head_requires_yolo_portrait_frame"})
            continue
        fullbody_region = region == "fullbody" or region.startswith("fullbody_")
        if task_head == "fullbody" and not fullbody_region:
            excluded.append({"record_id": str(row["id"]), "reason": "fullbody_head_requires_yolo_fullbody_region"})
            continue
        if task_head in {"arousal", "corruption"} and not (
                region in {"person", "portrait_frame"} or fullbody_region):
            excluded.append({"record_id": str(row["id"]), "reason": f"{task_head}_head_region_not_supported"})
            continue
        bbox = row.get("crop_bbox_xyxy")
        width, height = int(row.get("width") or 0), int(row.get("height") or 0)
        if not isinstance(bbox, list) or len(bbox) != 4 or width <= 0 or height <= 0:
            excluded.append({"record_id": str(row["id"]), "reason": "missing_crop_geometry"})
            continue
        source_hash = str(row.get("source_sha256") or "")
        if not source.is_file() or _file_hash(source) != source_hash:
            excluded.append({"record_id": str(row["id"]), "reason": "source_hash_verification_failed"})
            continue
        x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            excluded.append({"record_id": str(row["id"]), "reason": "invalid_crop_geometry"})
            continue
        key = (source_hash, tuple((x1, y1, x2, y2)), label,
               json.dumps(row.get("human_confirmed_labels", []), sort_keys=True))
        selected.setdefault(key, {**row, "bbox_int": [x1, y1, x2, y2], "yolo_region": region})

    if not selected:
        raise ValueError(f"No current, human-confirmed records are eligible for the {task_head} head.")

    version = _version()
    root = _export_root(Path(output_dir), f"{task_head}_cnn_dataset", version)
    counts = {split: 0 for split in ("train", "val", "test")}
    rows = []
    for index, row in enumerate(selected.values()):
        split = database.assign_split(task_family, row["source_sha256"], seed=seed,
                                      proportions=proportions)
        x1, y1, x2, y2 = row["bbox_int"]
        relative = Path(split) / str(row["class_label"]) / f"{row['source_sha256'][:12]}_r{row['id']}.png"
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(row["source_path"]) as image:
            crop = image.convert("RGB").crop((x1, y1, x2, y2))
            crop.save(destination, format="PNG")
        rows.append({
            "record_id": str(row["id"]), "task_head": task_head,
            "class_id": classes[row["class_label"]], "class_label": row["class_label"],
            "human_confirmed_labels": row.get("human_confirmed_labels", []),
            "source_workflow": row.get("workflow"), "source_image_id": str(row["source_image_id"]),
            "source_path": str(row["source_path"]), "source_sha256": row["source_sha256"],
            "crop": relative.as_posix(), "crop_sha256": _file_hash(destination),
            "coordinate_space": "source_pixels", "crop_bbox_xyxy": row["bbox_int"],
            "yolo_region_identity": row.get("yolo_region"),
            "human_confirmed": bool(row.get("human_confirmed")),
            "training_eligible": bool(row.get("training_eligible")),
            "taxonomy_id": row.get("taxonomy_id"), "taxonomy_version": row.get("taxonomy_version"),
        })
        counts[split] += 1
    manifest = {
        "dataset_type": "shared_cnn_head", "model_id": registry["model_id"],
        "checkpoint_identity": registry["checkpoint_identity"],
        "head": task_head, "registry_id": "newassetapp_unified_body_images_fullbody",
        "registry_version": registry["version"],
        "class_map": classes, "seed": seed, "proportions": proportions,
        "split_counts": counts, "human_confirmed_only": True, "training_performed": False,
        "source_selection": [str(value) for value in roots] or "all_current_confirmed_records",
        "records": rows, "excluded_records": excluded,
    }
    (root / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                                 encoding="utf-8")
    archive = _zip_dataset(root)
    return {"version": version, "directory": str(root), "zip": str(archive), **manifest}
