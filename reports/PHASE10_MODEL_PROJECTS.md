# Phase 10 — model project definitions

**Design only.** No checkpoint was loaded, modified, copied, trained, or moved in this phase.

## A. YOLO detection model

### Verified current model identity

- `models/yolo/best.pt` is the current local detector. SHA-256 is `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA` (22,523,946 bytes), matching `models/model_manifest.json`.
- `models/model_manifest.json`, `data/models/yolo_class_policy.json`, `train_data/YOLO_Project/dataset/classes.txt`, and the preserved YOLO registry all list the original 32 ordered classes:

```text
0 person                 8 pussy_cover_item       16 location_bar          24 fullbody_swim
1 face                   9 ass_cover_item         17 location_outdoor      25 fullbody_lingerie
2 portrait_frame        10 boobs_cover_item       18 location_bed          26 fullbody_work
3 boobs                 11 leg_cover_item         19 fullbody_shower       27 fullbody_casual
4 ass                   12 location_home          20 fullbody_maid         28 accessory_footwear
5 pussy                 13 location_class         21 fullbody_nurse        29 fullbody_topless
6 legs                  14 location_office        22 fullbody_uniform      30 fullbody_bottomless
7 action_event          15 location_bathroom      23 fullbody_athletic     31 fullbody_bare
```

- **Verified:** No approved 31-class registry was found. The 31-label CVAT project was reported in Phase 7; it has non-equivalent/missing labels, and its proposed map was not applied.
- Source dataset `train_data/YOLO_Project/dataset/`: 402 train + 251 val complete image/label pairs. Migration manifest says 652 valid active pairs and one quarantined invalid pair. All semantic labels remain pending human review per reports.
- `train_data/yolo/` is not the same valid package: 683 train images, 401 train labels, no val images, 251 val labels, and an inconsistent `classes.txt` (29 names + 3 blank lines versus a 32-class registry). Treat as blocked staging.
- `cvat_agent/func.py` is a native CVAT detection function using the existing YOLO checkpoint, emitting rectangle labels by the checkpoint class IDs/names. Phase 7 reports function registration and one-image local inference but no live project inference or corrected-annotation round trip.

### Proposed new model project

The project should own a versioned exact registry, separate from the original model registry. Each annotation is a class ID plus one source-coordinate box, serialized to normalized YOLO `xywh` at packaging. Sidecars/manifests retain original source IDs, hashes, reviewer history, exclusion reasons, and the mapping to any source model class.

**Starting weights recommendation:** Keep the 32-class checkpoint identity unchanged. First approve the new 31 target IDs/order. Then build the target detector architecture with exactly 31 output classes and deliberately transfer only compatible pretrained weights. Current Ultralytics documentation describes transferring compatible pretrained weights and reinitializing class-count-dependent output layers; current project runtime references Ultralytics 8.0.186 while checkpoint metadata reports 8.3.204, so the exact transfer behavior must be validated under the package’s pinned version and logged. For class-name overlaps, use a reviewed name-to-name mapping only; initialize newly introduced or semantically changed class outputs fresh. Verify the instantiated model’s `nc`, output tensor shapes, registry hash, and transfer summary before any Colab training. Editing `data.yaml` alone cannot change the old checkpoint’s learned head/class identity.

**Requires user decision:** the full 31-class target registry and exact mapping to original checkpoint IDs. Until then, do not emit target labels, train, or promise compatible weights. If the final task intentionally discards old classes, document the resulting retained-class evaluation limits and consider retaining old classes in a baseline/holdout evaluation project.

## B. Clothing CNN

### Verified taxonomy and dataset

The exact current 12-class registry/order is:

```text
0 bra       1 dress       2 footwear       3 lingerie
4 outerwear 5 pants       6 panty          7 shirt
8 shorts    9 skirt      10 socks         11 top
```

`top` and `lingerie` are separate from `shirt` and `bra`; `sweater` is not in the 12-class registry. Current `train_data/clothing_classifier/` has 2,328 active images, split 1,860 train / 234 val / 234 test. Per split counts are:

| Class | Train | Val | Test |
|---|---:|---:|---:|
| bra | 139 | 18 | 18 |
| dress | 244 | 31 | 31 |
| footwear | 162 | 20 | 20 |
| lingerie | 110 | 14 | 14 |
| outerwear | 68 | 8 | 8 |
| pants | 115 | 15 | 15 |
| panty | 191 | 24 | 24 |
| shirt | 227 | 28 | 28 |
| shorts | 99 | 13 | 13 |
| skirt | 259 | 33 | 33 |
| socks | 107 | 13 | 13 |
| top | 139 | 17 | 17 |

Duplicate handling is present in `review/duplicate_quarantine`; the split manifest uses exact content hashes but explicitly has no source-photograph grouping. The manifest status is a split/migration status, not human confirmation of every class.

### Checkpoint and training status

