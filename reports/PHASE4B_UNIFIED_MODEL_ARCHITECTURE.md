# Phase 4B unified model architecture

**Status: Implemented as an application and dataset architecture; all CNN task heads remain untrained.** The registry has exactly three entries: YOLO detector, one unified Body Images + Fullbody CNN, and one Clothing CNN.

| Component | Identity | Responsibility | State |
|---|---|---|---|
| Detector | `yolo_detector` | Original 32-class detection proposals and boxes | Existing checkpoint and class IDs preserved |
| Unified CNN | `unified_body_images_fullbody_cnn` | Body Images 8-class output group and Fullbody 3-state output group | One initialization checkpoint identity; revised heads not installed or trained |
| Clothing CNN | `clothing_classifier` | Existing 26-class Asset CNN for broad clothing-family evidence | Original class map/order and checkpoint retained; detailed tag is human-selected |

The unified ResNet-18 has one model identity, one coordinated training pipeline, and one checkpoint package. Its grouped outputs total 11 logits (8 + 3). Body Images and Fullbody examples share a dataset identity but use separate task paths. Existing portrait and Fullbody registrations are retired metadata, not active models. The old portrait initialization copy is retained for provenance.

YOLO region classes 8–11 route to Clothing crop proposals; the CNN's original 26-class probability vector remains intact while the application limits its broad-family selection to garment labels. It does not set a final detailed Clothing tag. YOLO body-region crops remain review-only candidate evidence.

`bodypart_cum` is a model evidence class. `cum` and `creampie` are distinct, mutually exclusive human-selected sub-main values. Demonstrated supported output pairs are `boobs_cum` and `ass_creampie`; unsupported pairs are blocked per record. The grammar follows `<main>_<sub-main>-<ordinary-subtags><number>.webp`. The older guide's conflicting fluid serialization is recorded in the taxonomy audit.

No model was trained, no sample images were processed, and no dependency was changed.
