# Training Data End-to-End Audit

Date: 2026-11-22

## 1. Executive summary

This was a read-only architecture and disposable-fixture audit. No production
database, source image, checkpoint, export, dataset, Girl Packer file, or
training artifact was modified. No model was trained and no dependency was
installed.

The strongest implementation is the immutable-source, append-only review and
handoff path: YOLO originals, effective boxes/classes, independent CNN task
reviews, Studio bundle validation, immutable dataset snapshots, source grouping,
and byte-capped segments are substantially implemented.

The principal remaining defects are:

1. The Body Images binary `cum`/`accessory` policy is not represented as two
   independent completed decisions. The GUI exposes a single target and has no
   explicit `none`/pending distinction.
2. Normal Processing does not apply the complete approved eligibility mapping:
   body-region crops are not allowed to create Arousal or Corruption targets,
   and clothing/fullbody eligibility contains separate restrictions.
3. The live YOLO 31-class target registry is explicitly distinct from the
   legacy 32-class checkpoint. The mapping is documented but not resolved.
4. RAR readiness is blocked because no legitimate RAR writer is installed.
5. Real CPU training and shared-five-head resume are not accepted end to end;
   dry-run, validation, and run tracking are implemented.

No Critical data-loss or silent-registry-remapping defect was confirmed. Several
High-risk gaps remain for approved eligibility and GUI acceptance.

## 2. Architecture and data flow

```text
Professional/Normal GUI
  -> yolo_detections + asset_proposals
  -> human correction/review tables
  -> training_examples or corruption_training_examples
  -> export_training_source_bundle()
  -> immutable v4 handoff bundle
  -> BundleImporter.inspect/import_bundle()
  -> Studio records + registries + media copy
  -> training_bundle byte segments
  -> DatasetService.create_dataset/create_version/finalize
  -> model-specific or shared CNN package
  -> Colab RAR or CPU training entry
```

Key persistence boundaries:

- NewAssetApp SQLite: `app/core/database.py`
- Handoff: `app/core/training_source_exporter.py`
- Studio SQLite: `TrainingDatasetStudio/studio/store.py`
- Studio import: `TrainingDatasetStudio/studio/importer.py`
- Dataset versions: `TrainingDatasetStudio/studio/datasets.py`
- Segment assignment: `StudioStore._assign_training_bundle`
- RAR creation: `TrainingDatasetStudio/studio/archive.py`
- CPU runs: `TrainingDatasetStudio/studio/training.py`, `train_entry.py`,
  `shared_train.py`, `shared_training.py`

## 3. NewAssetApp source inventory

### YOLO annotation and correction

Status: **Implemented and disposable-verified**.

- Original detection coordinates and class remain in `yolo_detections`.
- `save_bbox_edit` appends an effective geometry review.
- `save_yolo_annotation_correction` appends a correction and supersedes the prior
  training example.
- Class-only correction preserves the effective bbox.
- Bbox-only correction preserves the latest effective class.
- Unchanged bbox approval creates no geometry revision.
- Failed saves preserve prior state.
- Corrected YOLO dataset export uses normalized latest effective geometry.

Evidence:

- `app/core/database.py:983-1030`
- `app/core/database.py:1091-1210`
- `tests/test_independent_classification_reviews.py`

### Shared five-head CNN

Status: **Independently implemented/verified for labels, with a High gap in
Body Images multi-label semantics**.

The database has independent `classification_task_reviews` rows per task head,
append-only history, stale state on bbox change, and per-head training examples.
The shared registry is one model identity with five output groups.

Evidence:

- `app/core/database.py:1236-1410`
- `app/core/classification_eligibility.py`
- `data/models/unified_body_images_fullbody/class_registry.json`
- `tests/test_independent_classification_reviews.py`

Confirmed independent heads:

- Fullbody
- Body Images
- Portrait
- Arousal
- Corruption

### Body Images multi-label

Status: **Partial / not implementation-complete**.

The approved policy requires independent binary `cum` and `accessory` decisions,
with both true possible, both false as explicit `none`, and pending distinct
from `none`.

The implementation exposes one GUI option and one database field:

- `normal_body_cnn_target` contains only `bodypart_cum`,
  `bodypart_acc`, or null.
