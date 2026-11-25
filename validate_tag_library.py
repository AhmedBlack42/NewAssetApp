from __future__ import annotations

import argparse
import json
from pathlib import Path

GROUP_FILES = {
    "fullbody": "fullbody_tags.json",
    "body_images": "body_images_tags.json",
    "photoshoots": "photoshoot_tags.json",
    "clothing": "clothing_tags.json",
}
REQUIRED_FIELDS = {
    "id", "name", "group", "parent_id", "tag_type", "description",
    "examples", "separators", "source", "source_reference", "confidence",
    "requires_review",
}
TAG_TYPES = {"main", "subtag", "modifier", "compound", "metadata", "tag"}
CONFIDENCE = {"confirmed", "probable", "uncertain"}
SEPARATORS = {"<", ">", "-", "_", ",", " ", ".", "/"}


def validate_tag_library(data_dir: Path | str) -> list[str]:
    """Validate extracted JSON without normalizing or rewriting original tags."""
    root = Path(data_dir)
    errors: list[str] = []
    all_entries: list[dict] = []
    by_id: dict[str, dict] = {}
    per_group: dict[str, list[dict]] = {}
    for group, filename in GROUP_FILES.items():
        path = root / filename
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{filename}: cannot read valid JSON ({exc})")
            continue
        if payload.get("group") != group:
            errors.append(f"{filename}: group must be {group!r}")
        entries = payload.get("entries")
        if not isinstance(entries, list):
            errors.append(f"{filename}: entries must be an array")
            continue
        per_group[group] = entries
        for index, entry in enumerate(entries):
            label = f"{filename} entries[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{label}: entry must be an object")
                continue
            missing = REQUIRED_FIELDS - entry.keys()
            if missing:
                errors.append(f"{label}: missing fields {sorted(missing)}")
            if entry.get("group") != group:
                errors.append(f"{label}: incorrect group {entry.get('group')!r}")
            if entry.get("tag_type") not in TAG_TYPES:
                errors.append(f"{label}: invalid tag_type {entry.get('tag_type')!r}")
            if entry.get("confidence") not in CONFIDENCE:
                errors.append(f"{label}: invalid confidence {entry.get('confidence')!r}")
            if not isinstance(entry.get("requires_review"), bool):
                errors.append(f"{label}: requires_review must be boolean")
            if not isinstance(entry.get("examples"), list):
                errors.append(f"{label}: examples must be an array")
            if not isinstance(entry.get("separators"), list):
                errors.append(f"{label}: separators must be an array")
            else:
                for separator in entry["separators"]:
                    if separator not in SEPARATORS:
                        errors.append(f"{label}: invalid separator {separator!r}")
            entry_id = entry.get("id")
            if not isinstance(entry_id, str) or not entry_id:
                errors.append(f"{label}: id must be a nonempty string")
            elif entry_id in by_id:
                errors.append(f"{label}: duplicate id {entry_id!r}")
            else:
                by_id[entry_id] = entry
            all_entries.append(entry)

    for group, entries in per_group.items():
        local = {e.get("id"): e for e in entries if isinstance(e, dict)}
        parent_of: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            parent = entry.get("parent_id")
            if parent is None:
                continue
            target = local.get(parent)
            if target is None:
                errors.append(f"{group}: {entry['id']!r} has missing or cross-group parent {parent!r}")
            elif target.get("group") != group:
                errors.append(f"{group}: {entry['id']!r} parent belongs to {target.get('group')!r}")
            else:
                parent_of[entry["id"]] = parent
        for entry_id in parent_of:
            seen: set[str] = set()
            current = entry_id
            while current in parent_of:
                if current in seen:
                    errors.append(f"{group}: circular parent hierarchy at {current!r}")
                    break
                seen.add(current)
                current = parent_of[current]

    seen_tags: dict[tuple, str] = {}
    canonical_spellings: dict[tuple[str, str], tuple[str, str]] = {}
    canonical_types: dict[tuple[str, str], tuple[str, str]] = {}
    for entry in all_entries:
        value = entry.get("serialized_value")
        if value is None or not entry.get("selectable", True):
            continue
        key = (entry.get("group"), tuple(entry.get("context_path", [])), value)
        if key in seen_tags:
            errors.append(f"duplicate tag in context {key}: {seen_tags[key]!r} and {entry.get('id')!r}")
        else:
            seen_tags[key] = entry.get("id", "<missing id>")
        normalized_key = (str(entry.get("group")), str(value).casefold())
        spelling = canonical_spellings.get(normalized_key)
        if spelling and spelling[0] != value:
            errors.append(f"case-insensitive spelling collision in {entry.get('group')}: {spelling[0]!r} and {value!r}")
        else:
            canonical_spellings[normalized_key] = (str(value), entry.get("id", "<missing id>"))
        prior_type = canonical_types.get(normalized_key)
        if prior_type and prior_type[0] != entry.get("tag_type"):
            errors.append(f"conflicting tag types for canonical value {value!r} in {entry.get('group')}: {prior_type[0]!r} and {entry.get('tag_type')!r}")
        else:
            canonical_types[normalized_key] = (entry.get("tag_type"), entry.get("id", "<missing id>"))

    try:
        grammar = json.loads((root / "tag_grammar.json").read_text(encoding="utf-8"))
        tokens = grammar.get("tokens")
        if not isinstance(tokens, dict):
            errors.append("tag_grammar.json: tokens must be an object")
        else:
            for token, spec in tokens.items():
                if token not in SEPARATORS or not isinstance(spec, dict) or "status" not in spec:
                    errors.append(f"tag_grammar.json: invalid separator definition {token!r}")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"tag_grammar.json: cannot read valid JSON ({exc})")

    try:
        review = json.loads((root / "tag_review_required.json").read_text(encoding="utf-8"))
        review_ids = {tag_id for item in review.get("entries", []) if isinstance(item, dict)
                      for tag_id in item.get("affected_tag_ids", [])}
        for entry in all_entries:
            if entry.get("requires_review") and entry.get("id") not in review_ids:
                errors.append(f"tag_review_required.json: missing ambiguous entry {entry.get('id')!r}")
        for tag_id in review_ids:
            if tag_id not in by_id:
                errors.append(f"tag_review_required.json: references unknown tag id {tag_id!r}")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"tag_review_required.json: cannot read valid JSON ({exc})")

    try:
        inventory = json.loads((root / "tag_inventory.json").read_text(encoding="utf-8"))
        indexed = [e.get("id") for e in inventory.get("entries", [])]
        actual = [e.get("id") for e in all_entries if isinstance(e, dict)]
        if indexed != actual:
            errors.append("tag_inventory.json: derived entries do not match group JSON files")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"tag_inventory.json: cannot read valid JSON ({exc})")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate tag JSON without rewriting tags.")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent / "data" / "tags")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    errors = validate_tag_library(args.data_dir)
    result = {"valid": not errors, "errors": errors, "data_dir": str(args.data_dir)}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
