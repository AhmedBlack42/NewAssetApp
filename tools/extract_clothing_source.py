"""Safely extract literal Clothing records from the pasted game source.

This tool parses Python syntax and uses ast.literal_eval only. It never imports
or executes the game source file.
"""
from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "extract_clothing_tags.txt"
TAGS = ROOT / "data" / "tags"
SOURCE_ID = "extract_clothing_tags.txt"
BODY_PART_TO_YOLO = {
    "boobs": "boobs_cover", "legs": "legs_cover",
    "ass": "ass_cover", "pussy": "pussy_cover",
}


def literal(node: ast.AST):
    return ast.literal_eval(node)


def field_map(call: ast.Call) -> dict:
    result = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            raise ValueError(f"Expanded keyword at source line {keyword.lineno}")
        try:
            result[keyword.arg] = literal(keyword.value)
        except (ValueError, TypeError, SyntaxError):
            result[keyword.arg] = {"source_expression": ast.unparse(keyword.value)}
    return result


def field_type_map(call: ast.Call) -> dict[str, str]:
    result = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            raise ValueError(f"Expanded keyword at source line {keyword.lineno}")
        try:
            result[keyword.arg] = type(literal(keyword.value)).__name__
        except (ValueError, TypeError, SyntaxError):
            result[keyword.arg] = "expression"
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assignment_name(node: ast.Assign) -> str | None:
    return next((target.id for target in node.targets if isinstance(target, ast.Name)), None)


def direct_category_assignments(tree: ast.Module) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Name):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Subscript)):
                continue
            if ast.unparse(target.value.value) != "database_clothing_items":
                continue
            try:
                category, item_key = literal(target.value.slice), literal(target.slice)
            except (ValueError, TypeError):
                continue
            result[node.value.id].append({
                "category": category, "key": item_key,
                "line": node.lineno, "end_line": node.end_lineno,
            })
    return result


def headings_by_line(tree: ast.Module) -> list[tuple[int, str]]:
    values = []
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            title = node.value.value.strip()
            if title:
                values.append((node.lineno, title))
    return values


def current_heading(headings: list[tuple[int, str]], line: int) -> str | None:
    preceding = [title for heading_line, title in headings if heading_line < line]
    return preceding[-1] if preceding else None


def build_record(*, call: ast.Call, category: str, catalog_key: str,
                 variable: str | None, origin: str, line: int, end_line: int,
                 heading: str | None) -> dict:
    attributes = field_map(call)
    attribute_types = field_type_map(call)
    covered = attributes.get("covered_parts")
    if isinstance(covered, (list, tuple)):
        covered_parts, missing_coverage = list(covered), False
    elif covered is None:
        covered_parts, missing_coverage = None, "covered_parts" not in attributes
    else:
        covered_parts, missing_coverage = covered, False

    mapped, unmapped = [], []
    if isinstance(covered_parts, list):
        for part in covered_parts:
            target = BODY_PART_TO_YOLO.get(part) if isinstance(part, str) else None
            if target:
                mapped.append({"source_part": part, "yolo_group": target})
            else:
                unmapped.append(part)
    return {
        "record_id": f"gameclothing-item|{category}|{catalog_key}",
        "source_identifier": attributes.get("id"),
        "source_python_variable": variable,
        "source_catalog_key": catalog_key,
        "source_category": category,
        "source_section": heading,
        "source_reference": f"{SOURCE_ID}:L{line}-L{end_line}",
        "source_definition_kind": origin,
        "source_attributes": attributes,
        "source_attribute_python_types": attribute_types,
        "source_fields_present": list(attributes),
        "source_fields_missing_from_inventory_union": [],
        "explicit_covered_parts": covered_parts,
        "coverage_group_mappings": mapped,
        "unmapped_covered_parts": unmapped,
        "coverage_mapping_status": (
            "source_field_missing" if missing_coverage else
            "source_field_not_a_literal_list" if not isinstance(covered_parts, list) else
            "explicit_mapping_with_unmapped_parts" if mapped and unmapped else
            "explicit_source_mapping" if mapped else
            "source_parts_do_not_name_supported_body_regions"
        ),
    }


