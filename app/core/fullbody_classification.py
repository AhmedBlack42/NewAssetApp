from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
TAG_PATH = APP_ROOT / "data" / "tags" / "fullbody_tags.json"
POLICY_PATH = APP_ROOT / "data" / "models" / "fullbody_classification_policy.json"
OUTPUT_BY_STATE = {"clothed": "fullbody", "topless": "fullbody_topless",
                   "bottomless": "fullbody_bottomless"}
LEGACY_STATE_ALIASES = {"normal": "clothed"}


def verified_main_tag_values() -> list[dict]:
    tags = json.loads(TAG_PATH.read_text(encoding="utf-8"))
    return [dict(entry) for entry in tags.get("entries", [])
            if entry.get("tag_type") == "main" and entry.get("selectable")
            and not entry.get("requires_review")]


def fullbody_classification(main_tag: str, state_spec: str) -> dict:
    state_spec = LEGACY_STATE_ALIASES.get(state_spec, state_spec)
    entry = next((row for row in verified_main_tag_values()
                  if row.get("serialized_value") == main_tag
                  and main_tag not in {"topless", "bottomless"}), None)
    if not entry:
        raise ValueError(f"Fullbody main tag is not an approved selectable tag: {main_tag!r}")
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    output = OUTPUT_BY_STATE.get(state_spec)
    if output is None:
        raise ValueError("Fullbody state must be explicitly reviewed as clothed, topless, or bottomless.")
    compositions = policy["supported_compositions"]
    token = main_tag if state_spec == "clothed" else compositions.get(f"{main_tag}|{state_spec}")
    if token is None:
        raise ValueError(f"No documented Fullbody composition exists for {main_tag} + {state_spec}.")
    return {"main_tag": main_tag, "source_context": list(entry.get("context_path", [])),
            "state_spec": state_spec, "output_category": output,
            "serialized_filename_tag": token}


def fullbody_filename(main_tag: str, state_spec: str, sequence: int,
                      subtags: list[str] | tuple[str, ...] = ()) -> str:
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise ValueError("Filename sequence must be a positive integer.")
    fullbody_classification(main_tag, state_spec)
    values = _validate_subtags("fullbody", subtags)
    # State remains a dedicated structured field but is serialized as a subtag
    # so every category follows the same main[,main2]-subtag[,subtag2] grammar.
    from app.core.classification_taxonomy import serialize_filename
    return serialize_filename([main_tag], [state_spec, *values], sequence)


def _validate_subtags(category: str, subtags: list[str] | tuple[str, ...]) -> list[str]:
    values = [str(value).strip() for value in subtags]
    data_dir = APP_ROOT / "data" / "tags"
    shared = json.loads((data_dir / "shared_corruption_tags.json").read_text(encoding="utf-8"))["values"]
    payload = json.loads((data_dir / {"fullbody": "body_images_tags.json",
                                      "body_images": "body_images_tags.json",
                                      "clothing": "clothing_tags.json"}[category]).read_text(encoding="utf-8"))
    selectable = {entry.get("serialized_value") for entry in payload.get("entries", [])
                  if entry.get("tag_type") in {"subtag", "tag", "modifier"}
                  and entry.get("selectable") and not entry.get("requires_review")}
    if category == "fullbody":
        policy = json.loads((APP_ROOT / "data" / "models" / "fullbody_classification_policy.json").read_text(encoding="utf-8"))
        from app.core.classification_taxonomy import LOCATION_VALUES
        allowed = set(policy.get("supported_subtags", [])) | set(LOCATION_VALUES)
    else:
        from app.core.classification_taxonomy import LOCATION_VALUES
        allowed = selectable | set(shared) | set(LOCATION_VALUES)
        if category == "body_images":
            allowed |= {"cum", "creampie", "bb"}
    if len(values) != len(set(values)) or set(values) - allowed:
        raise ValueError(f"{category} contains an unsupported or duplicate subtag.")
    if any(not value or any(mark in value for mark in (",", "-")) for value in values):
        raise ValueError("Subtags must be individual exact tag values.")
    return values


