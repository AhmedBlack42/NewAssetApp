# Phase 11.6 — Training Handoff Audit

Date: 2026-11-09 (Africa/Cairo)

## Scope and status

This report records the Phase 11.6 **Stage 1 audit** of the current NewAssetApp
database, the first immutable Studio handoff bundle, the v1/v2 contracts, model
registries, launcher, and existing Studio files. It is an inspection report; no
database, source image, checkpoint, Girl Packer file, or existing bundle was
modified during this audit.

The roadmap requests staged execution and a report before continuing. Work stops
after this audit so the data-integrity findings can guide Stage 2 before building
the importer or Studio GUI.

## Git and workspace state

- **BLOCKED:** `git status --short --branch` could not run because
  `F:\My Tools\New folder\NewAssetApp` has no `.git` directory. The accessible
  workspace is therefore a source snapshot without Git history/status evidence.
- Confirmed current files include `app/core/training_source_exporter.py`,
  `app/workers/dataset_export_worker.py`, `app/gui/main_window.py`, both Studio
  import contracts, the Studio YOLO registry, the existing first bundle, and the
  NewAssetApp SQLite database.
- `TrainingDatasetStudio` currently has a README, two contracts, and YOLO registry
  files. It has no launcher, separate environment configuration, application
  entry point, Studio database, importer, GUI, project store, or dataset packager.

## First bundle inspection

Bundle:

`training_source/bundles/newassetapp_20261109T014752986366Z_12b7c0dbf0/manifest.json`

- Bundle ID: `newassetapp_20261109T014752986366Z`
- Schema version: 2
- Bundle SHA-256: `12b7c0dbf0bffb5b929f999c36c570ae09e2cd51209d6a87aaa9a0a925182f9f`
- **PASS:** Recomputed the canonical manifest hash (excluding the hash field) and
  it matches the declared hash.
- **PASS:** All five listed payload files exist and match their declared byte
  counts and SHA-256 values. The payload is three registry JSON files and two
  source images. The two unique images account for all five accepted records.
- **PASS:** The manifest has five accepted records and one explicit exclusion.
  The excluded record is `training_example:5`, task
  `asset_classification`, reason `label_not_in_current_model_registry`.
- **PASS:** The excluded row has not been deleted from the NewAssetApp database.
  Its original source exists and matches its stored hash.
- **NOT TESTED:** JSON Schema validation could not be run because `jsonschema` is
  not installed in the active Python 3.15 context. The contract itself parses as
  JSON. File integrity and canonical bundle-hash checks were performed directly.
- The producer version is the literal `workspace`; this is not a useful released
  application version and should be replaced by a stable application/build
  identity in a later contract/exporter change.

The record schema stores `bbox_xyxy` as four numbers but does not define their
coordinate space. Current exporter values are source-image pixel coordinates,
and the source width/height are included. The manifest does not explicitly mark
the units or coordinate space. The record has a single `bbox_xyxy`, a nullable
`detection`, and model prediction data in provenance; it does not consistently
provide separate original predicted geometry, final human geometry, and an edit
history suitable for YOLO ground truth. The importer must not infer these roles
from a bare box.

## Excluded `face` record investigation

Database record `training_example:5`:

- Task: `unified_body_images_fullbody` (bundle task `asset_classification`).
- Label: `face`.
- NewAssetApp state: `human_confirmed=1`, `training_eligible=1`.
- Proposal/detection: proposal 90, detection 90; proposal type `face`, category
  `body_images`, review state `pending`.
- Source image: ID 16, 920×1371, path
  `samples/71328784_037_2c7b.jpg`; the source exists and its SHA-256 matches the
  database and bundle.
- Bounding box: `[413.168975830078, 3.54559540748596,
  585.632873535156, 256.12548828125]` in source pixels.
- YOLO detection 90 says model `legacy_yolo`, class ID 1, class `face`, confidence
  `0.9030352830886841`, status `original`.
- The Studio YOLO registry `newassetapp_yolo_detector_v1` includes class ID 1
  `face`. The Unified Body Images + Fullbody registry has no `face` class in
  either output group.
- Its provenance also contains Asset CNN class `bodypart_face` and a high
  confidence YOLO `face` prediction. These predictions are evidence, not proof
  of the intended training task.

