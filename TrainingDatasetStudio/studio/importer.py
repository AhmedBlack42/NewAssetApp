from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator, FormatChecker

from .config import StudioConfig
from .store import StudioStore


REGION_IDENTITY = {"face", "boobs", "ass", "pussy", "legs"}
STATUS_NAMES = {"accepted", "warning", "quarantined", "rejected"}


def _approved_yolo_registry() -> dict:
    registry_dir = Path(__file__).resolve().parents[1] / "registries"
    registry = json.loads((registry_dir / "yolo_detector_v1.json").read_text(encoding="utf-8"))
    if (not isinstance(registry, dict)
            or registry.get("registry_id") != "newassetapp_yolo_detector_v1"
            or registry.get("schema_version") != 1
            or registry.get("status") != "approved_target_registry"):
        raise BundleImportError("The configured Studio YOLO registry is not approved.")
    rows = registry.get("classes")
    if (not isinstance(rows, list)
            or isinstance(registry.get("class_count"), bool)
            or not isinstance(registry.get("class_count"), int)
            or len(rows) != registry["class_count"]):
        raise BundleImportError("The approved Studio YOLO registry class count is inconsistent.")
    classes: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise BundleImportError("The approved Studio YOLO registry has malformed identities.")
        class_id, name = row.get("id"), row.get("name")
        if (isinstance(class_id, bool) or not isinstance(class_id, int)
                or not isinstance(name, str) or not name.strip()
                or class_id in classes or name in classes.values()):
            raise BundleImportError("The approved Studio YOLO registry has malformed identities.")
        classes[class_id] = name
    if sorted(classes) != list(range(len(classes))):
        raise BundleImportError("The approved Studio YOLO registry IDs are not contiguous.")
    names_path = registry_dir / "classes.txt"
    checksum_name = str(registry.get("class_map_sha256_file") or "")
    checksum_path = registry_dir / checksum_name
    if (not names_path.is_file() or not checksum_path.is_file()
            or checksum_path.resolve().parent != registry_dir.resolve()):
        raise BundleImportError("The approved Studio YOLO class map or checksum is missing.")
    checksum_tokens = checksum_path.read_text(encoding="ascii").strip().split()
    if (not checksum_tokens
            or hashlib.sha256(names_path.read_bytes()).hexdigest().casefold()
            != checksum_tokens[0].casefold()
            or names_path.read_text(encoding="utf-8").splitlines()
            != [classes[class_id] for class_id in sorted(classes)]):
        raise BundleImportError("The approved Studio YOLO registry, class map and checksum differ.")
    return registry


def _valid_body_images_target_mask(target_mask: dict | None,
                                  require_evaluated: bool = False) -> bool:
    if not isinstance(target_mask, dict):
        return False
    evaluated = False
    for name in ("cum", "accessory"):
        state = target_mask.get(name)
        if not isinstance(state, dict) or set(("target", "evaluated")) - set(state):
            return False
        if state["evaluated"] not in {True, False}:
            return False
        if state["evaluated"] and state["target"] not in {True, False}:
            return False
        if not state["evaluated"] and state["target"] is not None:
            return False
        evaluated = evaluated or state["evaluated"]
    return evaluated or not require_evaluated


class BundleImportError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def safe_bundle_path(root: Path, relative: str) -> Path:
    posix = PurePosixPath(str(relative).replace("\\", "/"))
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise BundleImportError(f"Unsafe bundle path: {relative}")
    candidate = root.joinpath(*posix.parts).resolve()
    if root.resolve() not in candidate.parents:
        raise BundleImportError(f"Bundle path escapes its root: {relative}")
    return candidate


def _bbox(value, width: int, height: int) -> list[float] | None:
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


