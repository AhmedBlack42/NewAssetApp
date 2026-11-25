# Normal Processing GUI Redesign Proposal

Date: 2026-11-24

Status: Audit and design only. No application UI or business logic was changed.

## 1. Executive Summary

NewAssetApp has a working Normal Processing implementation, but Proposal discovery
and current-state understanding are weaker than crop classification itself.

The isolated real-samples data currently contains:

- 287 source images
- 2263 detections
- 2263 proposals
- 0 orphan proposals
- 0 duplicate proposals
- Database integrity: `ok`

The current workflow has enough information in the data model, including pending,
confirmed, invalid, exported, stale, category, draft, CNN evidence, and effective
BBox fields. It does not present these states clearly or provide a fast way to find
one Proposal among thousands.

## 2. Actual GUI Structure

Normal Processing is built in `app/gui/main_window.py` as a horizontal workspace:

1. Category filter
2. Proposal icon gallery
3. Selected-crop preview and previous/confirm/next controls
4. Scrollable classification form
5. Export actions

The classification form exposes:

- Output category
- Main/detail tag
- Clothing broad family and cover area
- Fullbody state and Fullbody CNN target
- Cum and Accessory tri-state controls
- Arousal and Corruption targets
- Human subtags
- Location
- Filename preview
- Confirmation and export actions

The gallery currently displays category, confirmed/draft/invalid state, stale export
state, and filename-derived thumbnail text. It does not show Proposal ID, source
position, stale crop state, or confirmed CNN state as a compact set of visible fields.

Professional Review is a separate tab and is already structurally YOLO/BBox-only.

## 3. Visual Baseline

Unique synthetic Qt captures created for this audit:

- [1366×768 Normal Processing](/F:/My%20Tools/New%20folder/NewAssetApp/gui_screenshots/redesign_20261124/synthetic_qt_normal_processing_1366x768.png)
- [1920×1080 Normal Processing](/F:/My%20Tools/New%20folder/NewAssetApp/gui_screenshots/redesign_20261124/synthetic_qt_normal_processing_1920x1080.png)

These are synthetic `QWidget.grab()` captures, not headed Windows desktop captures.

The 1366×768 capture shows:

- A large icon gallery occupying the left third.
- A large blank/preview area.
- A dense classification column on the right.
- Controls requiring vertical scrolling.
- Confirmation and export controls separated across lower regions.

The 1920×1080 capture shows the same hierarchy with more available width, but the
information density does not improve the main task: the user still must visually
search for the correct Proposal and infer status from small text labels.

## 4. Confirmed Usability Problems

### NP-001: No direct way to find a Proposal

Evidence:

- Normal Processing exposes only a category filter.
- Proposal rows do not visibly expose a searchable Proposal ID.
- `normal_crop_records()` returns stable Proposal IDs, but the gallery UI does not
  show or navigate to them directly.

Impact:

- Users cannot return to a known Proposal quickly.
- Ordering by database ID is usable for technical users but not for visual review.

Priority: High

### NP-002: No compact proposal position

Evidence:

- Previous/next buttons exist, but no `N of 2263` indicator is shown.
- Filtering can change row count without displaying the current result position.

Impact:

- Users cannot estimate progress or predict nearby navigation.

Priority: High

### NP-003: Status is encoded as plain gallery text

Evidence:

- Pending, draft, confirmed, invalid, stale export, and exported information are
  combined into long row labels.
- Stale crop, CNN completed/pending, and source-invalid states are not exposed as
  compact independent status indicators.

Impact:

- The gallery is difficult to scan.
- A stale crop can be confused with a current crop.

Priority: Critical

### NP-004: The classification form is crowded

Evidence:

- Category, broad and detailed clothing controls, state controls, CNN targets,
  subtags, location, filename preview, and actions occupy one scrollable vertical
  form.
- Lower controls require scrolling at the supported 1366×768 size.

Impact:

- The user must repeatedly scroll to see validation and confirmation controls.
- Category changes can reveal unrelated controls while old choices remain in memory.

Priority: High

### NP-005: Unsaved draft feedback is weak

Evidence:

- `_normal_drafts` preserves state in memory.
- Gallery text becomes `Draft` after switching only in the in-memory refresh path.
- There is no persistent draft indicator and no explicit unsaved-change confirmation
  for switching away.

Impact:

- A user may not know that a crop has unsaved changes.
- Closing/reopening the app may lose in-memory draft edits.

Priority: High

### NP-006: No persistent stale-crop indicator

Evidence:

- `normal_export_status` and correction records exist.
- The current crop preview uses the effective BBox and category where available,
  but it does not show a persistent `Crop stale - BBox changed` state in a prominent
  banner.