- `models/clothing_classifier/clothing_classifier.pth` is an unchanged copy of the 26-class Asset Classifier checkpoint (SHA-256 `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2`). It is not 12-class-compatible.
- The metadata/inference code expects `models/clothing_classifier/clothing_classifier_12class.pth`, with metadata `class_count=12` and exact ordered names. That file is absent; the current CNN inference is intentionally disabled without it.
- `data/models/clothing_classifier_12class_map.json` matches the 12-class order. The project registry status is `not_trained_dataset_review_blocked`.
- Legacy training script `train_data/cnn_train/ai/cnn/cnn_model.py` derives class IDs by sorting folders, constructs an ImageNet-pretrained ResNet-18, trains only train/val, saves a bare `state_dict`, and has no test evaluation, source-group split manager, immutable registry binding, or current 12-class export integration. It is a historical reference, not a safe Studio trainer as-is.

### Proposed Clothing Studio adapter

Use one exact 12-class map, pinned into a registry hash. Review crop labels with image-grid correction; only human-confirmed single labels enter train/val/test. Consider source-group-aware splits only when parent provenance exists. The current filename-only examples cannot prove source groups; hash duplicates and perceptual-similarity warnings can reduce obvious leakage but do not establish family identity. Keep a dedicated unseen test set and report per-class metrics, confusion matrix, macro/micro measures, calibration/threshold policy, and dataset limits.

**Requires user decision:** whether these 2,328 existing folder examples are candidates for human verification in Studio or a new controlled import will replace them; what evidence/source relationship is sufficient for grouping.

## C. Asset Classifier CNN

### Verified original checkpoint and current architecture proposal

- Original checkpoint: `models/asset_classifier/asset_classifier.pth`, SHA-256 `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F04F210AE6D2`, 44,839,755 bytes.
- The exact original 26-class order is recorded in `models/model_manifest.json` and `models/asset_classifier/asset_class_map.json`:

```text
0 bodypart_ass               7 bra                     14 pants
1 bodypart_boobs             8 dress                   15 panty
2 bodypart_face              9 footwear                16 pantyhose
3 bodypart_legs             10 fullbody_clothed_states 17 shirt
4 bodypart_portrait_clothed 11 fullbody_costume_states 18 shorts
5 bodypart_portrait_topless 12 fullbody_nude_states    19 skirt
6 bodypart_pussy            13 outerwear               20 socks
21 special_wear  22 stockings  23 sweater  24 utility_cover  25 vest
```

- The proposed unified registry currently defines one ResNet-18 identity with a Body Images 4-logit head (`portrait`, `tportrait`, `bodypart_cum`, `bodypart_acc`) and Fullbody State 3-logit head (`clothed`, `topless`, `bottomless`). Its record says the backbone is reused and both heads are reinitialized. `models/unified_body_images_fullbody/asset_classifier_initialization_26class.pth` is hash-identical to the original 26-class source, so it is an initialization backbone source, not a trained 7-logit artifact.
- Legacy fullbody categories 10–12 are explicitly recorded as having no safe equivalence to the three-state head.
- Current NewAssetApp inference only implements YOLO plus optional 12-class Clothing. There is no verified unified Body Images/Fullbody runtime model implementation, no model-output state checkpoint, and no training loop for its proposed heads in the inspected project.
- Unified dataset registry does not include the human main tags `face`, `boobs`, `ass`, `pussy`, `legs` as model classes. Body Images tags `cum`, `creampie`, and `bb` are taxonomy values/pairs, not CNN classes. `bodypart_cum` and `bodypart_acc` are broad evidence outputs. Preserve this distinction.

### Architecture options

| Option | Advantages | Risks / costs |
|---|---|---|
| One shared ResNet-18 trunk with two task-specific heads (current registry proposal) | Reuses one backbone; separate compact class spaces; one artifact/runtime; can transfer the verified original trunk while reinitializing both heads. | Task imbalance and gradient interference; needs explicit task sampling, per-head loss/metrics, and a task key at inference; Body Images and Fullbody data may have different visual distributions. |
| One independent CNN/checkpoint per task head | Independent class maps, training cadence, review thresholds, and failure isolation; simpler data balancing/evaluation. | Duplicates storage/backbones/inference cost and training dependencies; less shared feature learning; two model identities to package and deploy. |
| Flat single 7-class output | Superficially simple. | Incorrectly conflates incompatible label spaces (e.g. Body Images `portrait` and Fullbody `topless`); not recommended. |

**Recommendation (proposed):** preserve the existing registry’s multi-head concept: shared ResNet-18 feature trunk plus independently defined Body Images and Fullbody-state heads, with one model version and explicit `head_key` in every sample. Train using a balanced per-task sampler and separate class-weighted losses only after dataset sufficiency is reviewed. Save a checkpoint bundle containing trunk + both heads + architecture version + exact head maps + preprocessing + source initialization hash. NewAssetApp integration must load only a fully verified bundle and remain opt-in until inference is separately tested.

This recommendation does not finalize the Body Images four classes. Keep the existing registry as a proposal and request approval after auditing the 546 unmanifested active-path files and reviewing candidate availability.

## Model release and integration gates

For every model project, Studio finalization should bind the architecture ID/version, task/head names, exact class IDs and ordered names, preprocessing, dataset version/hash, source checkpoint identity/hash, weight transfer/reinitialization report, training script/config hash, validation/test report, framework versions, training seed, and expected inference output schema. Google Colab training remains a user-triggered operation. A trained checkpoint is downloaded with its metadata and imported into NewAssetApp only through a later explicit, read-only-verifiable integration step; Studio itself must not overwrite a NewAssetApp model.