def parse_fullbody_filename(filename: str) -> dict:
    """Parse definitive Fullbody grammar and unambiguous legacy app/guide forms."""
    import re
    name = Path(filename).name
    image_stem = name[:-5] if name.lower().endswith(".webp") else None
    if image_stem is None:
        raise ValueError("Fullbody filename must be a .webp image.")
    try:
        from app.core.classification_taxonomy import parse_tag_filename
        parsed = parse_tag_filename(name)
        states = {value for value in parsed["subtags"] if value in {"clothed", "topless", "bottomless"}}
        if len(parsed["main_tags"]) == 1 and len(states) == 1:
            main = parsed["main_tags"][0]
            state = next(iter(states))
            result = fullbody_classification(main, state)
            return {**result, "subtags": [value for value in parsed["subtags"] if value != state],
                    "sequence": parsed["sequence"], "sequence_format": "tag_suffix",
                    "sub_main_tag": None, "filename": name, "source_metadata_only": True}
    except ValueError:
        pass
    sequence_match = re.search(r"_?(\d+)$", image_stem)
    sequence = int(sequence_match.group(1)) if sequence_match else None
    if sequence == 0:
        raise ValueError("Fullbody sequence numbers must be positive.")
    legacy_underscore_sequence = bool(sequence_match and image_stem[sequence_match.start():].startswith("_"))
    stem = image_stem[:sequence_match.start()] if sequence_match else image_stem
    legacy_sequence = None
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    candidates = []
    for entry in verified_main_tag_values():
        main = entry["serialized_value"]
        for state in OUTPUT_BY_STATE:
            try:
                resolved = fullbody_classification(main, state)
            except ValueError:
                continue
            candidates.append((resolved["serialized_filename_tag"], main, state, resolved))
    candidates.extend((legacy, canonical.split("_")[0], "bottomless", None)
                      for legacy, canonical in policy.get("legacy_read_aliases", {}).items())
    legacy_separator = None
    token = stem
    subtags: list[str] = []
    # Canonical grammar: composition-subtag1,subtag2. Legacy guide uses a comma;
    # older app builds also wrote composition_subtag1 before the sequence.
    for candidate, main, state, resolved in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        if stem == candidate:
            token, subtags, legacy_separator = candidate, [], None
            break
        legacy_match = re.fullmatch(re.escape(candidate) + r"(\d+),(.+)", stem)
        if legacy_match:
            token, subtags = candidate, legacy_match.group(2).split(",")
            legacy_sequence = int(legacy_match.group(1))
            legacy_separator = "sequence_before_subtags"
            break
        for sep in ("-", ","):
            prefix = candidate + sep
            if stem.startswith(prefix):
                token = candidate
                subtags = stem[len(prefix):].split(",")
                legacy_separator = "guide_comma" if sep == "," else None
                break
        if subtags or stem == candidate:
            break
        # Earlier NewAssetApp build wrote composition_sharedSubtagN.
        for value in sorted(json.loads((APP_ROOT / "data" / "tags" / "shared_corruption_tags.json").read_text(encoding="utf-8"))["values"], key=len, reverse=True):
            if stem.startswith(candidate + "_" + value):
                token, subtags, legacy_separator = candidate, [value], "legacy_underscore_subtag"
                break
        if subtags:
            break
    if token == stem and not any(stem == candidate for candidate, *_ in candidates):
        raise ValueError("Fullbody filename does not match a verified main/state composition.")
    composition = next((resolved for candidate, _, _, resolved in candidates
                        if candidate == token and resolved is not None), None)
    if composition is None:
        alias = policy.get("legacy_read_aliases", {}).get(token)
        if alias:
            main, state = "clothed", "bottomless"
            composition = fullbody_classification(main, state)
        else:
            raise ValueError("Fullbody filename composition is not allowlisted.")
    subtags = _validate_subtags("fullbody", subtags)
    if sequence is not None and legacy_sequence is not None:
        raise ValueError("Fullbody filename contains more than one sequence number.")
    sequence = legacy_sequence if legacy_sequence is not None else sequence
    return {**composition, "sub_main_tag": None,
            "sequence": sequence, "sequence_format": "sequence_before_subtags" if legacy_sequence is not None else "underscore" if legacy_underscore_sequence else "direct" if sequence_match else None,
            "legacy_separator": legacy_separator, "subtags": subtags, "filename": name,
            "source_metadata_only": True}