- `save_normal_crop_choice` validates only one `body_images_cnn_target`.
- Professional task review supports a single `target_label` per task.
- `data/task_eligibility_v1.json` declares the labels but also lacks persisted
  completed binary state.

Evidence:

- `app/gui/main_window.py:604-607`
- `app/gui/correction_dialog.py:188-190`
- `app/core/database.py:1658-1659`
- `app/core/database.py:1792-1796`

This is an implementation gap, not merely missing GUI acceptance.

### YOLO class-to-task eligibility

Status: **Professional implemented; Normal Processing incomplete**.

The approved JSON correctly records body regions, person, clothing, Fullbody,
location, and historical mappings. Professional task review uses
`shared_head_eligible` and passes the independent-head tests.

The Normal Processing confirmation path in `confirm_normal_crop_classification`
only permits Arousal/Corruption targets for person, portrait, or Fullbody regions.
It therefore rejects face, boobs, ass, pussy, and legs, which the approved
eligibility JSON declares eligible.

Evidence:

- `data/task_eligibility_v1.json`
- `app/core/database.py:1788-1810`
- `tests/test_classification_eligibility.py`
- `tests/test_independent_classification_reviews.py`

### Clothing

Status: **Implemented and disposable-verified**.

Broad and detailed records are separate. Broad supports the active family list,
while detailed stores the exact human tag. `footwear` is canonical.

Evidence:

- `app/core/database.py:1837-1846`
- `tests/test_independent_classification_reviews.py`
- `tests/test_training_heads_handoff.py`

### Normal Processing

Status: **Implemented, partially verified end to end**.

Normal choices persist independently of Professional Review. Repeated
confirmation reuses the same training example when source hash, bbox, label,
and exact confirmed labels are unchanged.

Normal export and training eligibility are separate: saving/export does not
automatically confirm all CNN targets.

Missing live acceptance remains for every category and repeated save/reload.

Evidence:

- `app/core/database.py:1583-1708`
- `app/core/database.py:1711-1850`
- `tests/test_phase9_crop_export.py`

### Professional Review

Status: **Implemented and disposable-verified; live GUI acceptance incomplete**.

Independent task state, bbox staling, orphan guards, and task rejection are
present. Multiple overlapping detections remain dependent on live navigation
and image-level queue acceptance.

Evidence:

- `app/core/database.py:1236-1410`
- `tests/test_independent_classification_reviews.py`

## 4. Studio schema and organization

Studio schema 3 stores:

- immutable imported bundles
- bundle registries
- imported records
- annotation events
- model/task segments
- datasets
- immutable dataset versions
- version record/split snapshots
- training runs

Schema locations:

- `TrainingDatasetStudio/studio/store.py:20-100`
- `TrainingDatasetStudio/studio/importer.py`
- `TrainingDatasetStudio/studio/datasets.py`

The shared CNN is grouped by one `shared_cnn` bundle identity across five task
heads. Clothing Broad and Clothing Detailed use separate task identities.

## 5. Model/head/target mapping

| Model/task | Identity | Status |
|---|---|---|
| YOLO | `newassetapp_yolo_detector_v1` | Implemented; active-vs-legacy checkpoint discrepancy unresolved |
| Shared five-head CNN | `unified_body_images_fullbody_cnn` | Implemented; one accumulating segment; real training unverified |
| Clothing Broad | `clothing_classifier` | Implemented and tested |
| Clothing Detailed | `newassetapp_detailed_clothing_classifier` | Implemented and tested |

The active target registry contains 31 classes, with IDs 0–30.
The preserved legacy checkpoint contains 32 classes and has no explicit mapping
to the new 31-class target registry.

Evidence:

- `TrainingDatasetStudio/registries/yolo_detector_v1.json`
- `data/models/unified_body_images_fullbody/class_registry.json`

## 6. End-to-end traceability matrix

