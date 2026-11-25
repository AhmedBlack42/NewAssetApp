# GUI Acceptance Backlog

## STUDIO-RAR-001 — External RAR Archive Integration

Status: Deferred.

Future scope:

- Detect an already-installed WinRAR or `rar.exe`.
- Create RAR archives only through a legitimate external writer.
- Preserve a genuine 4,000,000,000-byte minimum package size.
- Never pad or duplicate data.
- Verify archive integrity and file hashes.
- Do not install RAR tools without approval.

## STUDIO-RESUME-001 — Shared-training resume

Status: Explicitly unsupported.

Do not advertise resume until checkpoint epoch, optimizer, scheduler, and
dataset-version compatibility are implemented and verified.

## STUDIO-ACTIVATE-001 — Production activation and rollback

Status: Isolated only.

Studio returned artifacts and training runs must not modify NewAssetApp
production models until an explicit integration/approval workflow exists.

## YOLO-3132-001 — 31/32 registry mapping

Status: Unresolved.

Do not remap, reinterpret, or silently change the legacy 32-class checkpoint
against the active 31-class target registry.

## GUI-REDESIGN-001 — Broad visual redesign

Status: Deferred.

Only blocking usability defects identified through acceptance should be fixed
before the next design phase.

## GUI-PHASE3-001 — Complete real-widget workflow acceptance

Status: Completed by Phase 4 for remaining high-level workflow entry points.

Completed:

- Fail-closed disposable isolation manifest.
- Real Qt Normal Processing Body Images positive/negative save/reload.
- Real Studio navigation mapping for all 9 existing pages.

Remaining:

- Complete Professional Review correction-dialog coverage for every head and
  all independent CNN reload variants.
- Headed Windows desktop interaction and screenshot capture.

## GUI-PHASE4-001 — Professional Review and Studio lifecycle

Status: Partially complete.

Completed:

- Real Qt Normal Processing 7-state Body Images matrix.
- Real Qt Professional Review source/detection navigation.
- Real Qt Inspector class and bbox interactions.
- Real Qt independent task-card controls.
- Real Qt Studio import.
- Real Qt Studio dataset creation, validation refresh, immutable finalization,
  and package export.

Remaining:

- Fullbody, Portrait, Arousal, and Corruption task cards for every eligible
  fixture and reload state.
- Combined/class-only/bbox-only/second-correction/invalid-save correction matrix.
- Headed Windows desktop interaction and screenshots.

## GUI-PHASE5-1-001 — Manual Proposal blocker

Status: Fixed and PASS_REAL_APP_QT.

Completed:

- Manual Proposal now creates a real manual detection and linked proposal.
- The Correction Dialog exposes valid class and bbox controls.
- Combined class/bbox save completed through real Qt widgets.
- Effective class/bbox persisted and reloaded.
- Original manual detection data remained immutable.

Remaining:

- Broader correction matrix.
- Independent task-card matrix.
- Headed Windows desktop acceptance.

## REAL-SAMPLES-001 — Legacy YOLO mismatch guard

Status: Fixed for Professional class correction.

The real 32-class checkpoint produced names not present in the approved
31-class target registry. The Inspector now:

- Shows `Choose approved target class`.
- Disables Save Correction.
- Does not silently remap or default to Person.

The 31-versus-32 mapping itself remains unresolved and unchanged.

## REAL-SAMPLES-002 — Uncategorized Normal crop fallback

Status: Fixed.

Normal Processing now includes an explicit `Choose category` placeholder.
Confirmation is disabled until a valid category and required fields are chosen.

## REAL-SAMPLES-003 — Duplicate Fullbody bikini option

Status: Fixed.

Normal Processing deduplicates repeated canonical main-tag values, so
`bikini` appears only once in the UI.

## REAL-SAMPLES-004 — Real-sample classification and task-save completion

Status: Completed for the requested representative workflows with actual
in-process Qt events; broader export and headed-desktop acceptance remains.

Verified:

- Reused the existing isolated DB without another scan or inference; integrity
  check `ok`, all 287 source paths resolve, and source/detection/proposal counts
  remain 287 / 2,263 / 2,263.
- Actual Normal Processing saves/reloads for Fullbody, Body Images, Clothing,
  and Invalid; Invalid produced no eligible training example.
- Actual Professional Review saves/reloads for Body Images, Portrait, Arousal,
  Fullbody, and Corruption, with independent task state and human provenance.
- One Clothing crop exported through the real Qt export controls to the
  isolated workspace as a 245x235 WebP.
- Fixed the Invalid callback exception, Sources-view ID collision,
  `portrait_frame` Body Images validation, and narrow-panel target-control
  clipping; focused regression tests pass.

Not verified:

- Full export matrix, including BiRefNet/transparent-background output.
- Exact pixel-level preview alignment and headed Windows desktop interaction.
- Broader detection/review filters and proposal actions outside the requested
  representative workflows.

Blocker:

- Keep the 31/32 registry mapping unchanged. The Clothing CNN checkpoint
  remains unavailable.

Evidence: `reports/REAL_SAMPLES_GUI_PRODUCT_AUDIT.md`, completed in-process Qt
real-sample addendum dated 2026-11-23.
