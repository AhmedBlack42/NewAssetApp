# Detection, Crop, and Training Data Integrity

## Scope

This report documents the critical V1 integrity fixes for manual detections, YOLO eligibility, canonical crops, source grouping, and training handoff.

## Active-session baseline

No production database records were modified during investigation. Disposable copies and test databases were used for verification.

## Manual Draw Box root cause

The previous `create_manual_detection()` contract inserted `user_manual` detections with `manual_annotation` as the class name and no canonical class ID. The Professional Review correction workflow could later add a correction, but it could not reliably make the detection itself a valid manually-originated target YOLO Detection. The repair requires a selected approved registry class before persistence and records the canonical ID/name in the manual detection and its proposal.

## Corrected manual lifecycle

- `Draw box` prompts for an approved canonical YOLO class.
- A manual Detection is persisted with `model_id=user_manual`, canonical class ID/name, source-pixel BBox, and a linked Proposal.
- Existing Detection corrections remain on the immutable original YOLO record plus correction history.
- Repeated crop requests reuse the canonical crop identity.

## Eligibility

Normal Processing now derives category availability from `required_tasks()` in `classification_eligibility.py`. Person detections do not expose Fullbody; only eligible Arousal/Corruption controls remain available.

## Canonical crops

`active_detection_crops` remains the one-current-crop table keyed by Detection ID. The canonical identity includes Detection ID, source SHA-256, effective BBox, and generation version. BBox corrections invalidate the old pixel identity; unchanged class or field changes reuse it.

## Source-image grouping

The Normal Processing filter now exposes a canonical source-ID grouping selector with source filename and stable source ID. Filtering can be combined with existing category/status filters and drafts remain Proposal-scoped.

## Similar crops

No automatic identity or character clustering was introduced. Exact crop duplicate identity can be derived from crop SHA-256, but the UI is intentionally not claiming visual identity. Reliable cross-image character grouping remains a V2/blocker until embeddings or a proven local method are available.

## Training handoff

Human confirmation already creates `training_examples` independently of user-facing export. The training bundle exporter now emits dedicated authoritative PNG crops under `media/crops/` in addition to source media. Bundles remain source-hash and crop-bbox provenance-aware.

## Remaining validation

Focused tests and the full suite are to be run after implementation stabilization.
