# Phase 10 — Google Colab package specification

**Design only.** Studio prepares and packages finalized datasets. It does not launch Colab, upload data, or start training automatically.

## Package contract

Each archive is self-contained and portable: no Windows drive path, local database path, NewAssetApp install, open CVAT project, or network-mounted source is required to train. It contains the exact finalized data snapshot, registry/version, split manifest, integrity checks, scripts, configuration, pinned requirements, output metadata schema, and a copyable README. Keep private source paths out of the ZIP; use opaque source record IDs and hashes for provenance.

Proposed top-level common files:

```text
package_manifest.json
checksums.sha256
dataset_version.json
README_COLAB.md
requirements.txt
config/
  training.json
  registry.json
  split_manifest.json
  source_manifest.json
scripts/
  verify_package.py
  train.py
  validate.py
  evaluate.py
  export_checkpoint.py
  verify_checkpoint.py
reports/
  preparation_report.json
  review_coverage.json
  validation_report.json
```

The package manifest should include project/version ID, parent ID if any, task/model architecture version, dataset content hash, registry hash and exact ordered classes, head definitions, preprocessing, split algorithm/seed/ratios, example counts, excluded items with reasons, human review/finalization event IDs, source hash references, framework versions, script hashes, and a statement that no training was performed by Studio. Each file gets size + SHA-256. ZIP hash is reported outside or inside a detached checksum file; archive reproducibility policy (timestamps/ordering) must be specified if byte-identical rebuilds are required.

## A. YOLO package layout

```text
yolo_project_<version>/
  images/{train,val,test}/<opaque-source-key>.<ext>
  labels/{train,val,test}/<opaque-source-key>.txt
  data.yaml
  class_registry.json
  class_map_from_source.json       # if a prior model mapping was approved
  initial_weights/
    source_checkpoint.pt           # only if deliberately selected and hash-verified
    source_checkpoint.sha256
    target_initialization.pt       # only if derived and validated before package freeze
  config/training.json
  scripts/{verify_package.py,build_model.py,train.py,validate.py,evaluate.py,export.py,verify_checkpoint.py}
  manifests/{dataset.json,splits.json,source_groups.json,excluded.json,checksums.sha256}
  reports/{review_coverage.json,validation_report.json,transfer_report.json}
  requirements.txt
  README_COLAB.md
```

`data.yaml` uses a relative `path: .`, relative split paths, and the exact final ordered names. Annotation lines are YOLO detection `class_id cx cy width height` with normalized coordinates. `nc` must agree with the class registry and every annotation ID. Image/label basenames match exactly. Labeled-empty images have explicit empty text files and manifest state; missing labels are errors.

**Initial weights:** the original 32-class detector checkpoint is immutable source input. A 31-class target cannot be made compatible by changing the YAML. Only include it as a source initialization if the user approves a precise target mapping and a package-time transfer report verifies class-name mapping and target head shape under a pinned Ultralytics release. New/changed class outputs require deliberate initialization. Avoid publishing any derived target checkpoint until head class count/names and transfer report are validated. No approved target registry currently exists.

## B. Clothing CNN package layout

```text
clothing_project_<version>/
  dataset/{train,val,test}/<class_name>/<opaque-example-key>.png
  class_registry.json
  class_to_index.json
  initial_weights/
    source_asset_classifier_26class.pth    # only if selected and hash-verified
    source_checkpoint.sha256
  config/training.json
  scripts/{verify_package.py,build_model.py,train.py,validate.py,evaluate.py,export_checkpoint.py,verify_checkpoint.py}
  manifests/{samples.json,splits.json,source_groups.json,excluded.json,checksums.sha256}
  reports/{review_coverage.json,validation_report.json,evaluation.json}
  requirements.txt
  README_COLAB.md
```

The class map is fixed and contiguous: `{bra:0, dress:1, footwear:2, lingerie:3, outerwear:4, pants:5, panty:6, shirt:7, shorts:8, skirt:9, socks:10, top:11}`. It must be derived from the signed registry, not folder sorting. Preserve `top` and `lingerie`. Every image belongs to exactly one class and one split; unknown class folders are errors.

**Initial weights:** current `models/clothing_classifier/clothing_classifier.pth` is a 26-class legacy file, not a 12-class checkpoint. If approved, use only compatible ResNet-18 feature-trunk tensors, initialize a fresh 12-output layer, and include a strict transfer report; do not load its old final rows by position. Copy only weights with matching names/shapes after inspecting tensor metadata in the supported training environment. `lingerie` and `top` require class-specific outputs absent from that exact 26-name map; do not imply their old semantic mapping.

