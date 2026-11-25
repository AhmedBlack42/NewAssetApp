# YOLO class analysis and proposed policy

The checkpoint and registry contain 32 ordered classes. The current source maps 24 labels to individual detection-crop Asset CNN routing, 7 location labels to context-only observations, and has no verified image route for `action_event` (the code handles it only in a gated video path). The proposal policy retains all 32 raw detections and proposes to route only the 24 explicit asset labels. The policy remains `proposed_pending_user_review`; no class filtering decision is user-approved yet.

The 44 sample images were run at detector threshold 0.25. The table reports raw detection counts only. Zero detections means “not observed in this small sample set,” not “irrelevant.” Asset CNN crops were classified for source-routed classes only. No prediction is ground truth.

| ID | Exact class | Sample detections | Proposed use | Existing route/evidence |
|---:|---|---:|---|---|
| 0 | `person` | 71 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 1 | `face` | 43 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 2 | `portrait_frame` | 36 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 3 | `boobs` | 10 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 4 | `ass` | 4 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 5 | `pussy` | 4 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 6 | `legs` | 20 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 7 | `action_event` | 21 | Unresolved, retained | Raw detection is retained; active code treats action_event in a separate gated video path, with no verified image proposal route. |
| 8 | `pussy_cover_item` | 23 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 9 | `ass_cover_item` | 11 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 10 | `boobs_cover_item` | 20 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 11 | `leg_cover_item` | 3 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 12 | `location_home` | 11 | Supporting only | Existing route treats this as location/context evidence. It does not assign a tag, category, or photoshoot. |
| 13 | `location_class` | 0 | Supporting only | Existing route treats this as location/context evidence. It does not assign a tag, category, or photoshoot. |
| 14 | `location_office` | 1 | Supporting only | Existing route treats this as location/context evidence. It does not assign a tag, category, or photoshoot. |
| 15 | `location_bathroom` | 9 | Supporting only | Existing route treats this as location/context evidence. It does not assign a tag, category, or photoshoot. |
| 16 | `location_bar` | 0 | Supporting only | Existing route treats this as location/context evidence. It does not assign a tag, category, or photoshoot. |
| 17 | `location_outdoor` | 15 | Supporting only | Existing route treats this as location/context evidence. It does not assign a tag, category, or photoshoot. |
| 18 | `location_bed` | 10 | Supporting only | Existing route treats this as location/context evidence. It does not assign a tag, category, or photoshoot. |
| 19 | `fullbody_shower` | 0 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 20 | `fullbody_maid` | 4 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 21 | `fullbody_nurse` | 3 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 22 | `fullbody_uniform` | 0 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 23 | `fullbody_athletic` | 0 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 24 | `fullbody_swim` | 1 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 25 | `fullbody_lingerie` | 2 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 26 | `fullbody_work` | 0 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 27 | `fullbody_casual` | 6 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 28 | `accessory_footwear` | 19 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 29 | `fullbody_topless` | 4 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 30 | `fullbody_bottomless` | 7 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |
| 31 | `fullbody_bare` | 9 | Proposal/crop | Existing Image Workshop routing sends this class to a per-detection crop and the Asset CNN; result still requires human review. |

## Proposed allowlists for review

- **Raw detection allowlist:** all IDs 0–31, preserving source evidence.
- **Asset proposal/crop route:** IDs 0–6, 8–11, 19–28, and 29–31 (24 labels).
- **Supporting-only context:** IDs 12–18. These do not create asset categories, location tags, or Photoshoot assignment.
- **Unresolved image route:** ID 7 `action_event`. It is preserved, not passed to Asset CNN or assigned to a category pending the user's choice.

No label maps to `photoshoots`. The model/checkpoint remains unchanged. The detailed machine-readable policy is `data/models/yolo_class_policy.json`; its approval is the gate before normal image-batch processing. See the 21 observed `action_event` detections in `MODEL_AND_SAMPLE_SMOKE_RESULTS.json` when deciding its handling.
