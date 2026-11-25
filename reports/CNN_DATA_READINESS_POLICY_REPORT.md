# CNN Data Readiness Policy Report

Date: 2026-11-24

## Thresholds

- Insufficient: fewer than 50 source-image groups.
- Exploratory: 50–99 source-image groups.
- Minimum training-ready: at least 100 source-image groups.
- Recommended: at least 300 source-image groups.
- Strong: at least 500 source-image groups.

Minimum split coverage:

- Training: 70 source-image groups.
- Validation: 15 source-image groups.
- Test: 15 source-image groups.

Recommended split:

- Training: 210 source groups.
- Validation: 45 source groups.
- Test: 45 source groups.

## Counting Method

Each outcome is evaluated independently:

- Crop records remain separate crop samples.
- Unique source hashes are grouped for diversity.
- Duplicate crops are not additional source groups.
- Model suggestions do not count.
- Drafts do not count.
- Pending targets do not count as negative.
- Invalid/rejected records are excluded.
- Stale crop revisions are excluded.

## Body Images

Cum positive/negative and Accessory positive/negative are independent outcomes.

- `cum=true, accessory=true`
- `cum=true, accessory=false`
- `cum=false, accessory=true`
- `cum=false, accessory=false` = explicit negative outcomes for both independent heads

Partial evaluation contributes only to the evaluated independent outcome.

## Source-safe Splitting

Existing Studio dataset splitting remains source-grouped and reproducible.

All crop records for one source hash remain in the same split.
Finalized immutable versions cannot be silently edited.

## Evaluator

`DatasetService.readiness_report()` returns:

- Per Fullbody class
- Per Portrait class
- Per Arousal class
- Per Corruption class
- Per Cum and Accessory positive/negative outcome
- Eligible crop records
- Unique source groups
- Train/validation/test source-group counts
- Pending, invalid, stale, and duplicate exclusions
- Model-level weakest-link status

The Studio Validation page now includes a readiness table.

## Verification

Four readiness tests cover:

- Empty insufficient report.
- Pending/invalid exclusions.
- Independent Cum/Accessory outcomes.
- Explicit split thresholds.

## Current Limitation

No production or disposable dataset containing sufficient real CNN targets was
used to claim class-level training readiness. The evaluator accurately reports
insufficient/unknown data until human-confirmed eligible records exist.

## Implementation Result

The read-only evaluator is implemented in `TrainingDatasetStudio/studio/datasets.py`
and is surfaced through the Studio Validation page.

It reports:

- Eligible crop records
- Unique source groups
- Crop hashes and duplicate exclusions
- Train/validation/test source-group counts
- Pending, invalid, stale, and duplicate exclusions
- Per-class and per-binary-outcome status
- Weakest-link model status

The implementation does not create a dataset version, modify records, train a
model, or export a package.

## Test Result

- 7 readiness/draft focused tests passed.
- Studio readiness integration suite: 11 tests passed.
- Full NewAssetApp suite: 216 tests passed, 1 skipped.