**Confirmed diagnosis:** The exporter did not compare the row with the wrong
registry for the task it was given. It used the Unified CNN registry correctly;
the row was recorded under the wrong task/taxonomy for a `face` target. `face` is
a valid class in the separate YOLO target registry, but the existing row does not
establish that the human intended YOLO detection training rather than a CNN
classification. Automatically moving it to the YOLO task would reinterpret a
human decision. Preserve/quarantine it and require an explicit task correction
or a new reviewed YOLO annotation before packaging. The current bundle at least
retains its record ID and precise exclusion reason; it does not include its media
or all its data in the manifest exclusion entry.

## Current source/database integrity findings

- Database migration version: 13.
- `training_examples`: 6 current rows; 5 are accepted into the first bundle and
  one is the quarantined `face` row.
- `corruption_training_examples`: 0 rows.
- `correction_records`: 68 rows.
- Legacy `training_records`: 0 rows.
- `yolo_detections`: 1,124 rows; `asset_proposals`: 1,128 rows.
- Only one `correction_records` row currently has `yolo_training_eligible=1`.
  That row also has `human_confirmed=0`; its corrected payload contains YOLO
  class ID 27 and other legacy structured values. It must not become a confirmed
  target solely because the eligibility bit is set. Stage 2 must inspect its
  intended label/registry and reconcile eligibility with human confirmation
  without silently changing the user's decision.
- The current training-source exporter reads current `training_examples` and
  `corruption_training_examples`. It does not read `correction_records`, despite
  task-specific correction eligibility flags there. Thus the stored YOLO
  correction cannot travel through the current bundle path.
- Current training-example rows preserve model prediction JSON and the selected
  label/box, but do not carry an explicit model registry identity per row at
  database insertion, an immutable registry version for all tasks, or linked
  correction-event IDs. Exported provenance therefore cannot satisfy the
  roadmap’s complete correction lineage for all records.
- The person-to-Others policy is reflected in the current README; it must remain
  an independent person-region/corruption task and must not be mapped to
  Fullbody or the YOLO class `fullbody`.

## Contract and registry comparison

- v1 is a legacy single-registry schema with a narrow task enum and does not
  express the v2 model/registry-per-record structure. The first bundle is v2 and
  should be imported only after a strict v2 validator is implemented. Preserve
  v1 for backward compatibility; do not retrofit the first bundle as v1.
- v2 supports model and registry lists, task-specific records, referenced media,
  review state, provenance, excluded rows, file hashes, and a bundle hash. It
  does **not** currently require every model reference to resolve to exactly one
  listed registry, every registry reference to resolve to a registry file,
  annotation coordinate-space metadata, original and corrected YOLO geometry,
  YOLO class IDs on each target, or a rich preserved payload for exclusions.
- The v2 schema permits `detection: null` on every task. It does not constrain
  bbox ordering/bounds against source dimensions or ensure a YOLO class ID/name
  belongs to the referenced registry. Those are importer validation gaps.
- The existing YOLO registry has 31 target classes (IDs 0–30), including
  `person` as ID 0 and `face` as ID 1. Its provenance references a legacy
  32-class checkpoint. This registry is task-specific; do not reuse it for CNN
  labels. The raw `person` detection remains a person ROI and is not a Fullbody
  label.
- The Unified CNN registry identifies two separate output groups under one
  model identity: `body_images` and `fullbody_state`. The exporter currently
  records both as the broad task `asset_classification` and uses an
  `output_group` structured label. Future projects/packages must preserve the
  output-group identity so `portrait`/`tportrait` cannot mix with Fullbody state.
- Broad Clothing and Detailed Clothing have distinct registries and label
  spaces. The two current records are separate tasks and must remain separate.

## Launcher and Python environment

- `run_app.ps1` derives the root from `$PSScriptRoot`, sets `.venv` in
  `VIRTUAL_ENV` and `PATH`, changes working directory, checks the venv Python,
  prints its version/identity, passes through `$args`, and reports nonzero exits.
  It does not install/repair dependencies. Its current checks verify that the
  interpreter can start, not that required app imports succeed.
- `.venv/pyvenv.cfg` identifies Python 3.11.9 and points to
  `C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe`.
  `.venv\Scripts` contains Python and PySide6 launchers.
