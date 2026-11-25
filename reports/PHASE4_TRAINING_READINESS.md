# Phase 4 training readiness — superseded by Phase 4B

The earlier Phase 4 readiness report predates the authorized `train_data` reorganization and used separate-model assumptions. Current counts and review status are in `PHASE4B_TRAINING_READINESS.md`. No model training has started.

<!-- Historical Phase 4 text retained below for audit context. -->

**Overall: NOT READY.** No sample inference or image processing ran because taxonomy review remains pending. Trusted example counts are therefore zero for this phase; class shortages and imbalance cannot yet be assessed.

| Future task | Classes | Trusted examples prepared | Readiness |
|---|---|---:|---|
| Detailed Clothing | Selectable, non-review Clothing taxonomy entries | 0 | Not ready; taxonomy parent decisions and human labels required |
| Portrait | `portrait`, `tportrait` | 0 | Not ready; two-class head is not implemented; labels required |
| Fullbody state | `clothed`, `topless`, `bottomless` | 0 | Not ready; exact crop definition and labels required |
| Fullbody validity | `valid`, `invalid` if justified | 0 | Not selected; continue manual eligibility review |
| Body Images | Structured main/sub-main/subtags | 0 | Not a model dataset; compatibility/order review pending |
| Location | `bathroom`, `bar`, `beach`, `park`, `home`, `pier`, `shoot_studio`, `class` | 0 | Not ready; labels required and several YOLO classes unresolved |

No class can be declared sufficient. No metrics, held-out accuracy, calibration, or class balance are available. Do not train or select models from these zero-count records. After the taxonomy review, process samples into a review queue, collect human-confirmed labels, freeze crop/input specifications, split by source SHA-256, then prepare an independently reviewed training plan. Keep test sources unavailable to training/model selection.
