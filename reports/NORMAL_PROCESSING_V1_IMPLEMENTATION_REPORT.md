# Normal Processing V1 Implementation Report

Date: 2026-11-24

## Persistent Drafts

- New schema migration: NewAssetApp migration 25.
- Draft table: `normal_processing_drafts`.
- Draft identity: Proposal ID plus source hash, detection ID, BBox revision, and crop identity.
- Draft payload is JSON and versioned with `draft_schema_version`.
- Draft records preserve category, main/detail tags, subtags, Fullbody state,
  independent Body Images targets, Portrait/Arousal/Corruption targets, location,
  taxonomy version, crop revision, and timestamps.

## Autosave and Restoration

- A 300 ms Qt timer debounces draft writes.
- Category state recalculation schedules autosave.
- Closing the window flushes active draft timer work.
- Switching Proposals flushes draft capture before state restoration.
- Successful confirmation removes the draft only after database confirmation.
- Failed confirmation does not delete the draft.
- Restored drafts are labeled in the Normal Processing details panel.

## Revision Safety

- Draft payload includes source hash and effective BBox/crop identity.
- Reload records the latest source hash and corrected BBox.
- Restored drafts expose `stale_due_to_revision` when the source or authority changes.
- Stale drafts are retained and require review; they are never automatically confirmed.

## Proposal Management

- Exact numeric Proposal ID jump.
- Filtered Proposal position indicator.
- Category, status, needs-category, draft, confirmed, invalid, exported, and stale filters.
- Filters do not alter database records.
- Source-progress text reports sources whose relevant proposals are all confirmed.

## Layout

- Existing left gallery / center preview / right inspector layout is preserved.
- A proposal search and status filter row was added above the gallery.
- Source progress and filtered proposal counts are shown in the header.
- Stale, restored, and unsaved draft states are included in the selected details text.

## Keyboard and Actions

- `Ctrl+J`: focus Proposal search.
- `Ctrl+S`: flush draft.
- `Alt+Left/Right`: previous/next Proposal.
- `Ctrl+Enter`: confirm if the active focus is not an editable field.
- `Escape`: clear search.
- Explicit Discard draft button requires confirmation.

## Verification

- Persistent draft tests passed:
  - Independent fields autosave and reload.
  - Partial/pending states remain distinct.
  - Stale draft remains preserved.
  - Discard removes only the draft.
- Existing Normal Processing and correction tests remain passing in focused runs.

## Remaining Items

- Full headed-Windows launch remains blocked by the desktop automation safety boundary.
- Component-by-component draft timing instrumentation can be expanded later.
- Source progress currently uses confirmed records without per-head eligibility expansion.

## Final Implementation Status

- Migration 25 was applied and its draft table was verified.
- Proposal ID search and jump were added.
- Status filters were added for confirmed, pending, invalid, exported, stale,
  needs category, and draft/unsaved state.
- Current filtered Proposal position is maintained.
- Source progress is computed from all loaded proposals, not only filtered rows.
- Persistent draft restore includes source/hash/BBox-stale detection.
- The close event flushes the current draft.
- Classification confirmation removes the draft only after successful persistence.
- Screenshot evidence:
  - `gui_screenshots/v1_normal_processing/v1_synthetic_qt_normal_processing_1280x720.png`
  - `gui_screenshots/v1_normal_processing/v1_synthetic_qt_normal_processing_1366x768.png`
  - `gui_screenshots/v1_normal_processing/v1_synthetic_qt_normal_processing_1920x1080.png`

These are synthetic Qt captures, not headed Windows desktop evidence.

## Test Result

- Focused V1 implementation suite: 53 tests passed.
- Full NewAssetApp suite: 216 tests passed, 1 skipped.
- Studio integration suite: 11 tests passed.
- Python compileall: passed.
- Pylance syntax checks: passed for modified core/gui/readiness files.
- `git diff --check`: passed.
