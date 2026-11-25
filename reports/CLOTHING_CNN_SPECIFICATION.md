# Future dedicated Clothing CNN specification

> Phase 3 added the game source catalog to `data/tags/clothing_tags.json` as a separate `game_source_clothing` hierarchy. The complete literal source records and exact metadata are preserved in `data/tags/clothing_source_inventory.json`; region links and unresolved entries are in `clothing_coverage_map.json` and `clothing_review_required.json`. These additions do not approve a final model map.

## Scope and labels

Use `data/tags/clothing_tags.json` as the selectable candidate vocabulary while retaining distinct namespaces. The file now includes the guide-derived vocabulary and the source-defined catalog. Context records, empty-slot sentinels, quality modifiers, and entries flagged for user review are not garment classes. Source-defined catalog items are candidate human-selectable leaves; their availability does not freeze the model class map. Keep exact serialized IDs and parent contexts. Do not flatten modifiers into garment classes.

Recommended task hierarchy:

1. **Source catalog category:** the exact game catalog slot (such as `upper`, `lower`, `bra`, or `shoes`).
2. **Source catalog item:** a specific source `id` and name under its category, trained only with enough human-confirmed examples.
3. **Optional source tags:** explicit `clothing_tags` may be separate multi-label attributes when their semantics and user-facing role are approved.
4. **Metadata lookup:** retrieve `base_value`, `lewdness`, `revealingness`, `protection`, and `covered_parts` from the selected item record; never predict known metadata.

The existing Asset CNN's `footwear`, `outerwear`, `panty`, `special_wear`, `utility_cover`, and `vest` labels lack exact matching source item/category tokens. Keep these raw predictions and resolve them only through user-approved mappings. The full per-label evidence is in `reports/ASSET_CNN_CLOTHING_MAPPING.md`.

The current Asset CNN has 26 output labels; its clothing-like outputs (bra, dress, footwear, outerwear, pants, panty, pantyhose, shirt, shorts, skirt, socks, special_wear, stockings, sweater, utility_cover, vest) are legacy broad crop predictions. Preserve every raw class, probability vector, checkpoint digest and proposal link to enable a future head-to-head comparison. Treat them as review suggestions, not adequate final Clothing labels. Do not train now.

## Annotation record

One record per human-reviewed crop: source image ID/path/SHA-256, source dimensions, source-pixel xyxy box, crop hash, immutable raw YOLO/CNN predictions, human-confirmed parent and optional child tag IDs, selected validated modifiers, decision type, annotator confirmation, model/taxonomy versions, exclusion reason and timestamp. Unknown or uncertain is an explicit review status and is never a class label.

## Crop and preprocessing contract

- Use the human-corrected box when present; otherwise use a box explicitly confirmed unchanged.
- Coordinates are source pixels; validate finite values and `0 <= x1 < x2 <= width`, `0 <= y1 < y2 <= height`.
- Extract RGB crops, preserve the source hash and exact crop rectangle, and defer resize/normalization to a versioned Colab preprocessing function.
- Keep all crops from one source hash in one split. Exact-hash duplicates share a split; use perceptual duplicate checks before production training.

## Dataset and evaluation

Store crops under `train/<parent_or_leaf>/`, `val/`, and `test/`, with `labels.csv` and JSON manifest mapping crop to source, box, taxonomy IDs, human decision and split. Configure proportions and seed; persist split assignments between exports. Keep a held-out test split source-disjoint. Report macro-F1, per-class precision/recall, confusion matrix, hierarchical parent accuracy, coverage at abstention thresholds, and calibration/error rates. Compare the future model to the existing CNN on the same source-disjoint, human-confirmed examples. Require enough examples per class and report class counts; do not claim model accuracy before labeled evaluation.

## Integration contract

Run after YOLO region proposals on supported clothing/footwear crops. Preserve the old CNN output alongside the Clothing CNN prediction. A low-confidence parent, unsupported child, or conflicting model output yields a review-required proposal with no final tag. Only a human-confirmed tag becomes a final label or training record. Model inference will be opt-in after a checkpoint, taxonomy version and validation report are registered. Photoshoots are never an output class.
