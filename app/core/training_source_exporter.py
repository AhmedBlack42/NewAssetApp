from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

from app.core.database import Database, SCHEMA_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRAINING_SOURCE_ROOT = PROJECT_ROOT / "training_source"

_TASKS = {
    "yolo_detector": {
        "bundle_task": "yolo_detection",
        "model_id": "newassetapp_yolo_detector_v1",
        "registry_id": "newassetapp_yolo_detector_v1",
        "version": "1",
        "registry_path": Path("TrainingDatasetStudio/registries/yolo_detector_v1.json"),
    },
    "unified_body_images_fullbody": {
        "bundle_task": "asset_classification",
        "model_id": "unified_body_images_fullbody_cnn",
        "registry_id": "newassetapp_unified_body_images_fullbody",
        "version": "v2_five_head_shared_backbone_untrained",
        "registry_path": Path("data/models/unified_body_images_fullbody/class_registry.json"),
    },
    **{
        head: {
            "bundle_task": bundle_task,
            "model_id": "unified_body_images_fullbody_cnn",
            "registry_id": "newassetapp_unified_body_images_fullbody",
            "version": "v2_five_head_shared_backbone_untrained",
            "registry_path": Path("data/models/unified_body_images_fullbody/class_registry.json"),
            "head": head,
        }
        for head, bundle_task in {
            "body_images": "body_images_classification",
            "fullbody": "fullbody_state_classification",
            "portrait": "portrait_classification",
            "arousal": "arousal_classification",
            "corruption": "corruption_classification",
        }.items()
    },
    "clothing_broad": {
        "bundle_task": "clothing_classification",
        "model_id": "clothing_classifier",
        "registry_id": "clothing_classifier",
        "version": "clothing-broad-v2-12class",
        "registry_path": Path("data/models/clothing_classifier_registry.json"),
    },
    "clothing_fine": {
        "bundle_task": "clothing_classification",
        "model_id": "newassetapp_detailed_clothing_classifier",
        "registry_id": "newassetapp_detailed_clothing_v1",
        "version": "1.0.0",
        "registry_path": Path("data/tags/clothing_tags.json"),
    },
    "corruption_state": {
        "bundle_task": "corruption_classification",
        "model_id": "newassetapp_corruption_state_cnn",
        "registry_id": "newassetapp_corruption_state_v1",
        "version": "1.0.0",
        "registry_path": Path("data/models/corruption_state_classifier/class_registry.json"),
    },
}

# Region identity belongs to the detector. Historical unified-CNN rows carrying
# these labels are retained as excluded records; they are never converted into
# YOLO targets because a crop classification does not confirm a detector box.
_YOLO_BODY_IDENTITY_LABELS = {"face", "boobs", "ass", "pussy", "legs"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _iso_utc(value: str | None = None) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).isoformat()


def _registry_classes(raw: dict, task: str) -> set[str]:
    if task == "yolo_detector":
        return {str(item["name"]) for item in raw.get("classes", [])}
    if task in {"body_images", "fullbody", "portrait", "arousal", "corruption"}:
        labels = {str(item["class_name"])
                for item in raw.get("output_groups", {}).get(task, {}).get("classes", [])}
        if task == "body_images":
            labels.update({"body_images_multi_label", "body_images_none", "body_images_pending"})
        return labels
    if task == "unified_body_images_fullbody":
        return set()
    if task == "clothing_broad":
        return {str(item["class_name"]) for item in raw.get("classes", []) if item.get("active")}
    if task == "clothing_fine":
        return {str(item["serialized_value"]) for item in raw.get("entries", [])
                if item.get("selectable") and not item.get("requires_review")
                and item.get("serialized_value")}
    if task == "corruption_state":
        return {str(item["class_name"]) for item in raw.get("classes", [])}
    return set()


def _task_context(task: str, label: str, raw_registry: dict) -> str | None:
    if task in {"body_images", "fullbody", "portrait", "arousal", "corruption"}:
        return task
    return {
        "clothing_broad": "broad_family",
        "clothing_fine": "detailed_type",
        "corruption_state": "corruption_state",
    }.get(task)


def _bundle_task(task: str, output_group: str | None = None) -> str:
    if task == "yolo_detector":
        return "yolo_detection"
    if task == "unified_body_images_fullbody":
        if output_group is None:
            return "unified_classification_unresolved"
        return ("body_images_classification" if output_group == "body_images"
                else "fullbody_state_classification")
    return {
        "body_images": "body_images_classification",
        "fullbody": "fullbody_state_classification",
        "portrait": "portrait_classification",
        "arousal": "arousal_classification",
        "corruption": "corruption_classification",
        "clothing_broad": "broad_clothing_classification",
        "clothing_fine": "detailed_clothing_classification",
        "corruption_state": "corruption_state_classification",
    }.get(task, task)


