# Phase 3 decisions required before freezing taxonomy or training classes

**Status:** Pending user review. Proposed IDs and mappings remain unfrozen. No production dataset was generated and no model was trained.

Questions below are limited to decisions that change the selectable taxonomy, file grammar, or model class definition. Existing user instructions are recorded as settled and are not repeated as questions.

## 1. Fullbody tags and combinations

**Source/evidence:** `docs/girlpack_Guide.md` describes the `clothed-bottomless` example and lists the available types. `data/tags/fullbody_tags.json` preserves `atheletic` and two contextual `bikini` values. `data/models/fullbody_classification_policy.json` currently permits only `clothed_topless`, `clothed_bottomless`, and `bikini_bottomless`, with the old hyphen spelling read as an alias.

**Unclear:** The guide's hyphen spelling conflicts with the current underscore writer. `Atheletic` in the source map conflicts with guide spelling `athletic`. The two Bikini contexts share the same serialized value. The taxonomy also lists `topless` and `bottomless` under nude-state contexts, while the requested classifier separates those words into a state head and separately derives the output category.

**Supported interpretations:** Preserve current underscore output and read the hyphen alias; instead make the guide spelling canonical; preserve the misspelling as the game-compatible value; or introduce a separately approved alias. Keep Bikini contextual, or collapse it only if you approve that semantic merge. Retain `topless`/`bottomless` as historical main-tag candidates, or use them only as the separate state field.

**Recommendation:** Preserve exact source values and current restricted composition allowlist; do not generate additional combinations. Keep `atheletic` review-flagged and keep both Bikini contexts until you approve aliases/merging.

**Decision:** Which spelling should new Fullbody files write (`clothed_bottomless` or `clothed-bottomless`); should `atheletic` remain unchanged or receive an explicit alias; should the contextual Bikini entries remain separate; and should `topless`/`bottomless` be state-only or remain selectable main tags?

**Consequence:** This determines serialized filenames and main/state class identity. It does not change the three separate output categories.

## 2. Body Images tags and subtags

**Source/evidence:** The guide's template is `{main_tag},{main_tag2}-{sub_tag},{sub_tag2}` and it gives `face-cum.webp`. NewAssetApp preserves the main values and the source-derived fluid, corruption, and location subtags in `data/tags/body_images_tags.json`. `u_whore` is review-flagged because the guide says `Ultimate_whore` while the active source token is `u_whore`.

**Unclear:** Per-main subtag compatibility, order within each comma-separated list, and whether both corruption values may coexist are not specified.

**Supported interpretations:** Treat the documented separator/template as syntax only and require manual selection; add a compatibility allowlist only when documented/approved; preserve `u_whore` or add a separate display/serialization alias.

**Recommendation:** Keep current exact values and manual review; do not auto-compose or sort tags; decide `u_whore` before enabling it.

**Decision:** Should `u_whore` remain the serialized token or use an approved alias, and what subtag combinations/order rules should NewAssetApp enforce?

**Consequence:** These choices affect final filenames and any Body Images training labels.

## 3. Photoshoot tags and groups

**Settled by your instruction:** Photoshoots are manually assigned. YOLO and Asset CNN must not identify them, no image is routed there automatically, and visual appearance/count/poses/backgrounds are not evidence. The GUI's Photoshoots section and group membership stay independent from AI categories.

**Open question:** None. No new decision is needed to preserve manual-only behavior.

## 4. Clothing hierarchy

**Source/evidence:** `extract_clothing_tags.txt` defines ten `database_clothing_items` categories: `outer`, `upper`, `bra`, `lower`, `panties`, `socks`, `shoes`, `buttplug`, `pussy_acc`, and `nipple_acc`. The NewAssetApp extraction has 140 records: 55 named item definitions plus 85 literal catalog entries. Ten catalog entries are explicit `None` sentinels and are retained as nonselectable metadata. Source `clothing_type` values and categories remain exact.

**Unclear:** The game catalog groups apparel with buttplug, pussy accessory, and nipple accessory classes. The user request calls the future model a Clothing CNN and describes garment types, but does not say whether those accessory categories belong in the same selectable Clothing page/model.

