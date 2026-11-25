from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
YOLO_REGISTRY_PATH = APP_ROOT / "TrainingDatasetStudio" / "registries" / "yolo_detector_v1.json"
FULLBODY_FINAL_TAG_MAP_PATH = APP_ROOT / "data" / "models" / "yolo_fullbody_final_tag_mapping.json"
FULLBODY_TAGS_PATH = APP_ROOT / "data" / "tags" / "fullbody_tags.json"


@lru_cache(maxsize=1)
def approved_yolo_classes() -> dict[int, str]:
    registry = json.loads(YOLO_REGISTRY_PATH.read_text(encoding="utf-8"))
    if registry.get("status") != "approved_target_registry":
        raise ValueError("The configured YOLO registry is not the approved target registry.")
    rows = registry.get("classes")
    if not isinstance(rows, list) or len(rows) != int(registry.get("class_count", -1)):
        raise ValueError("Approved YOLO registry class count is inconsistent.")
    classes: dict[int, str] = {}
    names: set[str] = set()
    for row in rows:
        class_id, name = row.get("id"), row.get("name")
        if (isinstance(class_id, bool) or not isinstance(class_id, int)
                or not isinstance(name, str) or not name.strip()
                or class_id in classes or name in names):
            raise ValueError("Approved YOLO registry has duplicate or malformed class identities.")
        classes[class_id] = name
        names.add(name)
    if sorted(classes) != list(range(len(classes))):
        raise ValueError("Approved YOLO class IDs must be contiguous and zero-based.")

    registry_dir = YOLO_REGISTRY_PATH.parent
    names_path = registry_dir / "classes.txt"
    checksum_path = registry_dir / str(registry.get("class_map_sha256_file") or "")
    if not names_path.is_file() or not checksum_path.is_file():
        raise ValueError("Approved YOLO class-map verification files are missing.")
    expected_hash = checksum_path.read_text(encoding="ascii").strip().split()[0].lower()
    actual_hash = hashlib.sha256(names_path.read_bytes()).hexdigest()
    listed_names = names_path.read_text(encoding="utf-8").splitlines()
    if actual_hash != expected_hash or listed_names != [classes[i] for i in range(len(classes))]:
        raise ValueError("Approved YOLO registry, classes.txt, and checksum do not match.")
    return classes


def approved_yolo_class_ids() -> set[int]:
    return set(approved_yolo_classes())


def is_approved_yolo_identity(class_id: int | None, class_name: str | None) -> bool:
    if isinstance(class_id, bool) or not isinstance(class_id, int):
        return False
    return approved_yolo_classes().get(class_id) == class_name


@lru_cache(maxsize=1)
def fullbody_final_tag_mapping() -> dict[str, dict]:
    registry = json.loads(YOLO_REGISTRY_PATH.read_text(encoding="utf-8"))
    approved = approved_yolo_classes()
    payload = json.loads(FULLBODY_FINAL_TAG_MAP_PATH.read_text(encoding="utf-8"))
    if payload.get("registry_id") != registry.get("registry_id"):
        raise ValueError("Fullbody Final Tag mappings reference a different YOLO registry.")
    rows = payload.get("mappings")
    if not isinstance(rows, list):
        raise ValueError("Fullbody Final Tag mappings are malformed.")
    by_name: dict[str, dict] = {}
    for row in rows:
        name, class_id = row.get("class_name"), row.get("class_id")
        if (not isinstance(name, str) or name in by_name
                or isinstance(class_id, bool) or not isinstance(class_id, int)
                or approved.get(class_id) != name):
            raise ValueError("Fullbody Final Tag mapping class ID/name is not in the approved registry.")
        status, final_tag = row.get("status"), row.get("final_tag")
        if status == "resolved":
            tags = json.loads(FULLBODY_TAGS_PATH.read_text(encoding="utf-8")).get("entries", [])
            selectable = {
                entry.get("serialized_value") for entry in tags
                if entry.get("tag_type") == "main" and entry.get("selectable")
                and not entry.get("requires_review")
            }
            if final_tag not in selectable:
                raise ValueError(f"Unverified Fullbody Final Tag mapping: {final_tag!r}.")
        elif (status != "unresolved" or final_tag is not None
              or not str(row.get("reason") or "").strip()):
            raise ValueError("Unresolved Fullbody mappings must not define a Final Tag.")
        by_name[name] = dict(row)
    registry_fullbody = {name for name in approved.values() if name.startswith("fullbody_")}
    if set(by_name) != registry_fullbody:
        raise ValueError("Every approved Fullbody YOLO class needs exactly one explicit Final Tag disposition.")
    return by_name