| Case | GUI persistence | Training example | Handoff | Studio import | Dataset/package | Status |
|---|---|---|---|---|---|---|
| YOLO class correction | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| YOLO bbox correction | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| YOLO class-only correction | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| YOLO bbox-only correction | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| Unchanged bbox approval | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| Body Images cum=true | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | Head identity exists; multi-label state incomplete |
| Body Images accessory=true | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | Single-target model |
| Cum=true, accessory=true | FAIL | FAIL | FAIL | FAIL | FAIL | No independent two-target persistence |
| Explicit none | FAIL | FAIL | FAIL | FAIL | FAIL | No explicit completed-negative state |
| Pending/unreviewed | PARTIAL | PASS as absent | PARTIAL | PARTIAL | PARTIAL | Absence is representable but not explicit as body-image decisions |
| Fullbody head | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| Portrait head | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| Arousal head | PASS Professional | PARTIAL Normal | PASS | PASS | PASS | Normal eligibility gap |
| Corruption head | PASS Professional | PARTIAL Normal | PASS | PASS | PASS | Normal eligibility gap |
| Multiple heads for one crop | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| Clothing Broad + Detailed | PASS | PASS | PASS | PASS | PASS | PASS disposable |
| Invalid/rejected record | PASS DB | PASS suppression | PASS quarantine/exclusion | PASS | PASS exclusion | PASS disposable |
| Normal save/reload | IMPLEMENTED | PASS confirmation | PASS where exercised | PASS | PASS | NOT VERIFIED live GUI |
| Professional independent confirmation | PASS DB | PASS | PASS | PASS | PASS | NOT VERIFIED live GUI |
| Manual/orphan proposal | PASS guard | Not eligible | N/A | N/A | N/A | PASS DB guard; GUI guard not live-verified |
| Repeated handoff import | N/A | N/A | PASS | PASS duplicate detection | N/A | PASS disposable |
| Dataset snapshot/filter | N/A | N/A | N/A | PASS | PASS | PASS disposable |

## 7. Test evidence

Disposable audit command:

```powershell
.\.venv\Scripts\python.exe -m unittest
  tests.test_training_heads_handoff
  tests.test_independent_classification_reviews
  tests.test_phase9_crop_export
  tests.test_correction_crop_pipeline
  tests.studio.test_segment_capacity
  tests.studio.test_v2_pipeline
  tests.studio.test_shared_training
  tests.studio.test_workflow -v
```

Result: **62 tests passed** in 113.515 seconds.

Additional existing evidence:

- Full suite previously passed 177 tests.
- The training head handoff test exported, imported, filtered, versioned,
  and package-built all heads and clothing tasks in disposable data.
- Segment tests verified exact-fit rollover, complete-record-only rollover,
  duplicate identity deduplication, rollback, and shared CNN aggregation.

No test should be treated as live headed-GUI acceptance.

## 8. Import and provenance

Implemented safeguards:

- JSON schema validation for v2/v3/v4.
- Canonical bundle SHA-256 validation.
- Payload size and SHA-256 validation.
- Safe bundle-relative paths.
- Registry validation.
- YOLO class ID/name and coordinate-space validation.
- Region identity is not accepted as a Body Images head.
- Duplicate bundle import returns a duplicate result.
- Repeated import does not create duplicate records.
- Media is copied only after source SHA verification.

Potential exposure:

- Studio can reconstruct task, source, bbox, human state, and registry for
  accepted records.
- A record's complete correction history depends on producer lineage; historical
  rows without complete lineage remain warnings/exclusions.

## 9. Dataset lifecycle assessment

Implemented:

- Dataset creation by task and registry identity.
- Immutable version records.
- Annotation snapshots.
- Explicit include/exclude selections.
- Train/validation/test splits.
- Source-SHA grouping across splits.
- Finalization and exact split counts.
- Package export after finalization.
- Source revalidation by Studio media hash.
- Package hash manifest.

Verified by tests:

- Source leakage prevention.
- Shared and model-specific filtering.
- YOLO normalized labels.
- Shared CNN package validation.
- Dataset duplicate handling.

Not live-verified:

- GUI creation and confirmation of a snapshot.
- GUI split override and quarantine workflow.
- Full GUI package creation and archive selection.

## 10. Storage and 5 GB segment policy

Status: **Implemented and unit-verified**.

The exact production cap is `5_000_000_000` bytes. Segment accounting includes
complete media bytes plus annotation and original JSON bytes. A complete record
larger than the cap is rejected atomically. Rollover occurs only when a complete
record will not fit. Shared heads are grouped by `shared_cnn`.

Evidence:

- `TrainingDatasetStudio/studio/store.py:213-320`
- `tests/studio/test_segment_capacity.py`
- `tests/studio/test_v2_pipeline.py`

Production segment data was not inspected for byte totals or rolled over.

## 11. Colab RAR/package readiness

