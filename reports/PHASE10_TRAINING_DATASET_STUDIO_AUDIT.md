# Phase 10 — TrainingDatasetStudio audit and blueprint

**Status: inspection and design only.** No source, database, model, dataset, CVAT, or configuration files were changed in this phase. The only deliverables created are the six Phase 10 documents in this directory.

## Evidence labels

- **Verified** means observed directly in current NewAssetApp source, registries, files, or read-only database queries during this audit.
- **Inferred** means a conclusion from comparing those sources where the project does not explicitly guarantee it.
- **Proposed** means a design recommendation for TrainingDatasetStudio.
- **Requires user decision** means the implementation cannot safely choose the meaning or policy without your approval.

## Executive findings

1. **Verified:** NewAssetApp has a versioned SQLite database at `data/newassetapp.sqlite3` (schema version 9), raw YOLO detections, proposal records, append-only correction records, model predictions, and a reviewed-record dataset exporter. It does not have a dataset project lifecycle, immutable/finalized versions, or a training-ready gate.
2. **Verified:** The existing detector checkpoint and metadata describe **32 classes**. No verified 31-class registry was found. The 31-label CVAT project described in Phase 7 is not evidence of a 31-class checkpoint or a safe mapping.
3. **Verified:** `train_data/yolo/` is not a valid paired dataset in its current state: it has 683 train images and 401 train labels, zero validation images and 251 validation labels. A separate source dataset `train_data/YOLO_Project/dataset/` has 402 train and 251 val image/label pairs; its migration manifest says 652 valid pairs and one quarantined pair. The 683-image YOLO review task in CVAT is a separate annotation scope.
4. **Verified:** The unified Body Images/Fullbody manifest says 0 training-eligible samples and training was not performed. Yet active-looking `train/` and `val/` folders currently contain 546 images, which are not represented in the migration manifest’s `copies` or `crops` destinations (those are all under `review/`). These files have no verified review provenance in the inspected manifest and must be reconciled before inclusion.
5. **Verified:** The Clothing folder contains 2,328 active crops across 12 directories and has an exact-duplicate quarantine. Source identity is explicitly unavailable; the split manifest groups exact duplicates only. The current active checkpoint file at `models/clothing_classifier/clothing_classifier.pth` is the unchanged **26-class** original checkpoint. The configured/registered 12-class checkpoint path `models/clothing_classifier/clothing_classifier_12class.pth` does not exist.
6. **Verified:** The original Asset Classifier checkpoint is a 26-output ResNet-18. The unified registry proposes a shared ResNet-18 trunk with separate 4-logit Body Images and 3-logit Fullbody state heads; the file named as its initialization is byte-identical to the 26-class original and does not itself contain those new heads. No unified training implementation is wired into NewAssetApp inference.
7. **Verified:** Existing dataset exports produce timestamped directories/ZIPs and manifests, but not full Colab training projects. The current exporters may assign splits and may clear stored split assignments when asked for a new split; they have no finalization lock or immutable version state machine.
8. **Proposed:** TrainingDatasetStudio should import a signed/hashed, explicitly selected NewAssetApp snapshot through a read-only contract, copy data into its own project storage, keep source provenance, and own every subsequent review/split/finalization/package state.

## Scope and inspected sources

### Current application and data architecture

- `app/core/database.py`: schema version and migrations 1–9, proposal/detection relationships, correction history, split assignments, training records, normal crop isolation, current query counts.
- `app/core/dataset_exporter.py` and `app/workers/dataset_export_worker.py`: YOLO, legacy/broad/fine-grained Clothing CNN, and unified CNN package generation.
- `app/core/inference.py`, `app/core/models.py`, `app/core/proposals.py`, `app/core/fullbody_classification.py`, `app/core/filename_grammar.py`, and clothing taxonomy modules.
- `app/gui/main_window.py`, `app/gui/correction_dialog.py`, `app/gui/bbox_preview.py`: current review, selection, normal processing, and Phase 9 invalidation behavior.
- `data/models/phase4_model_registry.json`, `yolo_class_policy.json`, `unified_body_images_fullbody/class_registry.json`, `clothing_classifier_registry.json`, class maps, tag registries, composition policies, and `data/datasets/phase4*` files.
- `models/model_manifest.json`, actual checkpoint files, checkpoint file hashes, and current model directory contents.
- Current dataset trees and manifests under `train_data/yolo`, `train_data/YOLO_Project/dataset`, `train_data/unified_body_images_fullbody`, and `train_data/clothing_classifier`.
- `cvat_agent/func.py` and Phase 4B–9 dataset, CVAT, workflow, test, and environment reports listed in the related design documents.

Girl Packer was not opened or modified for this audit. Existing project metadata referring to its checkpoint provenance was treated as a recorded provenance claim, not as a new inspection of that reference tree.

## Verified database model and live database state

The current application database is `data/newassetapp.sqlite3`, 1,126,400 bytes at inspection time. It contains migration versions 1–9. Read-only counts:

