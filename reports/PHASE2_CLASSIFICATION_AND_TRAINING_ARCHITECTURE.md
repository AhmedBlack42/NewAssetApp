# Phase 2 classification, review, and export design

## YOLO class policy

`data/models/yolo_class_policy.json` retains all 32 checkpoint class IDs and names. The active image-region list is IDs 1–6, 8–11, and 28. IDs 12–18 are excluded location/context classes; IDs 19–27 and 29–31 are excluded legacy Fullbody labels and never provide a new subtype/state prediction; ID 7 `action_event` is excluded because no verified image-asset use was found. ID 0 `person` is not an active detection/training class. A raw legacy person detection may be retained solely as a review candidate with `status=unclassified_fullbody`, no subtype, and the original class/confidence/box; it is never confirmed by this fallback. `yolo_detection_disposition()` encodes the routing rule. All original checkpoints and maps remain unmodified.

Active region detections are evidence to create review proposals; the Asset CNN produces a raw prediction and confidence, with uncertain mappings routed to `others`. They do not choose final tags or photoshoot groups. `Analyze new / changed` loads local copied checkpoints only when clicked and uses the active IDs plus person fallback. Person results stay `unclassified_fullbody` even after an Asset CNN output. The full `samples/` folder and production data were not processed in this phase.

## Fullbody taxonomy and state

The full verified `main` entries in `data/tags/fullbody_tags.json` are preserved as the vocabulary, including the source spelling `atheletic` with its review flag. The taxonomy carries source context (`clothed_states`, `nude_states`, `costume_states`) and exact serialized tokens; it does not collapse these values into newly invented classes. The three reviewed output categories are stored separately as `fullbody`, `fullbody_topless`, and `fullbody_bottomless`. A correction must explicitly pair `state_spec` (`normal`, `topless`, or `bottomless`) with its matching output category. Main tag and state remain separate metadata.

The only current composition tokens supported by Girl Packer's extracted composition map are `clothed_topless`, `clothed_bottomless`, and `bikini_bottomless`; the legacy `clothed-bottomless` spelling is read-only. No other cross-product is generated. `fullbody_classification.py` validates the selected tag/state and produces guide-compatible filenames such as `shower1.webp`; the confirmed main tag and state remain separate database fields. Collision-free asset writing/number allocation still belongs to the later output-processing stage.

The Asset CNN's three Fullbody labels (`fullbody_clothed_states`, `fullbody_costume_states`, `fullbody_nude_states`) are broad group predictions, not verified main tags and not a reliable topless-vs-bottomless discriminator. Their original label, score and model identity are retained as evidence. They never auto-populate main tag, state, or output category. Low-confidence or ambiguous predictions stay in review/`others`.

## Corrections and provenance

Migrations 2–5 add append-only `correction_records`, source-root/change metadata, persistent `dataset_split_assignments`, separate Fullbody output categories, a source content-version ledger, proposed-tag snapshots and a persistent `tag_change_records` audit table. Each correction stores source ID/path/hash/dimensions, an immutable snapshot of original proposal/YOLO/CNN data, the corrected payload (including box in source pixels), decision type, final state, whether the prediction changed, user confirmation, per-task training eligibility, model version, taxonomy version and timestamp. User-created tag additions/edits/deprecations are also logged with source provenance when an image is selected. The original YOLO/CNN tables are not rewritten. A rejection is excluded from training by default. Only explicitly human-confirmed records whose per-task eligibility is true are export candidates.

`save_correction()` is the durable review API and `Review / correct selected proposal` provides the GUI workflow. The user can also create a manual proposal from any scanned image and adjust its source-pixel box. Distinguish `confirmed_prediction` from `corrected`; both are human reviewed, but only corrections set `user_changed_prediction`. A plain rejection is not a negative label. A negative YOLO image can be explicitly recorded as a confirmed manual annotation with `no_objects: true` and YOLO eligibility.

## Dataset packages

`app/core/dataset_exporter.py` builds versioned ZIP packages separately for YOLO, Asset CNN and the future Clothing CNN. YOLO uses only the active policy classes, maps their legacy IDs to a dense export ID table, checks source hashes and pixel-coordinate boxes, normalizes only at export, writes image/label pairs and empty labels only for explicit `no_objects` annotations. Asset CNN training requires a label from the existing 26-class model map; future Clothing CNN labels must match the extracted Clothing taxonomy. CNN exporters produce RGB crops and labels.csv with source provenance. The persistent global split key is source SHA-256, so the same source stays in the same split across tasks and exports, and multiple crops/duplicates cannot leak. Default proportions are 80/10/10 with seed 42; assignments remain stable unless the user explicitly chooses a new split.

Exports include dataset version/time, source selection, class map, split distribution, source hashes, annotation/crop counts, exclusions and taxonomy version, plus a ZIP. No export is run automatically. The UI's Prepare Training Dataset action is optional. Packages do not require either desktop application in Colab.

## Runtime scope and open items

- No new model was trained, downloaded, or overwritten.
- There is no labeled validation set, so no classifier accuracy claim is made.
- Model inference is user-triggered, local and per-new-or-changed-image; it is not run during scan. Full-folder sample processing remains pending user review of the unresolved taxonomy decisions.
- No automatic photoshoot membership exists; manual proposal/group actions remain separate from inference.
- Near-duplicate detection beyond exact SHA-256 is not implemented.
- Confirm the flagged `Atheletic` source spelling, Fullbody composition aliases, and clothing modifier mappings from `reports/TAG_REVIEW_QUESTIONS.md` before promoting those labels into a trained model.