Impact:

- A stale crop can be mistaken for a current crop.

Priority: Critical

### NP-007: Missing/failed previews have insufficient visible distinction

Evidence:

- Gallery missing/failed paths are tooltips only.
- The preview shows `Preview unavailable` and a details string after an exception.
- There is no permanent loading placeholder or retry action.

Impact:

- Missing source, decode failure, invalid BBox, and stale crop do not share one clear
  visual language.

Priority: High

### NP-008: Export confirmation and validation are not visually grouped

Evidence:

- The filename preview is inside the scrollable form.
- Export controls are in a bottom action row.
- The export button becomes enabled by selection rather than by a clear completed
  classification summary.

Impact:

- User may export a selected crop before understanding whether its tags are valid
  or confirmed.

Priority: High

## 5. Target Normal Processing Layout

Recommended structure:

```text
+------------------------------------------------------------------------------------------------+
| Status/position: Proposal 482 of 2263 | Pending 812 | Confirmed 120 | Invalid 31 | Stale 18   |
+----------------------+------------------------------+-------------------------------------------+
| Proposal Navigator   | Crop Preview                 | Classification Inspector                 |
|                      |                              |                                           |
| Search / ID jump     | Source thumbnail/context     | Category                                  |
| Status filter        | Large crop preview           | Main/detail tag                           |
| Category filter      | Stale/missing banner         | Subtags/cover area/CNN decisions          |
| Proposed ordering    | Previous / Next             | Validation summary                        |
| 2263-row gallery     |                              | Draft/confirmed indicator                 |
|                     |                              | Save / Confirm / Export                    |
+------------------------------------------------------------------------------------------------+
```

The existing left gallery, central crop preview, and right inspector should remain.
The redesign should compact and reorganize rather than replace them.

## 6. Proposal Navigation and Filtering

### Current Proposal position

Add a compact `Proposal 482 of 2263` indicator above the preview.

Implementation:

- Derive position from the filtered visible list.
- Update after filter, next/previous navigation, and gallery refresh.
- Keep Proposal ID available through search/diagnostic tooltip.

Business logic risk: UI-only if the filtered row list is preserved.

### Search and direct ID jump

Add a small compact search field above the gallery:

- Placeholder: `Proposal ID`
- Accept exact numeric Proposal ID.
- Optional filename substring search can follow in a later phase.

Suggested interaction:

1. Enter an ID.
2. Select Enter or Jump.
3. Scroll to that Proposal.
4. Select it.
5. Preserve the existing unsaved draft.

Business logic risk: UI-only, using existing `normal_crop_records()` row IDs.

### Status filters

Recommended compact filters:

- Pending
- Confirmed
- Invalid
- Exported
- Stale crop
- Needs category

Combined filter behavior:

- AND semantics for status dimensions.
- `Needs category` and `Pending` can overlap.
- Exclude stale source records if already excluded by `normal_crop_records()`.
- No filter should delete or discard unsaved `_normal_drafts`.

The result count should show:

`2263 proposals · 812 pending · 120 confirmed · 31 invalid`

## 7. Crop and BBox Visual-State Design

Use one status banner above the crop preview:

- `Current crop`
- `Unsaved changes`
- `Draft classification`
- `Confirmed`
- `Stale crop - BBox changed`
- `Missing source`
- `Thumbnail/decode unavailable`
- `Invalid/rejected proposal`

The banner should use text and an icon, not color alone.

Stale crop behavior:

- Keep original correction history.
- Show effective BBox revision separately.
- Disable export until refreshed.
- Render only the latest effective BBox.
- Never show the old thumbnail as current.

This phase is UI-state design only; the effective-BBox authority already exists.

## 8. Save, Validation, and Export Feedback

Add a compact validation summary directly above confirmation:

- `Category: Clothing`
- `Main tag: mini_skirt`
- `Cover area: ass_cover`
- `Human subtags: 0`
- `Status: ready to confirm`

For incomplete decisions:

- Show exact missing fields.
- Disable confirmation and explain why.
- Do not open a generic warning dialog for normal validation.

For saved confirmation:

- Show inline success: `Classification confirmed · ready to export`.
- Keep confirmation independent from export.
- For export:
  - Show `Selected: 3 confirmed · 1 invalid excluded`.
  - Show progress.
  - Show success with actual output path.

Unsaved draft switching:

- Mark the Proposal with `Unsaved`.
- Keep the draft in `_normal_drafts`.
- Switching to another Proposal should not silently lose it.
- A persistent draft should be clearly labeled after reselecting the Proposal.

