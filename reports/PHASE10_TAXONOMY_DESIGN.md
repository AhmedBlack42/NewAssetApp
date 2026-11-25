# Phase 10 — normalized taxonomy design

**Design only; no migration performed.** Facts and recommendations are labeled using the Phase 10 evidence definitions in `PHASE10_TRAINING_DATASET_STUDIO_AUDIT.md`.

## Current authoritative structures

### Verified sources

- Current tag values are defined by `data/tags/fullbody_tags.json`, `body_images_tags.json`, `clothing_tags.json`, and `shared_corruption_tags.json`, with policy files under `data/models/`.
- `data/models/fullbody_classification_policy.json` distinguishes Fullbody state values (`clothed`, `topless`, `bottomless`) from output categories (`fullbody`, `fullbody_topless`, `fullbody_bottomless`) and from main Fullbody tag tokens. Fullbody main/state combinations are explicitly allowlisted.
- `data/models/body_images_composition_policy.json` currently lists supported pairs `boobs_cum`, `ass_creampie`, and `ass_bb`. `cum` and `creampie` are mutually exclusive and represented as sub-main composition values for those pairs, while `bb` is a distinct supported pair.
- `data/models/unified_body_images_fullbody/class_registry.json` proposes task-specific outputs: Body Images = `portrait`, `tportrait`, `bodypart_cum`, `bodypart_acc`; Fullbody state = `clothed`, `topless`, `bottomless`. All seven outputs require human-reviewed labels; the two broad evidence classes do not map to final application tags.
- Clothing's model registry has 12 fixed class names and ordering, separate from fine-grained Clothing filename tags. `top` and `lingerie` remain distinct. The registry marks detailed tag selection as human-only.
- `data/tags/shared_corruption_tags.json` currently serializes shared corruption values as `slut`, `conservative`, `whore`, `u_whore`. The review-required report documents the `u_whore` spelling decision and says not to normalize it. Fullbody policy also contains `u_whore` as a supported subtag.
- `app/core/filename_grammar.py` and `app/core/fullbody_classification.py` implement serializers/parsers with `_`, `-`, and `,` as serialization syntax. These are filename rules, not a normalized taxonomy schema.

## Proposed normalized data model

Do not make a filename the source of taxonomy truth. Store a reviewed detection/example with typed fields and provenance:

```text
DatasetExample
  example_id
  source_asset_id / source_sha256 / source_record_ref
  task_id                    (yolo_detection | clothing_classification | asset_classification)
  sample_kind                (full_source | detection_box | materialized_crop)
  bbox_xyxy                  (nullable, source pixel coordinates)
  detection_category         (fullbody | body_images | clothing | other)
  model_target               (nullable task-specific output group)
  main_classification       (nullable typed value)
  subtag_values[]            (0..N; taxonomy references)
  corruption_values[]        (0..N; explicit taxonomy references)
  metadata_values[]          (typed, scoped, optional)
  review_state               (candidate | in_review | reviewed | rejected)
  invalid_status             (valid | invalid; independent of category)
  invalid_reason             (nullable; required when invalid)
  label_origin               (model | imported_legacy | human | derived)
  label_confirmed_by / at    (nullable)
  taxonomy_version
  source_snapshot_id
```

Use normalized tables in Studio rather than only one JSON blob:

```text
taxonomy_versions(version_id, taxonomy_id, version, checksum, status)
taxonomy_fields(field_id, taxonomy_version_id, key, scope, value_type, cardinality, required_policy)
taxonomy_values(value_id, field_id, stable_id, serialized_value, display_label, active, parent_id)
examples(example_id, project_id, source_ref_id, task, bbox_json, review_state, invalid_reason, ...)
example_labels(example_id, field_id, value_id, origin, confidence, confirmed, event_id)
review_events(event_id, example_id, event_type, before_json, after_json, actor, occurred_at, note)
model_targets(target_id, model_project_id, head_key, class_id, value_id, trainable, mapping_status)
```

Taxonomy relationships must be explicit and typed. The same token can appear in multiple scopes without accidental equivalence. A model class is a model target; a human filename tag is a taxonomy value; a detection class is a box category. Training targets are mapped only by a versioned, approved mapping record.

### Proposed separation of concepts

