# GUI Acceptance Phase 4 Report

Date: 2026-11-22

## Executive summary

Phase 4 closed the separate Studio lifecycle acceptance gaps and substantially
expanded real Qt coverage for Normal Processing and Professional Review.

Evidence run:

- `gui_screenshots/acceptance/20261122_174821_5324`
- 1366x768 real application widget captures
- Separate bounded scenario timing
- Disposable synthetic fixtures only

## Isolation

Each Phase 4 scenario writes a manifest under the run's `manifests/` directory.
The manifests confirm:

- Separate NewAssetApp and Studio databases under a disposable root.
- Synthetic source media.
- No production database touch.
- No production model checkpoint or production media copy.

## Real-widget acceptance matrix

| Workflow | Status | Evidence |
|---|---|---|
| Normal Processing false/false | PASS_REAL_APP_QT | Real combo, checkboxes, confirmation button, reload and database |
| Normal Processing true/false | PASS_REAL_APP_QT | Real GUI and persisted target mask |
| Normal Processing false/true | PASS_REAL_APP_QT | Real GUI and persisted target mask |
| Normal Processing true/true | PASS_REAL_APP_QT | Real GUI and persisted target mask |
| Normal Processing pending/pending | PASS_REAL_APP_QT | Pending not converted to false |
| Normal Processing Cum partial | PASS_REAL_APP_QT | Cum evaluated, Accessory pending |
| Normal Processing Accessory partial | PASS_REAL_APP_QT | Accessory evaluated, Cum pending |
| Professional detection navigation | PASS_REAL_APP_QT | Two independent detections selected |
| Professional real class and bbox controls | PASS_REAL_APP_QT | Inspector class button and preview mouse resize |
| Correction dialog opening/cancel | PASS_REAL_APP_QT | Real modal opened and closed |
| Independent task-card controls | PARTIAL | Inspector task controls exercised; complete five-head matrix remains incomplete |
| Studio GUI import | PASS_REAL_APP_QT | Real bundle path and Import button |
| Studio dataset creation | PASS_REAL_APP_QT | Real Dataset Builder controls |
| Studio validation refresh | PASS_REAL_APP_QT | Real Validation page refresh |
| Studio immutable version finalization | PASS_REAL_APP_QT | Real finalize button and database state |
| Studio package export | PASS_REAL_APP_QT | Real export button, metadata and hash manifest |
| Headed desktop interaction | BLOCKED | No reliable headed-desktop capture backend |

## Stage timing

The final evidence run reported:

- Normal Processing Body Images matrix: 6.715 seconds.
- Professional Review: 6.119 seconds.
- Studio import: 1.739 seconds.
- Studio lifecycle: 2.358 seconds.

The lifecycle stage timing is retained in
`manifests/phase4_studio_lifecycle.json`.

## Defect fixed

Professional Review reload previously omitted Cum/Accessory target and evaluation
fields from the in-memory detection task status. `detections_for_source()` now
returns these fields and `target_mask_json`.

Regression:

- `test_detection_reload_exposes_partial_body_images_decisions`

## Verification

- Full NewAssetApp suite: 192 tests passed in 122.970 seconds.
- Full Studio suite: 22 tests passed in 104.105 seconds.
- Focused GUI/correction suite: 8 tests passed in 24.193 seconds.
- Phase 4 evidence run: PASS overall; Professional Review remains PARTIAL.
- `compileall`: passed.
- `git diff --check`: passed.

## Remaining work

1. Complete every eligible Fullbody, Portrait, Arousal, and Corruption task card.
2. Complete class-only, bbox-only, combined, second-correction, unchanged,
   and invalid-bbox Professional Review matrix.
3. Complete any remaining Normal export-category matrix.
4. Obtain headed Windows desktop interaction and screenshots.
