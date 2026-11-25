# Phase 11.1 — Reconciliation and Studio Foundation

**Scope:** Reconcile Phase 10 with the Phase 11 decisions, inspect the current NewAssetApp state, and establish the versioned registry/import foundation for a separate TrainingDatasetStudio. This document covers Phase 11.1 only. No Studio application workflow, training, dependency change, checkpoint update, migration, or existing dataset edit was performed.

## Executive result

- **Launcher verified:** `run_app.ps1` uses the project `.venv` interpreter and performs its startup check. The ordinary restricted run failed because Windows could not start its configured Python 3.11 executable. In the approved elevated context the same launcher opened the existing **NewAssetApp — Normal Processing and Professional Review** window. The previous sandbox error is not evidence that the user's working environment is broken.
- **New target registry recorded:** `TrainingDatasetStudio/registries/yolo_detector_v1.json` contains the exact 31 names and order from the Phase 11 decision. `classes.txt` and its SHA-256 sidecar are separate X-AnyLabeling-friendly registry artifacts, checked against that order by tests.
- **Checkpoint identity kept separate:** The old `models/yolo/best.pt` 32-class checkpoint and its recorded SHA-256 remain the legacy identity. The new registry explicitly declares no class mapping. No old class ID is treated as equivalent to a new class ID, and the old checkpoint/map files were not edited.
- **Import contract established:** `TrainingDatasetStudio/contracts/newassetapp_import_v1.schema.json` defines a versioned, content-hashed bundle carrying task, source-image identity, dimensions, optional detection box, human-review/eligibility state, labels, registry identity, source snapshot, prediction/correction provenance, and bundle file hashes. It avoids absolute media paths. It is a contract only; no importer or database was built.
- **Phase 10 unresolved lineage remains a gate:** The 546 unexplained unified Body Images/Fullbody train/val images remain quarantined/excluded from any import. Existing staging inconsistencies and filename-only labels are not silently repaired or promoted to human-confirmed samples.

## Taxonomy and mapping decisions

1. **Detection classes:** The exact 31-class order in `yolo_detector_v1.json` is the new target. A class name is not by itself a reviewed human tag, location assignment, or eligibility signal. Existing 32-class detections/checkpoint outputs remain separately versioned legacy data.
2. **Body Images composition:** Keep the existing supported composition pairs `boobs_cum`, `ass_creampie`, and `ass_bb` as a human-label policy. Do not infer combinations from the new detector class list. Preserve historical `u_whore` as written; do not alias it to `ultimate_whore`.
3. **Fullbody:** Keep `clothed`, `topless`, and `bottomless` as Fullbody state concepts; they are not detector-class aliases. Do not derive a Fullbody state from `fullbody_bare` or other new detection classes without an explicit reviewed mapping.
4. **Locations:** The current `location_class_map.json` maps only `location_home`, `location_class`, `location_office`, `location_bathroom`, and `location_bar`; it marks `location_outdoor` and `location_bed` unmapped. The new target adds `location_park`, `location_beach`, and `location_clinic`. Those three have existing canonical location values but no YOLO mapping today. Keep mappings advisory/off until a versioned, human-reviewed mapping is created. Existing UI choices also include cafeteria, coffee_shop, locker_room, mall, pier, shower, and lounge; these remain valid distinct location labels, not aliases for the new seven classes.
5. **Other labels and dataset evidence:** Keep the current 12-class Clothing family model separate from detailed Clothing tags. Preserve source provenance and raw historical labels. Do not infer unknown source grouping from filename or directory. Imported historical assertions remain unconfirmed until reviewed.

## Import bundle contract

An import is an immutable snapshot with a manifest, records, and referenced media files. Each record carries a stable record key, task key (`yolo_detection`, `clothing_classification`, or `asset_classification`), source ID/hash/dimensions, optional detection ID and source-pixel `bbox_xyxy`, review state and eligibility with exclusion reason, structured labels, source snapshot ID, and model prediction/correction-event provenance when present. The bundle carries the producing app/database schema version and exact taxonomy/registry ID, version, and digest. Files are referenced by bundle-relative path with size and SHA-256; absolute paths are not serialized.

