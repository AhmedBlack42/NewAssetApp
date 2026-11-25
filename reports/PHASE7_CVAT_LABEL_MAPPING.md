# Phase 7 CVAT Label Mapping — Live Project Verification

Project `Yolo_v2` (ID 462846) was queried live through the authenticated API. It has 31 flat labels; no parent/group hierarchy was present in the returned label list. The mapping below is a proposal only. **No mappings have been applied in CVAT.** Original YOLO IDs and names are unchanged. “Exact” refers to semantic label equivalence; every model prediction still requires human review.

| YOLO ID | Original YOLO class | Proposed CVAT label | Semantically exact? | Manual review? | No matching label? | Notes |
|---:|---|---|---|---|---|---|
| 0 | `person` | `person` | Yes | Yes | No | Known geometry mismatch: checkpoint boxes may extend below the waist while intended `person` geometry is upper-body. Correct boxes manually. |
| 1 | `face` | `face` | Yes | Yes | No | Exact label. |
| 2 | `portrait_frame` | `portrait_frame` | Yes | Yes | No | Exact label. |
| 3 | `boobs` | `boobs` | Yes | Yes | No | Exact label. |
| 4 | `ass` | `ass` | Yes | Yes | No | Exact label. |
| 5 | `pussy` | `pussy` | Yes | Yes | No | Exact label. |
| 6 | `legs` | `legs` | Yes | Yes | No | Exact label. |
| 7 | `action_event` | — | No | Yes | Yes | No matching project label. |
| 8 | `pussy_cover_item` | `pussy_cover_item` | Yes | Yes | No | Exact label. |
| 9 | `ass_cover_item` | `ass_cover_item` | Yes | Yes | No | Exact label. |
| 10 | `boobs_cover_item` | `boobs_cover_item` | Yes | Yes | No | Exact label. |
| 11 | `leg_cover_item` | `leg_cover_item` | Yes | Yes | No | Exact label. |
| 12 | `location_home` | `location_home` | Yes | Yes | No | Exact label. |
| 13 | `location_class` | `location_class` | Yes | Yes | No | Exact label. |
| 14 | `location_office` | `location_office` | Yes | Yes | No | Exact label. |
| 15 | `location_bathroom` | `location_bathroom` | Yes | Yes | No | Exact label. |
| 16 | `location_bar` | `location_bar` | Yes | Yes | No | Exact label. |
| 17 | `location_outdoor` | — | No | Yes | Yes | `location_park` and `location_beach` are narrower; neither is an exact equivalent. |
| 18 | `location_bed` | — | No | Yes | Yes | No matching project label. |
| 19 | `fullbody_shower` | `fullbody_shower` | Yes | Yes | No | Exact label. |
| 20 | `fullbody_maid` | `fullbody_maid` | Yes | Yes | No | Exact label. |
| 21 | `fullbody_nurse` | `fullbody_nurse` | Yes | Yes | No | Exact label. |
| 22 | `fullbody_uniform` | `fullbody_uniform` | Yes | Yes | No | Exact label. |
| 23 | `fullbody_athletic` | `fullbody_athletic` | Yes | Yes | No | Exact label. |
| 24 | `fullbody_swim` | `fullbody_bikini` | No | Yes | No | User previously selected this target for a small CVAT test. The source class is broader; manually correct non-bikini swimsuit cases. Not applied. |
| 25 | `fullbody_lingerie` | `fullbody_underwear` | No | Yes | No | User previously selected this broader target. Verify each prediction. Not applied. |
| 26 | `fullbody_work` | `fullbody_work` | Yes | Yes | No | Exact label. |
| 27 | `fullbody_casual` | `fullbody_clothed` | No | Yes | No | User previously selected this broader target. Verify each prediction. Not applied. |
| 28 | `accessory_footwear` | `accessory_footwear` | Yes | Yes | No | Exact label. |
| 29 | `fullbody_topless` | — | No | Yes | Yes | No matching project label; do not merge with `fullbody_bare`. |
| 30 | `fullbody_bottomless` | — | No | Yes | Yes | No matching project label; do not merge with `fullbody_bare`. |
| 31 | `fullbody_bare` | `fullbody_bare` | Yes | Yes | No | Exact label; keep distinct from `person` and outfit/state classes. |

## Live CVAT project labels

IDs and names returned by the project label API:

| Label ID | CVAT label |
|---:|---|
| 8753461 | `person` |
| 8753462 | `face` |
| 8753463 | `portrait_frame` |
| 8753464 | `boobs` |
| 8753465 | `ass` |
| 8753466 | `pussy` |
| 8753467 | `legs` |
| 8753468 | `boobs_cover_item` |
| 8753469 | `pussy_cover_item` |
| 8753470 | `ass_cover_item` |
| 8753471 | `leg_cover_item` |
| 8753472 | `accessory_footwear` |
| 8753473 | `fullbody_shower` |
| 8753474 | `fullbody_maid` |
| 8753475 | `fullbody_nurse` |
| 8753476 | `fullbody_uniform` |
| 8753477 | `fullbody_athletic` |
| 8753478 | `fullbody_swimsuit` |
| 8753479 | `fullbody_bikini` |
| 8753480 | `fullbody_work` |
| 8753481 | `fullbody_clothed` |
| 8753482 | `fullbody_bare` |
| 8753483 | `fullbody_underwear` |
| 8753484 | `location_class` |
| 8753485 | `location_office` |
| 8753486 | `location_bathroom` |
| 8753487 | `location_bar` |
| 8753488 | `location_park` |
| 8753489 | `location_beach` |
| 8755131 | `location_clinic` |
| 8755160 | `location_home` |

## Project-only labels

These seven CVAT labels have no same-name source class in the checkpoint: `fullbody_swimsuit`, `fullbody_bikini`, `fullbody_clothed`, `fullbody_underwear`, `location_park`, `location_beach`, and `location_clinic`. The proposed mappings from `fullbody_swim`, `fullbody_lingerie`, and `fullbody_casual` are broader/non-exact and must remain manually reviewed. They have not been applied.

## Unmatched checkpoint classes

`action_event`, `location_outdoor`, `location_bed`, `fullbody_topless`, and `fullbody_bottomless` have no exact matching project label. No automatic substitute was selected.