def main() -> int:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    marker = next((i for i, line in enumerate(lines) if line.startswith("THIS IS the source code")), len(lines))
    source_lines = lines[:marker]
    tree = ast.parse("\n".join(source_lines) + "\n", filename=str(SOURCE))
    headings = headings_by_line(tree)
    direct_destinations = direct_category_assignments(tree)
    records: list[dict] = []
    direct_calls: dict[str, ast.Call] = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if not isinstance(node.value.func, ast.Name) or node.value.func.id != "Clothing":
            continue
        name = assignment_name(node)
        if name is None:
            raise ValueError(f"Unassigned Clothing() call at line {node.lineno}")
        direct_calls[name] = node.value
        destinations = direct_destinations.get(name, [])
        if not destinations:
            raise ValueError(f"No database_clothing_items destination for {name!r}")
        for destination in destinations:
            records.append(build_record(
                call=node.value, category=destination["category"], catalog_key=destination["key"],
                variable=name, origin="named_clothing_definition", line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                heading=current_heading(headings, node.lineno),
            ))

    catalog_assign = next(
        node for node in tree.body if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "database_clothing_items" for target in node.targets
        )
    )
    catalog_node = catalog_assign.value
    if not isinstance(catalog_node, ast.Dict):
        raise ValueError("database_clothing_items is not a literal dictionary")
    catalog_counts = {}
    for category_node, items_node in zip(catalog_node.keys, catalog_node.values):
        category = literal(category_node)
        if not isinstance(items_node, ast.Dict):
            raise ValueError(f"Nonliteral item dictionary in category {category!r}")
        catalog_counts[category] = len(items_node.keys)
        for item_key_node, call in zip(items_node.keys, items_node.values):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "Clothing":
                raise ValueError(f"Non-Clothing item at line {call.lineno}")
            records.append(build_record(
                call=call, category=category, catalog_key=literal(item_key_node), variable=None,
                origin="database_clothing_items_literal", line=call.lineno,
                end_line=call.end_lineno or call.lineno, heading="database_clothing_items",
            ))

    field_union = sorted({field for record in records for field in record["source_attributes"]})
    for record in records:
        record["source_fields_missing_from_inventory_union"] = [
            field for field in field_union if field not in record["source_attributes"]
        ]
    quality_assign = next(
        node for node in tree.body if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "database_clothing_quality_tags" for target in node.targets
        )
    )
    quality_tags = literal(quality_assign.value)
    key_counts = Counter((r["source_category"], r["source_catalog_key"]) for r in records)
    if any(count > 1 for count in key_counts.values()):
        raise ValueError("Duplicate source catalog key within a category")

    inventory = {
        "schema_version": 1,
        "source": {
            "path": SOURCE_ID, "sha256": sha256(SOURCE),
            "total_file_lines": len(lines), "parsed_source_lines": len(source_lines),
            "trailing_non_source_lines": list(range(marker + 1, len(lines) + 1)),
            "trailing_non_source_note": "A natural-language user instruction follows the Python source; it was not executed or treated as clothing data.",
            "source_language": "Python syntax parsed with ast.parse; no source execution",
            "clothing_definition_calls": len(direct_calls),
            "literal_catalog_category_count": len(catalog_counts),
            "literal_catalog_item_count": sum(catalog_counts.values()),
            "total_extracted_clothing_records": len(records),
            "catalog_definition_line": catalog_assign.lineno,
            "quality_tag_definition_line": quality_assign.lineno,
            "quality_tag_category_count": len(quality_tags),
            "observed_source_fields": field_union,
            "item_fields_not_present": ["price", "value", "coverage"],
            "field_context_note": "Clothing records use base_value and covered_parts; the separate quality-tag modifier mapping uses value. No aliases or numeric reinterpretations are added.",
        },
        "catalog_category_counts": catalog_counts,
        "records": records,
        "quality_tag_definitions": {
            "source_reference": f"{SOURCE_ID}:L{quality_assign.lineno}-L{len(source_lines)}",
            "description": "Full literal database_clothing_quality_tags mapping preserved separately; these are item quality/modifier choices, not garments or model classes.",
            "values": quality_tags,
        },
    }

    review_entries, coverage_entries = [], []
    for record in records:
        coverage_entries.append({
            "record_id": record["record_id"], "source_identifier": record["source_identifier"],
            "source_category": record["source_category"], "source_reference": record["source_reference"],
            "source_field": "covered_parts" if "covered_parts" in record["source_attributes"] else None,
            "explicit_covered_parts": record["explicit_covered_parts"],
            "yolo_coverage_groups": [item["yolo_group"] for item in record["coverage_group_mappings"]],
            "mapping_evidence": record["coverage_group_mappings"],
            "unmapped_source_parts": record["unmapped_covered_parts"],
            "status": record["coverage_mapping_status"],
        })
        status = record["coverage_mapping_status"]
        if status == "explicit_source_mapping":
            continue
        reason = {
            "explicit_mapping_with_unmapped_parts": "Some source covered_parts values map literally to a requested YOLO body region and others do not.",
            "source_field_missing": "The source record has no covered_parts field; coverage must not be inferred from category or appearance.",
            "source_parts_do_not_name_supported_body_regions": "The source covered_parts values do not explicitly name one of the four YOLO body regions.",
        }.get(status, "The source coverage value is not a literal list and needs review.")
        review_entries.append({
            "record_id": record["record_id"], "source_identifier": record["source_identifier"],
            "source_category": record["source_category"], "source_reference": record["source_reference"],
            "exact_source_value": record["explicit_covered_parts"], "reason": reason,
            "decision_needed": "Whether an additional source rule exists for these values; do not infer a YOLO coverage class yet.",
        })

    taxonomy_path = TAGS / "clothing_tags.json"
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    taxonomy["entries"] = [entry for entry in taxonomy["entries"]
                            if entry.get("asset_context") != "game_source_clothing"
                            and entry.get("node_kind") != "source_taxonomy_context"]
    categories = sorted({record["source_category"] for record in records})
    new_entries = []
    for category in categories:
        new_entries.append({
            "id": f"gameclothing-category|{category}", "name": category,
            "display_name": category, "group": "clothing", "parent_id": None,
            "tag_type": "metadata", "description": "Source-defined game clothing catalog category; separate from the standalone clothing asset slot.",
            "examples": [], "separators": [], "source": SOURCE_ID,
            "source_reference": f"{SOURCE_ID}:L{catalog_assign.lineno}", "confidence": "confirmed",
            "requires_review": False, "selectable": False,
            "context_path": ["game_source_clothing", category],
            "node_kind": "source_taxonomy_context", "asset_context": "game_source_clothing",
            "source_category": category,
        })
    for record in records:
        attrs = record["source_attributes"]
        sentinel = attrs.get("id") == "none" and attrs.get("name") == "None"
        label = str(attrs.get("name", attrs.get("id", record["source_catalog_key"])))
        new_entries.append({
            "id": record["record_id"], "name": label, "display_name": label,
            "group": "clothing", "parent_id": f"gameclothing-category|{record['source_category']}",
            "tag_type": "metadata" if sentinel else "main",
            "description": "Explicit source catalog item. Its source metadata and coverage evidence are separate; CNN mappings are not asserted.",
            "examples": [], "separators": [], "source": SOURCE_ID,
            "source_reference": record["source_reference"], "confidence": "confirmed",
            "requires_review": False, "selectable": not sentinel,
            "context_path": ["game_source_clothing", record["source_category"]],
            "serialized_value": attrs.get("id"), "source_key": record["source_catalog_key"],
            "source_identifier": record["source_identifier"], "asset_context": "game_source_clothing",
            "source_category": record["source_category"], "source_attributes": attrs,
            "source_attribute_python_types": record["source_attribute_python_types"],
        })
    taxonomy["source_files"] = list(dict.fromkeys(taxonomy.get("source_files", []) + [SOURCE_ID]))
    taxonomy["description"] = "Existing guide-derived vocabulary plus a distinct source-defined game catalog hierarchy. The game catalog is human-selectable; it does not establish model-label mappings."
    taxonomy["entries"].extend(new_entries)

    TAGS.mkdir(parents=True, exist_ok=True)
    (TAGS / "clothing_source_inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (TAGS / "clothing_review_required.json").write_text(json.dumps({
        "schema_version": 1, "source": SOURCE_ID,
        "summary": "Source-derived coverage mappings left unresolved where covered_parts is absent or does not exactly name a supported YOLO body region.",
        "entries": review_entries,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (TAGS / "clothing_coverage_map.json").write_text(json.dumps({
        "schema_version": 1, "source": SOURCE_ID,
        "mapping_rule": "Map only exact source covered_parts values boobs, legs, ass, pussy. No garment category, visual appearance, or inferred region is used.",
        "body_part_to_yolo_group": BODY_PART_TO_YOLO, "entries": coverage_entries,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    taxonomy_path.write_text(json.dumps(taxonomy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    index_path = TAGS / "tag_inventory.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    group_files = [("fullbody", "fullbody_tags.json"), ("body_images", "body_images_tags.json"),
                   ("photoshoots", "photoshoot_tags.json"), ("clothing", "clothing_tags.json")]
    all_entries, groups = [], []
    for group, filename in group_files:
        payload = json.loads((TAGS / filename).read_text(encoding="utf-8"))
        rows = payload["entries"]
        all_entries.extend(rows)
        groups.append({
            "group": group, "file": filename, "entry_count": len(rows),
            "selectable_count": sum(bool(item.get("selectable", True)) for item in rows),
            "review_required_count": sum(bool(item.get("requires_review")) for item in rows),
            "source_files": payload.get("source_files", []),
        })
    index["groups"], index["entries"] = groups, all_entries
    index["review_required_entry_ids"] = [item["id"] for item in all_entries if item.get("requires_review")]
    index["source_inventory_files"] = list(dict.fromkeys(index.get("source_inventory_files", []) + [SOURCE_ID]))
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "records": len(records), "named_definitions": len(direct_calls),
        "catalog_entries": sum(catalog_counts.values()), "category_counts": catalog_counts,
        "taxonomy_new_entries": len(new_entries), "review_required_coverage_records": len(review_entries),
        "coverage_status_counts": dict(Counter(record["coverage_mapping_status"] for record in records)),
        "quality_tag_categories": len(quality_tags), "source_sha256": inventory["source"]["sha256"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
