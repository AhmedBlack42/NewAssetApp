# Phase 9 Normal Crop Export Tests

## Result

**Automated unit coverage: PASS. Live GUI workflow: NOT VERIFIED.**

`tests.test_phase9_crop_export` and `tests.test_phase8_workflow_independence` cover normal export behavior using isolated temporary databases and output directories. They do not process a live source through the desktop GUI.

## Covered in automated tests

- Normal route handles Fullbody, Body Images, and Clothing independently of Professional Review confirmation.
- Each route writes WebP output and preserves source-to-output traceability.
- Export history is separate from review state; export records are not inserted into training records or split assignments.
- Filename collisions preserve the first file and advance to another name.
- Background-removal failure and disabled removal retain the crop with an explicit history/result fallback.
- Cancellation between items preserves completed output/history and reports remaining crop IDs.
- Body Images guide-specific crop rules and Fullbody alpha crop rules remain in force.

Full suite result: 89 tests passed (see `PHASE9_TEST_RESULTS.md`).

## Live workflow matrix

| Requested check | Status | Evidence/limitation |
|---|---|---|
| Folder scan and image analysis through GUI | Not run | UI capture timed out; no live interaction was possible. |
| Normal crop/category selection | Not run | Automated exporter tests only. |
| Fullbody, Body Images, Clothing routing | Automated pass | Temporary test fixtures; no real GUI export. |
| Crop geometry/aspect ratios | Automated contract coverage | Existing guide-ratio tests and Phase 6 crop tests pass; no fresh desktop preview inspection. |
| WebP conversion | Automated pass | Test outputs are opened and checked in the tests. |
| Collision handling | Automated pass | Test confirms first output survives and next name is used. |
| Source/output traceability and export history | Automated pass | Checked in isolated DB fixtures. |
| Failure handling | Automated pass | Fallback record asserted for removal failure/disabled behavior. |
| Professional Review independence | Automated pass | Phase 8 workflow independence tests pass. |
| Training dataset isolation | Automated pass | No training/split records created by test exports. |

No original source image was modified by the Phase 9 quality script; it reads source images and writes evidence outputs under `gui_screenshots/phase9/birefnet/`. A real GUI crop export, history inspection, and output-file traceability check remain to be performed interactively.
