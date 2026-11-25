# NewAssetApp runtime isolation and model verification

**Verification date:** 2026-11-06. **Runtime:** `F:\My Tools\New folder\NewAssetApp\.venv\Scripts\python.exe`.

## Interpreter and dependency checks

- The required interpreter exists and starts in the authorized execution context. It reports Python 3.11.9, 64-bit AMD64. The default restricted shell initially returned `No Python at C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe`; retrying the same NewAssetApp interpreter in the approved elevated execution context succeeded. No alternate interpreter was used.
- Verified package versions include torch 2.0.1+cpu, torchvision 0.15.2+cpu, PySide6 6.6.1, ultralytics 8.0.186, transformers 4.44.2, timm 1.0.30, kornia 0.7.4, einops 0.8.1, safetensors 0.8.0, opencv-python 4.8.1.78, Pillow 10.0.1, NumPy 1.24.3, requests 2.31.0, and PyYAML 6.0.1.
- CUDA is unavailable and the selected device is CPU. `python -m pip check` reported no broken requirements.
- Existing automated tests: **30 passed, 0 failed**, run through the exact interpreter above. The test harness printed `sys.executable` before discovery.
- Runtime `sys.path` contained no Girl Packer path. The launcher and application config point at NewAssetApp; data/database, output, logs, and model paths resolve under the NewAssetApp project root. NewAssetApp does not import Girl Packer modules or use its virtual environment. `Girl Packer` mentions in model provenance and taxonomy text are static references only.
- No packages were installed, upgraded, downgraded, or removed; `requirements.txt` was not changed.

## Checkpoints and loaders

`model_setup.py verify --all-models` checked every declared model file under NewAssetApp and all expected size/SHA-256 values matched. No downloads were performed.

| Model | Evidence | Result |
|---|---|---|
| YOLO `models/yolo/best.pt` | Loaded by the application `ImageAssetAnalyzer` through Ultralytics 8.0.186. Exact 32 ID/name registry matched `data/models/yolo_class_policy.json`; SHA-256 `57449664aa24427c703770ae155a361da252f26be4840242aae95f3017df58ea`. Active legacy crop IDs remain 1–6, 8–11, and 28 under the current review policy. | **Loaded successfully on CPU.** No image inference was run in this model-loading check. |
| Asset CNN `models/asset_classifier/asset_classifier.pth` | Strict `load_state_dict(..., strict=True)` in `ImageAssetAnalyzer`; ResNet-18 with 26-output head. Exact ordered map loaded from the adjacent JSON; SHA-256 `eb1251dade9293098e327f3e708bf92f0c5fc09c272c6cddb0f4f04f210ae6d2`. Preprocessing verified as RGB/Resize 256/CenterCrop 224/ToTensor/ImageNet normalization. | **Loaded successfully on CPU.** This confirms tensor compatibility, not classification quality. |
| BiRefNet general | Local implementation/config and 884,878,856-byte `model.safetensors` are inside `models/birefnet/general`. `AutoModelForImageSegmentation.from_pretrained(local_path, trust_remote_code=True, local_files_only=True)` loaded the local custom `BiRefNet` class and 220,176,498 parameters on CPU. Transformers, torch, torchvision, timm, kornia, einops, safetensors, OpenCV, and Pillow are present. | **Loaded successfully offline.** No segmentation inference was run. It is not currently wired into an application worker. |
| BiRefNet portrait | Corresponding implementation/config and checkpoint are inside `models/birefnet/portrait`; same local-only loader, 220,176,498 parameters on CPU. | **Loaded successfully offline.** No inference was run; not wired into an application worker. |
| Real-ESRGAN x2plus | Checkpoint `models/realesrgan/RealESRGAN_x2plus.pth` is inside NewAssetApp and passes the manifest hash check. NewAssetApp contains no RRDBNet implementation or checkpoint loader. The inspected legacy implementation is `Girl Packer1/tools/image_upscaler.py`, whose default checkpoint path resolves to Girl Packer; it was not executed or imported. Its implementation must be separately reviewed/ported before this NewAssetApp checkpoint can be used. | **Checkpoint present; NewAssetApp loading status unverified/not loadable through current app code.** This is a remaining implementation blocker, not a package-install issue. |

The Real-ESRGAN manifest entry describes an architecture and package set, but that is not an implementation or loader. The NewAssetApp dependency list includes the tensor/array packages used by the inspected legacy custom loader; no `realesrgan`, `basicsr`, `facexlib`, or `gfpgan` package is installed, and the inspected legacy custom implementation does not require them. No missing code or dependencies were repaired in this phase.

## Launcher verification

`run_app.bat` and `run_app.ps1` use the adjacent `.venv\Scripts\python.exe` directly, set `VIRTUAL_ENV`/prepend its Scripts directory, resolve paths from their own location, check `main.py` and Python startup, show failures, and never install packages.

- Controlled temporary-copy probes for both launchers correctly returned exit code 1 with understandable messages for missing `.venv`, missing `main.py`, and a non-starting placeholder `python.exe`.
- Both real launchers started the NewAssetApp process in `QT_QPA_PLATFORM=offscreen`: the batch launcher from the project root and the PowerShell launcher from a different working directory. Their child executable path was the NewAssetApp `.venv` interpreter. The app remained alive in its Qt event loop for the 10-second observation and initialized its NewAssetApp database/log paths. The processes were then stopped by the test harness.
- This is an offscreen startup check, **not** live desktop GUI acceptance. The app startup check did not scan or analyze images.

## Remaining runtime-gate blocker

Real-ESRGAN cannot yet be loaded by NewAssetApp because its implementation/loader is absent there. YOLO, Asset CNN, both local BiRefNet variants, package consistency, tests, and both launchers passed the checks above. No training, bulk image processing, sample-folder processing, or model download was performed.
