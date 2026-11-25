# Girl Packer runtime investigation

## Current live launch evidence

After the user launched Girl Packer, Windows process inspection identified:

| PID | Executable | Command line |
|---:|---|---|
| 6844 | `F:\My Tools\New folder\Girl Packer1\.venv_girlpacker\Scripts\python.exe` | the project venv interpreter running `Girl Packer1\main.py` |
| 9380 | `C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe` | child runtime executing the same `main.py` |

The venv is configured for Python **3.11.9, 64-bit AMD64**. Its base Python is present and working when inspected with the correct Windows access context. A prior sandbox-only attempt reported the base as missing because filesystem/process access was denied; that was not the actual live launch state.

The repository launcher `run_girlpacker.ps1` resolves `.venv_girlpacker\Scripts\python.exe`, runs `tools/verify_environment.py`, then launches `main.py`. `setup_girlpacker_env.ps1` names Python 3.11 and refuses to replace an existing broken venv. The app entry point is `main.py`; no `.bat`/`.cmd` or alternate app executable was found in the project. Project-local PowerShell launch/setup scripts were inspected. Start Menu shortcuts found in the checked locations were for Python, not Girl Packer. `conda` is not registered as the project launcher.

## Verified package versions

| Component | Version in the running project's environment |
|---|---|
| Python | 3.11.9 x64 |
| PyTorch | 2.0.1+cpu |
| torchvision | 0.15.2+cpu |
| Ultralytics | 8.0.186 |
| OpenCV import | 4.8.1 (`opencv-python` distribution 4.8.1.78) |
| PySide6 | 6.6.1 |
| Transformers | 4.44.2 |
| safetensors | 0.8.0 |
| timm / Kornia / einops | 1.0.30 / 0.7.4 / 0.8.1 |

The environment also has `opencv-python-headless` 4.11.0.86 alongside `opencv-python` 4.8.1.78. `pip check` passes, but two distributions provide the `cv2` namespace; NewAssetApp's single requirements file includes only `opencv-python==4.8.1.78` to avoid reproducing that overlap.

`tools/verify_environment.py` passed with CPU-only CUDA status, image encode/decode, imports, checkpoints, and AI service imports. `pip check` reported no broken requirements. No package was installed or upgraded during this phase.

## Python discovery

`py -0p` lists Python 3.15, 3.14, and 3.11; no Python 3.10 runtime is registered. The running app uses the verified Python 3.11.9 venv. Python 3.10 support is assessed separately from availability in `PYTHON_MODEL_COMPATIBILITY.md`.

## Boundaries

This is live process/runtime identity and dependency evidence. It does not prove model accuracy. CUDA is unavailable in the active PyTorch build; the loaded model tests ran on CPU. The desktop app remained open during the check; no settings or original project files were changed.
