from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = APP_ROOT / "models" / "model_manifest.json"
MODELS_ROOT = APP_ROOT / "models"
CHUNK_SIZE = 1024 * 1024


def load_manifest():
    with MANIFEST_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path: Path, spec: dict) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    if path.stat().st_size == 0:
        return False, "empty file"
    if spec.get("size_bytes") is not None and path.stat().st_size != spec["size_bytes"]:
        return False, f"size mismatch: {path.stat().st_size} != {spec['size_bytes']}"
    expected_hash = spec.get("sha256")
    if expected_hash and sha256(path).lower() != expected_hash.lower():
        return False, "SHA-256 mismatch"
    return True, "verified" if expected_hash else "present; no published digest in manifest"


def safe_target(relative: str) -> Path:
    target = (APP_ROOT / relative).resolve()
    if target != MODELS_ROOT.resolve() and MODELS_ROOT.resolve() not in target.parents:
        raise ValueError(f"Model target must stay inside {MODELS_ROOT}: {relative}")
    return target


def download_resumable(url: str, target: Path, spec: dict, *, force: bool = False):
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "The requests package is required for model downloads; install requirements.txt first."
        ) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        valid, reason = verify_file(target, spec)
        if valid:
            print(f"Already present: {target} ({reason})")
            return
        if not force:
            raise RuntimeError(f"Existing target is invalid ({reason}); use --force: {target}")
        target.unlink()

    partial = target.with_name(target.name + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    with requests.get(url, headers=headers, stream=True, timeout=(30, 180)) as response:
        if response.status_code == 416:
            valid, reason = verify_file(partial, spec)
            if valid:
                partial.replace(target)
                print(f"Completed resumed file: {target}")
                return
            raise RuntimeError(f"Server rejected resume and partial file is invalid ({reason}): {partial}")
        response.raise_for_status()
        append = bool(offset and response.status_code == 206)
        if offset and not append:
            offset = 0
        mode = "ab" if append else "wb"
        with partial.open(mode) as stream:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())

    valid, reason = verify_file(partial, spec)
    if not valid:
        if reason == "SHA-256 mismatch" or reason.startswith("size mismatch"):
            partial.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file failed verification ({reason}): {url}")
    partial.replace(target)
    print(f"Downloaded and verified: {target}")


def download_model(model_id: str, *, force: bool = False):
    model = load_manifest()["models"].get(model_id)
    if not model:
        raise KeyError(f"Unknown model ID: {model_id}")
    if model_id in ("yolo", "asset_classifier"):
        raise RuntimeError(
            f"{model_id} is an existing project checkpoint with no verified public download URL. "
            "Use the copy command with an explicit source file."
        )
    if model_id in ("birefnet_general", "birefnet_portrait"):
        repo, revision = model["repository"], model["revision"]
        for file_spec in model["files"]:
            url = f"https://huggingface.co/{repo}/resolve/{revision}/{file_spec['name']}"
            target = safe_target(model["target_directory"] + "/" + file_spec["name"])
            download_resumable(url, target, file_spec, force=force)
        return
    if model_id == "realesrgan_x2plus":
        download_resumable(model["url"], safe_target(model["target_path"]),
                           model["file"], force=force)
        return
    raise RuntimeError(f"No verified setup strategy exists for model {model_id}.")