def _registry_class(registry: dict, task: str, output_group: str | None, label: str):
    if task in {"yolo_detection", "yolo_detector"}:
        return next((c for c in registry.get("classes", []) if c.get("name") == label), None)
    if task in {"body_images_classification", "fullbody_state_classification", "asset_classification",
                "portrait_classification", "arousal_classification", "corruption_classification"}:
        groups = registry.get("output_groups", {})
        group = groups.get(output_group or "")
        if task in {"asset_classification", "portrait_classification", "arousal_classification",
                    "corruption_classification"} and not output_group:
            return None
        if group:
            return next((c for c in group.get("classes", []) if c.get("class_name") == label), None)
        return None
    if task == "broad_clothing_classification":
        return next((c for c in registry.get("classes", [])
                     if c.get("class_name") == label and c.get("active", True)), None)
    if task == "detailed_clothing_classification":
        return next((c for c in registry.get("entries", [])
                     if c.get("serialized_value") == label and c.get("selectable")
                     and not c.get("requires_review")), None)
    if task == "corruption_state_classification":
        return next((c for c in registry.get("classes", []) if c.get("class_name") == label), None)
    return None


def _task_validation(record: dict, version: int, model_registry: dict[str, dict],
                     registries: dict[str, dict]) -> tuple[str, str | None, int | None, str | None]:
    task = str(record.get("task") or "")
    model = record.get("model") or {}
    model_id = model.get("id") if isinstance(model, dict) else None
    registry_id = model.get("registry_id") if isinstance(model, dict) else None
    registry_version = model.get("registry_version") if isinstance(model, dict) else None
    if version == 2 and task == "asset_classification":
        structured = record.get("labels", {}).get("structured", {})
        group = structured.get("output_group")
        task = ("fullbody_state_classification" if group == "fullbody_state" else
                "body_images_classification" if group == "body_images" else task)
    elif version == 2 and task == "clothing_classification":
        task = ("broad_clothing_classification" if registry_id == "clothing_classifier" else
                "detailed_clothing_classification")
    if model_id not in model_registry or model_registry[model_id].get("registry_id") != registry_id:
        return task, registry_id, None, "model_registry_identity_mismatch"
    if registry_id not in registries:
        return task, registry_id, None, "referenced_registry_missing"
    if task in {"yolo_detection", "yolo_detector"}:
        if (registry_id != "newassetapp_yolo_detector_v1"
                or registries[registry_id] != _approved_yolo_registry()):
            return task, registry_id, None, "approved_yolo_registry_mismatch"
    model_spec = model_registry[model_id]
    if (model_spec.get("registry_version") is not None and registry_version is not None
            and str(model_spec["registry_version"]) != str(registry_version)):
        return task, registry_id, None, "model_registry_version_mismatch"
    label = str(record.get("labels", {}).get("class_label") or "")
    structured = record.get("labels", {}).get("structured", {})
    group = structured.get("output_group")
    expected_groups = {
        "body_images_classification": {"body_images"},
        "fullbody_state_classification": {"fullbody", "fullbody_state"},
        "portrait_classification": {"portrait"},
        "arousal_classification": {"arousal"},
        "corruption_classification": {"corruption"},
    }
    if task in expected_groups and group not in expected_groups[task]:
        return task, registry_id, None, "task_output_head_identity_mismatch"
    if task == "body_images_classification" and label in REGION_IDENTITY:
        return task, registry_id, None, "architecture_body_region_identity_is_yolo_task"
    if task in {"yolo_detection", "yolo_detector"} and record.get("annotation", {}).get("empty_image") is True:
        annotation = record.get("annotation", {})
        if (label != "__empty__" or annotation.get("target_class_id") is not None
                or annotation.get("target_bbox_xyxy") is not None
                or record.get("bbox_xyxy") is not None
                or structured.get("no_objects") is not True
                or annotation.get("coordinate_space") != "source_pixels"):
            return task, registry_id, None, "empty_yolo_annotation_invalid"
        return task, registry_id, None, None
    if task == "body_images_classification":
        target_mask = (record.get("annotation", {}).get("body_images_target_mask")
                       or structured.get("body_images_target_mask"))
        label = str(record.get("labels", {}).get("class_label") or "")
        if target_mask is None and label == "bodypart_cum":
            target_mask = {"cum": {"target": True, "evaluated": True},
                           "accessory": {"target": None, "evaluated": False}}
        elif target_mask is None and label == "bodypart_acc":
            target_mask = {"cum": {"target": None, "evaluated": False},
                           "accessory": {"target": True, "evaluated": True}}
        elif target_mask is None and label in {"portrait", "tportrait"}:
            target_mask = {"cum": {"target": None, "evaluated": False},
                           "accessory": {"target": None, "evaluated": False}}
        if not isinstance(target_mask, dict):
            return task, registry_id, None, "body_images_target_mask_missing"
        if not _valid_body_images_target_mask(target_mask):
            return task, registry_id, None, "body_images_target_mask_malformed"
        label = str(record.get("labels", {}).get("class_label") or "")
        if label not in {"body_images_multi_label", "body_images_none", "body_images_pending",
                         "portrait", "tportrait"}:
            # Backward-compatible single-target records remain accepted.
            cls = _registry_class(registries[registry_id], task, group, label)
            if cls is None:
                return task, registry_id, None, "label_not_in_task_registry"
            class_id = cls.get("class_id")
            target_id = record.get("annotation", {}).get("target_class_id")
            if class_id is not None and target_id is not None and int(target_id) != int(class_id):
                return task, registry_id, None, "cnn_target_class_id_name_mismatch"
            return task, registry_id, int(class_id) if class_id is not None else None, None
        return task, registry_id, None, None
    cls = _registry_class(registries[registry_id], task, group, label)
    if cls is None:
        return task, registry_id, None, "label_not_in_task_registry"
    if task in {"yolo_detection", "yolo_detector"}:
        target_id = record.get("annotation", {}).get("target_class_id")
        if target_id is None or int(target_id) != int(cls.get("id", -1)):
            return task, registry_id, None, "yolo_target_class_id_name_mismatch"
        if record.get("annotation", {}).get("coordinate_space") != "source_pixels":
            return task, registry_id, None, "yolo_annotation_coordinate_space_unknown"
        return task, registry_id, int(target_id), None
    class_id = cls.get("class_id")
    target_id = record.get("annotation", {}).get("target_class_id")
    if class_id is not None and target_id is not None and int(target_id) != int(class_id):
        return task, registry_id, None, "cnn_target_class_id_name_mismatch"
    return task, registry_id, int(class_id) if class_id is not None else None, None


