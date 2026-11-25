# NewAssetApp training source

This folder is the handoff source for TrainingDatasetStudio. It is separate from
`output/` (user-facing processed images) and `train_data/` (legacy dataset
materials and earlier packages).

Use **Export Studio source** in NewAssetApp to create an immutable bundle under
`bundles/`. A bundle contains only current, human-confirmed, training-eligible
records, their task registries, source hashes, reviewed crop boxes, provenance,
and one verified copy of each referenced source image. Studio should crop or
annotate from those source images using the manifest; export filenames are not
used as labels.

Each export creates a new versioned bundle. Existing bundles are not overwritten.
New exports use `TrainingDatasetStudio/contracts/newassetapp_import_v3.schema.json`.
The v3 contract declares source-pixel box coordinates, task-specific targets,
registry versions, original model geometry, and retained exclusion payloads. The
earlier v2 bundle remains immutable and uses its original contract. No
train/validation split or model training occurs in this source export.
