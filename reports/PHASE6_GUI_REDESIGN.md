# Phase 6 GUI Redesign

## Status

**Partially complete; interactive GUI acceptance is untested.** NewAssetApp launched through `run_app.ps1`. The live accessibility tree showed the Normal Processing workspace, folder field, scan/analyze actions, crop gallery, selection, and export controls. Screenshot capture timed out, and Professional Review interaction was not verified. The main window has clearly named **Normal Processing** and **Professional Review** tabs. It opens at a more practical size, has a lower minimum size, and the professional workspace uses adjustable splitters with a linked detection list and image preview. The correction dialog is scrollable and offers separate annotation and classification confirmation actions.

The Normal Processing tab currently lists and batch-selects crops whose proposals have already been confirmed and tagged. First-time proposal correction still requires the Professional Review tab. This means the requested independent first-time normal-user workflow is not complete.

## Changes

- `app/gui/main_window.py`: separate workspace tabs, compact responsive minimum dimensions, normal crop gallery, category filter, select-all, progress display, and selected-crop export.
- `app/gui/bbox_preview.py`: selecting an item in the professional detection list highlights its box; clicking a box selects the corresponding list item.
- `app/gui/correction_dialog.py`: scrollable review form and separate **Confirm Annotation**, **Save edits — confirmation required**, and **Confirm Classification** actions.
- `app/core/database.py`: schema migration 8 adds append-only classification review history. A changed bounding box invalidates a prior classification confirmation.

## Untested behavior

Verify on a small display and a large display, including keyboard navigation, overlapping boxes, direct box selection, window resizing, and dialog visibility. Manual steps are in `PHASE6_TEST_RESULTS.md`.
