# Phase 10 — dataset preparation, review, and lifecycle

**Design only; no dataset was split, annotated, exported, or changed.**

## Shared engine, model-specific adapters

**Proposed:** Build one reusable lifecycle engine around immutable inputs and model-specific data adapters. Share project identity/versioning, source ingestion, eligibility, duplicate/source grouping, deterministic split assignments, review events, validation reports, finalization, package checksums, and lineage. Keep formats/validation rules separate for YOLO, Clothing classification, and Asset Classifier multi-head examples.

```text
NewAssetApp (read-only source boundary)
     │ explicit snapshot/export + manifest + checksums
     ▼
TrainingDatasetStudio import staging
     │ validate origin/hash/schema; copy into Studio-owned storage
     ▼
Dataset project / draft version
     ├─ model-specific adapter + class registry version
     ├─ selection / exclusion log
     ├─ deterministic group split plan
     ├─ copy-on-write human review set
     ├─ validation report and blockers
     └─ immutable finalized version → self-contained package
```

## Proposed separate workspace layout

```text
TrainingDatasetStudio/
  app/                         # UI entry point and screens
  studio_core/                 # project, import, review, split, validate, finalize APIs
  adapters/
    newassetapp_readonly/      # versioned snapshot contract; no DB writes
    yolo/                       # YOLO format + X-AnyLabeling round trip
    clothing_cnn/               # single-label image-grid workflow
    asset_mult_head_cnn/         # separate task-head schema and review
  config/
    studio.json                 # local settings; no source-project paths in packages
  database/
    studio.sqlite3              # independent migrations/backups
  workspace/
    imports/<snapshot-id>/      # immutable manifests and verified source blobs
    projects/<project-id>/
      project.json
      taxonomies/<taxonomy-version>/
      versions/<version-id>/
        manifest.json
        selections.json
        splits.json
        review_events/
        validation/
        finalized/               # read-only snapshot only after finalization
      review_jobs/<job-id>/      # disposable writable external-tool copy
      packages/<version-id>/    # packages of finalized versions only
  logs/
  requirements.lock
```

Keep Studio's DB, media storage, configuration, and output entirely in this separate root. Import snapshots should not be placed inside the application source tree.

Do not point a mutable Studio project at NewAssetApp's SQLite database or source directories. Imported references can be retained as provenance, but review edits must be attached to Studio-owned records.

## Proposed state machine

| State | Meaning | Permitted actions | Exit gate |
|---|---|---|---|
| Draft | Project config, selected import snapshot, registry, and inclusion decisions can change. | Import/reconcile sources; select/exclude; set task schema; inspect inventory. | Inputs and exact registry version are frozen for preparation. |
| Prepared | Materialized or verified sample records/annotations exist with provenance. | Validate source hashes, bounds, classes, missing files, invalids, duplicates; correct structure. | All selected samples pass structural checks or have explicit exclusion reasons. |
| Split | Reproducible split assignments and counts are recorded. | Review group leakage, distribution, and policy; create a new split-plan revision before review. | Approved group policy/seed/ratios; no source group crosses split. |
| Under Review | Review copy is open to human correction. | Use Studio interface and, for YOLO only, export/import a separate X-AnyLabeling review copy. | Every included sample meets its required review status; no unresolved import conflicts. |
| Reviewed | Human label/annotation review is complete. | Run validation; fix findings by creating review events. | Validation passes; all mapped labels are in the frozen registry. |
| Validated | Required checks pass and are recorded for this exact content hash. | Inspect report, then finalize. Any edit invalidates validation. | Explicit human finalization action references the report and registry/version hashes. |
| Finalized | Immutable version: content, registry, assignments, and review events frozen. | Read/verify/download; clone to a child version for any correction. | Complete checksums and finalization actor/time are present. |
| Packaged | Self-contained package built from that finalized snapshot and independently verified. | Rebuild package byte-for-byte from frozen version; download. | Archive manifest and SHA-256 verified; no local absolute-path dependency. |

