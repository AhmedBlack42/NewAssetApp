# Phase 7 GUI Redesign

## Implemented changes

- Increased the preview's share of the main layout using splitter defaults `[155, 420, 725]` and stretch weights that favor the preview; adjusted the review split to `[520, 150]`.
- Added a concise review hint for wheel zoom, middle-button pan, and double-click fit.
- Added cursor-anchored zoom, middle-button panning, and double-click reset to the bounding-box preview while keeping edits in source-image coordinates.
- Reduced box fill opacity, emphasized the selected outline, improved label readability/clamping, and enabled anti-aliasing.
- Raised the preview minimum size and prevented an unchanged click from emitting a geometry edit.
- Added focused tests for zoom coordinate preservation and no-op selection.

## Verification and limits

The focused preview tests passed (5 tests), and the full NewAssetApp suite passed (77 tests). The app was launched and its accessible screens were discovered, but desktop capture and input failed. Image aspect ratio, real screen space, selection/drag/resize/draw/delete, overlapping boxes, visibility toggles, and responsive behavior have not been accepted through hands-on interaction.

This redesign is an implementation pass, not a claim that the GUI is complete or accepted.
