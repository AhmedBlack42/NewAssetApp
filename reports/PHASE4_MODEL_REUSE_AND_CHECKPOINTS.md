# Phase 4 model reuse and checkpoints — superseded by Phase 4B

The prior report described a separate portrait classifier. Phase 4B supersedes that architecture with one unified Body Images + Fullbody CNN initialization identity and one Clothing CNN identity. Checkpoint paths, hashes, and retained retired artifacts are documented in `PHASE4B_MODEL_CHECKPOINTS.md`. No checkpoint was trained or overwritten.

<!-- Historical Phase 4 text retained below for audit context. -->

No original checkpoint was edited or moved. This phase made one byte-for-byte copy inside NewAssetApp:

| Role | Path | SHA-256 | Result |
|---|---|---|---|
| Existing YOLO detector | `models/yolo/best.pt` | `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA` | Existing manifest digest; class IDs/names preserved |
| Existing Asset CNN source within NewAssetApp | `models/asset_classifier/asset_classifier.pth` | `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2` | Preserved |
| Portrait initialization copy | `models/portrait_classifier/asset_classifier_26class_initialization.pth` | `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2` | Hash matches source |

The source has a ResNet-18 backbone and a 26-output head. For a portrait task, the intended reuse is backbone initialization followed by a separate two-output head for `portrait` and `tportrait`. That head replacement is **specified only**; this copy still contains the original 26-class head and is not a portrait classifier. No forward pass was run.

The existing Asset CNN class IDs/map and original checkpoint remain available for broad review evidence. Existing YOLO checkpoint, names, and IDs remain as in `models/model_manifest.json`; YOLO 8–11 mark clothing coverage regions only. Future Fullbody state and validity models have no selected checkpoint. `data/models/phase4_model_registry.json` is explicit about each model’s task, version, checkpoint, classes, status, and review policy. An entry does not imply a trained model.

The model manifest was not repointed to the portrait copy: it remains a distinct initialization artifact, not an active production model. No dependencies were changed and no checkpoint was trained, fine-tuned, or replaced.