Status: **Package generation exists; RAR delivery is blocked**.

Implemented:

- Model-specific package staging.
- Dataset manifest and checksums.
- Registry inclusion.
- Training code and Colab instructions for shared and model-specific packages.
- Exact 4,000,000,000-byte uncompressed minimum.
- RAR-only behavior with no ZIP fallback.
- RAR archive-size and integrity test checks.

Exact read-only readiness result:

- RAR writer: **not found**
- `rar_available`: false
- Exact 4 GB threshold code: present
- No archive was created.

External blocker: a legitimate WinRAR/RAR executable must be approved and
installed or an approved path must be supplied. No repository or environment
change was made.

## 12. Local CPU-training readiness

Status: **Dry-run/validation exists; real training is not accepted**.

Implemented:

- CPU compatibility checks.
- Confirmed-run guard.
- Unique run directories.
- Run metadata/log database rows.
- Cooperative cancel file.
- Shared five-head masked loss.
- Checkpoint generation for real shared training.
- Unique checkpoint path per run.

Missing/blocked:

- Shared `resume` explicitly raises an unsupported error.
- Real shared training was not run.
- Real resource/time estimates from an approved small dataset are unavailable.
- RAR delivery does not complete the delivery lifecycle.

## 13. GUI workflow coverage

The existing synthetic Qt acceptance suite covers:

- NewAssetApp main, Normal Processing, Professional Review.
- Studio projects, segments, builder, records, validation, packages,
  artifacts, import/activation, and history.

This evidence proves widget navigation and layout only. It does not prove
headed-desktop save/reload/export behavior or real model/data workflows.

## 14. Data integrity, duplication, provenance, and leakage risks

### Confirmed risks

- TDA-001 / High: Body Images binary decisions are not persisted independently.
- TDA-002 / High: Normal Processing Arousal/Corruption eligibility conflicts with
  the approved body-region mapping.
- TDA-003 / High: Live 31/32 YOLO registry discrepancy remains unresolved.
- TDA-004 / High: Real CPU resume is unsupported.
- TDA-005 / High: RAR package delivery is blocked by missing external writer.
- TDA-006 / Medium: Live GUI save/reload and modal acceptance are incomplete.

### Controls that reduce risk

- Training examples are superseded rather than silently overwritten.
- Invalid crops are recorded and suppress stale targets.
- Source SHA changes invalidate current exports.
- Studio rejects duplicate bundle hashes.
- Studio uses explicit task/content identities for segment deduplication.
- Dataset versions block source leakage across splits.
- RAR code requires genuine package size and refuses ZIP fallback.

## 15. Findings with remediation references

### TDA-001

- Severity: High
- Application: NewAssetApp
- References: `app/gui/main_window.py:604-607`,
  `app/core/database.py:1658-1659`, `data/task_eligibility_v1.json`
- Evidence: only one target field/GUI option exists.
- Impact: cannot store both cum and accessory true or explicit both-negative
  decision.
- Recommended fix: persist two independent binary fields plus a completed/none
  state. Do not change them into separate image copies.
- Dependency: approved UI wording and storage schema decision.
- Safe verification: disposable database test for four binary combinations.

### TDA-002

- Severity: High
- Application: NewAssetApp / Normal Processing
- References: `app/core/database.py:1788-1810`
- Evidence: Normal Processing rejects body-region Arousal/Corruption targets.
- Impact: approved eligible records cannot reach training.
- Recommended fix: use `required_tasks`/`shared_head_eligible` consistently for
  Normal and Professional paths.
- Dependency: no taxonomy change.
- Safe verification: disposable face/boobs/ass/pussy/legs confirmation matrix.

### TDA-003

- Severity: High
- Application: Both / YOLO
- References: `TrainingDatasetStudio/registries/yolo_detector_v1.json`
- Evidence: 31 approved target classes and legacy 32-class checkpoint with
  `"mapping": "none"`.
- Impact: wrong class IDs can enter training if the legacy model is used
  directly.
- Recommended fix: require an explicit approved legacy-to-target mapping or
  activate only an explicitly mapped detector checkpoint.
- Dependency: external taxonomy/model decision.
- Safe verification: model/predictor ID and class-ID fixture check.

### TDA-004

