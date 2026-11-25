# Phase 0 — Environment and model audit

Date: 2026-11-05

## Scope and isolation

The new application is at `F:\My Tools\New folder\NewAssetApp`, a sibling of
`F:\My Tools\New folder\Girl Packer1`. Inspection of Girl Packer was read-only.
No package was installed into either environment, no checkpoint was copied, and no
Girl Packer source/configuration/data was changed for this audit. The attempted
NewAssetApp dependency install from the preceding implementation turn was stopped;
its temporary Python 3.12 environment was removed because it did not match the
Python 3.11 model stack. NewAssetApp has no installed environment now.

## Existing Python environment

Girl Packer references `.venv_girlpacker` in its README and `run_girlpacker.ps1`.
The project root contains `.venv_girlpacker`; references to `.venv_recovery` and
`girlpacker_env` in older reports do not correspond to directories found at the
current project root. The configured venv is Python 3.11.9, and its `pyvenv.cfg`
points to `C:\Users\asker\AppData\Local\Programs\Python\Python311`. That base
executable is no longer available. Running the venv's own `Scripts\python.exe
--version` and `-m pip --version` returned:

`No Python at '"C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe"'`

The Python launcher reports `No installed Pythons found!`; the global `python`
shim reports 3.15.0 and was not used to inspect Girl Packer packages. Therefore,
the actual venv cannot currently perform package import checks, `pip check`, CUDA
queries through PyTorch, GUI startup, or model loading.

`reports/environment_inventory.json` contains the complete package list read from
the venv's installed `.dist-info/METADATA` files. It is a static on-disk inventory,
not proof those packages import. Metadata records pip 26.2.1, PyTorch 2.0.1,
torchvision 0.15.2, OpenCV packages 4.8.1.78 and 4.11.0.86, Pillow 10.0.1,
PySide6 6.6.1, and Ultralytics 8.0.186. The checkpoint registry records YOLO
checkpoint metadata 8.3.204, so 8.0.186 is a version mismatch risk. Both
`opencv-python` and `opencv-python-headless` distributions are installed in the
old venv and share the `cv2` namespace; do not carry both into the new requirements.
Current `pip check` and module import status are **unverified**. The previous
`docs/IMAGE_MODEL_INSTALLATION_REPORT.md` records successful CPU smoke tests and
imports on 2026-10-21, but that historical pass does not override today's broken
interpreter path.

## CUDA and hardware

The explicit NVIDIA utility reports **NVIDIA NVS 4200M**, driver **392.68**, and
**512 MiB**. The bundled PyTorch environment is not available to query
`torch.cuda.is_available()` now. The installed GPU/driver is not a suitable target
for the project's PyTorch 2.0.1 CUDA 11.x wheels; use CPU wheels. NVIDIA's CUDA 11.x
minor-compatibility floor is Windows driver 452.39, higher than the observed driver.
The PyTorch official previous-version command for 2.0.1/0.15.2 CPU wheels is
included below. [PyTorch's versioned installation instructions](https://docs.pytorch.org/get-started/previous-versions/)
list that matched pair; [NVIDIA documents the CUDA driver floor](https://docs.nvidia.com/deploy/cuda-compatibility/610/minor-version-compatibility.html).

## Model inventory and compatibility

All required reference files listed below exist in Girl Packer. They remain in place;
NewAssetApp does not depend on them after the user copies a verified checkpoint into
its own models directory.

| Model | Reference size and SHA-256 | Architecture / input | Need and licensing/source |
|---|---|---|---|
| YOLO `best.pt` | 22,523,946 bytes; `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA` | Ultralytics detector; registry lists 32 classes and checkpoint metadata 8.3.204; BGR H×W×3, native letterbox, source-coordinate boxes | Required. Custom project checkpoint; no verified public URL/license recorded. Copy later from project and verify hash. |
| Asset CNN `asset_classifier.pth` | 44,839,755 bytes; `EB1251DADE9293098E327F3E708BF92F0C5FC09C272C6CDDB0F4F210AE6D2` | ResNet-18, 26 classes; RGB crop, Resize 256, CenterCrop 224, ImageNet normalization | Required. Custom project checkpoint; no verified public URL/license recorded. Copy later with matching class map. |
| Asset class map | 596 bytes; `6AC9C2276686265F933C37832F909ADA87CC85337B3F16C33134B5DC571DECBE` | Exact 26-label-to-index map | Required companion file. Copy only with classifier and verify. |
| BiRefNet general | 884,878,856 bytes; `77277264c0e8c74149d3ff2fade4fd8176965b7108f3c5fc3b8c9c811edb4519` | BiRefNet, Swin V1 Large backbone; local app reference uses 512×512 CPU input and restores soft mask | Optional processing model. MIT. Official pinned repo `ZhengPeng7/BiRefNet`, revision `8b15dd17f7137e1057ccab224047ca276a1272d5`. |
| BiRefNet portrait | 884,878,856 bytes; `4a4eb3a5469b75f0cccaec6772c22fc30e6c12ed429c2c0ba71b43e3d8d97182` | BiRefNet portrait variant with same inference contract | Optional. MIT. Official pinned repo `ZhengPeng7/BiRefNet-portrait`, revision `af9eec4b221a103778489b51413c4778a48cd0a9`. |
| Real-ESRGAN x2plus | 67,061,725 bytes; `49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb` | Custom RRDBNet x2plus (23 RRDB blocks), tiled CPU inference; 1.5× via Lanczos after x2 | Optional. BSD-3-Clause in the project release record. Official v0.2.1 release URL is in the manifest. |

BiRefNet requires the pinned `config.json`, `BiRefNet_config.py`, `birefnet.py`,
`README.md`, and safetensors weights for each selected variant. The local model source
and code are available offline once these files are installed. Its runtime depends
on PyTorch/torchvision, Transformers, safetensors, timm, Kornia, einops, Pillow,
NumPy, and OpenCV. The project recorded a Kornia 0.8.3 TorchScript import failure
and verified 0.7.4. The Real-ESRGAN path is implemented in project code and does not
require the `realesrgan`, BasicSR, GFPGAN, or facexlib packages. The Action CNN is a
video-only model and is excluded from the image app.

The detector checkpoint was created with metadata 8.3.204 while the stale venv
metadata lists 8.0.186. The new requirements pin Ultralytics 8.3.204 to match the
checkpoint metadata. Actual checkpoint loading still requires verification after
the user builds the new Python 3.11 environment.

## Sample audit

The reference folder is spelled `smaples` in Girl Packer. Both that folder and
NewAssetApp's `samples/` contain 44 supported images, all JPEG. Filename and
SHA-256 comparison confirmed the corresponding 44 files match exactly. Read-only
inspection found no decode errors or exact duplicate groups within either set.
Dimensions: 920×1380 (11), 920×614 (10), 912×1358 (4), 920×518 (9), 920×1371 (3),
920×1381 (3), 920×1379 (4). The folder also contains 13 MP4s; the new scanner
ignores video extensions. These images are suitable for exercising scan, detection,
crop, and GUI paths, but have no ground-truth boxes/labels and cannot establish
classifier accuracy. The NewAssetApp scanner was run against both folders using
temporary databases: 44/44 images indexed from each, 0 duplicates, and 0 decode
errors. All sample files remained in place; no audit operation copied or modified
them.

## New application requirements

The sole dependency file is `requirements.txt`. It pins Python 3.11-compatible
versions for PySide6, NumPy, Pillow, one OpenCV distribution, CPU PyTorch/torchvision,
Ultralytics, BiRefNet runtime components, and model setup/export support. The file
does not include Girl Packer's video packages, VLC, qtawesome, `transparent-background`,
or the duplicate headless OpenCV package. Real-ESRGAN uses the existing architecture
implementation without a third-party ESRGAN package.

Model files are installed separately by `model_setup.py` using the central
`models/model_manifest.json`. Existing YOLO/CNN checkpoints are copied only from
explicit user-provided paths and checked by size/hash. Public BiRefNet files are
fetched from pinned Hugging Face revisions; Real-ESRGAN comes from the official
v0.2.1 release. Downloads use `.part` files, HTTP range resume where supported, and
manifest verification before atomic placement in NewAssetApp. Existing verified
files are skipped. No model has been downloaded or copied in this audit.

## Manual setup commands

The launcher currently reports no registered Python installations. Install Python
3.11 x64 first, then open PowerShell in the new app directory and run:

```powershell
cd 'F:\My Tools\New folder\NewAssetApp'
py -3.11 --version
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

BiRefNet and Real-ESRGAN are optional; skip their download commands to defer those
large files. `python model_setup.py verify --all-models` also requires the optional
weights. These commands are prepared for the user and were **not executed**.

## Outstanding checks / decisions

- Restore/install a Python 3.11 x64 interpreter before fresh-environment import or
  `pip check` validation. No decision on a CUDA build is needed for the observed
  NVS 4200M/driver; CPU is the supported choice here.
- After manual setup, verify YOLO 8.3.204 loads `best.pt` and Asset CNN state-dict
  matches the 26-class map. The current Girl Packer interpreter cannot prove this.
- No public source/license was recorded for the custom YOLO and Asset CNN weights;
  retain the user's project copy and confirm usage rights for any redistribution.
- Real sample inference and visual segmentation/upscale review remain for a later
  phase. Audit did not run any AI model or alter sample data.
