# NewAssetApp

Independent desktop application for image asset detection, review, and production.
Girl Packer is a read-only reference and is not imported by this project.

## Setup and launch

Install Python 3.11 x64 first. Then use the CPU-only PyTorch build selected for
the observed NVIDIA driver/hardware:

```powershell
cd 'F:\My Tools\New folder\NewAssetApp'
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
python model_setup.py copy yolo --source '..\Girl Packer1\ai\models\best.pt'
python model_setup.py copy asset_classifier --source '..\Girl Packer1\ai\models\asset_classifier.pth'
python model_setup.py download birefnet_general
python model_setup.py download birefnet_portrait
python model_setup.py download realesrgan_x2plus
python model_setup.py verify
python main.py
```

All Python dependencies are consolidated in `requirements.txt`. The PyTorch command
uses the official CPU wheel index. YOLO and Asset CNN checkpoints are project-owned
files with no verified public download; model_setup copies them from explicit local
paths and verifies their recorded sizes and SHA-256 hashes. BiRefNet and Real-ESRGAN
are optional model assets installed separately under this app's `models/` directory.

## Current application status

Implemented and covered by the current test suite: launcher, configuration/logging,
versioned SQLite migrations, recursive folder scan with content hashes, the
Normal Processing and Professional Review workspaces, manual detections/proposals,
YOLO bbox review and class correction, independent CNN task review records,
YOLO/Studio handoff, and dataset/Studio packaging workflows.

The implementation status is mixed rather than complete for every advertised UI
area. Use [the authoritative current status report](reports/CURRENT_PROJECT_STATUS.md)
for verified, partial, broken, blocked, and unverified features.

Actual GUI product maturity must not be inferred from unit tests alone. In the
latest live inspection, NewAssetApp opened at 1366x768 and showed working
Professional Review navigation, but automated screenshot capture returned
accessibility text without an image. No visual acceptance claim is made.

The database, logs, user-facing outputs, and Studio training-source bundles are
kept separately under `data/`, `logs/`, `output/`, and `training_source/`.
Original images are read-only.

## AI and review boundary

The app loads the copied local checkpoints when the user selects **Analyze new /
changed**. The active YOLO policy retains all 32 original IDs for provenance and
uses approved image-region classes. A raw `person` prediction becomes a human-review
proposal in **Others** with `asset_type=person`; its box is a person-region ROI for
future corruption-state CNN training, not a Fullbody classification. No corruption
state is inferred until a reviewer explicitly assigns one. Legacy Fullbody,
location, and `action_event` classes are excluded. Asset CNN predictions and
confidence remain visible review evidence. Fullbody main tag, normal / topless /
bottomless state, category, and final tag require a human decision.
Uncertain findings remain review proposals or go to `others`.

Use **Prepare Training Dataset** to choose YOLO, Asset CNN, or future Clothing CNN
exports, select all reviewed records or a source folder, choose split percentages
and seed, and reuse or reset the source-hash split assignments. Each export is a
unique Colab-ready ZIP with class map, manifest, README and report. Rejections and
unreviewed predictions do not become labels. The Clothing CNN export is a data
preparation format only; no dedicated model is trained.

Use **Export Studio source** to create a separate immutable import bundle from
current, human-confirmed, eligible training records. It copies each source image
once by hash and stores source-pixel boxes, task-specific model/registry identity,
original detector geometry, correction lineage, and reviewable exclusions in the
v4 manifest. It does not reuse ordinary exports, create dataset splits, or train a
model.

See [CURRENT_PROJECT_STATUS.md](reports/CURRENT_PROJECT_STATUS.md),
`reports/PHASE2_CLASSIFICATION_AND_TRAINING_ARCHITECTURE.md`,
`reports/CLOTHING_CNN_SPECIFICATION.md`, and
`reports/GOOGLE_COLAB_DATASET_PACKAGE_README.md`. The sample folder is a growing
source folder, not a fixed 44-image dataset.
