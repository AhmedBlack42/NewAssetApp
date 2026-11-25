# Phase 3 classification and training proposal

**Status:** Review specification. Taxonomy decisions and training classes remain unfrozen.

## Responsibilities and stored values

| Layer | Candidate output | Must not decide |
|---|---|---|
| YOLO | Region boxes for face, portrait_frame, boobs, ass, pussy, legs, and four body-region coverage classes | Garment type, Fullbody main/state, asset acceptance, or Photoshoot membership |
| Existing Asset CNN | Raw legacy 26-class crop score/vector | A confirmed tag or a specific game item when only a broad family is supported |
| Future Clothing CNN | Source-defined category/item suggestions, optionally source clothing_tags | Source metadata already known from the selected item, or final acceptance |
| Future Fullbody classifier | Main type and state as separate proposals | Arbitrary combinations outside the approved composition allowlist |
| Future Body Images classifier | Main asset type and optional subtag suggestions | Validity of undocumented main/subtag combinations |
| Human reviewer | Accepted/corrected category, item, tags, boxes, and training eligibility | — |

`photoshoots` remains a separately managed user assignment and group membership. No model receives photoshoot labels or routes any proposal there.

The only automatic asset proposal categories remain `fullbody`, `body_images`, and `clothing`; findings that are unclear or unsupported stay in `others`. A source catalog item or raw model prediction is never itself a final accepted asset.

## YOLO regions and the legacy map

The pending 10-class proposal is in `data/models/proposed_yolo_class_map_v1.json`. Its numeric IDs are provisional only. Legacy IDs and names remain untouched in `models/yolo/best.pt` and `data/models/yolo_class_policy.json`.

Legacy coverage IDs map by exact body-region token: 10 `boobs_cover_item` → `boobs_cover`; 11 `leg_cover_item` → `legs_cover`; 9 `ass_cover_item` → `ass_cover`; 8 `pussy_cover_item` → `pussy_cover`. The six body-image classes preserve their names. The new map excludes `person`, locations, action_event, old Fullbody labels, and Photoshoots.

`accessory_footwear` is not included in the 10-class proposal. The copied Asset CNN has a `footwear` output, but that classifier cannot localize footwear on its own and the game's clothing source uses category `shoes`, not the exact term `footwear`. Keep the legacy ID 28 and CNN label as historical/review evidence. Decide whether a dedicated footwear box is useful before adding an eleventh YOLO class.

## Detection-to-garment relationship

Each human-confirmed detection has its source image ID/hash and corrected source-pixel box. For clothing, preserve a stable garment/proposal identity and attach one or more coverage detections to it. A single garment can be associated with multiple explicitly supported regions without being duplicated as separate garments. Asset CNN and future Clothing CNN outputs remain separate raw predictions linked to the same crop/detection, with separate decision records.

The source code provides `covered_parts`; only exact `boobs`, `legs`, `ass`, and `pussy` values map directly to the proposed YOLO groups. `clothing_coverage_map.json` preserves all source values and distinguishes exact mappings from missing, partial, and unsupported values. Category, item appearance, name, or tag text is never used to infer a coverage group.

## Fullbody and Body Images classifiers

Fullbody training uses separate candidate heads for source main tag, state (`normal`, `topless`, `bottomless`), and constrained output category. The three output categories remain `fullbody`, `fullbody_topless`, and `fullbody_bottomless`. The existing broad Asset CNN Fullbody classes are baseline evidence only and do not provide enough detail for main type or state.

Body Images main classes are the source values `face`, `portrait`, `tportrait`, `boobs`, `pussy`, `ass`, and `legs`. Subtags remain separate multi-label candidates: fluids (`cum`, `creampie`), corruption (`conservative`, `slut`, `whore`, review-flagged `u_whore`), and locations (the exact selectable values in `body_images_tags.json`). Main/subtag compatibility and order remain open. Model outputs must remain suggestions until reviewed.

## Source clothing hierarchy and future classifier

The full parser output is `data/tags/clothing_source_inventory.json`; 140 source records (55 named definitions and 85 catalog entries) cover categories `outer`, `upper`, `bra`, `lower`, `panties`, `socks`, `shoes`, `buttplug`, `pussy_acc`, and `nipple_acc`. Ten explicit `None` slot sentinels are preserved but not selectable. The five top-level clothing quality groups and all nested values are preserved separately in the same inventory.

The candidate future classifier should use a category head followed by a source-item head and optional `clothing_tags` attribute head. It must not turn all source properties into independent visual classes. After a human selects an item, read its exact `base_value`, `lewdness`, `revealingness`, `protection`, `covered_parts`, clothing tags, image fields, and purchase/damage fields from the source record. The item source has no `price`, `value`, or `coverage` property; the separate quality modifier mapping has `value` effects. Do not equate those fields without a decision.

The existing Asset CNN remains a baseline for its exact outputs. The crosswalk in `reports/ASSET_CNN_CLOTHING_MAPPING.md` identifies direct tokens, broad categories, inferred synonyms, and unsupported outputs. Preserve all original predictions even when no taxonomy match exists.

## Training provenance and Colab preparation

Keep task datasets logically separate: YOLO boxes; Fullbody main/state/category; Body Images main/subtag; Clothing category/item/metadata relationships. Only human-confirmed annotations may become labels. Keep the original AI snapshot, user correction, final confirmed values, box correction, taxonomy/model versions, source ID/hash, crop relationship, human decision, and persistent split assignment. Existing split assignment is keyed to source SHA-256 so crops from one image stay together. Existing package/export code targets Google Colab; this phase did not create a production training archive.

No model was trained, fine-tuned, overwritten, or evaluated for accuracy. No `samples/` folder was processed. Do not freeze the pending class map or generate the production Clothing CNN class map until the questions in `reports/USER_DECISIONS_REQUIRED.md` have answers.