| Concept | Example | Meaning |
|---|---|---|
| Detection category | `body_images` | What type of region the annotation represents. Not a model output class by itself. |
| YOLO target class | class ID/name from the approved detector registry | Box class ID consumed by that detector version. |
| Human main classification | `portrait`, `boobs`, a verified Fullbody main tag, or exact Clothing label | Reviewer-confirmed semantic label. |
| Model output class | `bodypart_cum`, `bodypart_acc`, `topless` | Output of one explicitly defined model head. It can be broad evidence, not final naming. |
| Subtag | `bb`, `cum`, `creampie`, or another approved value | An additional structured label with category/field scope and allowed-pair rules. |
| Corruption metadata | `slut`, `whore`, `conservative`, `ultimate_whore` (decision pending) | Optional independent field, potentially multi-label only if policy approves. |
| Invalid status | invalid + reason | Review disposition for one example/detection. Never a source-image label. |

## Candidate field schemas by project

### YOLO

Each annotation row has a stable `class_id`, exact `class_name` from a frozen registry version, and normalized box geometry for the packaged YOLO text file. Keep review quality flags and taxonomy metadata in Studio manifests/sidecars; YOLO text itself remains the standard numeric annotation format. Invalid or rejected boxes are excluded with a reason in the version manifest, not represented as train classes unless a later explicit class decision says otherwise.

### Clothing CNN

One image crop gets exactly one `clothing_family` target from the fixed ordered 12-class registry: `bra`, `dress`, `footwear`, `lingerie`, `outerwear`, `pants`, `panty`, `shirt`, `shorts`, `skirt`, `socks`, `top`. Separate `human_final_clothing_tag` can be stored as metadata, but it is not the 12-class output unless the registry explicitly maps to it. Human must select among exact tags; no family-to-fine-tag promotion is automatic.

### Asset Classifier CNN

Define a record with `head_key` and a class ID within that head. The current registry has two heads, not one seven-label flat taxonomy: `body_images` (4 names) or `fullbody_state` (3 values). A single sample is labeled for one task head. Human final tags/subtags are attached separately and are not implicitly predicted by either head. Whether the model should retain the 4 Body Images outputs exactly as proposed is a user decision.

## Historical import without semantic loss

1. Preserve original source bytes and exact original path/hash; do not rename originals.
2. Preserve raw filename verbatim, its parser version, and the entire parse result including any ambiguity/legacy marker.
3. If a current parser maps a filename unambiguously, import its token as an **unconfirmed legacy claim** with origin `imported_legacy`; do not set human confirmation from a filename alone.
4. If a filename has an unknown token, multiple plausible parses, a deprecated form, or a policy conflict, retain raw text and attach `needs_mapping_review`; do not guess a parent or field.
5. Retain historical `u_whore` exactly as `u_whore`. Never auto-map it to `ultimate_whore`. Preserve both values separately if the latter is approved for future labels.
6. Do not derive detection category from tokens like `topless` or `bottomless`; they are Fullbody state values. Do not derive YOLO IDs from any filename.
7. Optionally create a rendered export filename from the structured label using the existing serializer at package time. The structured values remain authoritative.

## Ambiguities requiring approval

1. **Requires user decision:** Is `ultimate_whore` intended to be a new canonical corruption value, separate from the existing `u_whore`, or should new entries continue using `u_whore`? Existing project evidence explicitly preserves `u_whore`; it does not authorize a new alias.
2. **Requires user decision:** Are corruption subtags a multi-label set or exactly one mutually exclusive state? Existing serializers accept a list of subtags, while some older review fields store one `corruption_subtag` and a separate `corruption_state`; these are not one consistent schema.
3. **Requires user decision:** Should Body Images main values include the full canonical set (`face`, `portrait`, `tportrait`, `boobs`, `ass`, `pussy`, `legs`) for human labels, while the unified CNN retains its separate 4 broad outputs?
4. **Requires user decision:** Which tags/subtags may coexist for each main value, beyond the three current supported Body Images pairs? Do not infer combinations from parser permissiveness.
5. **Requires user decision:** Should `topless` and `bottomless` be stored only under a Fullbody state field, or also emitted as a separate output category for compatibility? Keep them out of the detector category registry either way.
6. **Requires user decision:** How should `bodypart_acc` resolve to structured human evidence? It is not the filename values `cum` or `creampie` and must not choose between them.
7. **Requires user decision:** Should `invalid` be a dataset review disposition only, as proposed, or a versioned dataset taxonomy label? Recommendation: disposition only.

No schema migration, alias, automatic filename conversion, or training-label mapping should proceed until these are approved.
