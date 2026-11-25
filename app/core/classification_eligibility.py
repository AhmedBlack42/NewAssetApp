"""Central eligibility rules for human-confirmed detection classifications."""
from __future__ import annotations
import json
from pathlib import Path

from app.core.yolo_registry import approved_yolo_classes

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "task_eligibility_v1.json"
with _REGISTRY_PATH.open("r", encoding="utf-8") as _registry_file:
    TASK_ELIGIBILITY = json.load(_registry_file)


BODY_IMAGE_REGIONS = frozenset({"face", "boobs", "ass", "pussy", "legs"})
AROUSAL_REGIONS = frozenset({"person", "face", "boobs", "ass", "pussy", "legs"})
CORRUPTION_REGIONS = frozenset({
    "person", "portrait_frame", "face", "boobs", "ass", "pussy", "legs",
    "pussy_cover_item", "ass_cover_item", "boobs_cover_item",
    "leg_cover_item", "accessory_footwear",
})
AROUSAL_LABELS = frozenset({"aroused", "edging"})
FULLBODY_LABELS = frozenset({"clothed", "topless", "bottomless", "bra", "panty"})
BODY_IMAGES_LABELS = frozenset({"bodypart_cum", "bodypart_acc"})
PORTRAIT_LABELS = frozenset({"portrait", "tportrait"})
CORRUPTION_LABELS = frozenset({"conservative", "slut", "whore", "u_whore"})
SHARED_HEADS = ("body_images", "fullbody", "portrait", "arousal", "corruption")


def is_fullbody_region(region: str | None) -> bool:
    name = (region or "").strip().casefold()
    return name in {
        class_name.casefold() for class_name in approved_yolo_classes().values()
        if class_name.startswith("fullbody_")
    }


def required_tasks(region: str | None) -> tuple[str, ...]:
    """Return the approved required task identities for a YOLO region."""
    name = (region or "").strip().casefold()
    if name in set(TASK_ELIGIBILITY["historical_only"]):
        return ()
    if is_fullbody_region(name):
        tasks = TASK_ELIGIBILITY["fullbody_task_rule"]
    elif is_location_group(name):
        tasks = TASK_ELIGIBILITY["location_task_rule"]
    else:
        tasks = TASK_ELIGIBILITY["tasks"].get(name, [])
    return tuple(tasks)


def is_location_group(region: str | None) -> bool:
    """The approved YOLO registry represents its location_group with location_* classes."""
    name = (region or "").strip().casefold()
    return name in {
        class_name.casefold() for class_name in approved_yolo_classes().values()
        if class_name.startswith("location_")
    }


def arousal_eligible(region: str | None, *, confirmed_portrait: str | None = None) -> bool:
    name = (region or "").strip().casefold()
    if name in AROUSAL_REGIONS:
        return True
    return name == "portrait_frame"


def shared_head_eligible(head: str, region: str | None, *, confirmed_portrait: str | None = None) -> bool:
    del confirmed_portrait
    return head in required_tasks(region)


def eligible_shared_heads(region: str | None, *, confirmed_portrait: str | None = None) -> set[str]:
    return {
        head for head in SHARED_HEADS
        if shared_head_eligible(head, region, confirmed_portrait=confirmed_portrait)
    }
