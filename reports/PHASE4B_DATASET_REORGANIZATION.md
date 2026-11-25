# Phase 4B dataset reorganization

## Inventory and preservation

The pre-migration inventory records 4,548 files under `train_data` (480,657,994 bytes). A full hashed backup is at `reports/backups/train_data_pre_phase4b_20261107`; backup verification checked all 4,548 files with no missing files or hash mismatches. `reports/PHASE4B_SOURCE_PRESERVATION_VERIFICATION.json` records the original-tree check. Original data remains in place.

## Resulting layout

```text
train_data/
  unified_body_images_fullbody/
    classes/{body_images_classes.txt,fullbody_state_classes.txt,registry.json}
    train/{body_images,fullbody_state}/ val/{body_images,fullbody_state}/ test/{body_images,fullbody_state}/
    review/{legacy_body_images,legacy_fullbody_groups,yolo_candidates}/ manifests/
  clothing_classifier/
    classes/{classes.txt,registry.json}
    train/<26 empty class folders>/ val/<26 empty class folders>/ test/<26 empty class folders>/ review/ manifests/
  yolo/{images,labels}/{train,val,test}/ review_required/{train,val}/
    classes.txt class_registry.json dataset.yaml manifests/
  shared/{source_inventory.json,manifests/migration_manifest.json}
  cnn_train/ and YOLO_Project/  # preserved original sources
```

Original CNN data contains 3,203 files and YOLO source contains 1,345 files. Clothing examples were not copied, relabeled, or reorganized; its class tree is initialized empty for user review. 356 legacy Body Images examples and 490 legacy Fullbody broad-group examples were copied into `review/` only; their folder labels are not treated as confirmed ground truth. YOLO retains 652 valid source pairs (401 train, 251 val); one invalid pair is copied intact to `review_required`.

The migration manifest records source paths and hashes, split provenance, annotation boxes, crop hashes, review states, and eligibility. YOLO crops came from existing annotations, not fresh model inference. Nothing entered training folders as a confirmed example. The migration is guarded by backup verification, copy hashes, and validate-only mode.