**Invariant:** No UI or exporter may call data “training-ready” because it was generated, split, or zipped. Training-ready requires reviewed + validated + explicitly finalized. A package records that training is manual and outside Studio.

## Project and version records

**Proposed metadata entities:**

- `studio_project`: stable project ID, task family, display name, creation time, config version.
- `dataset_version`: immutable version number, parent version ID, state, registry ID/hash, schema ID/hash, source snapshot IDs, split-plan ID, content manifest hash, validation report hash, finalizer and timestamp.
- `source_ref`: source application, source record IDs, original path, original SHA-256, dimensions, current Studio-owned blob/materialized file reference, import timestamp.
- `example`: version-owned stable sample key, task, detection ID or crop identity, source-group key, bbox or crop path, inclusion/exclusion status, invalid reason.
- `label_event`: append-only before/after labels, origin, actor, timestamp, reviewer note, source annotation file hash for external edits.
- `split_assignment`: version ID, group key, split, seed, algorithm/version; immutable once the version enters review.
- `validation_run`: exact version content hash, ruleset version, results, errors/warnings, tool version, completed timestamp.
- `package_artifact`: finalized version ID, archive path, byte length, SHA-256, per-file manifest.

Do not mutate or relabel a finalized version. `Create child version` copies its snapshot/assignments as a starting point and records `parent_version_id`; corrections then invalidate validation and require the full gate again.

## Import and sample eligibility

1. User selects a NewAssetApp export/snapshot and task scope. The import screen first displays sample count, source count, review/eligibility state, taxonomy version, detector/checkpoint identity, and exclusions.
2. Import reads only the explicit manifest and associated files. It validates manifest schema, content hashes, source hashes, crop hashes, record IDs, dimensions, bounding boxes, class map, and allowed review/eligibility statuses.
3. Studio copies approved content into its own content-addressed import storage before review. The imported manifest is immutable. Re-import of identical content is idempotent; changed content yields a new snapshot identity.
4. Eligible records require the task-specific human-confirmed state and explicit task eligibility flag. Raw detections, proposals, filename labels, CNN predictions, rejected/invalid records, and candidates are not automatically eligible.
5. Every excluded record retains a reason, including unconfirmed label, invalid status, stale source, missing file, hash mismatch, unknown class, malformed box, non-approved source, duplicate policy, or taxonomy conflict.

**Current NewAssetApp import source:** prefer a future explicit export contract over direct DB reads. Today the exporter is useful as a reference but emits absolute source paths in manifests and has no import protocol version or immutable finalized-version marker. If an initial integration reads SQLite, make it read-only, use one transaction/snapshot, record schema version, and never write back.

## Source identity, duplicates, and leakage control

### Source-group keys

- For NewAssetApp detections/crops, use the verified parent source image SHA-256 as the group key; multiple boxes/crops from one source stay in a single split.
- For an imported original photograph with a known Studio source record, carry its immutable source identity and hash.
- For legacy images with no trustworthy parent/source relation, use exact file SHA-256 as a **minimum duplicate grouping**, not as proof that related crops do not share a source.
- Never use filename prefixes or naming patterns as authoritative identity. They may be warning-only heuristics.
- Permit manually declared group relationships, but record the actor, evidence, and event. Group merges after a split plan require a new split-plan revision and re-validation.

### Duplicate logic

Detect exact byte duplicates by SHA-256; optionally add perceptual similarity as a warning queue, never an automatic merge. Surface same-hash cross-label collisions, within-split duplicates, and cross-split duplicates. A reviewer decides whether near duplicates are separate useful views. Preserve one canonical file reference and keep all original record IDs in provenance.

### Split policy