def _registry_class_id(raw_registry: dict, task: str, output_group: str | None,
                       label: str) -> int | None:
    if task in {"body_images", "fullbody", "portrait", "arousal", "corruption"}:
        rows = raw_registry.get("output_groups", {}).get(task, {}).get("classes", [])
        if task == "body_images" and label.startswith("body_images_"):
            return None
        return next((int(row["class_id"]) for row in rows
                     if row.get("class_name") == label and row.get("class_id") is not None), None)
    if task == "yolo_detector":
        rows = raw_registry.get("classes", [])
        key = "id"
    elif task in {"clothing_broad", "corruption_state"}:
        rows = raw_registry.get("classes", [])
        key = "class_id"
    elif task == "clothing_fine":
        rows = raw_registry.get("entries", [])
        key = "class_id"
    else:
        return None
    return next((int(row[key]) for row in rows
                 if row.get("name", row.get("class_name", row.get("serialized_value"))) == label
                 and row.get(key) is not None), None)


def _valid_bbox(value, width: int, height: int) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        box = [float(item) for item in value]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in box):
        return None
    if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
        return None
    return box


def _map_confirmed_body_identity_to_yolo(database: Database, item: dict) -> tuple[bool, str | None]:
    """Validate the historical Normal Processing identity row before task remapping."""
    label = str(item.get("class_label") or "")
    if label not in _YOLO_BODY_IDENTITY_LABELS:
        return False, None
    provenance = item.get("suggestion_provenance") or {}
    predicted = provenance.get("yolo") if isinstance(provenance, dict) else None
    if not isinstance(predicted, dict):
        return False, "body_identity_missing_yolo_provenance"
    try:
        with database.connect() as connection:
            row = connection.execute(
                """SELECT d.id,d.source_image_id,d.class_id,d.class_name,d.model_id,d.model_digest,
                          d.confidence,d.x1,d.y1,d.x2,d.y2,d.status,
                          p.corrected_bbox_json,n.category normal_category,n.main_tag normal_main_tag
                   FROM yolo_detections d JOIN asset_proposals p ON p.detection_id=d.id
                   LEFT JOIN normal_crop_choices n ON n.proposal_id=p.id
                   WHERE d.id=? AND p.id=? AND d.source_image_id=?""",
                (int(item.get("detection_id") or 0), int(item.get("proposal_id") or 0),
                 int(item.get("source_image_id") or 0)),
            ).fetchone()
        if not row:
            return False, "body_identity_missing_linked_yolo_detection"
        detection = dict(row)
        registry_path = PROJECT_ROOT / _TASKS["yolo_detector"]["registry_path"]
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        target_class = next((entry for entry in registry.get("classes", [])
                             if str(entry.get("name")) == label), None)
        if not target_class:
            return False, "body_identity_missing_yolo_target_class"
        if (detection["normal_category"] != "body_images"
                or detection["normal_main_tag"] != label
                or not item.get("human_confirmed") or not item.get("training_eligible")):
            return False, "body_identity_lacks_human_confirmed_region_label"
        if (detection["class_name"] != label
                or int(detection["class_id"]) != int(target_class["id"])
                or int(predicted.get("class_id", -1)) != int(detection["class_id"])
                or predicted.get("class_name") != detection["class_name"]
                or predicted.get("model_id") != detection["model_id"]
                or predicted.get("model_digest") != detection["model_digest"]):
            return False, "body_identity_yolo_prediction_or_registry_mismatch"
        original_bbox = [detection[key] for key in ("x1", "y1", "x2", "y2")]
        target_bbox = item.get("crop_bbox_xyxy")
        corrected_bbox = json.loads(detection["corrected_bbox_json"] or "null")
        expected_target = corrected_bbox or original_bbox
        if _valid_bbox(original_bbox, int(item.get("width") or 0), int(item.get("height") or 0)) is None:
            return False, "body_identity_invalid_original_yolo_bbox"
        validated_target = _valid_bbox(target_bbox, int(item.get("width") or 0),
                                       int(item.get("height") or 0))
        if validated_target is None or any(abs(a - b) > 1e-4 for a, b in zip(validated_target, expected_target)):
            return False, "body_identity_target_bbox_does_not_match_reviewed_geometry"
        item["_source_task"] = item["task"]
        item["_task_mapping"] = {
            "source_task": item["task"],
            "source_record_id": item.get("_record_id"),
            "mapping": "human_confirmed_body_region_identity_to_yolo_detection",
            "reason": "YOLO owns body-part identity; the human-confirmed region label matches the linked YOLO class.",
        }
        updated = dict(predicted)
        updated["original_bbox_xyxy"] = original_bbox
        updated["detection_status"] = detection["status"]
        item["suggestion_provenance"] = dict(provenance)
        item["suggestion_provenance"]["yolo"] = updated
        item["task"] = "yolo_detector"
        item["class_label"] = label
        item["taxonomy_id"] = _TASKS["yolo_detector"]["registry_id"]
        item["taxonomy_version"] = _TASKS["yolo_detector"]["version"]
        item["_task_spec"] = _TASKS["yolo_detector"]
        return True, None
    except (OSError, ValueError, TypeError, KeyError):
        return False, "body_identity_annotation_validation_failed"


