# Phase 11.4 — NewAssetApp Classification and Review UX Update

## Status

**PARTIAL — NOT ACCEPTED.** The requested scroll-list and preview UX changes are implemented and verified. The live v10 database was intentionally left untouched; therefore the v11 migration has not been applied to the live database and this phase is not ready for acceptance.

## Changes

- Replaced Normal Processing crop export checkboxes with extended list selection. “Select all visible” still selects all available crops for batch export.
- Kept human-selected subtags and corruption values in separate multi-select scroll lists. The corruption list is ordered Slut, Whore, Ultimate Whore, Conservative; Ultimate Whore serializes as `u_whore`. These values are excluded from the ordinary subtags list.
- Changed location selection to a single-select scroll list in Normal Processing and proposal review.
- Replaced proposal-review box visibility toggles with one selector: All boxes, Selected box, or Hide boxes. The preview is centered, narrower, and taller to leave room for the detection list.
- Replaced proposal-review training eligibility and corruption eligibility checkboxes with a multi-select scroll list of task-specific destinations. The separate legacy Clothing CNN eligibility is not offered.

## Verification

- Full NewAssetApp suite: **108 tests passed** using `F:\My Tools\New folder\NewAssetApp\.venv\Scripts\python.exe` (Python 3.11).
- Native Windows screenshots were captured from actual Qt windows using synthetic records and a disposable database only. The live application and user database were not used for capture.
- Display size: 1360×768. Screenshot client/window dimensions are recorded in `gui_screenshots/phase11_4/capture_manifest.json`.
- Preview screenshot: `gui_screenshots/phase11_4/professional_overlapping_detections_1360x749.png`.
- Scroll selectors screenshot: `gui_screenshots/phase11_4/normal_location_scroll_list.png`.

## Remaining acceptance work

The migration remains limited to v11 code and disposable/test databases. The live v10 database has not been migrated or backed up in this phase, so production startup against v11 and live-data migration/rollback evidence are outstanding.