- The current shell resolves `python` to Python 3.15.0, and `py -0p` reports no
  installed Python runtimes. The recorded Python 3.11 path is inaccessible to
  this execution context (access denied on path inspection); invoking the venv
  Python previously returned “No Python at …Python311…”.
- **BLOCKED / NOT DETERMINED:** This context cannot establish whether the base
  Python was removed or is merely hidden by its restricted access profile. The
  user's report that `run_app.ps1` worked previously is consistent with an
  execution-context difference but does not prove the present GUI can launch.
  Do not repair or install anything without approval. Studio launcher must
  follow the root-relative, no-auto-install approach after environment
  availability is established.

## Evidence not obtained

- No live NewAssetApp GUI edit/save/close/reopen test was run.
- No YOLO correction, box resize/move, add/delete annotation, or new class was
  changed during this audit.
- No Studio GUI/importer exists to run an import or persistence test.
- No end-to-end bundle → importer → GUI → model-specific package test exists.
- No model training or bulk annotation was run.
- No hardware inventory or local-training feasibility benchmark was performed
  in this audit.
- Existing output isolation was not exercised end to end.

## Stage 1 outcome and proposed Stage 2 order

**Stage 1: PASS with data-integrity blockers.** The bundle is internally
hash-consistent and its media/registries are intact. The excluded `face` record
is recoverable and its registry mismatch is understood. The source database has
an eligible-but-unconfirmed YOLO correction, correction rows are not exported,
and task/geometry lineage is insufficient for lossless YOLO ground truth.

Before implementing Studio import, Stage 2 should:

1. Define canonical task/model/registry identities, keeping YOLO, Unified CNN
   `body_images`, Unified CNN `fullbody_state`, broad Clothing, detailed Clothing,
   and corruption-state tasks separate.
2. Audit correction persistence methods and GUI class/box operations against the
   live schema on a disposable database. Define immutable prediction snapshots
   alongside append-only human edits and explicit confirmation/eligibility.
3. Add a v3 bundle contract/export path or a backward-compatible v2 extension
   that explicitly carries coordinate space, original/final boxes, YOLO class
   ID/name, registry identity/version, correction history, and complete excluded
   row payloads. Never silently remap the existing `face` CNN record.
4. Add end-to-end persistence/export tests using disposable databases before
   building importer behavior on top of ambiguous records.
5. Recheck Python 3.11 under the user's normal launcher context before creating
   Studio's independent environment. Do not alter `.venv` or install packages
   from this restricted context.

These are recommendations, not changes made by this Stage 1 audit.

---

## Stage 2 — Follow-up handoff integrity verification

Date: 2026-11-09 (Africa/Cairo)

This addendum verifies the original requested v2 bundle against the current
schema-16 database and records the subsequent v3 export work. The original v2
bundle was not modified. Database totals below are current observations and are
not retroactively attributed to the database state at the v2 bundle's creation.

### First bundle: record-by-record result

The v2 bundle hash remains
`12b7c0dbf0bffb5b929f999c36c570ae09e2cd51209d6a87aaa9a0a925182f9f`.
Canonical re-hashing matched it. All five payloads (two images and three
registries) exist and match both byte size and SHA-256. Both media files match
their source-image hashes in the current database and their original files in
`samples/`.

| Record | Intended task/label | Human state in current DB | Registry finding | Audit result |
|---|---|---|---|---|
| `training_example:3` | Unified CNN / Fullbody State / `topless` | Confirmed and eligible | `topless` belongs to the Fullbody State output group | Acceptable confirmed target; v2 task alias is broad, but `structured.output_group` disambiguates it |
| `training_example:6` | Unified CNN / Body Images / `portrait` | Confirmed and eligible | `portrait` belongs to the Body Images output group | Acceptable confirmed target; shared source with other records is retained |
| `training_example:4` | Unified CNN / Body Images / `portrait` | Confirmed and eligible | `portrait` belongs to the Body Images output group | Acceptable confirmed target |
| `training_example:1` | Broad Clothing / `bra` | Confirmed and eligible | `bra` is class ID 0 in the broad-clothing registry | Acceptable confirmed target |
| `training_example:2` | Detailed Clothing / `plain_bra` | Confirmed and eligible | `plain_bra` is present in the separate detailed-clothing vocabulary | Acceptable confirmed target; do not combine with the broad Clothing class space |
| `training_example:5` (excluded) | Stored as Unified CNN / Body Images / `face` | Confirmed and eligible flags in the source DB | `face` is absent from this CNN output group. A distinct YOLO registry has a `face` detector class, but this record has no YOLO target-class annotation and was stored as CNN classification. | Quarantine as unresolved task/registry mismatch. Do not remap it to YOLO or admit it to CNN training without a new explicit review. |

