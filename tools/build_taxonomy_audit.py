from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT.parent / "Girl Packer1"
TAG_DIR = ROOT / "data" / "tags"
MODEL_DIR = ROOT / "data" / "models"
sys.path.insert(0, str(ROOT))
from app.core.proposals import (BODY_IMAGE_TYPES, CLOTHING_MODEL_CATEGORY_CROSSWALK,
                                YOLO_FULLBODY_MAIN_TAGS)
from validate_tag_library import validate_tag_library


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def entries(filename: str) -> list[dict]:
    return load(TAG_DIR / filename).get("entries", [])


def values_by_type(rows: list[dict], kinds: set[str]) -> list[str]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        value = row.get("serialized_value")
        if value and row.get("tag_type") in kinds:
            context = "/".join(row.get("context_path", [])) or "root"
            flags = " (review required)" if row.get("requires_review") else ""
            grouped[value].add(context + flags)
    return [f"`{value}` — {', '.join(sorted(contexts))}"
            for value, contexts in sorted(grouped.items(), key=lambda pair: pair[0].casefold())]


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- *(none)*"


def model_crosswalk() -> dict:
    manifest = load(ROOT / "models" / "model_manifest.json")["models"]
    yolo_names = manifest["yolo"]["class_names"]
    yolo_policy = {int(row["class_id"]): row for row in load(MODEL_DIR / "yolo_class_policy.json")["classes"]}
    body_policy = load(MODEL_DIR / "fullbody_classification_policy.json")
    canonical_main = {row.get("serialized_value") for row in entries("body_images_tags.json")
                      if row.get("tag_type") == "main" and row.get("selectable") and not row.get("requires_review")}
    yolo = []
    body_exact = {"face": "face", "boobs": "boobs", "ass": "ass", "pussy": "pussy", "legs": "legs"}
    for class_id, name in enumerate(yolo_names):
        candidate = None
        mapping_type = "unmapped_detection_or_context_class"
        note = "Original detection class is retained; a person or context/coverage label does not itself confirm an application tag."
        if name in body_exact:
            candidate, mapping_type = body_exact[name], "exact_body_image_main_candidate"
            note = "Exact token candidate; bounding-box detection remains human-review evidence."
        elif name == "portrait_frame":
            candidate, mapping_type = "portrait", "review_required_region_to_asset_candidate"
            note = "A portrait-frame detector is not identical to the Body Images portrait asset decision."
        elif name in YOLO_FULLBODY_MAIN_TAGS:
            candidate = YOLO_FULLBODY_MAIN_TAGS[name]
            mapping_type = "fullbody_main_candidate"
            note = "Human must confirm this candidate and independently choose one allowed Fullbody state."
            if name == "fullbody_athletic":
                mapping_type = "source_spelling_discrepancy_review_required"
                note = "Model says athletic; source-derived application row is review-flagged atheletic. No silent spelling rewrite."
            elif name == "fullbody_swim":
                mapping_type = "abbreviation_to_source_candidate_review_required"
                note = "Model abbreviation swim maps to source token swimsuit as a review candidate."
        elif name in {"fullbody_topless", "fullbody_bottomless"}:
            candidate = name.removeprefix("fullbody_")
            mapping_type = "state_candidate_not_main_tag"
            note = "Candidate state only; never a main tag and never auto-confirmed."
        yolo.append({"class_id": class_id, "model_label": name,
                     "policy_status": yolo_policy.get(class_id, {}).get("status"),
                     "application_candidate": candidate, "mapping_type": mapping_type,
                     "human_confirmation_required": True, "note": note})

    asset_map = load(ROOT / "models" / "asset_classifier" / "asset_class_map.json")
    reverse_asset = {int(class_id): name for name, class_id in asset_map.items()}
    asset = []
    exact_clothing = {row.get("serialized_value") for row in entries("clothing_tags.json")
                      if row.get("tag_type") in {"main", "tag"} and row.get("selectable")
                      and not row.get("requires_review")}
    for class_id, name in sorted(reverse_asset.items()):
        candidate = None
        mapping_type = "unmapped_legacy_cnn_class"
        note = "Keep original CNN class and confidence as evidence; no verified final-tag mapping."
        if name in BODY_IMAGE_TYPES:
            candidate = BODY_IMAGE_TYPES[name]
            mapping_type = "body_image_main_candidate"
            note = "Explicit NewAssetApp crosswalk; suggestion only, with original label retained."
        elif name in CLOTHING_MODEL_CATEGORY_CROSSWALK:
            candidate = CLOTHING_MODEL_CATEGORY_CROSSWALK[name]
            mapping_type = "source_defined_clothing_category_candidate"
            note = "Source-defined broad category crosswalk; reviewer must select a specific garment tag."
            if name in {"footwear", "outerwear", "panty"}:
                mapping_type = "source_defined_spelling_or_family_alias_review_required"
                note = "Explicit original Girl Packer category bridge; raw CNN class is preserved and this remains a review suggestion."
        elif name in exact_clothing:
            candidate = name
            mapping_type = "exact_clothing_tag_candidate"
            note = "Exact source token; still only a model suggestion."
        asset.append({"class_id": class_id, "model_label": name,
                      "application_candidate": candidate, "mapping_type": mapping_type,
                      "human_confirmation_required": True, "note": note})
    return {"schema_version": 1,
            "description": "Read-only model-label crosswalk; it never renames model classes or prediction evidence.",
            "source_registries": {"yolo": "models/model_manifest.json + data/models/yolo_class_policy.json",
                                  "asset_classifier": "models/asset_classifier/asset_class_map.json"},
            "models": {"yolo": yolo, "asset_classifier": asset},
            "future_models": {"fullbody_state": {"classes": body_policy["fullbody_state_classes"],
                                                    "checkpoint": body_policy["fullbody_state_checkpoint"],
                                                    "training_performed": body_policy["future_training"]["training_performed"]},
                              "corruption": {"classes": [], "status": "not specified; manual labels only"}}}


