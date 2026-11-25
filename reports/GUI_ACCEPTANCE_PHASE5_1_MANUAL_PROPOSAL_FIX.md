# GUI Acceptance Phase 5.1 — Manual Proposal Fix

Date: 2026-11-22

## Outcome

`FIXED_AND_PASS_REAL_APP_QT`

## Root cause

The “Create manual proposal from selected image” action created an orphan
`asset_proposals` row with `detection_id IS NULL`. The Correction Dialog was
therefore unable to expose a persisted detection for YOLO class/bbox correction,
and the class/bbox save actions were correctly disabled. This made the real
manual proposal workflow return to an unusable correction state.

The production callback in `_create_manual_proposal()` also opened the dialog
directly after changing category/navigation. No manual detection or linked
proposal existed before dialog construction.

## Production fix

- `_create_manual_proposal()` now creates a real manual detection and linked
  proposal using `create_manual_detection()`.
- The default proposal box is a valid inset of the source image.
- The existing correction dialog now exposes and validates effective YOLO class
  and source-pixel bbox controls.
- The dialog has separate class, bbox, and combined save actions.
- Combined correction uses `save_yolo_annotation_correction()` as the
  authoritative existing persistence path.
- Manual Proposal no longer depends on a model prediction or synthetic class.

## Call path

1. Source image selected.
2. `Create manual proposal from selected image` clicked.
3. `_create_manual_proposal()` creates a manual detection and proposal.
4. The Others gallery selects and opens the linked proposal.
5. `CorrectionDialog` receives a detection-linked proposal.
6. Human changes class and bbox.
7. `Save combined correction` validates and accepts the dialog.
8. Main Professional Review receives `combined_correction`.
9. `save_yolo_annotation_correction()` persists the effective annotation.
10. Detection reload uses the latest effective class/bbox.

## Focused acceptance

Command:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_manual_proposal_acceptance.ManualProposalAcceptanceTests.test_manual_proposal_combined_save_real_dialog_and_reload -v
```

Result: PASS in 1.747 seconds.

The test exercised:

- One synthetic source image.
- Real source gallery selection.
- Real Manual Proposal button.
- Real CorrectionDialog.
- Real approved Person class selection.
- Real bbox coordinate controls.
- Real combined-save button.
- Parent result handling and database reload.

Before correction:

- Original class: `manual_annotation`.
- Original bbox: `[30, 40, 570, 760]`.

After correction and reload:

- Effective class: `person`.
- Effective bbox: `[100, 120, 400, 500]`.
- Original YOLO/manual detection class and bbox remained unchanged.

## Focused regressions

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_correction_dialog_layout tests.test_correction_crop_pipeline -v
```

Result: 12 tests passed in 3.533 seconds.

```powershell
.\.venv\Scripts\python.exe -m compileall -q app TrainingDatasetStudio scripts tests
git --no-pager diff --check
```

Both passed.

## Retry and hang investigation

The previous broader Phase 5 retry loop repeatedly entered modal
`CorrectionDialog.exec()` attempts and did not add any successful evidence.
The first isolated run of this phase showed the actual modal blocker:
`_create_manual_proposal()` was creating an orphan proposal.

A subsequent first-run fixture failure was also identified: the temporary
fixture lacked copied taxonomy tag assets, so `CorrectionDialog` construction
raised `FileNotFoundError`. The fixture was corrected and one bounded rerun passed.

No repeated identical retry was used after the pass.

## Remaining work

- Broader class/bbox/second-correction/invalid-bbox matrices remain separate.
- Full five-head Professional task-card acceptance remains separate.
- Headed Windows desktop interaction remains blocked.
- RAR, model training, activation, 31/32 mapping, and redesign remain deferred.
