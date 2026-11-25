# Python and model compatibility

## Selected runtime for NewAssetApp

Use **Python 3.11.9 x64 with CPU PyTorch**. This is the user's working Girl Packer runtime and the only runtime in the available registry that was actually exercised for all copied models. No installation or upgrade was performed. NewAssetApp has one `requirements.txt`; its Ultralytics pin now matches the observed/tested 8.0.186 runtime.

## Model matrix

| Model | Exact contract/runtime tested | Result and limit |
|---|---|---|
| YOLO | `best.pt`, 32 ordered classes; Ultralytics 8.0.186, torch 2.0.1+cpu, torchvision 0.15.2+cpu, OpenCV 4.8.1; BGR image, native letterbox, source-pixel xyxy boxes. Checkpoint registry metadata says 8.3.204. | Strict class-name order loaded and 44-image inference succeeded in 8.0.186. Metadata/runtime version difference is documented; do not silently upgrade. |
| Asset CNN | ResNet-18 state dict, 26 outputs; torch 2.0.1+cpu, torchvision 0.15.2+cpu, Pillow 10.0.1; RGB, Resize(256), CenterCrop(224), ImageNet normalization. | Strict state-dict/class-map loading and 300 detection-crop predictions succeeded. Training-crop provenance and accuracy remain unverified. |
| BiRefNet general | Transformers 4.44.2, safetensors 0.8.0, timm 1.0.30, Kornia 0.7.4, einops 0.8.1, torch 2.0.1+cpu, torchvision 0.15.2+cpu. | Copied local checkpoint loaded strictly and produced original-size mask output on a synthetic fixture. Fixture output is not quality evidence. |
| BiRefNet portrait | Same shared runtime; pinned portrait config/code/checkpoint. | Strict local load and inference returned an original-size alpha output. Synthetic fixture mask was all zero, so only loader/shape execution passed; portrait quality needs real human-reviewed examples. |
| Real-ESRGAN x2plus | Custom RRDBNet x2plus (23 blocks); torch 2.0.1+cpu, NumPy 1.24.3, OpenCV 4.8.1. | Strict weights load and 2x synthetic in-memory inference succeeded. No sample was altered/upscaled. |
| GUI | PySide6 6.6.1 under Python 3.11.9 x64. | Imports in the active environment; NewAssetApp UI startup/interaction is not a model compatibility test. |

All five checkpoints were loaded/inferred using the copied NewAssetApp paths. Details and limitations are in `MODEL_AND_SAMPLE_SMOKE_RESULTS.json`.

## Python 3.10 assessment

Python 3.10 was not found by the Python launcher and was not runtime-tested. The selected PyTorch 2.0.1 / torchvision 0.15.2 pair has official Windows CPU/CUDA wheel artifacts for CPython 3.10; PySide6 6.6.1 publishes a Windows x64 `cp38-abi3` wheel; Ultralytics 8.0.186 is a `py3-none-any` wheel and declares Python >=3.8. These primary package artifacts support a technical expectation that 3.10 could run the selected stack, but BiRefNet/custom model inference on Python 3.10 remains unverified. Python 3.11.9 is preferred because it was directly tested across the complete stack.

Primary references: [PyTorch 2.0.1 previous-version commands](https://pytorch.org/get-started/previous-versions/), [official CPU wheel index](https://download.pytorch.org/whl/cpu/torch/), [PySide6 6.6.1 release files](https://pypi.org/project/PySide6/6.6.1/), [Ultralytics 8.0.186 release](https://pypi.org/project/ultralytics/8.0.186/). The later PyTorch 2.15 release removed Python 3.10 wheels, so a 3.10 environment would need to retain the selected 2.0.1 stack rather than upgrade to 2.15; see [PyTorch 2.15 release notes](https://pytorch.org/blog/pytorch-2-15-release-blog/).

## Hardware and environment choice

The verified environment reports `torch.cuda.is_available() == False`; all inference evidence is CPU-only. The machine's older 512 MiB NVS GPU is not used. There is no reason to introduce a second model environment: one Python 3.11.9 CPU environment loaded YOLO, Asset CNN, both BiRefNet variants, and Real-ESRGAN. Package installation remains a manual user step.

## Version discrepancy

The YOLO registry records checkpoint metadata version 8.3.204, but the live application environment and tested inference use Ultralytics 8.0.186. The checkpoint loaded and ran under 8.0.186 across the sample set. NewAssetApp pins the tested runtime and records the metadata discrepancy; changing to 8.3.204 requires a separately reviewed environment update and re-verification.