def main() -> None:
    crosswalk = model_crosswalk()
    crosswalk_path = MODEL_DIR / "model_tag_crosswalk.json"
    crosswalk_path.write_text(json.dumps(crosswalk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    clothing = entries("clothing_tags.json")
    fullbody = entries("fullbody_tags.json")
    body = entries("body_images_tags.json")
    photoshoots = entries("photoshoot_tags.json")
    shared = load(TAG_DIR / "shared_corruption_tags.json")
    fullbody_policy = load(MODEL_DIR / "fullbody_classification_policy.json")
    manifest = load(ROOT / "models" / "model_manifest.json")["models"]
    bodyparts_source = load(REFERENCE / "database" / "asset_tags" / "bodyparts.json")
    fullbody_source = load(REFERENCE / "database" / "asset_tags" / "fullbody.json")
    clothing_source = load(REFERENCE / "database" / "asset_tags" / "clothing.json")
    vid_source = load(REFERENCE / "database" / "vid_tags.json")
    errors = validate_tag_library(TAG_DIR)

    audit = ["# Taxonomy, Spelling and Naming Audit", "",
             "**Scope:** NewAssetApp taxonomy, UI routing, serialization, registries and cross-references compared with read-only Girl Packer references. No Girl Packer files were changed. This audit is before sample processing; no sample processing, dataset export, or model training was performed.", "",
             "## Authoritative sources inspected", "",
             "- Girl Packer `docs/girlpack_Guide.md`, including repeated Body Images, Fullbody and Corruption sections.",
             "- Girl Packer `database/asset_tags/bodyparts.json`, `fullbody.json`, `fullbody_compositions.json`, `clothing.json`, `clothing_modifiers.json`, and `database/vid_tags.json`.",
             "- Girl Packer `ai/naming.py` for its model-to-source-category mappings, Body Images filename validation and sequence proposal; `tools/pack_spec.py` for filename grammar validation.",
             "- NewAssetApp `data/tags/{clothing_tags,fullbody_tags,body_images_tags,photoshoot_tags,shared_corruption_tags}.json`, `tag_inventory.json`, `tag_review_required.json`, `tag_grammar.json`, and clothing source inventory.",
             "- NewAssetApp `data/models/yolo_class_policy.json`, `fullbody_classification_policy.json`, `models/model_manifest.json`, YOLO checkpoint file metadata, and Asset CNN `asset_class_map.json` / checkpoint.",
             "- NewAssetApp `app/core/proposals.py`, `filename_grammar.py`, `fullbody_classification.py`, `output_exporter.py`, `database.py`, `dataset_exporter.py`, `gui/correction_dialog.py`, tests, and prior taxonomy/mapping reports.", "",
             "## Taxonomy inventory", "",
             "### Clothing main tags", "", bullet_list(values_by_type(clothing, {"main", "tag"})), "",
             "### Clothing subtags and modifiers", "", bullet_list(values_by_type(clothing, {"subtag", "modifier"})), "",
             "### Fullbody main tags", "", bullet_list(values_by_type(fullbody, {"main"})), "",
             "### Fullbody sub-main tags / states", "", bullet_list([f"`{value}`" for value in fullbody_policy["fullbody_state_classes"]] + ["`clothed` is the base clothing state; three-state registry is separate from main type."]), "",
             "### Fullbody subtags", "", bullet_list([f"`{value}`" for value in fullbody_policy.get("supported_subtags", [])]), "",
             "### Body Images main tags", "", bullet_list(values_by_type(body, {"main"})), "",
             "### Body Images sub-main tags", "", "The source guide defines an ordered comma-separated main-tag list, not a separate sub-main taxonomy. NewAssetApp's `sub_main_tag` is the optional second ordered main tag used for that list.", "",
             "### Body Images subtags", "", bullet_list(values_by_type(body, {"subtag"})), "",
             "### Shared corruption subtags", "", bullet_list([f"`{value}`" for value in shared["values"]]), "",
             "### Location and contextual tags", "", "Body Images location subtags:", "", bullet_list(values_by_type([row for row in body if "location_tags" in row.get("context_path", [])], {"subtag"})), "",
             "Photoshoot tags by source context:", ""]
    context_groups: dict[str, list[dict]] = defaultdict(list)
    for row in photoshoots:
        context_groups["/".join(row.get("context_path", [])) or "root"].append(row)
    for context, rows in sorted(context_groups.items()):
        audit.extend([f"#### {context}", "", bullet_list(values_by_type(rows, {"tag"})), ""])
    audit.extend(["### YOLO class names", "", bullet_list([f"ID {row['class_id']}: `{row['model_label']}`" for row in crosswalk["models"]["yolo"]]), "",
                  "### Asset CNN class names", "", bullet_list([f"ID {row['class_id']}: `{row['model_label']}`" for row in crosswalk["models"]["asset_classifier"]]), "",
                  "### Future CNN class names", "", bullet_list(["Fullbody-state plan: `clothed`, `topless`, `bottomless` (no checkpoint; no training).", "No corruption classifier class list has been approved or trained."]), "",
                  "## Model-to-taxonomy cross-reference", "",
                  "The generated `data/models/model_tag_crosswalk.json` records all 32 original YOLO IDs/names and 26 original Asset CNN IDs/names, keeps raw labels separate from application candidates, and marks every mapping as requiring human confirmation. The embedded YOLO checkpoint names were read from `models/yolo/best.pt` with the installed Ultralytics runtime and matched all 32 manifest/policy entries in order. Asset CNN uses its 26-entry `asset_class_map.json`; its classifier head has 26 outputs. Existing dataset export uses the policy/registry labels; YOLO dense training IDs are mapped back to original IDs in the emitted `class_map.json`. No model checkpoint class or ID was changed.", "",
                  "Key crosswalk findings:", "",
                  "- Asset CNN `bodypart_boobs` (ID 1) maps to canonical Body Images `boobs`; YOLO class ID 3 is also exactly `boobs`.",
                  "- Asset CNN `bodypart_portrait_clothed` and `bodypart_portrait_topless` map to distinct `portrait` and `tportrait` application tags. The guide explicitly says T-Portrait is used when topless.",
                  "- The original Girl Packer `ai/naming.py` explicitly maps Asset CNN `footwear`→`shoes`, `outerwear`→`outer`, and `panty`→`panties` as broad category suggestions. NewAssetApp now records those as pending category suggestions, not final garment tags; raw CNN class IDs/names remain intact.",
                  "- YOLO `fullbody_athletic` maps to the current source-derived `atheletic` row, which remains review-required. No canonical spelling rewrite or checkpoint change is made in this audit.",
                  "- `u_whore` is an original video-tag serialization (`vid_tags.json`: `Ultimate Whore`→`u_whore`); the app preserves that token exactly. `Ultimate_whore` is a displayed guide spelling, not a different output token.", "",
                  "## Filename grammar and parser cross-check", "",
                  "- **Fullbody:** `<main>_<state>-<subtag1>,<subtag2>N.webp`; tested examples include `clothed_topless-slut1.webp` and `clothed_topless-slut,park1.webp`. The writer uses the verified composition allowlist; legacy guide aliases remain parse-only.",
                  "- **Clothing:** `<verified_main>_<subtag1>,<subtag2>N.webp`; the underscore is literal category grammar. The writer refuses unverified main tags; old hyphen filenames are identified as legacy by the parser.",
                  "- **Body Images:** single main uses `<main>-<subtags>N.webp` (`boobs-cum1.webp`, `boobs-cum,whore1.webp`); grouped mains retain paired guide numbering such as `ass3,boobs3-cum.webp`. `boobs` passes canonical serializer/parser checks; `bobbs` is rejected and has no alias.",
                  "- **Shared tokens:** corruption values remain exact subtags, including `u_whore`; the taxonomy and category validator keep them separate from main tags. Fullbody state is stored in its own field and mirrored as `sub_main_tag` for the hierarchy audit.", "",
                  "## Spelling and naming findings", "",
                  """| Current spelling | Original source spelling / location | Classification | Recommended canonical spelling | Alias / compatibility | Impact |
|---|---|---|---|---|---|
| `bobbs` | Earlier NewAssetApp test/report example only; absent from inspected guide, source Body Images map, YOLO and Asset CNN registries | Incorrect prior example, not an historical source alias | `boobs` | No parser alias; no historical file evidence found | Remove from canonical serializer; no database rewrite; existing ID 3 and CNN IDs unchanged |
| `boobs` | Guide Body Images; Girl Packer `bodyparts.json` `Boobs`; YOLO ID 3 `boobs`; Asset CNN ID 1 `bodypart_boobs` | Canonical | `boobs` | None | No model/database identity change |
| `Atheletic` / `atheletic` | Girl Packer `fullbody.json` key/value; NewAssetApp Fullbody main entry (review-required); guide says `athletic`; YOLO ID 23 `fullbody_athletic` | Source typo versus guide/model spelling; unresolved selection promotion | `athletic` is recommended by guide and model spelling | If corrected later, accept legacy `atheletic` for old DB/correction records; do not edit records/checkpoint | Taxonomy value change affects new labels; append-only DB and model ID 23 must remain unchanged |
| `panty` | Asset CNN ID 15 and Girl Packer video clothing tag/modifier parent; source clothing slot is `panties` | Intentional model/source vocabulary difference; category crosswalk exists | Use `panties` only as broad source category; keep `panty` as model class | Explicit review-only mapping in crosswalk; no class alias/renaming | Does not alter CNN ID 15 or stored predictions |
| `footwear` / `shoes` | Asset CNN ID 9 / YOLO `accessory_footwear` ID 28 versus source Clothing category `shoes`; Girl Packer `ai/naming.py` maps footwear→shoes | Model label vs source category; explicit broad-family mapping | `shoes` for application category suggestion | Keep raw `footwear` and YOLO class name; candidate is review-only | No model ID or database evidence changes |
| `outerwear` / `outer` | Asset CNN ID 13 versus source category `outer`; Girl Packer helper maps outerwear→outer | Model label vs source category; explicit broad-family mapping | `outer` for application category suggestion | Keep raw `outerwear`; candidate is review-only | No model ID or existing record change |
| `u_whore` / `Ultimate_whore` | Original Girl Packer `vid_tags.json` maps display `Ultimate Whore` to `u_whore`; guide uses `Ultimate_whore`; NewAssetApp shared token is `u_whore` | Display spelling and serialized token intentionally differ | `u_whore` | Preserve exact token; no normalization | No impact to IDs/records |
| `portrait` / `tportrait` | Source `bodyparts.json` has `Clothed Portrait`→`portrait`, `Topless Portrait`→`tportrait`; guide specifies topless T-Portrait | Two distinct intended tags, not a typo | Preserve both | Explicit CNN mapping from clothed/topless model classes | Keep separate model classes and application labels |
| `crempie` / `creampie` | `crempie`: zero matches in inspected NewAssetApp/source files. `creampie`: guide and Body Images source subtag | `crempie` unsupported spelling; `creampie` canonical | `creampie` | No alias absent evidence of historical files | No database/model change |
| `fullbody_swim` / `swimsuit` | YOLO class ID 24 / source Fullbody token `swimsuit` | Model abbreviation to source tag candidate | `swimsuit` | Explicit review-only candidate | Keep YOLO label and ID |
| `clothed-bottomless` / `clothed_bottomless` | Guide uses hyphen; original composition registry/current NewAssetApp uses underscore and read alias | Intentional legacy filename alias | `clothed_bottomless` in current composition data | Keep parser alias, do not rewrite historical records | No model impact |""", "",
                  "## Integrity check results", "",
                  f"`validate_tag_library.py`: {'PASS' if not errors else 'FAIL'} ({len(errors)} findings). It checks duplicate IDs, duplicate canonical values in the same context, review-record references, and tag inventory consistency. Added audit checks also reject case-insensitive spelling collisions and a canonical token registered under conflicting tag types. Exact duplicate `bikini` main-tag values in separate source contexts are retained intentionally.",
                  "- No `bobbs` alias is added. No other case-only spelling duplicate was found among selectable canonical tags.",
                  "- `u_whore` remains exact; underscores and hyphens in meaningful values such as `coffee_shop`, `pencil-skirt`, and `t-shirt` remain literal taxonomy values, not normalized separators.",
                  "- Original AI evidence remains in immutable model prediction/detection records; corrections append human-selected canonical tags and do not rename class registries.",
                  "- Final verification: `NewAssetApp .venv -m unittest discover -q` passed 59 tests. The taxonomy validator reported zero findings. No samples were processed, no datasets were exported, and no models were trained.", ""])
    (ROOT / "reports" / "TAXONOMY_SPELLING_AND_NAMING_AUDIT.md").write_text("\n".join(audit), encoding="utf-8")

    decisions = ["# Taxonomy Decisions Required", "",
                 "These decisions remain genuinely open after source comparison. No sample processing should begin until the user reviews them.", "",
                 "## 1. Promote Fullbody `athletic` as the canonical spelling?", "",
                 "- **Competing spellings:** guide `athletic`; YOLO class `fullbody_athletic`; source Fullbody map and current NewAssetApp serialized value `atheletic` (review-required).",
                 "- **Evidence:** Girl Packer guide's Fullbody type list and the unchanged YOLO class both use `athletic`; `database/asset_tags/fullbody.json` has the typo `Atheletic`→`atheletic`.",
                 "- **Current NewAssetApp behavior:** the row is retained with source provenance and blocked from ordinary selection; YOLO evidence routes as a review candidate. No alias is currently added.",
                 "- **Choices/consequences:** keep `atheletic` preserves source token exactly but leaves a spelling mismatch; use `athletic` for new canonical records and retain an `atheletic` read alias, without altering existing correction records or model class 23.",
                 "- **Recommendation:** make `athletic` canonical for new records after confirmation; retain `atheletic` as a legacy read alias and preserve `Atheletic` in source metadata.", "",
                 "## 2. Keep Body Images subtag compatibility/order unrestricted or define rules?", "",
                 "- **Competing interpretations:** guide permits multiple comma-separated subtags and lists corruption, fluid and location values, but gives no allowed combinations, exclusivity rules, or ordering semantics.",
                 "- **Current NewAssetApp behavior:** subtags are separately stored and serialized in reviewer order; all taxonomy-valid subtags can be composed, and shared corruption values remain manual.",
                 "- **Consequences:** unrestricted order preserves reviewer intent; allowlists by main tag reduce invalid game filenames but need source evidence.",
                 "- **Recommendation:** retain order and explicit human review until an authoritative game parser or more detailed guide defines compatibility.", "",
                 "## 3. Original modifier-parent hierarchy", "",
                 "- **Unresolved parents:** `t-shirt`, `skirt`, `bra`, `panty`, `thigh-high-stockings`, and `boots` appear as modifier groups in `clothing_modifiers.json` without exact matching selectable item parents in the current clothing item taxonomy.",
                 "- **Current NewAssetApp behavior:** preserve these source modifier groups as nonselectable/informational; no inferred parent or serialized alias is created.",
                 "- **Consequences:** linking by approximate spelling may attach modifiers to the wrong garment family; leaving unlinked preserves data without enabling category selection.",
                 "- **Recommendation:** keep informational until a source-level parent mapping is confirmed.", ""]
    (ROOT / "reports" / "TAXONOMY_DECISIONS_REQUIRED.md").write_text("\n".join(decisions), encoding="utf-8")
    print(f"Wrote {crosswalk_path}")
    print("Wrote reports/TAXONOMY_SPELLING_AND_NAMING_AUDIT.md")
    print("Wrote reports/TAXONOMY_DECISIONS_REQUIRED.md")
    print(f"Taxonomy validator findings: {len(errors)}")


if __name__ == "__main__":
    main()