**Supported interpretations:** Keep all source categories under the source catalog namespace and separate the classifier's apparel/accessory heads; or present/train the accessory categories as part of the same Clothing task.

**Recommendation:** Keep all extracted records selectable for human assignment, but treat apparel and accessories as separate future classifier families unless you want one unified task. The source extraction is complete either way.

**Decision:** Should `buttplug`, `pussy_acc`, and `nipple_acc` remain in the Clothing selector and future Clothing CNN, or should they be separated into an accessories task/category?

**Consequence:** This changes task names, review filters, and the future class hierarchy, not the preserved source inventory.

## 5. Clothing coverage mapping

**Source/evidence:** The source records use `covered_parts`. Exact values `boobs`, `legs`, `ass`, and `pussy` map to the corresponding proposed YOLO coverage classes. Across 140 records, 35 map without extra unmapped values, 59 contain both directly mapped and unmapped source values, 19 have `covered_parts` values naming no supported body region, and 27 have no `covered_parts` field. The full per-item evidence is in `data/tags/clothing_coverage_map.json` and the 105 unresolved records are in `data/tags/clothing_review_required.json`.

**Unclear:** Source values such as `bra`, `panties`, `upper`, `feet`, and `socks` are not one of the four body-region names. It is not documented whether these mean garment layers, body regions, or another game-specific relation.

**Supported interpretations:** Map only the four exact body terms and leave all other values unresolved; obtain a source rule for additional mappings; or manually map particular items after review. A garment with several explicit body terms can associate with multiple coverage detections under one garment identity.

**Recommendation:** Keep the current exact-token mapping only. Never infer from garment name, category, or appearance.

**Decision:** Do `covered_parts` entries other than the exact four body terms carry a defined mapping to YOLO coverage groups? If so, provide or confirm that rule; otherwise keep them unresolved.

**Consequence:** This determines which clothing crops can receive coverage-region associations. It does not change item metadata or garment identity.

## 6. Separator and filename grammar

**Source/evidence:** `reports/TAG_GRAMMAR_ANALYSIS.md`, `reports/TAG_REVIEW_QUESTIONS.md`, and `data/tags/tag_grammar.json` document comma, hyphen, underscore, spaces, and extension boundaries. The `<` token has no definition in the inspected guide or active serializer.

**Unclear:** The Fullbody separator conflict and Body Images combination/order rules above remain open. The `<` mention has no source-backed interpretation.

**Supported interpretations:** Keep `<` unsupported until a schema/source is provided; use separators only in their documented contexts; do not normalize spaces or punctuation.

**Recommendation:** Keep the existing parser/writer allowlist and exact stored strings; do not add `<` or global separator substitutions.

**Decision:** Is `<` part of a separate external filename/schema rule NewAssetApp must support? If yes, provide its authoritative definition.

**Consequence:** Without a definition, enabling `<` risks creating incompatible filenames; no current file is rewritten.

## 7. YOLO detection classes

**Source/evidence:** The loaded legacy checkpoint has 32 classes. New proposal in `data/models/proposed_yolo_class_map_v1.json` has six body-image regions and four cover-region classes, with provisional IDs 0–9. Legacy IDs 10, 11, 9, and 8 map by exact region name to `boobs_cover`, `legs_cover`, `ass_cover`, and `pussy_cover`. Old checkpoint IDs/names remain preserved; no locations, person, legacy Fullbody labels, or Photoshoot class are proposed.

**Unclear:** Whether small footwear regions justify a separate detection class. Asset CNN `footwear` is classification-only and cannot localize a shoe, while the game catalog uses `shoes` rather than `footwear`.

**Supported interpretations:** Keep the proposed 10 classes and handle footwear by manual crop/review; or add an eleventh footwear detector class if localized shoe crops are required.

**Recommendation:** Start with the 10 requested region classes and omit footwear unless you need its independent boxes.

**Decision:** Should `accessory_footwear` be retained as an eleventh YOLO class, or omitted from the new detector?