class BundleImporter:
    def __init__(self, config: StudioConfig, store: StudioStore):
        self.config = config
        self.store = store
        self.config.ensure_directories()

    def inspect(self, bundle_dir: Path | str) -> dict:
        root = Path(bundle_dir).resolve()
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            raise BundleImportError("Bundle manifest.json is missing.")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = manifest.get("schema_version")
        schema_path = self.config.contract_dir / f"newassetapp_import_v{version}.schema.json"
        if version not in {2, 3, 4} or not schema_path.is_file():
            raise BundleImportError(f"Unsupported bundle schema version: {version}")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors = sorted(validator.iter_errors(manifest), key=lambda e: list(map(str, e.absolute_path)))
        if errors:
            error = errors[0]
            pointer = "/".join(map(str, error.absolute_path))
            raise BundleImportError(f"Manifest schema validation failed at {pointer}: {error.message}")
        hashed = dict(manifest)
        expected = hashed.pop("bundle_sha256", None)
        actual = canonical_sha256(hashed)
        if not expected or actual != expected:
            raise BundleImportError("Canonical manifest SHA-256 does not match bundle_sha256.")
        files = {}
        for entry in manifest.get("files", []):
            relative = entry.get("relative_path") or entry.get("path")
            path = safe_bundle_path(root, relative)
            if not path.is_file() or path.stat().st_size != int(entry.get("bytes", -1)):
                raise BundleImportError(f"Bundle payload is missing or has a wrong size: {relative}")
            digest = sha256_file(path)
            if digest.casefold() != str(entry.get("sha256", "")).casefold():
                raise BundleImportError(f"Bundle payload hash mismatch: {relative}")
            files[relative] = path
        registries = {}
        for reference in manifest.get("registries", []):
            relative = reference["relative_path"]
            path = files.get(relative) or safe_bundle_path(root, relative)
            if not path.is_file() or sha256_file(path).casefold() != reference["sha256"].casefold():
                raise BundleImportError(f"Registry payload hash mismatch: {relative}")
            registries[str(reference["id"])] = {
                "reference": reference, "payload": json.loads(path.read_text(encoding="utf-8")),
            }
        models = {str(row["id"]): row for row in manifest.get("models", [])}
        return {"root": root, "manifest": manifest, "registries": registries,
                "models": models, "files": files}

    def import_bundle(self, bundle_dir: Path | str) -> dict:
        checked = self.inspect(bundle_dir)
        root, manifest = checked["root"], checked["manifest"]
        digest = manifest["bundle_sha256"]
        with self.store.connect() as db:
            previous = db.execute("SELECT id FROM bundles WHERE bundle_sha256=?", (digest,)).fetchone()
            if previous:
                return {"bundle_id": manifest["bundle_id"], "bundle_sha256": digest,
                        "duplicate": True, "record_count": 0, "accepted": 0,
                        "warning": 0, "quarantined": 0, "rejected": 0,
                        "message": "This immutable bundle is already imported."}
        created_media: list[Path] = []
        try:
            with self.store.connect() as db:
                cursor = db.execute("""INSERT INTO bundles(bundle_id,schema_version,bundle_sha256,
                                    source_path,manifest_json) VALUES(?,?,?,?,?)""",
                                    (manifest["bundle_id"], int(manifest["schema_version"]), digest,
                                     str(root), json.dumps(manifest, ensure_ascii=False, sort_keys=True)))
                bundle_pk = int(cursor.lastrowid)
                for registry_id, value in checked["registries"].items():
                    ref, payload = value["reference"], value["payload"]
                    db.execute("""INSERT INTO registries(bundle_id,registry_id,version,sha256,
                                 relative_path,payload_json) VALUES(?,?,?,?,?,?)""",
                               (bundle_pk, registry_id, str(ref.get("version", "")), ref["sha256"],
                                ref["relative_path"], json.dumps(payload, ensure_ascii=False, sort_keys=True)))
                counts = {name: 0 for name in STATUS_NAMES}
                for record in manifest.get("records", []):
                    prepared = self._prepare_record(record, int(manifest["schema_version"]), checked, root,
                                                    created_media)
                    final_status = self._insert_record(db, bundle_pk, prepared)
                    counts[final_status] += 1
                for excluded in manifest.get("excluded_records", []):
                    prepared = self._prepare_exclusion(excluded, checked, root, created_media)
                    final_status = self._insert_record(db, bundle_pk, prepared)
                    counts[final_status] += 1
            return {"bundle_id": manifest["bundle_id"], "bundle_sha256": digest,
                    "duplicate": False, "record_count": sum(counts.values()), **counts}
        except Exception:
            for path in created_media:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise

    def _copy_media(self, media: dict | None, source: dict | None, root: Path,
                    created_media: list[Path]) -> str | None:
        if not media or not source:
            return None
        relative = media.get("relative_path")
        path = safe_bundle_path(root, relative)
        digest = str(media.get("sha256", "")).casefold()
        if not path.is_file() or sha256_file(path).casefold() != digest:
            return None
        role = str(media.get("role") or "")
        if role == "authoritative_detection_crop":
            crop_source_hash = str(media.get("source_sha256") or "").casefold()
            if crop_source_hash != str(source.get("sha256", "")).casefold():
                return None
        elif digest != str(source.get("sha256", "")).casefold():
            return None
        suffix = path.suffix.lower()[:10] or ".img"
        target = self.config.media_dir / (digest + suffix)
        if target.exists():
            if sha256_file(target).casefold() != digest:
                raise BundleImportError(f"Studio media store contains a hash collision for {digest}.")
            return str(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".import_", dir=target.parent, delete=False) as tmp:
            staging = Path(tmp.name)
        try:
            shutil.copyfile(path, staging)
            if sha256_file(staging).casefold() != digest:
                raise BundleImportError("Imported media failed its post-copy hash check.")
            os.replace(staging, target)
            created_media.append(target)
        finally:
            staging.unlink(missing_ok=True)
        return str(target)

    def _prepare_record(self, record: dict, version: int, checked: dict, root: Path,
                        created_media: list[Path]) -> dict:
        source = record.get("source") or {}
        media = self._copy_media(record.get("media"), source, root, created_media)
        task, registry_id, target_id, reason = _task_validation(
            record, version, checked["models"], {key: value["payload"]
                                                   for key, value in checked["registries"].items()})
        box = record.get("annotation", {}).get("target_bbox_xyxy") or record.get("bbox_xyxy")
        width, height = int(source.get("width", 0)), int(source.get("height", 0))
        valid_box = _bbox(box, width, height)
        empty_yolo = (task in {"yolo_detection", "yolo_detector"}
                      and record.get("annotation", {}).get("empty_image") is True
                      and record.get("labels", {}).get("class_label") == "__empty__"
                      and record.get("labels", {}).get("structured", {}).get("no_objects") is True
                      and record.get("annotation", {}).get("target_class_id") is None
                      and box is None)
        status = "accepted"
        if not media:
            status, reason = "quarantined", reason or "source_media_unavailable_or_hash_mismatch"
        else:
            try:
                from PIL import Image
                with Image.open(media) as image:
                    image.verify()
                with Image.open(media) as image:
                    if (record.get("media") or {}).get("role") == "authoritative_detection_crop":
                        crop_box = (record.get("media") or {}).get("bbox_xyxy") or box
                        if isinstance(crop_box, list) and len(crop_box) == 4:
                            crop_width = max(1, int(round(float(crop_box[2]) - float(crop_box[0]))))
                            crop_height = max(1, int(round(float(crop_box[3]) - float(crop_box[1]))))
                            dimensions_match = image.size == (crop_width, crop_height)
                        else:
                            dimensions_match = False
                    else:
                        dimensions_match = image.size == (width, height)
            except Exception:
                dimensions_match = False
            if not dimensions_match:
                status, reason = "quarantined", reason or "source_image_invalid_or_dimensions_mismatch"
        if media and dimensions_match and not valid_box and not empty_yolo:
            status, reason = "quarantined", reason or "annotation_bbox_invalid_or_out_of_bounds"
        if reason:
            status = "quarantined"
        provenance = record.get("provenance") or {}
        review = record.get("review") or {}
        if not isinstance(provenance.get("model_prediction", {}), dict):
            status, reason = "quarantined", "model_prediction_provenance_invalid"
        if not bool(review.get("human_confirmed")) or not bool(review.get("eligible")):
            status, reason = "quarantined", reason or "human_confirmation_or_eligibility_missing"
        if not record.get("record_id"):
            status, reason = "rejected", "record_id_missing"
        body_mask = (record.get("annotation", {}).get("body_images_target_mask")
                     or record.get("labels", {}).get("structured", {}).get("body_images_target_mask"))
        legacy_label = str(record.get("labels", {}).get("class_label") or "")
        if task == "body_images_classification" and body_mask is None:
            if legacy_label == "bodypart_cum":
                body_mask = {"cum": {"target": True, "evaluated": True},
                             "accessory": {"target": None, "evaluated": False}}
            elif legacy_label == "bodypart_acc":
                body_mask = {"cum": {"target": None, "evaluated": False},
                             "accessory": {"target": True, "evaluated": True}}
            elif legacy_label in {"portrait", "tportrait"}:
                body_mask = {"cum": {"target": None, "evaluated": False},
                             "accessory": {"target": None, "evaluated": False}}
        annotation = {
            "task": task, "class_label": record.get("labels", {}).get("class_label"),
            "target_class_id": target_id if target_id is not None else record.get("annotation", {}).get("target_class_id"),
            "bbox_xyxy": valid_box or box, "original_model_bbox_xyxy": record.get("annotation", {}).get("original_model_bbox_xyxy"),
            "empty_image": empty_yolo,
            "coordinate_space": record.get("annotation", {}).get("coordinate_space", "source_pixels"),
            "confirmed": bool(review.get("human_confirmed")), "eligible": bool(review.get("eligible")),
            "model": record.get("model"), "labels": record.get("labels"),
            "body_images_target_mask": body_mask,
        }
        model = record.get("model") or {}
        return {"external_id": str(record.get("record_id", "")), "task": task,
                "model_id": model.get("id"), "registry_id": registry_id,
                "registry_version": (model.get("registry_version") or
                                     checked["registries"].get(registry_id, {}).get("reference", {}).get("version")),
                "class_label": record.get("labels", {}).get("class_label"),
                "target_class_id": target_id, "status": status, "reason": reason,
                "source_image_id": str(source.get("source_image_id", "")),
                "source_project_id": str(checked["manifest"].get("producer", {}).get("project_id") or ""),
                "source_sha256": source.get("sha256"), "source_width": width,
                "source_height": height, "media_path": media,
                "original_json": record, "annotation": annotation,
                "human_confirmed": bool(review.get("human_confirmed")),
                "training_eligible": (bool(review.get("eligible")) and status == "accepted"
                                     and (task != "body_images_classification"
                                          or _valid_body_images_target_mask(body_mask,
                                                                            require_evaluated=True)))}

    def _prepare_exclusion(self, excluded: dict, checked: dict, root: Path,
                           created_media: list[Path]) -> dict:
        source = excluded.get("source") or {}
        media = self._copy_media(excluded.get("media"), source, root, created_media)
        model = excluded.get("model") or {}
        task = str(excluded.get("task") or "unresolved")
        label = (excluded.get("labels") or {}).get("class_label")
        if label in REGION_IDENTITY and task in {"body_images_classification", "unified_classification_unresolved",
                                                 "asset_classification"}:
            task = "yolo_detection_unresolved"
        annotation = {"task": task, "class_label": label,
                      "bbox_xyxy": excluded.get("bbox_xyxy"), "confirmed": False,
                      "eligible": False, "original_exclusion": excluded}
        return {"external_id": str(excluded.get("record_id", "")), "task": task,
                "model_id": model.get("id"), "registry_id": model.get("registry_id"),
                "registry_version": (model.get("registry_version") or
                                     checked["registries"].get(model.get("registry_id"), {}).get("reference", {}).get("version")),
                "class_label": label,
                "target_class_id": None, "status": "quarantined",
                "reason": str(excluded.get("reason") or "source_bundle_exclusion"),
                "source_image_id": str(source.get("source_image_id", "")) if source else None,
                "source_project_id": str(checked["manifest"].get("producer", {}).get("project_id") or ""),
                "source_sha256": source.get("sha256"), "source_width": source.get("width"),
                "source_height": source.get("height"), "media_path": media,
                "original_json": excluded, "annotation": annotation,
                "human_confirmed": False, "training_eligible": False}

    def _insert_record(self, db, bundle_pk: int, row: dict) -> str:
        cursor = db.execute("""INSERT INTO records(bundle_id,external_id,task,model_id,registry_id,registry_version,
                     class_label,target_class_id,status,reason,source_image_id,source_sha256,source_width,
                     source_height,media_path,original_json,annotation_json,human_confirmed,training_eligible,source_project_id)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (bundle_pk, row["external_id"], row["task"], row["model_id"], row["registry_id"],
                      row["registry_version"], row["class_label"], row["target_class_id"], row["status"],
                      row["reason"], row["source_image_id"], row["source_sha256"], row["source_width"],
                      row["source_height"], row["media_path"],
                      json.dumps(row["original_json"], ensure_ascii=False, sort_keys=True),
                      json.dumps(row["annotation"], ensure_ascii=False, sort_keys=True),
                      int(row["human_confirmed"]), int(row["training_eligible"]), row.get("source_project_id")))
        stored = db.execute("SELECT * FROM records WHERE id=?", (int(cursor.lastrowid),)).fetchone()
        StudioStore._assign_training_bundle(db, stored, self.store.training_bundle_max_bytes)
        status = db.execute("SELECT status FROM records WHERE id=?",
                            (int(cursor.lastrowid),)).fetchone()
        return str(status["status"])

