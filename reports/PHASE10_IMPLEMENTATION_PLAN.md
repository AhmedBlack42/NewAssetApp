# Phase 10 — TrainingDatasetStudio implementation plan

**Proposed plan only.** No Studio application code is implemented by this phase. Implementation should begin only after you review/approve this blueprint and settle the blocking taxonomy/model choices.

## Guiding constraints

- Studio owns its app/workspace, DB, config, storage, review events, split plans, versions, and packages.
- NewAssetApp is read-only from Studio's perspective. Use a versioned import/export contract; do not mutate its source images, detector/model snapshots, original corrections, or normal crop exports.
- A model project owns a frozen output schema and registry. Never repurpose an original checkpoint class ID by changing a `data.yaml`.
- Every dataset sample has source identity/hash, inclusion/exclusion, class-registry version, reviewer event, and split group where known.
- A generated ZIP is not training-ready. Require complete review, validation, and explicit finalization.
- No model training happens in Studio; the user starts training manually in Colab.

## Phase 0 — decisions and evidence repair

**Dependencies:** this audit, dataset-folder reconciliation, user decisions.

1. Approve exact 31-class YOLO registry/order and mapping (or decide a different detector target count); decide initialization source and class-row transfer policy.
2. Decide Body Images head classes and whether the existing proposed 4+3 shared multi-head model remains the target.
3. Decide `ultimate_whore` vs historical `u_whore`, corruption cardinality, allowed combinations, and how `bodypart_acc` maps to no final tag.
4. Reconcile 546 active-looking unified train/val files against their absent manifest lineage; quarantine from any new project until their provenance is established.
5. Repair/rebuild only through a separately approved later phase: verify the 652 valid YOLO pair inventory and rebuild a correctly paired Studio import; do not reuse current malformed `train_data/yolo/` staging as source of truth.
6. Decide if current 2,328 Clothing candidates are human-review inputs or should be replaced; define unknown-source grouping warning/acceptance policy.

**Acceptance:** decision record exists; all class registries and model IDs have unique versioned hashes; YOLO 31-vs-32 issue resolved; unexplained files have an approved disposition. No code work begins while targets are ambiguous.

## Phase 1 — separate application shell and database

**Dependencies:** Phase 0.

- Create new repository/workspace or explicit top-level `TrainingDatasetStudio` project independent of NewAssetApp. Define its database and migration policy, configuration, project root, logging, backups, and local storage layout.
- Create tables for users/reviewers, model projects, registry versions, import snapshots, examples, label events, selection/exclusion reasons, group keys, split plans, validation runs, dataset versions, finalization events, packages, and checksums.
- Add foreign keys and append-only review/finalization history. Make finalization transition transactional; finalized contents are read-only.
- Add data-root containment checks, safe relative paths, symlink policy, path sanitization, and private-data handling.

**Acceptance:** Studio can create/open/list projects in its own DB and local root; no imports or writes reach NewAssetApp; a new project has a reproducible schema version and backup/restore smoke test.

## Phase 2 — read-only NewAssetApp import contract

**Dependencies:** Phase 1 and approved eligible record rules.

- Specify an export schema version from NewAssetApp containing explicit selected IDs, task, source hashes, detection/crop geometry, human-confirmed status, task-specific eligibility, taxonomy version, AI snapshot provenance, and exclusions.
- Prefer export bundle to direct SQLite integration. If direct query is used as a transitional read-only adapter, run read-only, capture schema version, begin consistent read snapshot, and save an import manifest before copying.
- Stage files by hash, copy into Studio-owned store, verify hashes after copy, store original source references without absolute paths in package output.
- Implement idempotency, retry, duplicate exact-hash groups, stale source checks, unknown schema rejection, and explainable excludes.

**Acceptance:** same manifest imported twice creates one immutable import snapshot; changed source hash creates new snapshot; corrupt/missing/ambiguous rows fail closed; source DB checksum/count and source files are unchanged after import.

## Phase 3 — taxonomy registry and model adapters

**Dependencies:** approved taxonomy and class decisions.

- Implement typed, versioned taxonomy registry with stable IDs, display and serialized values, field scopes, cardinality, allowed combinations, deprecation status, and migration/read aliases (read aliases never mutate old data).
- Implement separate adapters for YOLO text, Clothing single-label folders, and Asset multi-head CNN. Include round-trip tests from structured labels to task files and back.
- Preserve original filename/string as import metadata; do not parse filenames into confirmed labels.
- Create visible taxonomy mapping review for unsupported/ambiguous historical records.

**Acceptance:** exact map/order tests, unknown category/value hard failures, regression fixtures for historical spelling and ambiguous filename examples, no implicit `u_whore` conversion, separate broad model evidence and final human tags.

## Phase 4 — inventory, selection, and split engine

**Dependencies:** Phase 2, Phase 3.

