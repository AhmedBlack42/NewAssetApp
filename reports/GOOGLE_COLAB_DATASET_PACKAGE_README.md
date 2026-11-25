# Google Colab dataset package guide

NewAssetApp writes one uniquely versioned directory and ZIP per export under the output folder chosen in the GUI. The package is self-contained and does not need either desktop app in Colab.

## Export types

- **YOLO detection:** `images/train|val|test`, matching `labels/train|val|test` (including empty text labels for explicitly confirmed no-object images), `data.yaml`, dense export `class_map.json`, source-hash `dataset_manifest.json`, `export_report.json`, and this Colab guide.
- **Asset CNN:** source-linked RGB crops arranged as `train|val|test/<one of the existing 26 CNN class labels>/`, with `labels.csv`, manifest, and README. Only explicit labels from the existing Asset CNN class map are accepted.
- **Future Clothing CNN:** RGB crops arranged by exact selectable Clothing taxonomy label. This is preparation only; no dedicated Clothing model is trained.

Every package includes version/time, source selection, source SHA-256 provenance, model/taxonomy versions where present, exclusions, class counts and split assignments. Export prompts to reuse the persisted hash-based splits or explicitly create a new split. Multiple crops and exact duplicates sharing a source hash stay in one split. Default split fractions are 80/10/10 with seed 42. Near-duplicate visual detection is not yet implemented.

## Upload / mount in Colab

1. Upload the ZIP through the Colab Files pane, or mount Drive and point `zip_path` to it.
2. Unzip it to a working directory and inspect `dataset_manifest.json` and `export_report.json` before training.
3. For YOLO, install `ultralytics` in the Colab runtime and pass the extracted `data.yaml` to the YOLO training API. Class IDs in YOLO labels are dense; `class_map.json` maps them back to original legacy IDs.
4. For either CNN dataset, read `labels.csv` and `dataset_manifest.json`; paths are relative to the package root and labels identify the reviewed taxonomy classes. Crops are RGB PNG. Apply a documented, versioned resize/normalization transform in the notebook.
5. Keep the manifest and resulting training code/checkpoint with the exported dataset version.

These packages include only human-confirmed, task-eligible examples. Unreviewed predictions are never ground truth. Rejections are excluded unless separately annotated by an explicit manual background annotation.