- Severity: High
- Application: TrainingDatasetStudio
- References: `TrainingDatasetStudio/studio/shared_train.py:48-49`
- Evidence: `resume` explicitly unsupported.
- Impact: interrupted real shared training cannot resume.
- Recommended fix: implement checkpoint epoch/optimizer/state resume only after
  format and artifact compatibility are designed.
- Dependency: approved artifact format.
- Safe verification: interrupted disposable training with exact run recovery.

### TDA-005

- Severity: High
- Application: TrainingDatasetStudio
- References: `TrainingDatasetStudio/studio/archive.py:49-95`
- Evidence: no RAR writer in environment.
- Impact: required Google Drive RAR delivery is unavailable.
- Recommended fix: install an approved WinRAR/RAR executable or provide its
  executable path under explicit configuration.
- Dependency: external application/license and approval.
- Safe verification: create a disposable 4 GB genuine package and test RAR
  integrity.

### TDA-006

- Severity: Medium
- Application: Both
- References: GUI scenarios and screenshot inventory
- Evidence: synthetic Qt capture pass; no complete headed live workflow.
- Impact: layout and persistence defects can remain undiscovered.
- Recommended fix: run one disposable headed workflow per representative case.
- Dependency: stable live desktop capture and concurrent-user avoidance.
- Safe verification: disposable database and temporary source directory.

## 16. Disposable lifecycle verification addendum

Date: 2026-11-22

Scope: Studio accumulation, dataset snapshots, readiness accounting, package
binding, and read-only RAR inspection. This addendum does not replace the
upstream NewAssetApp findings above.

### Changes and focused evidence

- Studio schema 4 now persists a dataset's model identity, including a
  migration/backfill from its selected training segment. Dataset versions select
  all matching records for that model/task/registry across segment rollovers.
- Segment keys include the model/registry series identity. Same source/crop/head
  identities with identical targets deduplicate; contradictory targets suppress
  every conflicting member and persist a conflict marker so a later import
  cannot re-enroll that disputed crop. Invalidated segment membership is removed
  with byte/count accounting, and importer counts use each record's final
  status.
- Finalization re-hashes media and checks source/crop provenance, including
  authoritative crops. Explicit Body Images negative masks are validated as
  evaluated targets. CNN export copies an authoritative crop as-is rather than
  applying its source-coordinate box a second time.
- Readiness is scoped to the dataset's model identity, understands nested
  Body Images masks and actual shared-head metadata, and does not report 100+
  source groups as ready unless the documented train/validation/test group
  minima are met.
- Generic package manifests now bind the exact dataset-version ID, model and
  registry; their file list includes hashes and byte counts. The training gate
  checks package files and the generic dataset records against the finalized
  Studio snapshot. Shared packages are checked against all five finalized head
  versions and their record provenance. A disposable test exercised acceptance
  with the trainer stubbed; no training was started.
- RAR inspection no longer labels a tiny package ready simply because a writer
  exists. A genuine archive is attempted only when both a writer and sufficient
  uncompressed input are present; the actual `.rar` size and integrity test
  remain authoritative.

Focused command:

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.studio.test_dataset_lifecycle `
  tests.studio.test_segment_capacity `
  tests.studio.test_v2_pipeline `
  tests.test_training_source_exporter.TrainingSourceExporterTests.test_explicit_empty_yolo_image_survives_v4_studio_and_colab
```

Result: **22 tests passed** in 68.398 seconds. Python compilation checks also
passed for all changed Python files.

### RAR status (supersedes the earlier environment observation)

- Existing writer found: `C:\Program Files\WinRAR\WinRAR.exe` (not installed or
  changed during this task).
- Read-only inspection of the small Studio package source tree: 919,078 bytes;
  3,999,080,922 bytes short of the 4,000,000,000-byte precondition.
- Status: **blocked**. No archive was created, no data was padded, and no
  substitute format was used. A real package of adequate size and its actual
  RAR integrity test remain unverified.

### Deferred work and limits

- No GUI/Qt tests or layout acceptance were run.
- No model training was run. One expanded handoff test command reached a
  `dry_run_ok` result but remained active past its 180-second limit; it was
  stopped and is not counted as passing evidence.
- No dependency was installed. Production databases, source assets, model
  checkpoints, and production exports were not modified.
- The upstream eligibility and YOLO checkpoint-mapping risks in TDA-001 through
  TDA-004 remain open. No user-facing GUI redesign or acceptance is claimed.

