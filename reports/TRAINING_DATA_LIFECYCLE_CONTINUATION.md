# Training Data Lifecycle Continuation

## Result

The disposable lifecycle checks pass for registry alignment, Body Images masks,
cross-project accumulation, source-group splits, readiness gates, immutable
finalization, and explicit training authorization. **The lifecycle is not
complete or production-ready:** no production dataset was opened, the
demonstration imports are far below minimum group counts, and no 4 GB RAR was
created or integrity-verified. No model was trained and neither GUI was
redesigned.

## Approved YOLO registry and Fullbody map

`TrainingDatasetStudio/registries/yolo_detector_v1.json` is the active source of
truth: **31 classes, IDs 0–30**. The five registry consistency tests passed:
active mappings match the registry, and unsupported classes cannot become
active targets.

All 11 approved Fullbody detector classes have explicit resolved dispositions:

| YOLO ID | YOLO class | Human-facing Final Tag |
|---:|---|---|
| 12 | `fullbody_shower` | `shower` |
| 13 | `fullbody_maid` | `maid` |
| 14 | `fullbody_nurse` | `nurse` |
| 15 | `fullbody_uniform` | `uniform` |
| 16 | `fullbody_athletic` | `athletic` |
| 17 | `fullbody_swimsuit` | `swimsuit` |
| 18 | `fullbody_bikini` | `bikini` |
| 19 | `fullbody_work` | `work` |
| 20 | `fullbody_clothed` | `clothed` |
| 21 | `fullbody_bare` | `bare` |
| 22 | `fullbody_underwear` | `underwear` |

`fullbody_lingerie` is absent from the active map. Its old crosswalk entry
remains only under `historical_legacy_yolo`; it is not an active class.
Historical `atheletic` is preserved, while new `fullbody_athletic` decisions
use `athletic`. YOLO classes remain separate from CNN labels and human tags.
The five-head shared CNN, YOLO, Clothing Broad, and Clothing Detailed registry
identity checks passed; broad and detailed clothing were validated against
distinct registries.

## Body Images lifecycle

The independent targets are `cum` and `accessory`, each stored as a target plus
an evaluated bit. Tests covered both positive, either target alone, explicit
`none` (two evaluated negatives), pending, partial evaluation, and updating one
target without overwriting the other. The full confirmation → bundle → Studio
import → version/split → package path passed. The six eligible mask
distributions were:

- Cum: 3 positive, 2 negative, 1 pending.
- Accessory: 2 positive, 3 negative, 1 pending.

One fully pending example created no eligible training record. Package
provenance and independent masks survived; `none` is not pending or a third
mutually exclusive target.
The regression suite also confirmed that a previously completed decision can
return to a partial state without retaining a stale completion flag.

## Accumulation, provenance, splits, and readiness

Two independent disposable NewAssetApp projects were imported sequentially
into one disposable Studio database:

| Checkpoint | Model segments | Records | Segment bytes |
|---|---:|---:|---:|
| Before import | 0 | 0 | 0 |
| After project one | 1 | 1 | 3,631 |
| After project two | 1 | 2 | 7,262 |
| After re-import of project two | 1 | 2 | 7,262 |

Both projects contributed to `unified_body_images_fullbody_cnn`'s same segment;
re-import was idempotent. Tests verified distinct source hashes and project
IDs, task/head/model identity, human confirmation, effective BBox, detection
ID/class/model provenance, and crop-revision metadata. The configured
per-segment capacity is exactly **5,000,000,000 bytes**. Rollover behavior
passed an isolated boundary test; the import test also asserted that exact
production capacity. A single record is not divided across segments.

Source-group splitting kept crops from one source together and rejected a
leaking assignment. A 100-source-group fixture produced **70 train / 15
validation / 15 test groups**. Readiness reports include target distributions,
eligibility/status, invalid media and hash checks, duplicates, source leakage,
and minimum group blockers.

An underfilled finalized fixture was reported `blocked_from_training` at
`source_group_minimum_not_met:1/100`; minimum split groups are 70/15/15.
Invalid media, changed package hashes, wrong-version packages, and a mismatched
approved YOLO registry blocked finalization/authorization. A valid disposable
100-group package passed readiness and explicit authorization in a dry-run
with the trainer stubbed; the queued run did not train a model.

**Per-model readiness:** no production model dataset was inspected or modified.
The two-source shared-CNN Fullbody fixture proves accumulation only; with two
source groups it cannot satisfy the 100-group minimum and has no training
authorization. The five shared heads and other model identities passed their
focused mapping/registry checks, but no real dataset versions or per-model
production split counts were examined. They are therefore **not certified
ready**. Finalization alone is not readiness.

## Colab RAR

No RAR archive was created, so no archive hash or integrity result exists. The
latest previously measured legitimate package was **919,078 bytes**, which is
**3,999,080,922 bytes below** the 4,000,000,000-byte minimum. The disposable
RAR-readiness test correctly returned `blocked`, with archive size unverified.
No padding, file duplication, or ZIP/7z substitution was used.

## Verification outcome

Passed focused runs:

- Registry consistency: 5 tests.
- Body Images lifecycle and partial-update regressions: 4 tests.
- Two-project accumulation/idempotency/provenance: 1 test.
- Studio registry, head, and segment pipeline: 5 tests.
- Training-source exporter regressions: 2 tests.
- Dataset lifecycle/readiness/authorization suite: 10 tests.
- Python syntax compilation: passed.

The focused groups above total **27 passing test cases**; the separate long
segment-capacity case remains inconclusive as stated below.

An earlier run failed two stale assertions (an obsolete YOLO registry alias
and an expectation that omitted detection metadata); both were corrected and
the corresponding focused suites passed on rerun. The separate long
`more_than_512_records` segment-capacity run produced no output and was stopped;
that test remains **inconclusive**. The GUI acceptance suite was not run.

## Files changed

- `TrainingDatasetStudio/README.md`
- `TrainingDatasetStudio/studio/datasets.py`
- `TrainingDatasetStudio/studio/importer.py`
- `TrainingDatasetStudio/studio/store.py`
- `TrainingDatasetStudio/studio/training.py`
- `app/core/database.py`
- `app/core/training_source_exporter.py`
- `app/core/yolo_registry.py`
- `data/models/fullbody_classification_policy.json`
- `data/models/model_tag_crosswalk.json`
- `data/models/yolo_fullbody_final_tag_mapping.json`
- `data/tags/fullbody_tags.json`
- `reports/TRAINING_DATA_END_TO_END_AUDIT.md`
- `tests/studio/test_cross_project_accumulation.py`
- `tests/studio/test_dataset_lifecycle.py`
- `tests/studio/test_v2_pipeline.py`
- `tests/test_tda_001_002.py`
- `tests/test_yolo_registry_consistency.py`
