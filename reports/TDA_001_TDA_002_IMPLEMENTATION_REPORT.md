# TDA-001 and TDA-002 Implementation Report

Date: 2026-11-22

## 1. Summary

Both targeted findings are implemented:

- **TDA-001:** Body Images has independent Cum and Accessory binary decisions,
  explicit completion, partial evaluation, pending state, and both-negative
  `none`. Legacy single-target records remain readable.
- **TDA-002:** Normal Processing now uses the same shared eligibility API for
  Arousal and Corruption targets as Professional Review. Body-region,
  portrait, person, clothing, Fullbody, location, and unsupported groups are
  handled consistently.

No broad GUI redesign, YOLO registry/checkpoint change, model training,
BiRefNet work, RAR work, dependency change, or production-data change was
performed.

## 2. Exact changed areas

- `app/core/database.py`
  - Added schema migration 24 for Normal Processing binary fields.
  - Added migration-23 compatibility for Professional binary fields.
  - Added `_normalize_body_images_decisions`.
  - Added binary fields to Normal Processing persistence and confirmation.
  - Added binary mask fields to Professional task reviews and training examples.
  - Changed Normal Arousal/Corruption validation to shared eligibility helpers.
  - Kept existing correction/history behavior append-only.
- `app/gui/main_window.py`
  - Replaced Normal Processing single Body Images target dropdown with two
    tri-state checkboxes and an explicit completion checkbox.
  - Hid Normal Arousal/Corruption controls when the effective detection class
    does not qualify.
  - Added independent Professional Review tri-state Body Images controls.
- `app/core/training_source_exporter.py`
  - Exported detailed two-output target masks.
  - Preserved legacy `bodypart_cum` and `bodypart_acc` records as derived masks.
- `TrainingDatasetStudio/contracts/newassetapp_import_v4.schema.json`
  - Added versioned `body_images_target_mask` annotation properties.
- `TrainingDatasetStudio/studio/importer.py`
  - Validated, derived, and preserved legacy/modern Body Images masks.
- `TrainingDatasetStudio/studio/store.py`
  - Added compatibility for internal multi-label and pending Body Images records.
- `TrainingDatasetStudio/studio/datasets.py`
  - Shared packages preserve target masks and validate contradictory masks.
- `TrainingDatasetStudio/studio/shared_training.py`
  - Shared-package validation supports masked multi-label Body Images records.
- `TrainingDatasetStudio/studio/shared_train.py`
  - Uses masked binary loss for Cum/Accessory and cross-entropy for scalar heads.
- `scripts/gui_acceptance/scenarios/newassetapp_normal.py`
  - Updated disposable Normal Processing scenario for independent checkboxes.
- `tests/test_tda_001_002.py`
  - Added focused TDA-001/TDA-002 persistence, handoff, Studio, and eligibility tests.

## 3. Database and migration behavior

New migration 24 is additive and disposable-safe:

- `body_images_cum_target`
- `body_images_cum_evaluated`
- `body_images_accessory_target`
- `body_images_accessory_evaluated`
- `body_images_completed`

Migration 23 already persists:

- `cum_target`
- `cum_evaluated`
- `accessory_target`
- `accessory_evaluated`
- `target_mask_json`

Legacy records remain readable. Missing legacy fields are not silently
interpreted as explicit negatives:

- Legacy `bodypart_cum` derives Cum evaluated/true and Accessory pending.
- Legacy `bodypart_acc` derives Accessory evaluated/true and Cum pending.
- Legacy portrait/tportrait records derive both outputs pending.
- Explicit false values require evaluated flags and completion state.

No production database migration was run.

## 4. Body Images data contract

Target masks use this shape:

```json
{
  "cum": {"target": true, "evaluated": true},
  "accessory": {"target": false, "evaluated": true}
}
```

States:

| Cum | Accessory | Meaning |
|---|---|---|
| true/evaluated | true/evaluated | Both detected |
| true/evaluated | false/evaluated | Cum only |
| false/evaluated | true/evaluated | Accessory only |
| false/evaluated | false/evaluated | Explicit none |
| null/not evaluated | null/not evaluated | Pending |
| one evaluated | other pending | Partial completed decision |

No missing/null/pending value is serialized as explicit false.

## 5. Eligibility matrix

The shared function `shared_head_eligible` and `eligible_shared_heads` are
authoritative. Normal Processing now calls the same rules for Arousal,
Corruption, Clothing, and Fullbody decisions.

| YOLO group | Eligible tasks |
|---|---|
| Body Parts 1-6 | Body Images, Arousal, Corruption |
| portrait_frame 2 | Body Images, Portrait, Arousal, Corruption |
| person 0 | Arousal, Corruption |
| Cover/clothing 8-11 and 28 | Clothing Broad, Clothing Detailed, Corruption |
| Fullbody 19-27 and 31 | Fullbody, Corruption |
| Location 12-18 | Location |
| action_event 7 | None |
| Historical 29-30 | Historical only |

The 31/32 YOLO registry mapping was not changed.

## 6. Trace evidence

Verified in disposable fixtures:

- GUI controls → Normal crop choice columns.
- Professional tri-state decisions → `classification_task_reviews`.
- Confirmed decisions → `training_examples.target_mask_json`.
- Training bundle export → v4 `body_images_target_mask`.
- Studio import → `records.annotation_json`.
- Dataset snapshot → target-mask annotation snapshot.
- Shared package → `shared_dataset.json` target masks.
- Shared loss → masked binary Cum/Accessory loss.
- Repeated bundle import → duplicate bundle result.

No crop is copied per binary target.

## 7. GUI acceptance

Latest visual run:

- Run: `20261122_142103_5776`
- Overall: **PASS**
- 1280x720, 1366x768, 1920x1080
- NewAssetApp Normal and Professional: PASS
- Synthetic Qt captures are layout evidence only, not headed-desktop acceptance.
- Unique screenshots are under `gui_screenshots/automated/20261122_142103_5776/`.

## 8. Test evidence

Focused TDA command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_tda_001_002 -v
```

Result: **6 tests passed**.

Full NewAssetApp suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
```

Result: **183 tests passed** in 166.767 seconds.

Full Studio suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/studio -p "test*.py" -v
```

Result: **22 tests passed** in 91.422 seconds.

Other verification:

- GUI visual suite: PASS.
- Python compileall: PASS.
- `git diff --check`: PASS.

## 9. Remaining limitations

- Live headed-desktop save/reload interaction remains manual acceptance.
- Real model training was not run.
- RAR/Colab packaging was not changed.
- The active 31/32 YOLO mapping remains unresolved and was intentionally not
  modified.
- Legacy Portrait/tPortrait historical records remain pending/masked in the
  Body Images binary contract rather than being silently reinterpreted.

## 10. Completion

- **TDA-001:** Complete in implemented code and disposable tests.
- **TDA-002:** Complete for shared eligibility and Normal/Professional checks.
