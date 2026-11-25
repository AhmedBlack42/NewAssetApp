# Normal Processing Detection Review Upgrade

## Active-session baseline

- Read-only live-session inspection: NewAssetApp is running and the active tab is **Professional Review**.
- The active source folder is `F:/My Tools/New folder/NewAssetApp/samples`.
- Live Professional Review shows **292 source images** in the active folder and **358 items** in the All library count.
- The active library row is `10963092_034_b6d8.jpg`.
- The active detection is **YOLO Detection #1187**, original and effective YOLO class `face`, confidence `82.8727%`.
- Detection #1187 is linked to **Proposal #1196**.
- Original bbox: `[240.2496, 260.4804, 358.0865, 370.1926]`.
- Effective bbox: `[206.9013, 254.5954, 363.9714, 366.2692]`.
- The bbox is approved in `yolo_bbox_reviews`; no task-head review exists for Detection #1187.
- There is no active cached crop row for Detection #1187, so the crop must not be assumed fresh from the active-crop cache.
- The independent Normal Processing draft record is currently **Proposal #983**, linked to Detection #983; it is fullbody_maid and is marked invalid in `normal_crop_choices`.

## Database counts used to explain the baseline

- Global database: 358 sources, 2809 detections, 2825 proposals, 351 CNN predictions.
- Active `samples` folder: 292 source images and 2308 Normal Processing records in the current implementation.
- Earlier screenshot counts may reflect a prior database/result set and are not the denominator for the current live database.

## Model and record semantics

- The source database has 358 source rows, 292 of which are under the active samples folder.
- Normal Processing currently exposes 2308 proposal/crop records for the 292 active sources.
- Active samples counts at baseline: 14 confirmed, 1 invalid, 86 stale prior export statuses, and 351 non-empty CNN predictions.
- The line `Model evidence: fullbody_maid · suggestion only` combines a candidate category asset type and YOLO evidence. `fullbody_maid` is not a confirmed final export tag; the human-selected state/tag and confirmation remain separate.
- The existing `normal_crop_choices.is_invalid` scope is Proposal-scoped. Professional detection invalidation (`yolo_detections`/correction records) is Detection-scoped and is preserved separately.
- Existing crop invalidation excludes the Proposal crop, preserves source/detection/history, and can be reversed with the Proposal-scoped restore path.

## Implementation

- Normal Processing now shows Detection ID, effective/original YOLO class, confidence, effective BBox, BBox approval/revision, crop freshness, and source-context highlighting.
- Added explicit `Approve` and `Reject` suggestion actions backed by `classification_task_reviews`. Approval is a draft/review decision, not confirmation or export. Reject is Proposal/task-specific and does not invalidate the crop or insert a negative target.
- Added separate `Mark Crop Invalid` and restore actions. The action confirms scope and changes only `normal_crop_choices` for the selected Proposal.
- Added exact cross-tab navigation to Source + Proposal + Detection plus a return action. Normal drafts are captured before navigation and restored after refresh.
- Active crops are now identified by effective bbox match and revision; stale/uncached states are explicit.

## Counts and progress

- Proposal counts, source counts, detections, CNN predictions, and confirmed-source progress are distinct.
- `292 sources` means source rows fully/partly represented by the active folder.
- `303/358/2308` style numbers are proposal/crop-library counts and must not be interpreted as source-image counts.
- `Analyzed 0 / 0` is the analysis-worker/reset counter and is separate from gallery rows.

## V2 compatibility

No broad schema change was made. Existing source SHA-256, Proposal ID, Detection ID, crop bbox/revision, and source-image path fields can carry still-image provenance. Video/frame fields remain a V2 concern and should use a parent-source grouping key rather than treating frames as unrelated sources.

## Validation

- Focused Normal/draft/classification suite: 52 tests passed.
- Full suite: 219 tests run, 217 passed, 1 skipped, 1 environmental failure.
- Environmental failure: `test_all_heads_and_clothing_tasks_export_import_validate_and_package` rejects the host because available RAM is 1 GiB, below the validator's conservative 2 GiB minimum.
- Synthetic Qt capture: `gui_screenshots/normal_processing_review_upgrade/synthetic_normal_processing_review_001.png`.
- Synthetic capture time: approximately 447 ms, including 1366x768 Qt window grab.
- Live headed desktop screenshot was not created because the live session was only inspected read-only and the task forbids altering it merely for evidence.