- Build inventory screens with per-class/per-split counts, exclusions/reasons, exact and near duplicate warnings, source-group provenance and uncertain-group warnings.
- Add selection and eligibility based only on explicit human review plus task eligibility.
- Deterministic source-group split manager with seed, algorithm version, locked plan, 80/10/10 suggested default, stratification under group constraints, and explainable class balance limitations.
- Keep images/labels paired; distinguish missing labels from explicit empty labels.

**Acceptance:** deterministic same-input/same-seed assignment tests; no group leakage; tests for duplicate grouping, source groups, class imbalance, empty/missing labels, unknown IDs, and repeatable preview counts; changing a plan after review creates a new revision.

## Phase 5 — human review interfaces and X-AnyLabeling round trip

**Dependencies:** Phase 3, Phase 4.

- Implement CNN image-grid review with single-label control, task/head selector, status filters, keyboard shortcuts, confidence/provenance context, batch audit logging, and undo/history.
- Implement YOLO review copy export/import. Do not write into an original/finalized path. Pin X-AnyLabeling release and test conversion/import/export exact ID/geometry/empty-label behavior with representative fixtures.
- Add diff/merge UI to accept/reject imported boxes per image; preserve generated and prior reviewed snapshots.
- Keep external AI/model inference optional and off unless user explicitly selects a local model; human review is supported without it.

**Acceptance:** save/reopen/review state tests; overlapping object editing; category IDs match exact registry; external change import only updates Studio review history; original input hashes unchanged; no silent conflict resolution.

## Phase 6 — validation, finalize, and immutable versions

**Dependencies:** all previous phases.

- Implement task-specific validators and human-coverage gates.
- Any edit invalidates downstream validation/finalization readiness. Finalization action binds manifest hash, registry hash, split plan, validation report, reviewer coverage, user/time, and predecessor ID.
- Frozen versions reject mutation at DB/API/filesystem layer; corrections clone into a child project version and rerun checks.

**Acceptance:** state-machine transition tests, unauthorized transition tests, hash tamper detection, fork/parent lineage tests, post-finalization write rejection, and invalidation of reports after an edit.

## Phase 7 — package builders and Colab verification

**Dependencies:** approved model architecture and finalized datasets.

- Build the three packages in `PHASE10_COLAB_PACKAGE_SPEC.md` with portable paths, exact class maps, scripts, requirements, manifests, checksums, and full README.
- Add deterministic archive ordering/timestamps if reproducible ZIP hashes are required.
- Test each archive from a clean Colab runtime: verify, build compatible initialization, train a tiny non-production smoke job only in a disposable test package/environment, validate/evaluate, export and reload checkpoint. Do not run training during this planning phase; later execution must be explicitly authorized by the user in Colab.
- Package builder must refuse incomplete review, failed validation, missing decisions, unknown registry, or mutable version.

**Acceptance:** clean-runtime smoke evidence, no absolute paths, archive hash validation, all script exits reviewed, generated reports consistent with package content, no live NewAssetApp files changed.

## Phase 8 — NewAssetApp checkpoint integration contract

**Dependencies:** real user-trained Colab artifact and separate approval.

- Define import-only handoff: model project ID/version, architecture, checkpoint checksum, input preprocessing, class map/head maps, dependency versions, metric report, test set report, and sample inference fixture.
- Validate compatibility in an isolated NewAssetApp test copy; retain existing model/checkpoint as rollback and never overwrite automatically.
- Require a separately approved integration operation after human review.

**Acceptance:** strict checkpoint/schema validation, integration smoke tests, rollback verified, original checkpoint hashes retained, no new model becomes default without explicit approval.

## Risks and acceptance gates

| Risk | Mitigation / gate |
|---|---|
| 31-class detector target unspecified | No label creation or class map until user signs off exact order. |
| 26-class checkpoint mistaken for 12-class Clothing model | Checkpoint hash + metadata + output tensor shape verification; missing 12-class file remains a blocker. |
| Unified active-path examples have no manifest provenance | Quarantine from project import until reconciled. |
| Source leakage in legacy Clothing dataset | Exact hash groups only; surface source identity unavailable; require a user-approved limitation or new provenance. |
| Review tool silently changes IDs or files | Isolated copy, exact registry hash, round-trip fixtures, diff before acceptance. |
| Filename parser becomes taxonomy | Raw filename preserved; structured, approved taxonomy values are training target source. |
| Package appears training-ready too early | Hard state machine; no finalization without review + validation + explicit action. |
| NewAssetApp tests/environment inaccessible | Keep Studio runtime independent; require supported CI and reproducible locked env; current environment note in audit. |

## Recommended first implementation slice

After user decisions, implement one narrow vertical slice first: Clothing classification project with immutable import snapshot, exact 12-class registry, review grid, source/exact-duplicate grouping warnings, deterministic split preview, validation, immutable finalize, portable Colab ZIP, and no automatic training. It has a clear class map and a currently populated dataset, while still explicitly resolving human review/source identity and the absent compatible checkpoint. In parallel, fix the import contract and evidence integrity; do not start with YOLO 31 classes or migrate the unexplained unified images before the related decisions are resolved.
