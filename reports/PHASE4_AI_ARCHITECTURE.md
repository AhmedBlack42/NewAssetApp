# Phase 4 AI architecture — superseded by Phase 4B

This earlier architecture proposed separate Portrait and Fullbody CNN identities. Phase 4B supersedes that proposal. The current registry has one unified Body Images + Fullbody CNN (8 + 3 grouped outputs), one 26-class Clothing CNN, and the original 32-class YOLO detector. Retired portrait/fullbody identities remain provenance metadata only; the old portrait initialization copy is retained, not active.

See `PHASE4B_UNIFIED_MODEL_ARCHITECTURE.md` and `PHASE4B_CLASS_MAPPING.md` for current responsibilities, class counts, and mappings. No model training occurred.

<!-- Historical Phase 4 text retained below for audit context. -->

**Status:** Architecture and review boundaries documented. Sample inference is paused pending the three user decisions in `TAXONOMY_DECISIONS_REQUIRED.md`. No training or fine-tuning occurred.

## Model responsibilities

| Identity | Responsibility | State |
|---|---|---|
| `yolo_legacy_32` | Immutable object detections and original-coordinate boxes for reviewer evidence | Existing checkpoint and 32 IDs/names preserved |
| `asset_cnn_clothing_baseline` | Broad legacy 26-class evidence | Existing checkpoint/map preserved; not a detailed garment tagger |
| `clothing_detailed_v1` | Future selectable Clothing taxonomy classifier | Specification only; no checkpoint/head |
| `portrait_classifier_v1` | Distinguish exactly `portrait` and `tportrait` | Independent 26-class weight copy; two-class head not implemented |
| `fullbody_state_v1` | Exactly `clothed`, `topless`, `bottomless` | Future separate model; untrained |
| `fullbody_validity_v1` | Optional valid/invalid eligibility gate | Not selected; manual review remains |
| `body_images_tags_v1` | Structured main, sub-main, and ordinary subtags | Manual taxonomy review; no classifier |
| `location_classifier_v1` | Eight canonical location labels | Specification only; untrained |

## Clothing pipeline

YOLO IDs 8–11 (`pussy_cover_item`, `ass_cover_item`, `boobs_cover_item`, `leg_cover_item`) are coverage-region detections. Their original class, confidence, box, source hash, and model digest remain detection evidence. A future Clothing classifier receives a crop derived from each eligible detection, while the source image and unpadded detection box remain traceable. Padding parameters and crop hash belong in the derived crop record. None of these four YOLO names is a final Clothing tag. The existing Asset CNN may provide a separate broad suggestion; it cannot be relabeled as an individual garment. A future detailed classifier must output only selectable canonical Clothing values, then await a human choice.

## Other tasks and taxonomy boundaries

- Portrait keeps `portrait` and `tportrait` as separate semantic outputs. The current head remains the old 26-class head; a new two-class head is specified but not installed or trained.
- Fullbody state is a separate three-way mutually exclusive task. Old `fullbody_clothed_states`, `fullbody_costume_states`, and `fullbody_nude_states` are broad evidence only. State and validity are separate review concepts.
- Body Images persists `main_tag`, optional `sub_main_tag`, and ordered ordinary `subtags` independently. Per the Phase 4 task, `cum` and `creampie` are exposed as distinct sub-main choices and rejected from the ordinary subtag field. The game guide currently describes them as subtags; this conflict is recorded, and output serialization for fluid sub-main compositions is blocked until combinations/grammar are explicitly confirmed. No model assigns them automatically.
- Canonical locations are exactly `bathroom`, `bar`, `beach`, `park`, `home`, `pier`, `shoot_studio`, `class`. YOLO `location_home`, `location_class`, `location_bathroom`, and `location_bar` have direct candidates. `location_outdoor`, `location_office`, and `location_bed` remain unmapped pending explicit review; `location_outdoor` does not imply beach, park, or pier.

## Input, provenance, and review

Existing Asset CNN preprocessing is RGB, Resize(256), CenterCrop(224), tensor conversion, and ImageNet normalization. Detection/crop predictions are candidates only. The current correction dialog separates the reviewed category, category-specific main/sub-main/subtag controls, Clothing choice, and Fullbody state, and displays YOLO/CNN context. Original detection rows and snapshots are retained; corrections are appended separately. Do not expose controls that imply the future detailed, portrait, state, or location model is trained.

Future dataset splits use seed 42 and 80/10/10 train/validation/test proportions, grouped by original source-image SHA-256. Only explicitly human-confirmed and eligible records belong in a trusted dataset; rejected, uncertain, AI candidates, and pseudo-labels are excluded. Test sources are held out. Dataset output root is `data/datasets/phase4/`, independent of samples, model checkpoints, and final game output.

The correction dialog displays the raw YOLO class/score/source hash separately from an optional human-selected canonical location field, whose values are validated against the eight-location registry. No location prediction is auto-applied. Future classifier controls were not added.

See `data/models/phase4_model_registry.json` for machine-readable model identities and `PHASE4_MODEL_REUSE_AND_CHECKPOINTS.md` for weight provenance.
