# Phase 6 Test Results

## Baseline

Before Phase 6 code changes, the existing suite had **72 tests: 71 passed and 1 failed**. The failure was `test_yolo_and_cnn_packages_share_source_split_assignments`; its fixture did not provide the family-matched verified Clothing tag and crop required by current validation.

## Current run

- Python 3.11 virtual environment: `F:\My Tools\New folder\NewAssetApp\.venv\Scripts\python.exe`.
- `compileall` completed successfully.
- `python -m unittest discover -s tests -v`: **75 tests passed** (including new Phase 6 crop and classification-audit tests).
- No dependencies were installed or changed.
- Existing PySide bounding-box tests cover scaled coordinates, movement/resizing, and manual box creation. New database coverage checks edit → confirmation → bounding-box invalidation.

## Not covered by automated tests

The app launched through `run_app.ps1` and its initial Normal Processing accessibility tree showed the primary controls. Screenshot capture timed out; interactive GUI layout, screen-size responsiveness, keyboard navigation, Professional Review, linked selection with overlapping boxes, real model-backed batch inference, and the full UI-to-WebP flow were not tested. Do not treat startup or unit tests as complete GUI acceptance.

## Manual acceptance steps

1. Launch using `run_app.ps1`; verify both workspace tabs and primary controls are visible at the normal display size and a smaller display size.
2. Scan and analyze a folder with multiple images; confirm progress and per-image failure reporting.
3. In Professional Review, choose a detection-list entry, then click a box; confirm selection stays linked, including overlapping boxes. Move/resize a box and verify source-pixel geometry after resizing the window.
4. Save a classification edit and verify it remains unconfirmed. Confirm it, change the box, and verify the status returns to needs confirmation. Confirm classification without exporting a crop.
5. Select several prepared crops in Normal Processing and export. Verify WebP files route to category folders, collisions advance filenames, source files remain unchanged, and a failed item does not stop later exports.
6. Verify opaque Fullbody and alpha-required Portrait/tportrait crops report an actionable skip; inspect output dimensions and aspect ratios for supported crops.
7. Prepare a training package separately and verify no ordinary crop files are produced by that action.
