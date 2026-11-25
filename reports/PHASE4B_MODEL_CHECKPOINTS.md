# Phase 4B model checkpoints

| Role | NewAssetApp path | SHA-256 | Provenance/state |
|---|---|---|---|
| YOLO detector | `models/yolo/best.pt` | `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA` | Existing checkpoint, original 32-class registry |
| Unified Body Images + Fullbody initialization | `models/unified_body_images_fullbody/asset_classifier_initialization_26class.pth` | `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2` | Copy of original Asset CNN; initialization only, still has 26-class head |
| Clothing CNN | `models/clothing_classifier/clothing_classifier.pth` | `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2` | Copy of original Asset CNN, unchanged 26-class identity |
| Original Asset CNN | `models/asset_classifier/asset_classifier.pth` | `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2` | Preserved source checkpoint |
| Retired portrait initialization copy | `models/portrait_classifier/asset_classifier_26class_initialization.pth` | `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2` | Retained; superseded identity metadata, not active |

There is exactly one unified Body Images + Fullbody CNN checkpoint identity. Its revised 8- and 3-output heads are not yet present in a trained artifact. The Clothing copy remains the existing 26-class broad classifier. Original checkpoints were not moved or overwritten. No dependency changes or training occurred.
