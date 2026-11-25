# Phase 11.3 — NewAssetApp GUI Layout Repair and Acceptance

Date: 2026-11-08

## Acceptance status

**PARTIAL — NOT ACCEPTED.** The code-level repair and regression suite pass. A real NewAssetApp screenshot confirms the Normal Processing preview no longer shares its area with the classification form. Full live interaction acceptance is incomplete: the desktop capture service times out, the shared app reported concurrent user input, several required crop/review states were not captured, and Windows constrained a 1920×1080 resize to the current display work area.

The separate environment and capture findings are in [PHASE11_3_ENVIRONMENT_AND_CAPTURE_DIAGNOSTIC.md](PHASE11_3_ENVIRONMENT_AND_CAPTURE_DIAGNOSTIC.md).

## Root cause

Normal Processing placed the selected-crop `QLabel`, model details, category/tag controls, location controls, and navigation in one vertical layout. The preview had a 320×250 minimum and received a source pixmap scaled only during main-window resize events. The classification form had no scroll container. When the available height was smaller than the combined layout hints, Qt could not keep the image and form within separate visible regions; the form painted over the lower part of the preview. Resizing the splitter did not refit the pixmap.

The Correction Dialog also forced five action buttons into one horizontal row. Its form duplicated the training-exclusion control, and construction referenced the legacy Fullbody suggestion helper without importing it.

## Changes

- Added an aspect-ratio-preserving preview label that rescales from the original pixmap whenever its own size changes.
- Split the selected crop preview from the classification form. The form now scrolls independently below the preview; the Previous and Next controls remain outside that scroll region.
- Removed the filename from the compact crop evidence summary. Category, model evidence, and human-selected fields remain distinct.
- Shortened compact Professional Review labels and removed horizontal scrolling from category navigation.
- Made the correction dialog size itself to the available screen, wrap long form rows, place action buttons in a compact grid, remove the duplicate exclusion control, and import the legacy candidate helper it calls.
- Updated legacy tests to assert the current structured-classification and export-time filename rules, including the retired Body Images sub-main behavior. Assertions were retained or rewritten to test the approved behavior; failing tests were not skipped or disabled.

No crop geometry, aspect-ratio policy, background-removal processing order, database schema, model checkpoint, model class ID, or dependency was changed.

## Screenshots and window sizes

- Before repair: [normal_processing_before_repair_overlay_1376x788.png](../gui_screenshots/phase11_3/normal_processing_before_repair_overlay_1376x788.png) shows the actual app with the crop image extending under the classification controls.
- After the Normal Processing repair: [normal_processing_crop_preview_repaired_1376x788.png](../gui_screenshots/phase11_3/normal_processing_crop_preview_repaired_1376x788.png) shows the actual app with the crop image contained in its preview region and classification controls below in their own scroll area. At capture time, no crops were checked for export; a current crop remained selected for inspection.
- Exploratory Professional Review captures with no detection selected: [900×579](../gui_screenshots/phase11_3/professional_review_no_detection_900x579.png), [1280×788](../gui_screenshots/phase11_3/professional_review_no_detection_1280x788.png), [1360×768](../gui_screenshots/phase11_3/professional_review_no_detection_1360x768.png), and [1380×788](../gui_screenshots/phase11_3/professional_review_no_detection_clamped_1380x788.png). These document real-window sizing behavior; they are not final selected-detection acceptance images.

The native `PrintWindow` method returned readable, nonblank images and the files were reopened for inspection. CUA screenshot calls timed out on File Explorer, Brave, and NewAssetApp. Requested 900×560 became 900×579 because the window minimum applies to its client area plus frame; 1280×800 became 1280×788; 1360×768 was exact; and a 1920×1080 request was constrained to 1380×788. Display settings were not changed.

The offscreen layout test exercised 900×560, 1280×800, 1360×768, and 1920×1080. It verified separate preview/form geometries and visible Normal Processing navigation/export controls. The correction-dialog test verified its actions fit at compact and larger sizes. These automated checks do not substitute for live interaction at those dimensions.

## Workflow and classification verification

- Normal Processing remains independent of professional confirmation. Focused tests now supply a human-selected structured main tag and, for Fullbody, an explicit state before normal export.
- Professional Review keeps confirmation and training eligibility separate. Tests use explicit valid and confirmed classifications where training records are expected.
- Location candidates remain advisory and require verified model identity; canonical location selection remains human-controlled.
- Legacy Fullbody CNN outputs remain advisory; ambiguous nude evidence requires a human `topless` or `bottomless` choice. The legacy YOLO 32-class registry remains distinct from the new 31-class target registry.
- Body Images composition values are tested as structured subtags with supported main/subtag pairs. No independent sub-main field is asserted or introduced.
- Filename generation tests use structured values and the current universal grammar. Normal exports continue to be tested for WebP output, source provenance, collision handling, and processing order.

These points were verified through existing and updated automated tests. Live GUI selection of Fullbody, Body Images, Clothing, and Professional Review records was not completed.

## Database, launcher, and regression results

- No migration or backup was needed because this phase made no database schema change. The live database was not changed through shell code.
- `run_app.ps1` was launched in the approved execution context and reported Python 3.11.9 from `NewAssetApp\.venv\Scripts\python.exe`. The real app window opened and returned its accessibility tree. The user reports the launcher also works in their normal PowerShell session; that separate run was not repeated here.
- Full suite: `& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v` — **100 tests ran, all passed**.
- Focused GUI layout checks — **4 tests passed**, covering aspect-ratio scaling, preview/form separation at the four target dimensions, and correction-dialog action placement.

## Remaining limits and data caution

- CUA could read the live app accessibility tree but could not capture windows and could not provide coordinate geometry for GUI interaction. It later reported user input in the shared app window, so further GUI actions were stopped.
- Actual post-fix screenshots with each required crop category selected, a Professional Review detection selected, and classification controls visible were not obtained. Live visual acceptance at 900×560, 1280×800, 1360×768, and 1920×1080 is therefore incomplete.
- During capture work, the app status showed `Saved normal crop category for 1 crop(s)` and two selected crops. A read-only query found a recent Clothing/heels normal-crop choice, but no prior value or audit trail was available. This may have followed a mis-targeted capture interaction or concurrent user activity. No direct database update or restoration was attempted; the cause remains uncertain.
- No database migration, dependency change, model training, checkpoint replacement, CVAT operation, or TrainingDatasetStudio GUI work was performed.

Phase 11.3 remains open until final live interactions and screenshots support acceptance at all required window sizes, including a display capable of showing the requested 1920×1080 window.