**Consequence:** This changes class-map length and future annotation effort. Proposed IDs remain provisional until the list is frozen.

## 8. CNN class hierarchy and Asset CNN reuse

**Source/evidence:** `reports/ASSET_CNN_CLOTHING_MAPPING.md` covers all 26 original outputs. Existing Asset CNN strictly loads as ResNet-18/26 labels. Exact source item/tag tokens exist for several outputs; some are broad categories; `footwear`, `outerwear`, `panty`, `special_wear`, `utility_cover`, and `vest` lack direct source matches. No labeled evaluation set establishes accuracy.

**Unclear:** Whether future training should use source catalog category → item → optional `clothing_tags` attribute heads, or a simpler single-level class list. The source contains 140 records and many item variants, so flattening all records risks sparse classes.

**Supported interpretations:** Keep the legacy CNN as a baseline suggestion model and use a hierarchical source-item model for new training; or keep only the legacy 26-class classifier until more labeled data exists.

**Recommendation:** Preserve the CNN and raw output; use its exact tokens only as review suggestions. Use hierarchical category/item training when human-confirmed samples are sufficient, with abstention for unsupported/missing classes.

**Decision:** Approve the hierarchical category→item proposal, with source tags as optional attributes, or keep the future classifier at category level until data supports item-level heads?

**Consequence:** This determines label granularity and the minimum examples required per class; no model retraining or fine-tuning is currently done.

## 9. Ambiguous source-code values

**Source/evidence:** The extracted `Clothing` records contain item fields such as `base_value`, `lewdness`, `revealingness`, `protection`, `covered_parts`, and clothing tags. The separate quality-tag modifier tree includes `value` effects. No item field named `price`, `value`, or `coverage` exists in the extracted `Clothing` calls. All exact fields and types are preserved in `clothing_source_inventory.json`.

**Unclear:** Whether `base_value` is intended to be shown under a user-facing `price` label, whether quality-tag `value` deltas should appear in the app, and whether `covered_parts` has meanings beyond its literal values.

**Supported interpretations:** Preserve exact names only; show `base_value` as a source-defined value without calling it price; optionally add an approved display alias later while retaining the source name; keep quality modifiers as a separate metadata vocabulary.

**Recommendation:** Preserve exact source names/types and keep `base_value`, quality `value`, and any future `price` field distinct until you confirm their game semantics.

**Decision:** Should the UI display `base_value` as-is, or is there a verified rule that maps it to the requested `price` field? Should quality-tag `value` modifiers be exposed to asset reviewers?

**Consequence:** This affects metadata display and serialization only; the classifier will not predict these values.

## 10. Runtime isolation and loader status

**Evidence:** NewAssetApp `.venv` runs Python 3.11.9 x64. Requirements/imports, `pip check`, 30 tests, YOLO, Asset CNN, both BiRefNet variants, and both launcher scripts passed their local checks. All tested checkpoint paths are inside NewAssetApp. The Real-ESRGAN checkpoint file/hash is present, but NewAssetApp has no implementation or loader. Its legacy implementation exists only under Girl Packer and was not executed or imported.

**Approval needed:** None for this phase. Your instructions say to report missing implementation/dependencies without repairing them. No package change or legacy modification was made.

**Remaining blocker:** Real-ESRGAN cannot be loaded through the current NewAssetApp code. Keep that optional feature unavailable until its implementation is separately authorized and reviewed. The sandbox's default execution context initially could not resolve the virtual environment's base Python; the same required interpreter started in the approved execution context, and no alternative runtime was used.

## Already-set decisions retained

- Only `fullbody`, `body_images`, `clothing`, and `others` are automatic proposal destinations. Unclear predictions remain in `others`.
- Photoshoots are manual only; no visual or model-based assignment.
- Existing Asset CNN and legacy YOLO maps/checkpoints remain intact.
- Model predictions and confidence remain review evidence; only human-confirmed decisions become training labels.
- No training or production training dataset generation occurs before decisions and class-map review.