## 9. CNN and Human Evidence

CNN evidence and human decisions should remain visually separate.

Recommended presentation:

- `Suggested: clothed · 84%` in muted text.
- `Human choice: topless` in a clear human-confirmed style.
- Per-head status:
  - Pending
  - Confirmed
  - Rejected
  - Stale after BBox

Keep:

- Cum and Accessory independent.
- Fullbody, Portrait, Arousal, and Corruption independent.
- No task card in Professional Review.

## 10. Keyboard and Navigation

Recommended:

- `Ctrl+J`: open Proposal jump/search.
- `Ctrl+F`: filename/search if implemented later.
- `PgUp/PgDn`: move one page in the gallery.
- `Alt+Left/Right`: previous/next Proposal.
- `Ctrl+Enter`: confirm valid classification.
- `Ctrl+S`: save draft.
- `Escape`: cancel search, not unsaved edits.

Acceptance criteria:

- Keyboard focus remains predictable after category changes.
- No accidental confirmation from Enter in a text or combo field.
- Next/previous navigation preserves unsaved drafts.
- Tab order follows gallery, preview, category, tags, confirmation, export.

## 11. Performance Risks and Expected Impact

Measured in the latest offscreen real-sample Qt run:

- Gallery refresh: approximately 1002 ms.
- Clothing selection: approximately 219 ms average in the 20-sample run.
- Body Images selection: approximately 157 ms average in the 20-sample run.
- Viewport thumbnail loading: approximately 38–246 ms.
- Maximum heartbeat gap: approximately 140 ms.

The largest risk is the complete `normal_crop_records()` query plus rebuilding the
entire 2263-row `QListWidget` on every refresh.

UI redesign estimates:

- Proposal search and jump: Medium implementation effort.
- Status filters: Medium effort.
- Current-position indicator: Low effort.
- Stale-crop banner: Low UI effort; use existing correction/export status data.
- Inline validation summary: Low-to-Medium effort.
- Unsaved-change feedback: Medium effort.
- Gallery virtualization: High effort and should be a separate performance phase.

No implementation benchmark should claim production gains until it is remeasured.

## 12. Prioritized Implementation Sequence

### Phase 1: Status and position

1. Add current Proposal position.
2. Add compact human-readable status text.
3. Add persistent stale-crop banner.
4. Add missing/failed preview explanation.

Acceptance:

- Position updates after selection/filter.
- Stale state is never presented as current.

### Phase 2: Search and filters

1. Add exact Proposal ID jump.
2. Add pending/confirmed/invalid/exported/stale filter.
3. Add needs-category filter.
4. Show result counts.

Acceptance:

- Jump selects the correct row.
- Combined filters do not modify records or drafts.

### Phase 3: Form compactness

1. Group category/tag controls.
2. Separate CNN decisions into collapsible category context.
3. Keep filename preview and validation visible.
4. Move confirmation/export into a compact sticky action region.

Acceptance:

- Key controls visible without excessive scrolling at 1366×768.
- Category changes update only applicable fields.

### Phase 4: Unsaved and confirmation feedback

1. Add in-memory draft indicator.
2. Add unsaved-change banner.
3. Add inline validation summary.
4. Add explicit confirmation success feedback.

Acceptance:

- Switching Proposals preserves drafts.
- Closing/reopening behavior is truthful and clearly stated.

### Phase 5: Performance follow-up

1. Incremental gallery refresh.
2. Incremental thumbnail loading.
3. Repeated selection timing instrumentation.
4. Virtualization only if measured and approved.

Acceptance:

- Selection remains below 250 ms in repeated real-Qt measurements.
- Gallery refresh remains below 250 ms for incremental updates.
- Full gallery rebuild is reserved for explicit refresh/filter changes.

## 13. Change Classification

UI-only changes:

- Search, position, status text, validation summary, stale banner, grouped layout,
  filter controls.

Changes requiring careful state integration:

- Unsaved draft persistence.
- Export readiness and confirmation feedback.
- Incremental gallery refresh.
- Virtualization.

No proposal for this audit changes database schema or taxonomy.

## 14. Acceptance Criteria

The redesign is ready for implementation only when:

- A user can jump to a known Proposal.
- A user can understand its pending/confirmed/invalid/exported/stale state.
- A stale BBox crop is clearly labeled before any export.
- Unsaved drafts are never silently lost.
- Confirmation feedback is distinct from export feedback.
- Normal Processing fits key controls at 1366×768 more effectively.
- Professional Review remains independent and YOLO/BBox-only.
- Existing 209-test regression baseline remains available.