Import behavior to implement later: validate the whole bundle before writes; deduplicate byte-identical sources by SHA-256 while preserving source IDs; retain conflicting records as separate history; reject unknown registry versions rather than guessing; ingest suggestions as unconfirmed; carry explicit rejection/exclusion reasons; and stage all records transactionally in the Studio-owned store. Imported content is read-only with respect to NewAssetApp. The Phase 9 detection-specific review semantics remain in the source app; Studio gets a copy of review events and provenance, never writes back to source records.

## Proposed Studio data and storage design

Keep project metadata separate from NewAssetApp's DB. Proposed relational core:

- `projects(project_id, task, title, status, active_registry_id, created_at)`
- `registry_versions(registry_id, version, sha256, manifest_json, status)`
- `sources(source_id, sha256, width, height, media_relpath, import_bundle_id)`
- `examples(example_id, project_id, source_id, task, detection_id, bbox_json, review_state, eligible, exclusion_reason, created_at)`
- `labels(label_id, example_id, field_key, value_json, origin, confirmed, registry_id, registry_version)`
- `review_events(event_id, example_id, event_type, before_json, after_json, actor, occurred_at, note)`
- `splits(project_version_id, source_sha256, split_name, assignment_policy, seed)`
- `project_versions(version_id, project_id, parent_version_id, manifest_sha256, state, finalized_at)`
- `package_files(package_id, relative_path, sha256, bytes)`

Recommended disk layout, owned only by TrainingDatasetStudio: `data/studio.sqlite3`; `data/projects/<project-id>/source/`; `review/`; `versions/<version-id>/manifest.json`; `versions/<version-id>/splits/{train,val,test}/`; and `packages/<package-id>/`. Preserve original media bytes in content-addressed storage and use relative references. A finalized version is immutable; edits create a child version. Split assignment is by source hash/group so crops or boxes from one source cannot leak across splits. These are implementation design decisions, not created DB tables or directories.

## Phase 10 reconciliation and stop conditions

| Phase 10 finding | Phase 11.1 disposition |
|---|---|
| New 31-class registry was previously unspecified | Resolved by the explicit Phase 11 order. Added a distinct target registry and class list. |
| Old detector checkpoint has 32 outputs | Preserved by exact file hash/identity; no transfer or remap approved. |
| 546 unified train/val images lack manifest lineage | Excluded/quarantined from import pending provenance and review. |
| `train_data/yolo` image/label pairs are split inconsistently; 32-class list has malformed blank lines | Unmodified. Not eligible as a Studio import source. |
| Phase 10 proposal requires careful separation of detector target, human label, broad model output, subtags, and invalidity | Carried into contract/design. Invalidity and eligibility are review states, not class labels. |
| Current DB has no Studio project lifecycle/finalized versions | Studio-owned database and version model designed; implementation remains later phase. |
| X-AnyLabeling uses class names by line for YOLO IDs | Registry-generated `classes.txt` follows the new order; import/export round-trip remains to be tested when annotation integration is implemented. |

## Files added and verification

- `TrainingDatasetStudio/registries/yolo_detector_v1.json`
- `TrainingDatasetStudio/registries/classes.txt`
- `TrainingDatasetStudio/registries/classes.sha256`
- `TrainingDatasetStudio/contracts/newassetapp_import_v1.schema.json`
- `tests/studio/test_phase11_foundation.py`
- `reports/PHASE11_1_RECONCILIATION.md`

The focused standard-library tests check all 31 IDs/names/order, the `classes.txt` byte content and digest, and key contract-version/provenance requirements. No application or model tests were run in the restricted context. Launcher verification is reported separately above.

**Stop point:** Phase 11.1 is complete. The next implementation phase can build Studio-owned persistence and import validation from this contract. Do not import the unexplained 546 files, rewrite the legacy 32-class detector, or treat any model suggestion as human confirmation.
