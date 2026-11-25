# Phase 10 — X-AnyLabeling review integration

**Design only.** X-AnyLabeling was not installed or launched, and no labels, CVAT project, or Studio dataset were changed. Product capabilities below were checked against the project's current official GitHub documentation during this audit; the exact installed release and round-trip behavior still require a controlled smoke test.

## Compatibility evidence

Official X-AnyLabeling user guide says detection YOLO annotations use `.txt` labels and a `classes.txt` where line order is zero-indexed class ID. It supports importing existing labels and provides a “Preserve Existing Annotations” option when merging, plus YOLO export to a selected/default labels directory. This makes manual review of existing rectangles a reasonable planned use without invoking model inference. The user guide also states the default export location may be a `labels` folder under the current image directory, so the Studio should always use an isolated review copy and explicit export destination.

Its official CLI supports conversion between YOLO and native XLABEL format using explicit `--images`, `--labels`, `--output`, `--classes`, and detection mode. The CLI documentation says it processes only the specified directory, not nested directories, and distinguishes missing labels from explicit empty labels through its `--skip-empty-files` behavior on conversion back. Therefore, split/class directories need per-directory conversion or a controlled flattening with collision-safe opaque filenames and a reversible manifest.

Sources checked:

- [X-AnyLabeling User Guide — YOLO import/export](https://github.com/CVHub520/X-AnyLabeling/blob/main/docs/en/user_guide.md#41-yolo-format)
- [X-AnyLabeling CLI — conversion and class index semantics](https://github.com/CVHub520/X-AnyLabeling/blob/main/docs/en/cli.md#32-show-detailed-help-for-a-specific-task)
- [X-AnyLabeling Image Classifier guide](https://github.com/CVHub520/X-AnyLabeling/blob/main/docs/en/image_classifier.md)

These are live `main`-branch documents; a Studio implementation should pin a tested release and preserve a copy of the operator instructions/version used for each round trip.

## Exact 31-class concern

**Verified:** current NewAssetApp checkpoint and preserved policy have 32 classes. The Phase 7 CVAT task/project had 31 labels but several classes have no exact match, and some proposed mappings were broad/non-equivalent. No CVAT mapping was applied. There is no verified Studio 31-class registry yet.

Do not open a Studio 31-class dataset in X-AnyLabeling until its exact registry is approved. `classes.txt` is positional; using the 32-class file or current 31-label CVAT list can silently change the meaning of IDs. Keep a registry checksum beside both the review-copy annotations and the Studio import manifest.

## Recommended safe round trip

1. **Freeze review input:** Studio creates a content-addressed review snapshot from one prepared version. Copy images and current YOLO text files into `review_jobs/<review-id>/input/`; retain original labels in immutable storage. Do not expose the package/finalized version path as the annotator's output folder.
2. **Write explicit class file:** copy the exact project version's `classes.txt`; include its SHA-256, class registry version, and a human-readable class ID/name table. Ensure one line per class and no blank/duplicate entries.
3. **Load existing annotations:** use X-AnyLabeling's existing annotation import or tested YOLO/XLABEL conversion path. Do not run any auto-label model. Confirm every existing box is visible before editing and that class IDs map to the intended names.
4. **Manual correction:** reviewer changes boxes/classes within the Studio-owned review copy. No server-side hosted AI is required. Studio retains a review job ID, reviewer identity, start/end time, and source input hashes.
5. **Export separately:** export corrected YOLO labels to `review_jobs/<review-id>/output/labels/` or a separate XLABEL directory. Export images only if X-AnyLabeling needs a standalone snapshot; never let the tool write into the original dataset tree.
6. **Re-import as a proposal:** validate the exported file list against the expected sample inventory. Validate label file hashes, class range, class registry hash, geometry, duplicate boxes if policy warns, and image-size correspondence. Reject unknown filenames or classes for manual reconciliation.
7. **Diff and accept:** show original/generated and corrected annotation side-by-side per image. The reviewer confirms import. Studio appends an event with before/after boxes, external tool version, both file hashes, registry hash, and actor, then creates a new reviewed dataset revision. It never overwrites generated labels.
8. **Revalidate and version:** external edit changes invalidate the previous validation report. Re-run the full dataset validator and human review gate. A finalized dataset must not be edited in place; any correction starts a child version.

## Import validation contract

Each reviewed label set should include a manifest row per expected image: opaque sample key, image SHA-256/dimensions, input annotation SHA-256, exported annotation SHA-256, class registry SHA-256, annotation count, empty-label-vs-missing-label state, and review job ID. Import must verify:

- every expected image is accounted for, with no unapproved additions/deletions;
- image and annotation basenames match by opaque key;
- every annotation line has exactly one known class ID and four finite box values;
- class ID range agrees with the exact registry and `classes.txt` line order;
- normalized coordinates are within [0,1], width/height are positive, and pixel-space boxes remain in image bounds;
- a missing annotation is not mistaken for an explicit no-object label;
- changes between copied input and exported output are attributable to recorded reviewer edits;
- no label was silently merged/reordered by a mapping operation.

## Class IDs and no-regeneration behavior

The documentation establishes the index mechanism and existing-label import options, but it does not prove that a chosen UI workflow round-trips our exact files losslessly. Make a one-image fixture for every supported path before implementation acceptance: include two existing boxes, distinct class IDs, a manually changed box, one empty label file, non-ASCII path, and a second nested split directory. Compare input and output IDs/coordinates within declared numeric tolerance. Confirm the tool did not run a model or create extra predictions. Save that result as an integration test and pin X-AnyLabeling version.

Use the YOLO annotation editor only for detection boxes. For ordinary Clothing and Asset CNN crops, use Studio's own image-grid classifier because it can enforce exact per-image class IDs, model head context, taxonomy metadata, eligibility, review events, source groups, and immutable dataset versions. X-AnyLabeling's docs do describe MultiClass/MultiLabel and object-level MultiTask classification, but binding those annotations back to Studio's registry/provenance remains a separate integration burden and is not needed for crop review.

## Current CVAT boundary

Existing CVAT integration is a native Ultralytics inference function, not a dataset lifecycle connector. The function takes a model, device, and image size and returns rectangles named from the checkpoint's 32 names. Phase 7 documents registration/function ID and local sample inference but no live project inference, export/re-import test, or annotation synchronization. The Phase 7 label map was proposed only, was not applied, and included unmatched/non-exact labels. CVAT may be useful later as an alternate external annotator only behind the same isolated review-copy/diff contract; do not treat its project registry as the new model registry.
