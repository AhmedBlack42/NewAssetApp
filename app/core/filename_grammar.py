from __future__ import annotations

import json
import re
from pathlib import Path

from app.core.fullbody_classification import APP_ROOT, _validate_subtags


def _main_values(group: str, tag_types=("main",)) -> set[str]:
    filename = {"clothing": "clothing_tags.json", "body_images": "body_images_tags.json"}[group]
    payload = json.loads((APP_ROOT / "data" / "tags" / filename).read_text(encoding="utf-8"))
    values = {entry.get("serialized_value") for entry in payload.get("entries", [])
              if entry.get("tag_type") in tag_types and entry.get("selectable")
              and not entry.get("requires_review")}
    user_file = APP_ROOT / "data" / "tags" / "user_tags.json"
    if user_file.exists():
        values |= {entry.get("serialized_value") for entry in json.loads(user_file.read_text(encoding="utf-8")).get("entries", [])
                   if entry.get("group") == group and entry.get("tag_type") in tag_types
                   and not entry.get("deprecated")}
    return values


def clothing_filename(main_tag: str, sequence: int, subtags=()) -> str:
    if main_tag not in _main_values("clothing", ("main", "tag")):
        raise ValueError(f"Unverified Clothing main tag: {main_tag!r}")
    values = _validate_subtags("clothing", subtags)
    from app.core.classification_taxonomy import serialize_filename
    return serialize_filename([main_tag], values, sequence)


def parse_clothing_filename(filename: str) -> dict:
    from app.core.classification_taxonomy import parse_tag_filename
    try:
        parsed = parse_tag_filename(filename)
        if len(parsed["main_tags"]) != 1:
            raise ValueError("Clothing filenames have exactly one main tag.")
        main = parsed["main_tags"][0]
        if main not in _main_values("clothing", ("main", "tag")):
            raise ValueError("Clothing filename contains an unknown main tag.")
        _validate_subtags("clothing", parsed["subtags"])
        return {"main_tag": main, "subtags": parsed["subtags"],
                "sequence": parsed["sequence"], "filename": Path(filename).name,
                "source_metadata_only": True}
    except ValueError:
        pass
    name = Path(filename).name
    if not name.lower().endswith(".webp"):
        raise ValueError("Clothing filename must be a .webp image.")
    stem = name[:-5]
    match = re.search(r"(\d+)$", stem)
    sequence = int(match.group(1)) if match else None
    if sequence == 0:
        raise ValueError("Clothing sequence numbers must be positive.")
    base = stem[:match.start()] if match else stem
    mains = sorted(_main_values("clothing", ("main", "tag")), key=len, reverse=True)
    known_subtags = set(_known_subtags("clothing"))
    for main in mains:
        if base == main:
            return {"main_tag": main, "subtags": [], "sequence": sequence, "filename": name}
        prefix = main + "_"
        if base.startswith(prefix):
            subtags = base[len(prefix):].split(",")
            _validate_subtags("clothing", subtags)
            return {"main_tag": main, "subtags": subtags, "sequence": sequence, "filename": name}
    parts = base.split("_")
    recovered = []
    for index in range(len(parts) - 1, 0, -1):
        main = "_".join(parts[:index])
        subtags = "_".join(parts[index:]).split(",")
        if main in mains and all(tag in known_subtags for tag in subtags):
            recovered.append((len("_".join(parts[index:])), main, subtags))
    if recovered:
        _, main, subtags = max(recovered, key=lambda row: row[0])
        return {"main_tag": main, "subtags": subtags, "sequence": sequence, "filename": name}
    if base in mains:
        return {"main_tag": base, "subtags": [], "sequence": sequence, "filename": name}
    # Compatibility for the immediately preceding human-entered hyphen form.
    for main in mains:
        if base.startswith(main + "-"):
            subtags = base[len(main) + 1:].split(",")
            return {"main_tag": main, "subtags": subtags, "sequence": sequence,
                    "filename": name, "legacy_separator": "hyphen"}
    raise ValueError("Clothing filename does not match main_subtag1,subtag2N.webp.")


def body_images_filename(main_tags: list[str] | tuple[str, ...], sequence: int, subtags=(), *,
                         sub_main_tag: str | None = None) -> str:
    mains = [str(tag).strip() for tag in main_tags]
    available = _main_values("body_images")
    if not mains or len(mains) != len(set(mains)) or set(mains) - available:
        raise ValueError("Body Images needs distinct verified main tags in confirmed order.")
    if sub_main_tag:
        # Deprecated API compatibility: old composition selection now becomes
        # an ordinary subtag and is validated with the current pair allowlist.
        subtags = list(subtags) + [sub_main_tag]
    values = _validate_subtags("body_images", subtags)
    from app.core.classification_taxonomy import REGISTRY, serialize_filename
    supported = REGISTRY["body_images"]["supported_main_subtag_pairs"]
    pair_values = {tag for main in mains for tag in supported.get(main, [])}
    for value in {"cum", "creampie", "bb"}.intersection(values):
        if value not in pair_values:
            raise ValueError(f"Unsupported Body Images main/subtag combination: {value}")
    if {"cum", "creampie"}.issubset(values):
        raise ValueError("cum and creampie are mutually exclusive Body Images subtags.")
    return serialize_filename(mains, values, sequence)


