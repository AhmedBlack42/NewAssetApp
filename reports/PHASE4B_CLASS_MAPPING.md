# Phase 4B class mapping

## Original Asset CNN provenance

The immutable original class map has 26 IDs, in order: `bodypart_ass`, `bodypart_boobs`, `bodypart_face`, `bodypart_legs`, `bodypart_portrait_clothed`, `bodypart_portrait_topless`, `bodypart_pussy`, `bra`, `dress`, `footwear`, `fullbody_clothed_states`, `fullbody_costume_states`, `fullbody_nude_states`, `outerwear`, `pants`, `panty`, `pantyhose`, `shirt`, `shorts`, `skirt`, `socks`, `special_wear`, `stockings`, `sweater`, `utility_cover`, `vest`.

## Unified CNN outputs

Body Images has 8 outputs. Source IDs 0–3 retain their names. Source ID 4 `bodypart_portrait_clothed` maps to `portrait`; source ID 5 `bodypart_portrait_topless` maps to `tportrait`; source ID 6 retains `bodypart_pussy`; new output ID 7 `bodypart_cum` has no legacy source checkpoint ID. The explicit mapping is `0→0`, `1→1`, `2→2`, `3→3`, `4→4 (renamed)`, `5→5 (renamed)`, `6→6`, plus new class 7.

Fullbody has exactly 3 new state outputs: ID 0 `clothed`, ID 1 `topless`, ID 2 `bottomless`. Legacy IDs 10–12 (`fullbody_clothed_states`, `fullbody_costume_states`, `fullbody_nude_states`) are provenance only and are not equated to these states.

The single unified model has 11 grouped output logits. Training text files and one machine-readable registry define each group independently. YOLO remains exactly 32 classes. Clothing remains exactly the original 26 Asset CNN classes and ordering, with application role `clothing_classifier`.

See `data/models/unified_body_images_fullbody/class_registry.json`, `data/models/clothing_classifier_registry.json`, and `models/asset_classifier/asset_class_map.json`.