**Proposed default:** 80/10/10 train/validation/test with a recorded seed (for example, 42 as a default seed only), deterministic group-level assignment algorithm version, and class-stratification optimization constrained by source group. The UI must show that exact balance may be impossible under source grouping. The seed is user-visible and never changes silently.

For sparse classes, show per-split counts and warnings; do not silently duplicate examples, break groups, or convert validation/test into train. Require explicit approval when a class lacks a meaningful validation/test count. A new split is a new version/revision, not a change to an already-reviewed or finalized assignment.

### Split report requirements

Display total examples, source groups, examples per class, train/validation/test counts per class, excluded count by reason, exact and near-duplicate warnings, missing labels, empty-label samples, class registry IDs, unmatched class names, and leakage warnings. YOLO images and labels move as one pair; a labeled-empty image is distinct from a missing annotation file. CNN crops retain original source-group keys and split with their source group.

## Human review mechanics

- YOLO review uses a read-only source version and a separate writable review copy. X-AnyLabeling never opens the finalized dataset directory directly.
- The round-trip import compares the expected review-copy hash and original annotation hash, class names/order, image inventory, and per-image boxes. It imports changed annotations into a new append-only Studio review event and retains original/generated labels.
- Conflicting external edits, missing images/labels, unknown classes, impossible boxes, or unexpected file additions are rejected for manual reconciliation. Never overwrite the original annotation version.
- Clothing classification uses an image grid with class filter, status filter, batch selection, exact class dropdown, keyboard navigation, and per-image before/after history. Multi-class tasks must enforce exactly one label per crop.
- Asset Classifier review uses separate views/filters per model head. It permits one confirmed label in the active task head, and optional human taxonomy fields are stored separately. No broad class is auto-converted to a final tag.
- Invalid/rejected items are excluded by disposition and carry reason/history, not recoded as a model class.

## Validation gate

### Common

- All files exist within project roots; paths are relative in portable artifacts.
- Checksums, expected file types, decodability, dimensions, manifest schema, registry IDs, required labels, class distributions, duplicate groups, source grouping, and exclusion reasons are complete.
- No unknown taxonomy value is silently mapped; no sample marked invalid/rejected or unconfirmed is included.
- Review coverage meets the configured required percentage (recommend 100% for any version called reviewed/finalized); all active classes have explicit reviewer-approved sample support or an approved exclusion/coverage exception.

### YOLO

- One exact class registry and exact order; every nonempty annotation line has a class ID in range and five valid values (`class_id`, normalized center x/y and width/height), with positive width/height and bounds in [0,1].
- Image/label basenames pair exactly. Empty label is explicit and supported; missing label is a distinct error.
- Annotation correction imported from review copy matches expected dataset images and preserves origin/provenance.

### CNN

- One label exactly where single-label; label maps are contiguous stable IDs and the exact registry version is embedded.
- Split group key is present where known; crop image is valid, source hash and source box provenance match the imported record, and crop hash is recorded.
- All head-specific class maps are validated independently; classes from one head cannot leak into another head's ID space.

## Current dataset readiness evidence

- Clothing current active tree: 2,328 images in 12 classes; split 1,860/234/234. The split manifest itself says source grouping is unavailable, so the project cannot certify no same-photograph leakage.
- YOLO source tree: 652 valid pairs according to migration manifest, one invalid pair quarantined, original class registry 32 classes. Current `train_data/yolo/` staging fails image/label pairing and registry file consistency.
- Unified current migration manifest: 3,075 YOLO crops + 356 legacy Body Images + 490 legacy broad Fullbody examples, all review-only; 0 training-eligible. The independent 546-image content found under train/val is not accounted for and is not eligible on present evidence.
- Current NewAssetApp DB: 0 training records and 0 split assignments, 16 bbox-only correction events with no eligibility flags. These are not training labels.

The detailed per-class inventory and checkpoint blockers are in `PHASE10_TRAINING_DATASET_STUDIO_AUDIT.md` and `PHASE10_MODEL_PROJECTS.md`.