The excluded row's source remains in `samples/` and its bytes still match its
database hash. The v2 manifest exclusion preserves its ID/task/reason but does
not embed the image or full rejected-row payload. The later v3 exporter includes
the unresolved row's data and source media in the exclusion entry, without
altering this original v2 bundle.

### Current database and person-ROI policy

- Current database migration version is 16. It contains 21
  `training_examples`, 73 `correction_records`, 1,124 YOLO detections, and 1,131
  asset proposals at the time of this verification. These counts differ from
  the historical Stage 1 snapshot.
- In the original v2 handoff, no record is a YOLO annotation. Its model
  predictions are provenance only. In current NewAssetApp policy, a YOLO
  `person` detection remains an Others/person-region ROI and cannot be
  confirmed as Fullbody; it is not silently turned into a Fullbody classifier
  target.
- The v2 media and labels are internally traceable, but v2 does not define the
  bbox coordinate space or preserve original-vs-corrected YOLO geometry and
  edit history. The original bundle is therefore unsuitable as a lossless
  corrected-YOLO handoff.

### Follow-up exporter and current v3 bundle

The workspace now has an additive v3 import contract and exporter. The v2
contract and bundle remain unchanged. The latest generated bundle is:

`training_source/bundles/newassetapp_20261109T023555894626Z_a0b1c3669b/`

- Bundle ID `newassetapp_20261109T023555894626Z`; schema version 3; canonical
  hash `a0b1c3669b653f65ae96df880ba81e709a66a4636278d406bed298cbd3e50d8a`.
- 19 accepted, human-confirmed records; 2 explicit unresolved exclusions;
  10 unique source images; 4 task-specific registries. Every listed payload
  exists and matches size/hash, and canonical manifest hashing matches.
- Task identities are separated for YOLO, Body Images, Fullbody State, broad
  Clothing, detailed Clothing, and corruption-state classification. Records
  carry source-pixel annotation geometry, target and original model boxes,
  class IDs where applicable, model/registry identity, and available correction
  lineage. Exclusions retain the record metadata and source media when
  verifiable.
- `training_example:5` (`face`) and `training_example:15` (`pussy`) remain
  explicitly quarantined as `unified_classification_unresolved`; no unrelated
  registry was changed to force either label into a model class list.
- Newly persisted professional-review YOLO corrections link to correction
  records in `training_examples`. Historical eligibility-only correction rows
  are not retroactively treated as confirmed dataset targets.
- The first focused verification run recorded in the workspace history passed
  55 tests before two more routing checks were added. A rerun after those later
  changes was pending at report preparation, so this addendum does not claim a
  current full/focused-suite pass. The latest v3 bundle was independently
  checked for canonical hash, listed file bytes/hashes, task identities,
  confirmation fields, and exclusion entries. Formal JSON Schema validation
  remains untested because `jsonschema` is unavailable in the active
  environment; no dependency was installed.

### Scope boundary and acceptance

No Studio importer, review GUI, immutable dataset-version builder, Colab
packager, or CPU training manager has been accepted in this phase. No real
training was started. The existing source bundle is immutable and the ordinary
user output roots (`output/body_images`, `output/clothing`, `output/fullbody`)
remain separate from `training_source/bundles`.

**Phase 11.6 status: PARTIAL.** The requested first-bundle audit is complete;
its hashes, source identity, confirmation flags, task-specific label mappings,
and `face` quarantine decision are recorded above. The v3 handoff materially
improves integrity and lineage, but formal schema validation and a current
post-change focused test rerun remain outstanding. Phase 11.7 work has not
started in this acceptance-gated sequence. Continue only after review of this
Phase 11.6 result.
