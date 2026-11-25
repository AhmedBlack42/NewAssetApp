from __future__ import annotations

import json
from pathlib import Path

from app.core.tag_library import TagLibrary


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "data/models/clothing_classifier_registry.json"
TAG_LIBRARY = TagLibrary(ROOT / "data/tags")
PARENT_FAMILIES = {
    "bra": {"context|clothing|bra|bra", "gameclothing-category|bra"},
    "footwear": {"context|clothing|shoes|shoes", "gameclothing-category|shoes"},
    "outerwear": {"context|clothing|outer|outer", "gameclothing-category|outer"},
    "panty": {"context|clothing|panties|panties", "gameclothing-category|panties"},
    "pants": {"context|clothing|lower|lower", "gameclothing-category|lower"},
    "shorts": {"context|clothing|lower|lower", "gameclothing-category|lower"},
    "skirt": {"context|clothing|lower|lower", "gameclothing-category|lower"},
    "shirt": {"context|clothing|upper|upper", "gameclothing-category|upper"},
    "top": {"context|clothing|upper|upper", "gameclothing-category|upper"},
    "dress": {"context|clothing|upper|upper", "gameclothing-category|upper"},
    "socks": {"context|clothing|socks|socks", "gameclothing-category|socks"},
}


def clothing_classes() -> list[dict]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    classes = registry.get("classes", [])
    if len(classes) != 12 or [row.get("class_id") for row in classes] != list(range(12)):
        raise ValueError("Clothing registry must define exactly 12 ordered class IDs.")
    return classes


def suggested_clothing_tags(family: str) -> list[str]:
    if family not in {row["class_name"] for row in clothing_classes()}:
        return []
    rows = TAG_LIBRARY.entries(group="clothing", include_review=False)
    accepted = []
    for row in rows:
        if row.get("tag_type") not in {"main", "tag"}:
            continue
        value = str(row.get("serialized_value", ""))
        parent = str(row.get("parent_id", ""))
        if family in PARENT_FAMILIES and parent in PARENT_FAMILIES[family]:
            if family == "pants" and any(token in value for token in ("skirt", "short")):
                continue
            if family == "shorts" and "short" not in value:
                continue
            if family == "skirt" and "skirt" not in value:
                continue
            if family == "shirt" and not any(token in value for token in ("shirt", "blouse")):
                continue
            if family == "top" and not any(token in value for token in ("top", "corset")):
                continue
            if family == "dress" and "dress" not in value:
                continue
            accepted.append(value)
            continue
        if family == "lingerie" and value.startswith("lingerie_"):
            accepted.append(value)
    return sorted(set(accepted))


def validate_final_clothing_tag(family: str, tag: str) -> bool:
    if tag not in {row.get("serialized_value") for row in TAG_LIBRARY.entries(group="clothing", include_review=False)
                   if row.get("tag_type") in {"main", "tag"}}:
        return False
    suggestions = set(suggested_clothing_tags(family))
    return tag in suggestions
