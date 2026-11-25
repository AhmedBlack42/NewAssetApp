# Final Pre-Release GUI and Export Audit

Date: 2026-11-22

## Scope

This pass was limited to the requested pre-release audit and verified Fullbody
stabilization. It does not implement Colab RAR packaging or CPU training.

## Fullbody export

### Root cause

The historical live failure was the combined BiRefNet CPU pipeline, not a
standalone image-conversion allocation. Model loading, normalized input tensors,
model activations, the sigmoid mask tensor, mask conversion/resizing, RGBA
copies, and cached mask storage can coexist. The existing runtime now lazily loads
the unchanged bundled general checkpoint once, selects 384–1024 inference
resolution from available RAM, retries smaller resolutions on CPU allocator
errors, and blocks unsafe exports before model allocation.

The tensor cleanup improvement added here releases `mask_tensor` and invokes
garbage collection/cache cleanup after mask conversion. This is a release
improvement, not a quality change.

### CPU profile

Disposable realistic crop: 720×1345 pixels.

| Stage | RSS / timing |
|---|---|
| Before model load | 0.181 GiB |
| After model load | 1.072 GiB |
| Peak after 384×384 inference | 1.145 GiB |
| After cleanup | 1.133 GiB |
| Model load | 49.75 s |
| Inference | 21.90 s |
| Postprocessing | 0.28 s |

The pre-existing 1024×1024 quality pass remains 114–128 seconds/crop. The
384×384 test is measured on this machine but is not a completed visual-quality
acceptance for every pose or edge case.

### Files changed

- `app/core/output_exporter.py`: release the postprocessed mask tensor and run
  CPU cleanup/GC for CUDA before returning the PIL output.

### Existing protection

- 2 GiB available-RAM preflight.
- Maximum 25 megapixel crop and 12,000-pixel side preflight.
- Resolution fallback: 1024, 768, 512, 384, 320.
- Process-wide single runtime.
- 32 MiB bounded alpha cache.
- No opaque fallback for required Fullbody exports.
- Useful failure text is preserved in export history/results.

### Verification

- Focused export/GUI suite: 28 tests passed.
- Full suite: 177 tests passed.
- `git diff --check`: passed.
- GUI visual runner: PASS.
- Real CPU sample: one realistic 720×1345 crop completed at 384×384 and
  produced a measured transparent mask path.
- WebP/filename/repeated-cancel/cache tests remain covered by the disposable
  export suite.

No replacement model or checkpoint was introduced.

## GUI review

### Screenshot inventory

Latest run:
`gui_screenshots/automated/20261122_024954_11520/`

The run contains 9 NewAssetApp captures and 27 Studio captures at
1280x720, 1366x768, and 1920x1080. The Qt captures use synthetic fixture data.
They are layout evidence, not live headed-desktop workflow proof.

### Reviewed surface coverage

- NewAssetApp: startup/main, Normal Processing, Professional Review.
- Studio: Model Projects, Dataset Segments, Dataset Builder, Dataset Records,
  Validation, Colab Packages, Model Artifacts, Import/Activation, and History.
- The runner also reports skipped scenarios for surface/application combinations
  that do not exist.

### Confirmed issues

| ID | Application | Severity | Finding | Evidence / action |
|---|---|---:|---|---|
| FP-001 | NewAssetApp | Medium | Normal Processing classification content remains vertically constrained at compact heights. | Existing live AX evidence and smaller captures; keep independent scroll/form preview and verify compact 1280x720 with real data. |
| FP-002 | NewAssetApp | High | Live headed-desktop interactions and modal save/reload behavior are incomplete. | Unit/disposable evidence exists, but no final real-user interaction pass. |
| FP-003 | NewAssetApp | Medium | Detection-backed actions can still encounter orphan/manual proposals at runtime. | Use explicit disabled-state handling and human-readable explanation. |
| FP-004 | Studio | High | Import→dataset→package GUI completion is not live-verified. | Workflow code/tests exist; require headed smoke with disposable data. |
| FP-005 | Both | Medium | The current visual runner uses synthetic fixture widgets; it is not headed live acceptance. | Retain it for layout regression, add optional real-screen capture where reliable. |
| FP-006 | Studio | Medium | Production activation and shared-training resume remain intentionally unsupported. | Report as remaining product decisions, not silently implement. |

No screenshot demonstrates an undisclosed visual defect caused by this audit.
Synthetic captures and prior live evidence do not establish final visual acceptance.

### Agreed design compliance

- NewAssetApp dark workstation styling is retained.
- Normal Processing has a three-column/preview workflow structure.
- Professional Review has a contextual large-canvas inspector structure.
- Studio navigation exposes project, segment, builder, record, validation,
  package, artifact, import/activation, and history surfaces.
- Comprehensive manual polish is not complete. Do not begin broad redesign until
  this report is approved.

## Remaining functional gaps

- Live Normal Processing save/reload/export for every taxonomy choice.
- Live Professional Review save/reload/failure/navigation acceptance.
- Detection-backed-action guard for orphan/manual proposals.
- Live Studio import→dataset→package flow.
- Real headed-desktop screenshots.
- Production activation/rollback policy.
- Shared-training resume decision.

Taxonomy and eligibility discrepancies were not modified.

## Existing automation limits

- Qt fixture captures prove layout and navigation, not real model/data behavior.
- Synthetic backgrounds and images are not evidence of Fullbody quality.
- Unit tests prove export and database behavior but not live WebP output on every
  real pose.
- 384×384 CPU acceptance is not a substitute for quality comparison at 1024.

## Prioritized next implementation order

1. Fix orphan/manual proposal action handling.
2. Complete a headed disposable Fullbody export pass and save before/after evidence.
3. Complete live Normal Processing taxonomy and export acceptance.
4. Complete live proposal navigation/reload/failure acceptance.
5. Complete Studio disposable import→dataset→package acceptance.
6. Decide activation/rollback and shared-training resume behavior.
7. Approve and begin any broad GUI redesign.
