# Phase 4 unresolved decisions

## User taxonomy review gate

These three Phase 4A items remain unanswered. Per that explicit instruction, no sample inference, crops, or image label datasets were prepared.

1. **Fullbody spelling:** Promote guide/model spelling `athletic` for new records and retain `atheletic` as a legacy read alias, or retain `atheletic`? Recommendation in the prior audit: promote `athletic`, preserving historical records and YOLO ID 23.
2. **Body Images subtags:** Keep combinations and order as entered by the reviewer, or define a compatibility/order table? Source material does not define combinations or ordering rules. Prior audit recommendation: preserve reviewer order and require explicit review.
3. **Clothing modifier parents:** Confirm exact parents for modifier groups `t-shirt`, `skirt`, `bra`, `panty`, `thigh-high-stockings`, `boots`, or keep them informational/unlinked? No approximate hierarchy was inferred.

4. **Body Images fluid hierarchy conflict:** The latest Phase 4B instruction defines `cum`/`creampie` as separate, mutually exclusive sub-main values and the `<main>_<sub-main>-...<number>.webp` grammar. NewAssetApp stores them separately. Only pairs demonstrated in source policy (`boobs_cum`, `ass_creampie`) serialize; unsupported pairs are blocked per record. The older guide describes a conflicting ordinary-subtag form, documented in the Phase 4B reports.

## Model architecture uncertainties

- Detailed Clothing class granularity must follow selectable canonical items and observed human-confirmed examples; broad Asset CNN labels cannot become fine tags.
- The unified model can reuse the copied ResNet-18 initialization; its grouped heads and training require a later approved training phase.
- Fullbody state is defined as three mutually exclusive semantic classes, but source crop policy remains open pending reviewed data.
- A separate valid/invalid Fullbody classifier is optional and not justified by current evidence; manual review is the current eligibility gate.
- `location_outdoor`, `location_office`, and `location_bed` have no safe direct mapping into the eight canonical classes. In particular, outdoor is not beach/park/pier.
- The current GUI supports human corrections, separate Body Images sub-main choice, and an optional canonical location choice beside raw YOLO evidence; no future-model controls were added that would imply untrained heads exist.

Training is prohibited until datasets, labels, and a training plan are reviewed and explicitly approved.