## C. Asset Classifier CNN package layout

```text
asset_classifier_project_<version>/
  dataset/{train,val,test}/<head_key>/<class_name>/<opaque-example-key>.png
  model_schema.json
  head_class_maps/
    body_images.json
    fullbody_state.json
  initial_weights/
    source_asset_classifier_26class.pth  # only if selected and hash-verified
    source_checkpoint.sha256
  config/training.json
  scripts/{verify_package.py,build_model.py,train.py,validate.py,evaluate.py,export_checkpoint.py,verify_checkpoint.py}
  manifests/{samples.json,splits.json,source_groups.json,excluded.json,checksums.sha256}
  reports/{review_coverage.json,validation_report.json,evaluation_by_head.json,transfer_report.json}
  requirements.txt
  README_COLAB.md
```

`model_schema.json` specifies model ID/version, backbone, preprocessing, and each independent output head. The current registry proposal is `body_images`: IDs 0–3 = `portrait`, `tportrait`, `bodypart_cum`, `bodypart_acc`; `fullbody_state`: IDs 0–2 = `clothed`, `topless`, `bottomless`. Each sample has exactly one `head_key` and one approved class ID in that head. A class ID in one head is never meaningful in the other head. Main tags/subtags/corruption values stay in the structured sample metadata and do not become targets unless a new architecture is approved.

**Initial weights:** the original 26-class ResNet-18 can be selected as a source for a shared feature trunk. Its `fc` is not compatible with the two proposed heads; the training script explicitly removes/reinitializes output heads. The downloaded package can include the unchanged source initialization and a deterministic, schema-checked `build_model.py`. It must label the resulting built model as a derived initialization, not an original checkpoint or trained model.

## Requirements and reproducibility

- Pin exact Python and package versions in a tested Colab-compatible requirements file; record CUDA/runtime information at training start. Keep YOLO runtime pins separate from PyTorch/torchvision CNN pins.
- Avoid a requirement set based only on NewAssetApp's Windows environment. Test package installation and all scripts in a clean Colab runtime before accepting the package builder.
- The scripts verify package checksums before loading data, verify exact registries, list per-class/per-split counts, and fail on unknown IDs, missing files, invalid boxes/crops, or mismatched head schemas.
- Training writes only to a fresh run directory. It must never overwrite the source initialization in the archive.
- `validate.py` evaluates against the finalized validation split; `evaluate.py` evaluates the held-out test split once, writes per-class metrics and a confusion matrix, and refuses to train on test data.
- `export_checkpoint.py` writes checkpoint + metadata only to a fresh output path; `verify_checkpoint.py` reloads it and checks architecture, output shapes, preprocessing, and exact class/head maps.
- Package README is complete and copyable: mount or upload ZIP, extract, run integrity verification, check map/count report, install pinned requirements, start training explicitly, validate/evaluate, locate checkpoint, download checkpoint plus metadata/reports, verify hashes, and follow a separate NewAssetApp integration procedure.
- The Studio UI states that the data in the archive may contain sensitive personal images. The user initiates any transfer to Google Colab and chooses the destination; Studio does not automatically upload it or place it in a shared/public bucket.

## Required Colab README sequence

1. Upload or mount the ZIP in a user-selected private Colab location.
2. Extract it into a fresh working directory.
3. Run `python scripts/verify_package.py --strict` and inspect class/count/split reports.
4. Install `requirements.txt` exactly; record Python/CUDA and package versions.
5. For transfer learning, run `build_model.py` and inspect the transfer report and output head dimensions.
6. Run `train.py` explicitly. Studio does not start this step.
7. Run `validate.py` and then `evaluate.py` on the held-out test split.
8. Run `export_checkpoint.py` and `verify_checkpoint.py`.
9. Download the checkpoint, registry/schema, preprocessing config, evaluation reports, and checksum manifest as one artifact bundle.
10. Keep the original checkpoint untouched. Follow a separate tested NewAssetApp integration guide; do not replace a live checkpoint until that later integration has a backup, compatibility check, and user approval.

## Current exporter delta

Existing `export_yolo_dataset`, `export_cnn_dataset`, and `export_unified_cnn_dataset` already create dataset ZIPs and manifests and hash/copy reviewed data. Current exporter READMEs are abbreviated; they do not provide complete training/validation/evaluation scripts or requirements. There is no verified 31-class target package; no 12-class Clothing checkpoint; no current unified multi-head training bundle; no finalized-version binding. The Studio package builder should reuse only validated domain logic after the current staging inconsistencies are resolved.