| Table | Rows |
|---|---:|
| `source_images` | 139 |
| `yolo_detections` | 1,124 |
| `cnn_predictions` | 351 |
| `asset_proposals` | 1,125 |
| `correction_records` | 16 |
| `classification_review_records` | 0 |
| `normal_crop_choices` | 2 |
| `normal_crop_exports` | 1 |
| `training_records` | 0 |
| `dataset_split_assignments` | 0 |
| `final_assets` | 0 |

All 16 correction rows currently represent `bbox_corrected`; they have `human_confirmed=0` and all training eligibility flags false. Current proposal review states: 108 pending, 828 review_required, 189 unclassified_fullbody. The database has no persisted training record, split assignment, or finalized asset version.

**Verified relationships:** `source_images` is the parent; `yolo_detections` and `asset_proposals` point to it. A proposal references a detection and may reference a CNN prediction. `correction_records` stores a source/detection/proposal association, original JSON snapshot, corrected JSON payload, review state, and per-task training eligibility flags. `classification_review_records` is detection-specific, but currently limited to task names `fullbody_state`, `body_images`, and `clothing_family`; it is empty in the current DB. `dataset_split_assignments` is keyed by dataset family and source SHA-256, but is empty. `training_records` is proposal-based with JSON payloads and is empty.

**Limitations:** classifications are substantially stored in JSON correction payloads, not normalized category/value rows. `asset_proposals.category` permits `fullbody`, `body_images`, `clothing`, and `others`; invalidity is represented by status/history, not a taxonomy category. There is no dataset-project foreign key, finalization table, immutable version table, label registry version association, or package checksum table.

## Verified model/checkpoint identity summary

| Model role | Current file and hash | Verified metadata/limitation |
|---|---|---|
| YOLO detector | `models/yolo/best.pt`, 22,523,946 bytes, SHA-256 `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA` | Registry and model manifest list 32 ordered classes. Hash matches `models/model_manifest.json`. Current checker did not load the binary; prior reports record strict load and inference under Ultralytics 8.0.186, while its checkpoint metadata is reported as 8.3.204. |
| Original Asset Classifier | `models/asset_classifier/asset_classifier.pth`, 44,839,755 bytes, SHA-256 `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2` | Model manifest identifies ResNet-18 with 26 outputs; `asset_class_map.json` preserves its original ordering. |
| Unified CNN initialization | `models/unified_body_images_fullbody/asset_classifier_initialization_26class.pth`, same size and SHA-256 as original Asset Classifier | Initialization copy only; the 26-output checkpoint head is not the proposed 4+3 output-head implementation. |
| Clothing active file | `models/clothing_classifier/clothing_classifier.pth`, same size and SHA-256 as original Asset Classifier | Still the 26-class checkpoint copy. It is not the 12-class checkpoint expected by current inference code/registry. |
| Clothing 12-class path | `models/clothing_classifier/clothing_classifier_12class.pth` | **Not present.** Inference code safely disables the Clothing CNN when this checkpoint is absent. |

Hashes here were computed from current files using read-only SHA-256. No checkpoint was loaded, rewritten, moved, or trained during this phase.

## Verified dataset inventory and blockers

| Dataset tree | Current evidence | Readiness interpretation |
|---|---|---|
| `train_data/YOLO_Project/dataset/` | 402 train + 251 val paired image/label files; 32-class `classes.txt`; one invalid pair is identified in the migration manifest and preserved here as original source. | Legacy annotations; semantic human review is pending. The valid active subset is 652 pairs; do not treat all original pairs as clean. No test split. |
| `train_data/yolo/` | 683 train images, 401 train labels, 0 val images, 251 val labels, 0 test pairs. Its `class_registry.json` says 32 classes; `classes.txt` currently has only 29 names followed by three blank lines. | Invalid staging layout: image/label pairs are broken across splits and class list disagrees with registry. Do not package or send this folder to an annotator. |
| `train_data/unified_body_images_fullbody/` | Manifest: 356 legacy Body Images copies, 490 legacy broad Fullbody copies, 3,075 YOLO-derived crops, all review-only and `training_eligible=false`; `training_eligible_count=0`. Current `review/` contains 3,921 candidate examples. Separately, active-looking `train/`/`val/` directories contain 443 and 103 images, respectively, not linked by the inspected manifest. `test/` is empty. | Review candidates are correctly gated in manifest. The unexplained 546 train/val images are an integrity/provenance blocker; they need an inventory/reconciliation decision before reuse. |
| `train_data/clothing_classifier/` | 1,860 train, 234 val, 234 test = 2,328 active image files, across the 12 fixed categories. `review/duplicate_quarantine` has an exact-duplicate manifest. Current split manifest uses seed 20261107 and says source-family identity is unavailable. | Usable as a reviewed-by-folder candidate dataset, but folder labels are not proven human-confirmed, groups by source are not proven, and class imbalance is substantial (e.g., 8 `outerwear` examples in val and 8 in test). Duplicate quarantine is not proof of broader semantic deduplication. |
| `data/datasets/phase4_preparation_status.json` | `awaiting_taxonomy_review`; samples_processed_this_phase 0; trusted_training_examples_this_phase 0; seed 42, 80/10/10, source image SHA-256 grouping declared. | Planning/status metadata, not a finalized dataset. Its unresolved taxonomy gates still apply. |

