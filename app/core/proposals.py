from __future__ import annotations

from dataclasses import dataclass
import math

from app.core.yolo_registry import (
    approved_yolo_classes,
    approved_yolo_class_ids,
    fullbody_final_tag_mapping,
    is_approved_yolo_identity,
)


# Exact Asset CNN labels inspected in Girl Packer's model registry/class map.
# No label maps to Photoshoots; assignment there is always a human decision.
BODY_IMAGE_TYPES = {
    "bodypart_ass": "ass", "bodypart_boobs": "boobs",
    "bodypart_face": "face", "bodypart_legs": "legs",
    "bodypart_portrait_clothed": "portrait",
    "bodypart_portrait_topless": "tportrait", "bodypart_pussy": "pussy",
}
# Resolved tags are suggestions only; the registry class remains detection evidence.
YOLO_FULLBODY_MAIN_TAGS = {
    name: row["final_tag"] for name, row in fullbody_final_tag_mapping().items()
    if row["status"] == "resolved"
}
# Canonical broad classes retain their model identity. Only legacy labels that
# are not active broad classes use the historical detailed-category crosswalk.
CLOTHING_BROAD_CLASSES = {
    "bra", "dress", "footwear", "lingerie", "outerwear", "pants", "panty",
    "shirt", "shorts", "skirt", "socks", "top",
}
CLOTHING_LEGACY_CATEGORY_CROSSWALK = {
    "pantyhose": "socks", "stockings": "socks", "vest": "upper",
}
CLOTHING_MODEL_CATEGORY_CROSSWALK = {
    **{name: name for name in CLOTHING_BROAD_CLASSES},
    **CLOTHING_LEGACY_CATEGORY_CROSSWALK,
}
YOLO_BODY_IMAGE_MAIN_CANDIDATES = {
    "face": "face", "boobs": "boobs", "ass": "ass", "pussy": "pussy", "legs": "legs",
}
YOLO_CLOTHING_REGION_NAMES = frozenset({
    "pussy_cover_item", "ass_cover_item", "boobs_cover_item", "leg_cover_item",
    "accessory_footwear",
})
YOLO_CLOTHING_REGION_CLASSES = {
    class_id for class_id, name in approved_yolo_classes().items()
    if name in YOLO_CLOTHING_REGION_NAMES
}
NORMAL_CNN_SUGGESTION_THRESHOLD = 0.77


def active_yolo_class_ids() -> set[int]:
    return approved_yolo_class_ids()


def yolo_detection_disposition(class_id: int, class_name: str, confidence: float,
                               bbox_xyxy: list[float]) -> dict:
    """Return an auditable routing decision without converting detections to labels."""
    if not is_approved_yolo_identity(class_id, class_name):
        return {"status": "review_required", "candidate_category": "others",
                "asset_type": None, "training_eligible": False,
                "reason": "Detection ID/name is not an exact match for the approved YOLO registry; retain as historical evidence only.",
                "original_yolo": {"class_id": class_id, "class_name": class_name,
                                  "confidence": confidence, "bbox_xyxy": list(bbox_xyxy)}}
    if class_id == 0 and class_name == "person":
        return {"status": "review_required", "candidate_category": "others",
                "asset_type": "person", "training_eligible": False,
                "reason": ("Person box is a review-only crop candidate for human-labeled corruption-state "
                           "CNN data; it is not a Fullbody classification."),
                "original_yolo": {"class_id": class_id, "class_name": class_name,
                                  "confidence": confidence, "bbox_xyxy": list(bbox_xyxy)}}
    if class_id in YOLO_CLOTHING_REGION_CLASSES:
        return {"status": "review_required", "candidate_category": "clothing",
                "asset_type": None, "training_eligible": False,
                "reason": "YOLO detected a clothing coverage region; Clothing CNN family output and exact human tag remain separate.",
                "original_yolo": {"class_id": class_id, "class_name": class_name,
                                  "confidence": confidence, "bbox_xyxy": list(bbox_xyxy)}}
    if class_name in YOLO_BODY_IMAGE_MAIN_CANDIDATES or class_name == "portrait_frame":
        return {"status": "review_required", "candidate_category": "body_images",
                "asset_type": YOLO_BODY_IMAGE_MAIN_CANDIDATES.get(class_name), "training_eligible": False,
                "reason": ("YOLO body-region evidence is only a Body Images candidate; reviewer may reject or correct it."
                           if class_name != "portrait_frame" else
                           "portrait_frame does not distinguish portrait from tportrait; reviewer confirmation is required."),
                "original_yolo": {"class_id": class_id, "class_name": class_name,
                                  "confidence": confidence, "bbox_xyxy": list(bbox_xyxy)}}
    candidate = YOLO_FULLBODY_MAIN_TAGS.get(class_name)
    fullbody_class = class_name.startswith("fullbody_")
    return {"status": "review_required", "candidate_category": "fullbody" if fullbody_class else "others",
            "asset_type": candidate, "training_eligible": False,
            "reason": ("YOLO Fullbody main-type candidate; user verification and a separate state decision are required."
                       if fullbody_class else
                       "YOLO evidence is retained for review; confirm its asset or context interpretation."),
            "original_yolo": {"class_id": class_id, "class_name": class_name,
                              "confidence": confidence, "bbox_xyxy": list(bbox_xyxy)}}


def valid_normal_cnn_suggestion(model_id: str | None, status: str | None,
                                class_name: str | None, confidence,
                                yolo_region: str | None) -> bool:
    if model_id != "clothing_classifier" or status != "ok":
        return False
    try:
        score = float(confidence)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(score) or not NORMAL_CNN_SUGGESTION_THRESHOLD <= score <= 1:
        return False
    from app.core.clothing_taxonomy import clothing_classes
    from app.core.classification_eligibility import shared_head_eligible
    return (class_name in {item["class_name"] for item in clothing_classes()}
            and shared_head_eligible("clothing_broad", yolo_region))


@dataclass(frozen=True)
class ProposalSuggestion:
    category: str
    asset_type: str | None
    confidence: float | None
    review_status: str
    reason: str


def suggest_proposal(class_name: str | None, confidence: float | None,
                     threshold: float = 0.77) -> ProposalSuggestion:
    if not class_name:
        return ProposalSuggestion("others", None, confidence, "review_required",
                                  "CNN did not return a supported class.")
    confidence_valid = confidence is not None and 0.0 <= confidence <= 1.0
    review_status = "pending" if confidence_valid and confidence > threshold else "review_required"
    confidence_reason = ("CNN confidence is missing or invalid." if not confidence_valid else
                         "CNN confidence is below the configured review threshold."
                         if confidence < threshold else None)
    if class_name in BODY_IMAGE_TYPES:
        return ProposalSuggestion("body_images", BODY_IMAGE_TYPES[class_name], confidence,
                                  review_status,
                                  confidence_reason or "Mapped from the inspected Asset CNN class map.")
    if class_name in CLOTHING_MODEL_CATEGORY_CROSSWALK:
        return ProposalSuggestion(
            "clothing", CLOTHING_MODEL_CATEGORY_CROSSWALK[class_name], confidence, review_status,
            confidence_reason or "Mapped to a source-defined Clothing category; select and confirm a specific garment tag.")
    return ProposalSuggestion("others", class_name, confidence, "review_required",
                              "Class has no verified output-category mapping.")