def copy_model(model_id: str, source: Path, *, force: bool = False):
    manifest = load_manifest()["models"]
    model = manifest.get(model_id)
    if not model or model.get("source_kind") != "copy_existing_project_file":
        raise RuntimeError(f"{model_id} is not configured as an explicit local-copy model.")
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source model file does not exist: {source}")
    spec = model["file"]
    valid, reason = verify_file(source, spec)
    if not valid:
        raise RuntimeError(f"Source model failed manifest verification ({reason}): {source}")
    target = safe_target(model["target_path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        valid, reason = verify_file(target, spec)
        if valid:
            print(f"Already present: {target} (verified)")
            return
        if not force:
            raise RuntimeError(f"Existing target is invalid ({reason}); use --force: {target}")
    temporary = target.with_name(target.name + ".part")
    shutil.copyfile(source, temporary)
    valid, reason = verify_file(temporary, spec)
    if not valid:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Copied model failed verification ({reason}): {temporary}")
    temporary.replace(target)
    print(f"Copied and verified: {source} -> {target}")

    if model_id == "asset_classifier":
        class_map = model["class_map"]
        map_source = source.with_name("asset_class_map.json")
        if not map_source.is_file():
            raise FileNotFoundError(
                "Copy the matching asset_class_map.json beside the classifier checkpoint."
            )
        map_spec = {key: class_map[key] for key in ("size_bytes", "sha256")}
        valid, reason = verify_file(map_source, map_spec)
        if not valid:
            raise RuntimeError(f"Asset class map failed verification ({reason}): {map_source}")
        map_target = safe_target(class_map["target_path"])
        map_target.parent.mkdir(parents=True, exist_ok=True)
        map_temp = map_target.with_name(map_target.name + ".part")
        shutil.copyfile(map_source, map_temp)
        map_temp.replace(map_target)
        print(f"Copied and verified class map: {map_target}")


def verify_environment(require_all_models: bool = False) -> int:
    os.environ.setdefault("YOLO_CONFIG_DIR", str(APP_ROOT / "data" / "ultralytics"))
    imports = {
        "numpy": "numpy", "opencv": "cv2", "Pillow": "PIL", "PySide6": "PySide6",
        "torch": "torch", "torchvision": "torchvision", "ultralytics": "ultralytics",
        "transformers": "transformers", "safetensors": "safetensors", "timm": "timm",
        "kornia": "kornia", "einops": "einops", "requests": "requests", "PyYAML": "yaml",
    }
    import_results = {}
    for label, module in imports.items():
        try:
            loaded = importlib.import_module(module)
            import_results[label] = {"ok": True, "version": getattr(loaded, "__version__", None)}
        except Exception as exc:
            import_results[label] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    try:
        torch = importlib.import_module("torch")
        cuda = {"available": bool(torch.cuda.is_available()),
                "version": getattr(torch.version, "cuda", None)}
    except Exception as exc:
        cuda = {"available": False, "error": f"{type(exc).__name__}: {exc}"}

    all_models = load_manifest()["models"]
    model_results = {}
    for model_id, model in all_models.items():
        required = bool(model.get("required_for_ai_pipeline"))
        if require_all_models and model_id not in ("asset_classifier",):
            required = True
        if model_id in ("birefnet_general", "birefnet_portrait"):
            entries = [(file_spec["name"], safe_target(
                model["target_directory"] + "/" + file_spec["name"]), file_spec)
                for file_spec in model["files"]]
        elif model_id == "asset_classifier":
            entries = [("checkpoint", safe_target(model["target_path"]), model["file"]),
                       ("class_map", safe_target(model["class_map"]["target_path"]),
                        model["class_map"])]
        else:
            entries = [("checkpoint", safe_target(model["target_path"]), model["file"])]
        checks = []
        for name, path, spec in entries:
            valid, detail = verify_file(path, spec)
            checks.append({"file": name, "path": str(path), "ok": valid, "detail": detail})
        model_results[model_id] = {"required": required, "files": checks}

    report = {"python": sys.version, "executable": sys.executable,
              "cuda": cuda, "imports": import_results, "models": model_results}
    print(json.dumps(report, indent=2))
    missing_import = any(not item["ok"] for item in import_results.values())
    missing_model = any(
        model["required"] and any(not file["ok"] for file in model["files"])
        for model in model_results.values()
    )
    return 1 if missing_import or missing_model else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install and verify NewAssetApp model files.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List model roles and setup requirements")
    download = subparsers.add_parser("download", help="Download a pinned public model")
    download.add_argument("model", choices=["birefnet_general", "birefnet_portrait", "realesrgan_x2plus"])
    download.add_argument("--force", action="store_true")
    copy = subparsers.add_parser("copy", help="Copy and verify a local checkpoint")
    copy.add_argument("model", choices=["yolo", "asset_classifier"])
    copy.add_argument("--source", required=True, type=Path)
    copy.add_argument("--force", action="store_true")
    verify = subparsers.add_parser("verify", help="Check package imports and local model files")
    verify.add_argument("--all-models", action="store_true", help="Require optional background/upscale models too")
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            print(json.dumps(load_manifest(), indent=2))
            return 0
        if args.command == "download":
            download_model(args.model, force=args.force)
            return 0
        if args.command == "copy":
            copy_model(args.model, args.source, force=args.force)
            return 0
        if args.command == "verify":
            return verify_environment(args.all_models)
    except Exception as exc:
        print(f"Model setup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
