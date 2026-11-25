from __future__ import annotations

import json
import re
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = APP_ROOT / "data" / "models" / "classification_taxonomy_v1.json"
REGISTRY = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
REGISTRY_ID = REGISTRY["registry_id"]
REGISTRY_VERSION = REGISTRY["version"]
LOCATION_VALUES = tuple(REGISTRY["locations"]["canonical_values"])
LEGACY_FULLBODY_POLICY_VERSION = "fullbody_legacy_state_candidates_v1"
LEGACY_ASSET_CNN_ID = "asset_cnn"
LEGACY_ASSET_CNN_DIGEST = "eb1251dade9293098e327f3e708bf92f0c5fc09c272c6cddb0f4f04f210ae6d2"


def legacy_fullbody_state_candidate(class_name: str | None, *, model_id: str | None = None,
                                    checkpoint_digest: str | None = None) -> dict | None:
    """Return an advisory legacy Asset CNN state candidate, never a confirmation."""
    if model_id != LEGACY_ASSET_CNN_ID or (checkpoint_digest or "").lower() != LEGACY_ASSET_CNN_DIGEST:
        return None
    if class_name in {"fullbody_clothed_states", "fullbody_costume_states"}:
        return {"candidate": "clothed", "ambiguous": False,
                "policy_version": LEGACY_FULLBODY_POLICY_VERSION,
                "human_decision_required": True}
    if class_name == "fullbody_nude_states":
        return {"candidate": None, "choices": ["topless", "bottomless"],
                "ambiguous": True, "policy_version": LEGACY_FULLBODY_POLICY_VERSION,
                "human_decision_required": True}
    return None


def location_candidates(evidence_name: str | None, *, registry_id: str | None = None,
                        model_id: str | None = None, class_id: int | None = None,
                        checkpoint_digest: str | None = None) -> list[str]:
    """Return advisory choices only when the evidence has a verified registry identity."""
    target_registry_id = "newassetapp_yolo_detector_v1"
    choices = REGISTRY["locations"]["suggestions_by_target_yolo_evidence"]
    if registry_id == target_registry_id:
        return list(choices.get(evidence_name, []))
    # Reuse suggestions for exact name/ID overlaps in the preserved 32-class
    # checkpoint; this does not reinterpret that model as the new target model.
    legacy_ids = {"location_home": 12, "location_class": 13, "location_office": 14,
                  "location_bathroom": 15, "location_bar": 16}
    expected_digest = "57449664aa24427c703770ae155a361da252f26be4840242aae95f3017df58ea"
    if (model_id == "legacy_yolo" and checkpoint_digest == expected_digest
            and class_id == legacy_ids.get(evidence_name)):
        return list(choices.get(evidence_name, []))
    return []


def validate_record(task: str, payload: dict) -> None:
    """Validate applicable human fields against the current versioned taxonomy."""
    if task not in {"fullbody", "body_images", "clothing", "others"}:
        raise ValueError(f"Unknown classification task: {task!r}")
    subtags = payload.get("subtags", [])
    if not isinstance(subtags, (list, tuple)) or len(subtags) != len(set(subtags)):
        raise ValueError("Subtags must be a unique list of exact registry values.")
    if task == "body_images":
        mains = payload.get("main_tags") or ([payload.get("main_tag")] if payload.get("main_tag") else [])
        allowed = set(REGISTRY["body_images"]["main_categories"])
        if not mains or set(mains) - allowed:
            raise ValueError("Body Images needs one or more exact main categories from the taxonomy.")
        pairs = REGISTRY["body_images"]["supported_main_subtag_pairs"]
        pair_subtags = set().union(*(set(pairs.get(main, [])) for main in mains))
        ordinary = set(REGISTRY["body_images"]["subtags"]) | set(_category_subtags("body_images"))
        if set(subtags) - (ordinary | pair_subtags):
            raise ValueError("Body Images contains an unknown subtag.")
        for value in ("cum", "creampie", "bb"):
            if value in subtags and value not in pair_subtags:
                raise ValueError(f"{value!r} is not supported for the selected Body Images main category.")
        if {"cum", "creampie"}.issubset(subtags):
            raise ValueError("cum and creampie are mutually exclusive subtags.")
    elif task == "fullbody":
        from app.core.fullbody_classification import fullbody_classification, _validate_subtags
        fullbody_classification(payload.get("main_tag", ""), payload.get("state_spec", ""))
        _validate_subtags("fullbody", list(subtags))
    elif task == "clothing":
        from app.core.filename_grammar import _main_values, _validate_subtags
        main = payload.get("main_tag")
        if main not in _main_values("clothing", ("main", "tag")):
            raise ValueError(f"Unknown Clothing main tag: {main!r}")
        _validate_subtags("clothing", list(subtags))
    location = payload.get("location") or payload.get("location_tag")
    if location and location not in LOCATION_VALUES:
        raise ValueError(f"Unknown canonical location: {location!r}")
    if payload.get("validity_state") not in {None, "", *REGISTRY["validity_values"]}:
        raise ValueError("Unknown classification validity state.")
    review_state = payload.get("human_review_state")
    if review_state and review_state not in REGISTRY["review_states"]:
        raise ValueError("Unknown human review state.")


def serialize_filename(main_tags: list[str] | tuple[str, ...], subtags=(), sequence: int = 1) -> str:
    """Serialize taxonomy tags as main[,main2]-subtag[,subtag2]N.webp."""
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("Filename sequence must be a positive integer.")
    mains = [str(value).strip() for value in main_tags]
    values = [str(value).strip() for value in subtags]
    if not mains or len(mains) != len(set(mains)) or any(not _valid_token(x) for x in mains):
        raise ValueError("Filename needs unique, non-empty main tags.")
    if len(values) != len(set(values)) or any(not _valid_token(x) for x in values):
        raise ValueError("Filename subtags must be unique, non-empty values.")
    return ",".join(mains) + ("-" + ",".join(values) if values else "") + f"{sequence}.webp"


def parse_tag_filename(filename: str) -> dict:
    """Parse tag-shaped names for display/audit only; callers must never hydrate labels from this."""
    name = Path(filename).name
    if not name.lower().endswith(".webp"):
        raise ValueError("Tagged filename must use .webp.")
    stem = name[:-5]
    match = re.fullmatch(r"(.+?)(\d+)", stem)
    if not match:
        raise ValueError("Tagged filename lacks a collision-safe sequence number.")
    label_part, sequence_text = match.groups()
    main_text, separator, sub_text = label_part.partition("-")
    mains = main_text.split(",")
    subtags = sub_text.split(",") if separator else []
    if not mains or any(not _valid_token(x) for x in mains + subtags) or len(set(mains)) != len(mains) or len(set(subtags)) != len(subtags):
        raise ValueError("Tagged filename contains invalid or duplicate values.")
    return {"main_tags": mains, "subtags": subtags,
            "sequence": int(sequence_text), "filename": name,
            "source_metadata_only": True}


def _valid_token(value: str) -> bool:
    return bool(value) and bool(re.fullmatch(r"[A-Za-z0-9_]+", value))


def _category_subtags(category: str) -> list[str]:
    path = APP_ROOT / "data" / "tags" / "body_images_tags.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [entry["serialized_value"] for entry in payload.get("entries", [])
            if entry.get("tag_type") in {"subtag", "tag", "modifier"}
            and entry.get("serialized_value") and entry.get("selectable")
            and not entry.get("requires_review")]