def parse_body_images_filename(filename: str) -> dict:
    from app.core.classification_taxonomy import REGISTRY, parse_tag_filename
    try:
        parsed = parse_tag_filename(filename)
        available = _main_values("body_images")
        if set(parsed["main_tags"]) - available:
            raise ValueError("Body Images filename contains an unknown main tag.")
        _validate_subtags("body_images", parsed["subtags"])
        pair_values = {tag for main in parsed["main_tags"]
                       for tag in REGISTRY["body_images"]["supported_main_subtag_pairs"].get(main, [])}
        if {"cum", "creampie", "bb"}.intersection(parsed["subtags"]) - pair_values:
            raise ValueError("Body Images filename contains an unsupported main/subtag combination.")
        return {"main_tags": parsed["main_tags"], "sub_main_tag": None,
                "subtags": parsed["subtags"], "sequence": parsed["sequence"],
                "filename": Path(filename).name, "source_metadata_only": True}
    except ValueError:
        pass
    name = Path(filename).name
    if not name.lower().endswith(".webp"):
        raise ValueError("Body Images filename must be a .webp image.")
    stem = name[:-5]
    main_text, separator, sub_text = stem.partition("-")
    subtags = sub_text.split(",") if separator else []
    available = _main_values("body_images")
    composition = main_text
    policy_path = Path(__file__).resolve().parents[2] / "data" / "models" / "body_images_composition_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    fluid_pairs = set(policy.get("supported_fluid_submain_pairs", [])) | set(policy.get("supported_submain_pairs", []))
    fluid_match = re.fullmatch(r"(.+?)(\d+)", stem)
    if fluid_match:
        numbered = fluid_match.group(1)
        sequence = int(fluid_match.group(2))
        for pair in fluid_pairs:
            main, sub_main = pair.split("_", 1)
            prefix = f"{main}_{sub_main}"
            if numbered == prefix or numbered.startswith(prefix + "-"):
                raw_subtags = numbered[len(prefix):].removeprefix("-")
                values = raw_subtags.split(",") if raw_subtags else []
                if sequence < 1:
                    raise ValueError("Body Images sequence numbers must be positive.")
                if sub_main != "bb" and {"cum", "creampie"}.intersection(values):
                    raise ValueError("Body Images cum/creampie values cannot also be ordinary subtags.")
                _validate_subtags("body_images", values)
                return {"main_tags": [main], "sub_main_tag": None,
                        "legacy_composition_value": sub_main,
                        "subtags": list(dict.fromkeys([sub_main, *values])),
                        "sequence": sequence, "filename": name,
                        "source_metadata_only": True}
    if not separator:
        unnumbered = re.sub(r"\d+$", "", stem)
        if any(unnumbered.endswith("_" + tag) for tag in _known_subtags("body_images")):
            raise ValueError("Body Images subtags must follow the guide's hyphen separator.")
    # Single-main canonical form stores its only sequence at the end.
    single_match = re.fullmatch(r"([A-Za-z0-9_]+?)(?:-(.+?))?(\d+)", stem)
    if single_match and single_match.group(1) in available:
        main = single_match.group(1)
        subtags = single_match.group(2).split(",") if single_match.group(2) else []
        if {"cum", "creampie"}.intersection(subtags):
            raise ValueError("Body Images cum/creampie values require the bb sub-main composition.")
        _validate_subtags("body_images", subtags)
        sequence = int(single_match.group(3))
        if sequence < 1:
            raise ValueError("Body Images sequence numbers must be positive.")
        return {"main_tags": [main], "sub_main_tag": None, "subtags": subtags,
                "sequence": sequence, "filename": name, "source_metadata_only": True}
    # Guide grouped-main format: main1,main21-subtag1,subtag2.
    mains = []
    numbers = []
    for raw in main_text.split(","):
        match = re.fullmatch(r"([A-Za-z0-9_]+?)(\d+)", raw)
        if not match or match.group(1) not in available:
            raise ValueError("Body Images filename has invalid main tags or image-set sequence.")
        mains.append(match.group(1))
        numbers.append(int(match.group(2)))
    if not numbers or len(set(numbers)) != 1 or numbers[0] < 1:
        raise ValueError("Grouped Body Images main tags must share one positive image-set number.")
    if {"cum", "creampie"}.intersection(subtags):
        raise ValueError("Body Images cum/creampie values must use a supported sub-main composition.")
    _validate_subtags("body_images", subtags)
    return {"main_tags": mains, "sub_main_tag": None, "subtags": subtags,
            "sequence": numbers[0], "filename": name, "source_metadata_only": True}


def _known_subtags(category: str) -> list[str]:
    data_dir = APP_ROOT / "data" / "tags"
    filename = "clothing_tags.json" if category == "clothing" else "body_images_tags.json"
    payload = json.loads((data_dir / filename).read_text(encoding="utf-8"))
    values = {entry.get("serialized_value") for entry in payload.get("entries", [])
              if entry.get("tag_type") in {"subtag", "tag", "modifier"}
              and entry.get("selectable") and not entry.get("requires_review")}
    values |= set(json.loads((data_dir / "shared_corruption_tags.json").read_text(encoding="utf-8"))["values"])
    return sorted(values, key=len, reverse=True)
