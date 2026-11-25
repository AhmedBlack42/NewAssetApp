# GUI Acceptance Phase 3 Report

Date: 2026-11-22

## Executive summary

Phase 3 established a disposable real-widget Qt acceptance path and completed
the independent Normal Processing Body Images positive/negative save/reload
scenario plus all actual Studio navigation mappings.

The main remaining acceptance gap is complete Professional Review and
Studio import/dataset/version/package interaction evidence. The existing
Studio workflow scenario was not used as passing evidence after it exceeded
the bounded run window.

## Isolation

Passing run: `20261122_165850_524`

Evidence:

- `gui_screenshots/acceptance/20261122_165850_524/`
- `manifests/isolation_manifest.json`
- `manifests/phase3_navigation.json`

The fail-closed manifest proves:

- A unique disposable root outside the repository was used.
- NewAssetApp and Studio databases were separate.
- No production NewAssetApp or Studio database was selected.
- No production source media or checkpoint was copied.
- Disposable synthetic source media was used.
- All acceptance paths stayed under the disposable root.

## Actual-application Qt evidence

Status: `PASS_REAL_APP_QT`

Normal Processing:

- Selected a real disposable crop through `normal_gallery`.
- Changed the real category combo to `body_images`.
- Used the real Cum and Accessory checkboxes.
- Clicked the real `normal_apply_category_button`.
- Verified database persistence after the GUI action.
- Verified Cum positive and Accessory explicitly negative.
- Navigated away and returned to the crop.
- Verified category and target reload through the real widget.

Studio navigation:

| Row | Label | Result |
|---|---|---|
| 0 | Model Projects | PASS |
| 1 | Dataset Segments | PASS |
| 2 | Dataset Builder | PASS |
| 3 | Dataset Records | PASS |
| 4 | Validation | PASS |
| 5 | Colab Packages | PASS |
| 6 | Model Artifacts | PASS |
| 7 | Import / Activation | PASS |
| 8 | History | PASS |

Every row/index mapping changed `QStackedWidget.currentIndex()` to the matching
row and produced a real widget capture.

## Complete acceptance matrix

| Workflow | Status | Evidence |
|---|---|---|
| Fail-closed disposable isolation | PASS_REAL_APP_QT | Isolation manifest |
| Normal Processing real save/reload | PASS_REAL_APP_QT | Real widget button, database reload |
| Body Images positive/negative | PASS_REAL_APP_QT | Cum true, Accessory false |
| Body Images pending/partial/none | TEST-ONLY/BLOCKED | Existing TDA tests; not all combinations completed in the real Qt run |
| Other Normal categories | TEST-ONLY | Existing unit/layout suites |
| Professional Review correction | TEST-ONLY | Existing disposable database/tests |
| Independent CNN task cards | TEST-ONLY | Existing disposable database/tests |
| Handoff and Studio import | TEST-ONLY/PARTIAL | Existing bundle/import tests; live Qt import lifecycle not completed |
| Studio navigation | PASS_REAL_APP_QT | All 9 real pages |
| Studio dataset/version/package GUI lifecycle | BLOCKED | Bounded workflow run did not complete |
| Headed desktop interaction | BLOCKED | No reliable headed-desktop screenshot backend |

## Verification

- Full NewAssetApp suite: 186 tests passed in 84.000 seconds.
- Full Studio suite: 22 tests passed in 80.550 seconds.
- Focused GUI suite: 2 tests passed in 6.607 seconds.
- Phase 3 Qt acceptance: PASS in 3.049 seconds.
- `compileall`: passed.
- `git diff --check`: passed.

## Blockers

- Professional Review real correction-dialog workflows remain incomplete.
- The complete Studio GUI import/dataset/version/package lifecycle did not
  complete within a bounded run and is retained as BLOCKED, not PASS.
- Headed Windows desktop capture remains unavailable.
- No manual or headed acceptance claim is made.