### GUI plan (deferred)

1. Make model-series selection explicit and show that a dataset accumulates
   matching records across all its byte-capped segments.
2. Show source-group split counts, excluded/pending/stale/duplicate reasons,
   per-head readiness, and required split coverage before finalization.
3. Present Body Images `cum` and `accessory` as separate evaluated
   true/false/pending outcomes.
4. Bind the training confirmation screen to the exact finalized version and
   verified package; show model, registry, package checksums, and CPU/dry-run
   state distinctly.
5. Keep RAR delivery disabled until the real archive meets the exact size and
   integrity checks; never pad or silently substitute an archive format.

## 16. Missing capabilities

- Explicit Body Images two-binary-state decision.
- Consistent Normal Processing eligibility for body regions and clothing.
- Explicit approved legacy-32 to target-31 YOLO mapping.
- Real shared-training checkpoint resume.
- Live headed-GUI acceptance.
- Real RAR writer/integrated archive delivery.
- Real CPU training resource benchmark.
- Production activation/rollback for Studio artifacts.

## 17. Prioritized remediation plan

1. Implement or decide the Body Images binary completion state.
2. Align Normal Processing eligibility with `task_eligibility_v1.json`.
3. Resolve/document the active YOLO 31/legacy 32 mapping before model use.
4. Add disposable headed GUI end-to-end acceptance for one crop per category.
5. Verify orphan/manual proposal GUI guards visually.
6. Define shared-training resume/artifact format.
7. Supply and verify an approved RAR writer.
8. Run only approved disposable real CPU smoke training.
9. Define production activation/rollback approval if required.

## 18. Final audit conclusion

The core persistence, handoff, Studio import, dataset version, 5 GB segment,
and package-generation architecture is substantially implemented and covered by
disposable tests.

It is not complete enough to claim end-to-end training-data readiness:

- Body Images multi-label semantics are incomplete.
- Normal Processing eligibility is inconsistent with the approved mapping.
- The YOLO active/legacy registry discrepancy is unresolved.
- RAR delivery is externally blocked.
- Real CPU training and shared resume are not verified.
- Headed live GUI acceptance remains incomplete.

## Registry and eligibility follow-up

The approved 31-class Studio YOLO registry remains unchanged and is now enforced
at three boundaries: bundle import, dataset finalization, and training
authorization. Each boundary compares the full registry payload to the installed
approved JSON; the installed registry is also validated against `classes.txt`
and its SHA-256 checksum.
Mismatched or legacy class mappings are quarantined; persisted legacy dataset
versions cannot bypass the later finalization or training checks. Historical
annotations are retained, and any current target requires explicit correction
to an approved class. The existing 32-class checkpoint is not remapped to this
registry.

The NewAssetApp active YOLO policy and crosswalk now follow the 31-class Studio
registry, with the old 32-class mapping retained as historical-only data.
Normal Processing review also uses the current eligibility validator, and stale
or unsupported model suggestions are not approvable. The
`fullbody_athletic` Final Tag disposition remains unresolved pending human
review.

Additional disposable evidence after the earlier addendum:

- Registry gate and missing-media/idempotency tests: 2 passed.
- Dataset lifecycle/finalization/training-gate tests: 8 passed, including a
  mismatched registry being blocked by both finalization and training.
- Segment capacity/idempotency tests: 9 passed.
- Existing handoff bundle import test: 1 passed.
- Changed Python files passed Pylance syntax checks.

These are focused checks, not a complete end-to-end readiness sign-off. The
previously stopped long handoff test remains inconclusive and was not rerun.
No training, GUI/layout acceptance, production-data modification, dependency
installation, or archive creation was performed. RAR readiness remains blocked
at the previously measured 919,078-byte package size, 3,999,080,922 bytes short
of the 4,000,000,000-byte minimum. The separate Body Images two-binary-decision
gap, human review of unresolved taxonomy, real shared-model training, and live
GUI acceptance also remain open.

## Superseding lifecycle continuation

The continuation report at
`reports/TRAINING_DATA_LIFECYCLE_CONTINUATION.md` supersedes stale conclusions
in this earlier audit about Body Images target semantics and Fullbody
`athletic` mapping. It records the latest focused verification, the inconclusive
long segment test, and the still-blocking real-dataset and RAR requirements.
