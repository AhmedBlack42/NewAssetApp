# Fullbody Correction and Training Confirmation Verification

## Result

All four requested focused test groups passed using temporary databases and
synthetic PNG media. Test-runner-reported time was 4.75 seconds total. No GUI,
Qt/layout, or full-suite tests were run.

## Evidence

- Legacy `fullbody_topless` and `fullbody_bottomless` detections accepted
  class-only corrections to approved Fullbody registry classes. A combined
  class-and-BBox correction also resolved to the requested effective state.
  Original detection class IDs and coordinates remained unchanged. An invalid
  BBox raised an error without adding a correction record.
- A separate class-correction regression (face to person) staled the prior
  confirmed CNN task review and suppressed its training example, preventing the
  old target from remaining in current training candidates.
- Four Normal Processing Fullbody confirmations immediately produced four
  current CNN training examples with no user-facing crop export.
- With user-facing crop export enabled, four WebP crops were written and the
  same four CNN training examples remained available.
- The handoff bundle contained four authoritative detection-crop records.
  TrainingDatasetStudio accepted all four with no quarantines. Reimporting the
  same immutable bundle was reported as a duplicate and did not add records.

## Readiness and limits

The verified readiness stage is **confirmed in NewAssetApp → bundled →
accepted in Studio staging**. Dataset finalization and model training were not
part of this verification. No production database, existing sample/export,
checkpoint, dependency, virtual environment, or launcher was changed; no model
was trained.

Focused evidence is from disposable synthetic fixtures only. GUI behavior and
the full test suite remain unverified, as requested.