def _record_rows(database: Database) -> tuple[list[dict], list[dict]]:
    eligible: list[dict] = []
    excluded: list[dict] = []
    for row in database.current_training_examples(include_stale_media=True):
        item = dict(row)
        if item.get("_training_block_reason"):
            excluded.append({
                "record_id": f"training_example:{item.get('id')}",
                "task": str(item.get("task_head") or item.get("task")),
                "reason": item["_training_block_reason"],
            })
            continue
        source_task = str(item.get("task"))
        task = str(item.get("task_head") or source_task)
        provenance = item.get("suggestion_provenance") or {}
        yolo_provenance = provenance.get("yolo") if isinstance(provenance, dict) else {}
        yolo_region = str(provenance.get("reviewed_yolo_class_name")
                          or (yolo_provenance or {}).get("class_name") or "")
        if source_task == "unified_body_images_fullbody" and not item.get("task_head"):
            label = str(item.get("class_label") or "")
            if label in _YOLO_BODY_IDENTITY_LABELS:
                task = "body_images"
                item["_forced_exclusion_reason"] = "body_region_identity_is_yolo_provenance_not_cnn_target"
                item["_forced_bundle_task"] = "body_images_classification"
            elif label in {"portrait", "tportrait"} and yolo_region == "portrait_frame":
                task = "portrait"
                item["_task_mapping"] = {
                    "source_task": source_task,
                    "source_record_id": f"training_example:{item.get('id')}",
                    "mapping": "confirmed_portrait_frame_classification_to_portrait_head",
                    "reason": "Human-confirmed portrait label and linked YOLO portrait_frame region.",
                }
            elif label in {"clothed", "topless", "bottomless", "bra", "panty"} and (
                    yolo_region == "fullbody" or yolo_region.startswith("fullbody_")):
                task = "fullbody"
                item["_task_mapping"] = {
                    "source_task": source_task,
                    "source_record_id": f"training_example:{item.get('id')}",
                    "mapping": "confirmed_fullbody_target_to_fullbody_head",
                    "reason": "Human-confirmed Fullbody target and linked YOLO Fullbody region.",
                }
            else:
                item["_forced_exclusion_reason"] = "legacy_shared_cnn_record_has_no_verified_head_identity"
                item["_forced_bundle_task"] = "unified_classification_unresolved"
        if task == "unified_body_images_fullbody" and str(item.get("class_label")) in _YOLO_BODY_IDENTITY_LABELS:
            # Keep the historical task and label in provenance, but quarantine
            # it from model targets. A human body-region choice is not a YOLO
            # annotation confirmation, and must not be silently remapped.
            item["_forced_exclusion_reason"] = "body_region_identity_is_yolo_provenance_not_cnn_target"
            item["_source_task"] = source_task
            item["_forced_bundle_task"] = "body_images_classification"
        spec = _TASKS.get(task)
        if not spec:
            excluded.append({"record_id": f"training_example:{item.get('id')}",
                             "task": task, "reason": "unsupported_training_task"})
            continue
        item["_source_task"] = source_task
        item["_source_table"] = "training_examples"
        item["_original_task"] = source_task
        item["task"] = task
        item["_record_id"] = f"training_example:{item['id']}"
        item["_task_spec"] = spec
        eligible.append(item)
    for row in database.current_corruption_training_examples(include_stale_media=True):
        item = dict(row)
        if item.get("_training_block_reason"):
            excluded.append({
                "record_id": f"corruption_training_example:{item.get('id')}",
                "task": "corruption_state_classification",
                "reason": item["_training_block_reason"],
            })
            continue
        item["_source_table"] = "corruption_training_examples"
        item["_record_id"] = f"corruption_training_example:{item['id']}"
        item["_source_task"] = "corruption_state"
        item["_original_task"] = "corruption_state"
        item["_task_mapping"] = {
            "source_task": "corruption_state",
            "mapping": "legacy_corruption_record_to_shared_corruption_head",
            "reason": "The existing human-confirmed corruption target is retained under the shared backbone head.",
        }
        item["_task_spec"] = _TASKS["corruption"]
        item["task"] = "corruption"
        eligible.append(item)

    # Explicit manual background annotations have no box and therefore do not
    # live in training_examples. Keep them as YOLO negative-image records.
    for row in database.reviewed_training_records("yolo"):
        item = dict(row)
        corrected = json.loads(item.get("corrected_payload_json") or "{}")
        if corrected.get("no_objects") is not True:
            continue
        original = json.loads(item.get("original_snapshot_json") or "{}")
        item.update({
            "_record_id": f"correction_record:{item['id']}",
            "_source_table": "correction_records",
            "_source_task": "yolo_detector",
            "_original_task": "yolo_detector",
            "_task_spec": _TASKS["yolo_detector"],
            "task": "yolo_detector",
            "class_label": "__empty__",
            "taxonomy_id": _TASKS["yolo_detector"]["registry_id"],
            "taxonomy_version": _TASKS["yolo_detector"]["version"],
            "crop_bbox_xyxy": None,
            "suggestion_provenance": {"yolo": original.get("yolo"),
                                       "manual_annotation": {"no_objects": True}},
            "workflow": "professional_review",
            "human_confirmed": True,
            "training_eligible": True,
            "_empty_yolo": True,
        })
        eligible.append(item)

    deduplicated: dict[tuple, dict] = {}
    for item in eligible:
        key = (item["task"], item.get("source_sha256"), item.get("proposal_id"),
               item.get("class_label"), json.dumps(item.get("crop_bbox_xyxy"), sort_keys=True))
        deduplicated.setdefault(key, item)
    if len(deduplicated) != len(eligible):
        kept_ids = {id(item) for item in deduplicated.values()}
        for item in eligible:
            if id(item) not in kept_ids:
                excluded.append({"record_id": item["_record_id"],
                                 "task": item["_task_spec"]["bundle_task"],
                                 "reason": "duplicate_current_training_record"})
    return list(deduplicated.values()), excluded


