# Phase 9 Implementation Summary

## Implemented

- Reused a process-level BiRefNet runtime instead of reloading the model for each export batch.
- Added a bounded alpha-mask LRU cache with tested cache-hit and eviction behavior.
- Added normal-export background-removal configuration, per-item progress, cooperative cancellation, and explicit original-crop fallback/history on error or when disabled.
- Preserved completed exports on cancellation and report remaining crop IDs.
- Added regression tests for workflow independence, normal export routes, WebP output, collisions, traceability/training isolation, background-removal fallback, cancellation, and cache behavior.

## Verified

- Existing NewAssetApp `.venv` runs Python 3.11.9 x64; `pip check` is clean.
- No dependencies were installed, upgraded, or removed.
- The YOLO checkpoint hash matches its recorded SHA-256; no checkpoint changes occurred.
- Full test suite: 89 passed.
- Four real BiRefNet output WebPs were produced and visually reviewed. Foreground retention was generally usable in these samples, with softness/halos at fine edges; mean CPU processing time was 122.35 seconds per crop.

## Remaining acceptance blockers

- Desktop screenshot capture timed out twice, so the actual GUI layout, smaller-window clipping, interactions, and desktop screenshots under `gui_screenshots/phase9/` were not verified.
- A real folder-scan-to-GUI-normal-export run, live history inspection, and end-to-end source/output traceability check remain unverified.
- BiRefNet CPU inference remains very slow for batch work; no alternative model or dependency change was made.

Phase 9 is therefore **partially implemented and not fully accepted**. Do not treat automated tests or the four standalone mask samples as proof of complete desktop workflow acceptance.