The current 31-class registry requested by the brief was not found. The current canonical detector registry remains 32-class. `train_data/yolo/classes.txt` having 29 populated lines and 3 empty lines is not a 29- or 31-class decision; it is malformed relative to the adjacent 32-class registry and YAML.

## Existing export capability and its boundary

`app/core/dataset_exporter.py` generates human-confirmed-record packages for YOLO, several CNN variants, and the unified CNN. The code hashes source images before copying/cropping, writes dataset manifests, records class maps, applies source-hash split assignments, writes some `README_COLAB.md` files, and ZIPs output. This is useful reusable domain logic.

It is not yet a Studio lifecycle engine: package generation is a single export operation, with no project isolation, selection/review UI, pre-package prepared state, split report UI, annotation revision import, validation gate, immutable finalization, or parent/child versioning. Its README is a short outline rather than a complete Colab recipe; it does not bundle model training, validation, evaluation, checkpoint integration, or pinned project requirements. The `new_split` option clears assignments, so it must not be exposed for frozen versions.

## Phase 9 current-state verification

The current source has Phase 9 additions in the intended area: detection-level category/status filtering, invalidation/restoration methods that append correction history, a detection list synchronized with the selected box, conditional category rows in the correction dialog, Body Images composition choices derived from its policy, lower preview minimum sizing, and dark-theme tab rules. These are present in current files; the database schema remains version 9. They can be reused as behavioral references, but they are not proof of complete Phase 9 acceptance.

Phase 9’s most recent saved report claims 89 passing tests in an approved/elevated Python 3.11 context. In this audit context, the same `.venv` launcher failed with `No Python at C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe`; available Python 3.15 lacks PySide6/Pillow. Therefore, this audit did not re-run project tests or launch the app. Earlier Phase 9 reports also mark GUI acceptance incomplete. The source edits made in the prior Phase 9 interaction happened after the saved test report; they have only syntax/smoke evidence from that interaction and require full suite/runtime retest in the supported environment.

## Recommended architecture

Create an independently deployable `TrainingDatasetStudio` with its own SQLite metadata DB, config, project storage, review history, split registry, finalization records, and package output. NewAssetApp remains the source-of-truth for its original scans, detections, model snapshots, corrections, and normal crop exports. Studio imports a read-only, content-addressed snapshot; it never points its writes into NewAssetApp.

Use a **shared dataset engine with model-specific adapters**. Share project/version state transitions, source hashing, duplicate/source grouping, selection/exclusion reasons, deterministic group split assignment, validation framework, review event logging, immutable finalization, and packaging/checksum infrastructure. Keep YOLO box annotation, Clothing single-label crops, and multi-head Asset CNN sample/label adapters separate. Do not force all tasks into one on-disk annotation format or one class registry.

The recommended normalized taxonomy, data lifecycle, project schemas, Colab layout, and X-AnyLabeling workflow are specified in the other Phase 10 reports.

## Decisions that block implementation

1. What is the exact 31-class YOLO registry, with stable order and disposition of original IDs? Does the new model retain a subset, merge only after explicit sign-off, or redefine classes? The 32-class checkpoint identity must remain untouched.
2. What are authoritative boundaries between detection category, model target, human main classification, subtag, and optional per-image metadata? In particular, whether broad model outputs remain the current unified 4+3 heads.
3. Is `ultimate_whore` a new structured human tag, while historical `u_whore` remains a distinct legacy value? No implicit alias is safe.
4. Should the unexplained 546 images in unified `train/` and `val/` be retained, reviewed as a new import, or excluded? Their present manifest does not establish lineage or eligibility.
5. What data source is allowed for populating the new human-reviewed Clothing project, and what is the expected source-group strategy for these existing filename-only images?
6. Should the new YOLO starting weights use the existing checkpoint with explicit, version-tested transfer (same-class rows only and new/changed outputs freshly initialized), or use an independently selected architecture/checkpoint? The 31-class target map must be approved first.
7. Which model families and labels are in the first deliverable, and is a three-way 80/10/10 split acceptable as default when source grouping is absent? A policy for unknown source groups is needed.

## Related design documents

- [Taxonomy design](PHASE10_TAXONOMY_DESIGN.md)
- [Dataset lifecycle](PHASE10_DATASET_LIFECYCLE.md)
- [Model projects](PHASE10_MODEL_PROJECTS.md)
- [Colab package specification](PHASE10_COLAB_PACKAGE_SPEC.md)
- [X-AnyLabeling integration](PHASE10_X_ANYLABELING_INTEGRATION.md)
- [Implementation plan](PHASE10_IMPLEMENTATION_PLAN.md)