def export_training_source_bundle(database: Database,
                                  output_root: Path | str | None = None) -> dict:
    """Write one immutable import bundle for TrainingDatasetStudio.

    Only current, human-confirmed, training-eligible database records are candidates.
    Source images are copied once by content hash; CNN/YOLO crop geometry remains in
    the manifest so Studio can prepare task-specific datasets independently.
    """
    source_root = Path(output_root) if output_root else DEFAULT_TRAINING_SOURCE_ROOT / "bundles"
    source_root = source_root.resolve()
    source_root.mkdir(parents=True, exist_ok=True)
    candidates, excluded = _record_rows(database)
    staging = Path(tempfile.mkdtemp(prefix=".staging_", dir=source_root))
    try:
        registries: dict[str, dict] = {}
        allowed_labels: dict[tuple[str, str], set[str]] = {}
        raw_registries: dict[str, dict] = {}
        for item in candidates:
            spec = item["_task_spec"]
            registry_id = spec["registry_id"]
            if registry_id not in registries:
                path = PROJECT_ROOT / spec["registry_path"]
                raw = json.loads(path.read_text(encoding="utf-8"))
                registry_bytes = path.read_bytes()
                relative = Path("registries") / f"{registry_id}_v{spec['version']}.json"
                relative = Path(str(relative).replace(":", "_").replace(" ", "_"))
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(registry_bytes)
                registries[registry_id] = {
                    "id": registry_id,
                    "version": str(spec["version"]),
                    "sha256": hashlib.sha256(registry_bytes).hexdigest(),
                    "relative_path": relative.as_posix(),
                }
                raw_registries[registry_id] = raw
            allowed_labels[(registry_id, item["task"])] = _registry_classes(
                raw_registries[registry_id], item["task"])

        records: list[dict] = []
        source_media: dict[str, dict] = {}
        crop_media: dict[str, dict] = {}
        correction_rows: dict[int, dict] = {}
        correction_history: dict[int, list[dict]] = {}
        bbox_review_rows: dict[int, dict] = {}
        with database.connect() as connection:
            if "correction_record_id" in {row["name"] for row in
                                          connection.execute("PRAGMA table_info(training_examples)")}:
                ids = sorted({int(item["correction_record_id"]) for item in candidates
                              if item.get("correction_record_id")})
                for correction_id in ids:
                    row = connection.execute(
                        "SELECT * FROM correction_records WHERE id=?", (correction_id,)
                    ).fetchone()
                    if row:
                        correction_rows[correction_id] = dict(row)
            if "bbox_review_id" in {row["name"] for row in connection.execute(
                    "PRAGMA table_info(training_examples)")}:
                bbox_review_ids = sorted({
                    int(item["bbox_review_id"]) for item in candidates
                    if item.get("bbox_review_id")
                })
                for review_id in bbox_review_ids:
                    row = connection.execute(
                        "SELECT * FROM yolo_bbox_reviews WHERE id=?", (review_id,)
                    ).fetchone()
                    if row:
                        bbox_review_rows[review_id] = dict(row)
            proposal_ids = sorted({int(item["proposal_id"]) for item in candidates if item.get("proposal_id")})
            for proposal_id in proposal_ids:
                rows = connection.execute("SELECT * FROM correction_records WHERE proposal_id=? ORDER BY id",
                                          (proposal_id,)).fetchall()
                correction_history[proposal_id] = [dict(row) for row in rows]
            detection_ids = sorted({int(item["detection_id"]) for item in candidates
                                    if item.get("detection_id")})
            detection_rows: dict[int, dict] = {}
            for offset in range(0, len(detection_ids), 500):
                batch = detection_ids[offset:offset + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""SELECT id,class_id,class_name,confidence,x1,y1,x2,y2,
                               model_id,model_digest,status
                        FROM yolo_detections WHERE id IN ({placeholders})""", batch
                ).fetchall()
                detection_rows.update({int(row["id"]): dict(row) for row in rows})
            active_crops: dict[int, dict] = {}
            for offset in range(0, len(detection_ids), 500):
                batch = detection_ids[offset:offset + 500]
                placeholders = ",".join("?" for _ in batch)
                rows = connection.execute(
                    f"""SELECT detection_id,crop_id,source_sha256,crop_sha256,
                               bbox_xyxy,bbox_revision
                        FROM active_detection_crops
                        WHERE detection_id IN ({placeholders})""", batch
                ).fetchall()
                active_crops.update({int(row["detection_id"]): dict(row) for row in rows})
        for item in candidates:
            spec = item["_task_spec"]
            registry_id = spec["registry_id"]
            record_id = item["_record_id"]
            source_path = Path(item["source_path"])
            source_hash = str(item.get("source_sha256") or "")
            label = str(item.get("class_label") or "")
            try:
                width, height = int(item.get("width") or 0), int(item.get("height") or 0)
            except (TypeError, ValueError):
                width = height = 0
            bbox = _valid_bbox(item.get("crop_bbox_xyxy"), width, height)
            source_summary = {"source_image_id": str(item.get("source_image_id") or ""),
                              "sha256": source_hash if len(source_hash) == 64 else "0" * 64,
                              "width": max(width, 1), "height": max(height, 1)}
            media = None
            if source_path.is_file() and len(source_hash) == 64 and _sha256(source_path) == source_hash:
                media = source_media.get(source_hash)
                if media is None:
                    suffix = source_path.suffix.lower() or ".img"
                    relative = Path("media") / "sources" / f"{source_hash}{suffix}"
                    destination = staging / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, destination)
                    copied_hash = _sha256(destination)
                    if copied_hash != source_hash:
                        raise ValueError(f"Copied training source failed its hash check: {source_path}")
                    media = {"relative_path": relative.as_posix(), "sha256": copied_hash,
                             "role": "source_image"}
                    source_media[source_hash] = media
            if bbox is not None and media is not None and str(item["task"]) != "yolo_detector":
                crop_key = (
                    f"{source_hash}:{','.join(f'{value:.3f}' for value in bbox)}"
                )
                crop_hash = hashlib.sha256(crop_key.encode("utf-8")).hexdigest()
                crop_media_entry = crop_media.get(crop_hash)
                if crop_media_entry is None:
                    with Image.open(source_path) as source_image:
                        rgb = source_image.convert("RGB")
                        x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
                        crop = rgb.crop((max(0,x1),max(0,y1),
                                        min(rgb.width,x2),min(rgb.height,y2)))
                        relative = Path("media") / "crops" / f"{crop_hash}.png"
                        destination = staging / relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        crop.save(destination, format="PNG")
                        crop.close()
                        rgb.close()
                    copied_hash = _sha256(destination)
                    crop_media_entry = {
                        "relative_path": relative.as_posix(),
                        "sha256": copied_hash,
                        "role": "authoritative_detection_crop",
                        "source_sha256": source_hash,
                        "bbox_xyxy": bbox,
                    }
                    crop_media[crop_hash] = crop_media_entry
                media = crop_media_entry
            forced_reason = item.get("_forced_exclusion_reason")
            if forced_reason:
                excluded.append({"record_id": record_id,
                                 "task": item.get("_forced_bundle_task") or _bundle_task(item["task"]),
                                 "reason": forced_reason,
                                 "model": {"id": spec["model_id"], "registry_id": registry_id,
                                           "registry_version": str(spec["version"])},
                                 "source": source_summary if source_path.is_file() else None,
                                 "media": media, "bbox_xyxy": bbox,
                                 "labels": {"class_label": label,
                                            "structured": {"task": item["task"],
                                                           "source_task": item.get("_original_task") or
                                                                         item.get("_source_task")}},
                                 "provenance": {"model_prediction": item.get("suggestion_provenance") or {},
                                                "source_workflow": item.get("workflow")}})
                continue
            if (not item.get("_empty_yolo")
                    and label not in allowed_labels.get((registry_id, item["task"]), set())):
                excluded.append({"record_id": record_id,
                                 "task": _bundle_task(item["task"], _task_context(
                                     item["task"], label, raw_registries[registry_id])),
                                 "reason": "label_not_in_current_model_registry",
                                 "model": {"id": spec["model_id"], "registry_id": registry_id,
                                           "registry_version": str(spec["version"])},
                                 "source": source_summary if source_path.is_file() else None,
                                 "media": media, "bbox_xyxy": bbox,
                                 "labels": {"class_label": label,
                                            "structured": {"task": item["task"],
                                                           "taxonomy_id": item.get("taxonomy_id"),
                                                           "taxonomy_version": item.get("taxonomy_version")}},
                                 "provenance": {"model_prediction": item.get("suggestion_provenance") or {},
                                                "source_workflow": item.get("workflow")}})
                continue
            if not source_path.is_file():
                excluded.append({"record_id": record_id, "task": _bundle_task(item["task"]),
                                 "reason": "source_image_missing", "model": None, "source": None,
                                 "media": None, "bbox_xyxy": bbox, "labels": {"class_label": label},
                                 "provenance": {"model_prediction": item.get("suggestion_provenance") or {}}})
                continue
            if len(source_hash) != 64 or _sha256(source_path) != source_hash:
                excluded.append({"record_id": record_id, "task": _bundle_task(item["task"]),
                                 "reason": "source_hash_mismatch", "model": None,
                                 "source": source_summary if width > 0 and height > 0 else None,
                                 "media": None, "bbox_xyxy": bbox, "labels": {"class_label": label},
                                 "provenance": {"model_prediction": item.get("suggestion_provenance") or {}}})
                continue
            if item.get("_empty_yolo"):
                provenance = item.get("suggestion_provenance") or {}
                correction_events = []
                for history_row in correction_history.get(int(item["proposal_id"]), []):
                    correction_events.append({
                        "correction_record_id": str(history_row["id"]),
                        "decision_type": history_row["decision_type"],
                        "final_state": history_row["final_state"],
                        "human_confirmed": bool(history_row["human_confirmed"]),
                        "original_snapshot": json.loads(history_row["original_snapshot_json"]),
                        "corrected_payload": json.loads(history_row["corrected_payload_json"]),
                    })
                model_identity = {"id": spec["model_id"], "registry_id": registry_id,
                                  "registry_version": str(spec["version"])}
                records.append({
                    "record_id": record_id, "task": "yolo_detection", "model": model_identity,
                    "source": {"source_image_id": str(item["source_image_id"]),
                               "sha256": source_hash, "width": width, "height": height},
                    "media": media, "bbox_xyxy": None, "detection": None,
                    "annotation": {"coordinate_space": "source_pixels", "target_bbox_xyxy": None,
                                   "original_model_bbox_xyxy": None, "target_class_id": None,
                                   "empty_image": True},
                    "review": {"human_confirmed": True, "eligible": True,
                               "review_state": "reviewed", "exclusion_reason": None},
                    "labels": {"class_label": "__empty__",
                               "structured": {"task": "yolo_detection", "no_objects": True}},
                    "provenance": {
                        "source_snapshot_id": f"{source_hash}:correction:{item['id']}:empty_yolo",
                        "created_at": _iso_utc(item.get("created_at")),
                        "model_prediction": provenance, "correction_events": correction_events,
                        "source_workflow": "professional_review",
                        "training_record_table": "correction_records",
                    },
                })
                continue
            if not bbox:
                excluded.append({"record_id": record_id, "task": _bundle_task(item["task"]),
                                 "reason": "invalid_or_missing_training_bbox",
                                 "model": {"id": spec["model_id"], "registry_id": registry_id,
                                           "registry_version": str(spec["version"])},
                                 "source": source_summary, "media": media, "bbox_xyxy": None,
                                 "labels": {"class_label": label},
                                 "provenance": {"model_prediction": item.get("suggestion_provenance") or {}}})
                continue

            provenance = item.get("suggestion_provenance") or {}
            if not isinstance(provenance, dict):
                provenance = {"raw_value": provenance}
            bbox_review_id = int(item["bbox_review_id"]) if item.get("bbox_review_id") else None
            bbox_review = bbox_review_rows.get(bbox_review_id) if bbox_review_id else None
            if bbox_review:
                provenance = {
                    **provenance,
                    "bbox_review": {
                        "bbox_review_id": str(bbox_review["id"]),
                        "review_status": bbox_review["review_status"],
                        "human_confirmed": bool(bbox_review["human_confirmed"]),
                        "confirmed_at": bbox_review["confirmed_at"],
                        "original_bbox_xyxy": json.loads(bbox_review["original_bbox_xyxy"]),
                        "effective_bbox_xyxy": json.loads(bbox_review["effective_bbox_xyxy"]),
                        "bbox_revision": bbox_review["bbox_revision"],
                        "approval_authority": "human_approved_unchanged",
                    },
                }
            correction_events = []
            correction_record_id = (int(item["correction_record_id"])
                                    if item.get("correction_record_id") else None)
            correction = correction_rows.get(correction_record_id) if correction_record_id else None
            for history_row in correction_history.get(int(item["proposal_id"]), []):
                correction_events.append({
                    "correction_record_id": str(history_row["id"]),
                    "decision_type": history_row["decision_type"],
                    "final_state": history_row["final_state"],
                    "human_confirmed": bool(history_row["human_confirmed"]),
                    "original_snapshot": json.loads(history_row["original_snapshot_json"]),
                    "corrected_payload": json.loads(history_row["corrected_payload_json"]),
                })
            output_group = _task_context(item["task"], label, raw_registries[registry_id])
            task_name = _bundle_task(item["task"], output_group)
            yolo_prediction = provenance.get("yolo") or {}
            original_bbox = (yolo_prediction.get("original_bbox_xyxy")
                             or provenance.get("original_bbox_xyxy"))
            if not original_bbox and all(yolo_prediction.get(key) is not None
                                         for key in ("x1", "y1", "x2", "y2")):
                original_bbox = [yolo_prediction[key] for key in ("x1", "y1", "x2", "y2")]
            detection = detection_rows.get(int(item["detection_id"])) if item.get("detection_id") else None
            active_crop = active_crops.get(int(item["detection_id"])) if item.get("detection_id") else None
            if active_crop and active_crop["source_sha256"] != source_hash:
                active_crop = None
            if not original_bbox and detection:
                original_bbox = [detection[key] for key in ("x1", "y1", "x2", "y2")]
            original_bbox = _valid_bbox(original_bbox, width, height)
            if detection:
                provenance = dict(provenance)
                provenance["yolo"] = {
                    **(yolo_prediction if isinstance(yolo_prediction, dict) else {}),
                    "detection_id": str(detection["id"]),
                    "class_id": int(detection["class_id"]),
                    "class_name": detection["class_name"],
                    "confidence": detection["confidence"],
                    "model_id": detection["model_id"],
                    "model_digest": detection["model_digest"],
                    "detection_status": detection["status"],
                    **({"original_bbox_xyxy": original_bbox} if original_bbox else {}),
                }
            class_id = _registry_class_id(raw_registries[registry_id], item["task"],
                                          output_group, label)
            model_identity = {"id": spec["model_id"], "registry_id": registry_id,
                              "registry_version": str(spec["version"])}
            target_mask = None
            if item["task"] == "body_images" and item.get("target_mask_json"):
                try:
                    target_mask = json.loads(item["target_mask_json"])
                except (TypeError, json.JSONDecodeError):
                    target_mask = None
            if item["task"] == "body_images" and target_mask is None:
                if label == "bodypart_cum":
                    target_mask = {"cum": {"target": True, "evaluated": True},
                                   "accessory": {"target": None, "evaluated": False}}
                elif label == "bodypart_acc":
                    target_mask = {"cum": {"target": None, "evaluated": False},
                                   "accessory": {"target": True, "evaluated": True}}
                elif label == "body_images_none":
                    target_mask = {"cum": {"target": False, "evaluated": True},
                                   "accessory": {"target": False, "evaluated": True}}
            if item["task"] == "body_images" and target_mask is None:
                excluded.append({"record_id": record_id, "task": "body_images_classification",
                                 "reason": "body_images_target_mask_missing",
                                 "model": model_identity,
                                 "source": source_summary if source_path.is_file() else None,
                                 "media": media, "bbox_xyxy": bbox,
                                 "labels": {"class_label": label},
                                 "provenance": {"model_prediction": provenance}})
                continue
            labels = {
                "class_label": label,
                "structured": {
                    "task": task_name,
                    "taxonomy_id": item.get("taxonomy_id"),
                    "taxonomy_version": item.get("taxonomy_version"),
                    "output_group": output_group,
                    "human_confirmed_labels": list(item.get("human_confirmed_labels") or []),
                    "location": (provenance.get("location") if isinstance(provenance, dict) else None),
                    **({"body_images_target_mask": target_mask}
                       if item["task"] == "body_images" else {}),
                },
            }
            record = {
                "record_id": record_id,
                "task": task_name,
                "model": model_identity,
                "source": {"source_image_id": str(item["source_image_id"]),
                           "sha256": source_hash, "width": width, "height": height},
                "media": media,
                "bbox_xyxy": bbox,
                "annotation": {"coordinate_space": "source_pixels",
                                "target_bbox_xyxy": bbox,
                                "original_model_bbox_xyxy": original_bbox,
                                "target_class_id": class_id,
                                **({"body_images_target_mask": target_mask}
                                   if item["task"] == "body_images" else {})},
                "detection": ({
                    "detection_id": str(detection["id"]),
                    "bbox_xyxy": original_bbox,
                    "class_id": int(detection["class_id"]),
                    "class_name": detection["class_name"],
                    "confidence": detection["confidence"],
                    "model_id": detection["model_id"],
                    "model_digest": detection["model_digest"],
                    "status": detection["status"],
                } if detection and original_bbox else None),
                "review": {"human_confirmed": True, "eligible": True,
                           "review_state": "reviewed", "exclusion_reason": None},
                "labels": labels,
                "provenance": {
                    "source_snapshot_id": f"{source_hash}:proposal:{item['proposal_id']}:{record_id}",
                    "created_at": _iso_utc(item.get("created_at")),
                    "model_prediction": provenance,
                    "correction_events": correction_events,
                    "source_workflow": item.get("workflow"),
                    "training_record_table": item["_source_table"],
                    **({"crop_revision": {
                        "crop_id": active_crop["crop_id"],
                        "source_sha256": active_crop["source_sha256"],
                        "crop_sha256": active_crop["crop_sha256"],
                        "bbox_xyxy": json.loads(active_crop["bbox_xyxy"]),
                        "bbox_revision": active_crop["bbox_revision"],
                    }} if active_crop else {}),
                    **({"bbox_review": provenance["bbox_review"]}
                       if isinstance(provenance, dict) and provenance.get("bbox_review") else {}),
                    **({"task_mapping": item["_task_mapping"]}
                       if item.get("_task_mapping") else {}),
                },
            }
            records.append(record)

        if not records:
            reasons = sorted({entry["reason"] for entry in excluded})
            raise ValueError("No supported, current, human-confirmed training records are available. "
                             f"Excluded records: {len(excluded)} ({', '.join(reasons) or 'none'}).")

        files = []
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                files.append({"relative_path": path.relative_to(staging).as_posix(),
                              "sha256": _sha256(path), "bytes": path.stat().st_size})

        with database.connect() as connection:
            database_schema_version = int(connection.execute(
                "SELECT COALESCE(MAX(version),0) FROM schema_migrations"
            ).fetchone()[0])
        bundle_id = datetime.now(timezone.utc).strftime("newassetapp_%Y%m%dT%H%M%S%fZ")
        manifest = {
            "schema_version": 4,
            "bundle_id": bundle_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "producer": {"application": "NewAssetApp", "version": "unreleased",
                         "database_schema_version": database_schema_version,
                         "project_id": hashlib.sha256(str(database.path.resolve()).encode("utf-8")).hexdigest()[:20]},
            "models": sorted({json.dumps(record["model"], sort_keys=True)
                              for record in records + [item for item in excluded if item.get("model")]}),
            "registries": sorted(registries.values(), key=lambda value: value["id"]),
            "records": sorted(records, key=lambda value: (value["task"],
                                                            value["source"]["sha256"],
                                                            value["record_id"])),
            "excluded_records": sorted(excluded, key=lambda value: value["record_id"]),
            "files": files,
        }
        manifest["models"] = [json.loads(value) for value in manifest["models"]]
        for item in manifest["excluded_records"]:
            item.setdefault("source", None)
            item.setdefault("media", None)
            item.setdefault("bbox_xyxy", None)
            item.setdefault("labels", None)
            item.setdefault("provenance", None)
        manifest["bundle_sha256"] = _canonical_sha256(manifest)
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

        final_name = f"{bundle_id}_{manifest['bundle_sha256'][:10]}"
        final_path = source_root / final_name
        if final_path.exists():
            raise FileExistsError(f"Immutable training bundle already exists: {final_path}")
        os.replace(staging, final_path)
        return {"bundle_id": bundle_id, "bundle_sha256": manifest["bundle_sha256"],
                "directory": str(final_path), "manifest": str(final_path / "manifest.json"),
                "record_count": len(records), "excluded_count": len(excluded),
                "source_media_file_count": len(source_media),
                "training_crop_file_count": len(crop_media),
                "media_file_count": len(source_media) + len(crop_media),
                "registries": len(registries)}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
