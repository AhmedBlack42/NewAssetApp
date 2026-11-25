from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .datasets import DatasetService, TASK_YOLO
from .store import StudioStore
from .importer import _approved_yolo_registry, sha256_file

SHARED_MODEL_ID = "unified_body_images_fullbody_cnn"
SHARED_TASKS = {"body_images_classification", "fullbody_state_classification",
                "portrait_classification", "arousal_classification", "corruption_classification"}


def _available_memory_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = MEMORYSTATUSEX(); status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except Exception:
            return None
    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except (ValueError, OSError, AttributeError):
        return None


def cpu_compatibility(task: str, model_id: str, checkpoint: Path | str | None,
                      dataset_dir: Path | str, output_dir: Path | str,
                      *, require_dataset: bool = True) -> dict:
    dataset_dir, output_dir = Path(dataset_dir), Path(output_dir)
    checkpoint_path = Path(checkpoint) if checkpoint else None
    cpus = os.cpu_count() or 1
    memory = _available_memory_bytes()
    disk = shutil.disk_usage(output_dir if output_dir.exists() else output_dir.parent).free
    is_yolo = task in TASK_YOLO
    is_shared = model_id == SHARED_MODEL_ID and task in SHARED_TASKS
    supported_architecture = (is_yolo and model_id == "newassetapp_yolo_detector_v1") or (
        not is_yolo and model_id == "clothing_classifier") or is_shared
    architecture = ("Ultralytics YOLO" if is_yolo else "Shared ResNet-18 with five task heads"
                    if is_shared else "ResNet-18 broad clothing classifier")
    required = ["torch"] + (["ultralytics"] if is_yolo else ["torchvision"])
    missing = []
    for name in required:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    cpu_torch = False
    torch_version = None
    try:
        import torch
        torch_version = str(torch.__version__)
        cpu_torch = torch.version.cuda is None
    except Exception:
        pass
    initialization_validation = None
    if is_shared:
        missing_checkpoint = False
        if checkpoint_path is not None:
            try:
                from .shared_training import load_verified_legacy_initialization
                _, initialization_validation = load_verified_legacy_initialization(checkpoint_path)
            except Exception as error:
                missing_checkpoint = True
                initialization_validation = {"valid": False, "error": str(error)}
    elif checkpoint_path is None or not checkpoint_path.is_file():
        missing_checkpoint = True
    else:
        missing_checkpoint = False
    if is_shared:
        train_dir = dataset_dir / "images" / "train"
        validation_dir = dataset_dir / "images" / "validation"
    elif is_yolo:
        train_dir = dataset_dir / "dataset" / "images" / "train"
        validation_dir = dataset_dir / "dataset" / "images" / "validation"
    else:
        train_dir = dataset_dir / "dataset" / "images" / "train"
        validation_dir = dataset_dir / "dataset" / "images" / "validation"
    train_images = sum(1 for path in train_dir.rglob("*") if path.is_file()) if train_dir.is_dir() else 0
    validation_images = sum(1 for path in validation_dir.rglob("*") if path.is_file()) if validation_dir.is_dir() else 0
    dataset_ok = (not require_dataset) or (dataset_dir.is_dir() and train_images > 0
                  and validation_images > 0 and (not is_yolo or (dataset_dir / "dataset.yaml").is_file()))
    shared_validation = None
    if is_shared and require_dataset:
        try:
            from .shared_training import validate_shared_dataset
            registry = json.loads((dataset_dir / "registry.json").read_text(encoding="utf-8"))
            shared_validation = validate_shared_dataset(dataset_dir, registry)
            dataset_ok = True
        except Exception as error:
            dataset_ok = False
            shared_validation = {"valid": False, "error": str(error)}
    dataset_bytes = (sum(path.stat().st_size for path in dataset_dir.rglob("*") if path.is_file())
                     if dataset_dir.is_dir() else 0)
    reasons = []
    if not supported_architecture:
        reasons.append("This model task has no verified local CPU training entry point; Colab export remains available.")
    if missing:
        reasons.append("Missing framework packages: " + ", ".join(missing))
    if not cpu_torch:
        reasons.append("Installed PyTorch build is not verified as CPU-only.")
    if missing_checkpoint:
        reasons.append("Select an existing compatible checkpoint before training.")
    if not dataset_ok:
        reasons.append("The finalized package needs nonempty train and validation splits and a valid task layout.")
    if cpus < 2:
        reasons.append("At least two logical CPU cores are recommended.")
    if memory is not None and memory < 2 * 1024**3:
        reasons.append("Available RAM is below the conservative 2 GiB minimum.")
    if disk < 2 * 1024**3:
        reasons.append("Available disk space is below the conservative 2 GiB minimum.")
    return {"compatible": not reasons, "task": task, "model_id": model_id,
            "architecture": architecture, "device": "cpu", "cpu_architecture": platform.machine(),
            "logical_cpu_cores": cpus, "available_ram_bytes": memory,
            "available_disk_bytes": disk, "python": sys.version.split()[0],
            "python_executable": sys.executable, "torch_version": torch_version,
            "cpu_only_torch": cpu_torch, "checkpoint": str(checkpoint_path) if checkpoint_path else None,
            "checkpoint_exists": not missing_checkpoint, "dataset_layout_valid": dataset_ok,
            "dataset_train_examples": train_images, "dataset_validation_examples": validation_images,
            "dataset_bytes": dataset_bytes,
            "shared_dataset_validation": shared_validation,
            "initialization_validation": initialization_validation,
            "reasons": reasons}


class TrainingManager:
    """Runs CPU-only model jobs out of process so the Qt event loop stays responsive."""

    def __init__(self, store: StudioStore, output_dir: Path | str,
                 python_executable: Path | str | None = None):
        self.store = store
        self.output_dir = Path(output_dir).resolve() / "training_runs"
        self.python_executable = str(python_executable or sys.executable)
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._cancel_path: Path | None = None

    def start(self, version_id: int, dataset_package: Path | str, model_id: str,
              checkpoint: Path | str | None, params: dict, *, confirmed: bool,
              dry_run: bool = False, callback: Callable[[str, str], None] | None = None) -> str:
        if not dry_run and not confirmed:
            raise ValueError("A real CPU training run needs explicit confirmation.")
        if self._thread and self._thread.is_alive():
            raise RuntimeError("A Studio training run is already active.")
        with self.store.connect() as db:
            version = db.execute("""SELECT dv.*,d.task,d.registry_id,d.registry_version,
                                         d.model_id
                                  FROM dataset_versions dv
                                  JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=?""",
                                 (int(version_id),)).fetchone()
        if not version or not version["finalized"]:
            raise ValueError("Select a finalized dataset version before training.")
        if version["task"] in TASK_YOLO:
            with self.store.connect() as db:
                registry_row = db.execute(
                    """SELECT payload_json FROM registries
                       WHERE registry_id=? AND version=? ORDER BY id DESC LIMIT 1""",
                    (version["registry_id"], version["registry_version"]),
                ).fetchone()
            try:
                registry = json.loads(registry_row["payload_json"]) if registry_row else None
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise ValueError("The finalized YOLO dataset registry is malformed.") from error
            if (version["registry_id"] != "newassetapp_yolo_detector_v1"
                    or registry != _approved_yolo_registry()):
                raise ValueError("Training is blocked because the finalized dataset does not use the approved Studio YOLO registry.")
        expected_model = str(version["model_id"] or "")
        if model_id != expected_model:
            raise ValueError("The training model does not match the finalized dataset model identity.")
        package_root = Path(dataset_package).resolve()
        package_manifest_path = package_root / "package_manifest.json"
        if not package_manifest_path.is_file():
            raise ValueError("Training requires a Studio package manifest bound to this finalized version.")
        try:
            package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("The training package manifest is unreadable.") from error
        if not self._verify_package_files(package_root, package_manifest):
            raise ValueError("The training package file hashes do not match its manifest.")
        if version["task"] in SHARED_TASKS:
            expected_version_ids = package_manifest.get("dataset_version_ids")
            shared_data_path = package_root / "shared_dataset.json"
            if (package_manifest.get("package_type") != "shared_five_head_cnn"
                    or package_manifest.get("model_id") != model_id
                    or package_manifest.get("registry_id") != version["registry_id"]
                    or package_manifest.get("registry_version") != version["registry_version"]
                    or not isinstance(expected_version_ids, dict)
                    or not shared_data_path.is_file()):
                raise ValueError("The shared training package has no dataset provenance manifest.")
            shared_data = json.loads(shared_data_path.read_text(encoding="utf-8"))
            dataset_provenance = shared_data.get("dataset_provenance") or {}
            required_heads = {"body_images", "fullbody", "portrait", "arousal", "corruption"}
            if set(expected_version_ids) != required_heads:
                raise ValueError("The shared package does not contain exactly the five authorized heads.")
            if (shared_data.get("model_id") != model_id
                    or shared_data.get("registry_id") != version["registry_id"]
                    or shared_data.get("registry_version") != version["registry_version"]):
                raise ValueError("The shared package identity does not match the finalized model.")
            matching_head = next((head for head, source_version_id in expected_version_ids.items()
                                  if int(source_version_id) == int(version_id)), None)
            if (matching_head is None
                    or int((dataset_provenance.get(matching_head) or {}).get("dataset_version_id", -1))
                    != int(version_id)):
                raise ValueError("The shared package does not contain this finalized head version.")
            expected_tasks = {
                "body_images": "body_images_classification",
                "fullbody": "fullbody_state_classification",
                "portrait": "portrait_classification",
                "arousal": "arousal_classification",
                "corruption": "corruption_classification",
            }
            expected_shared_records = []
            with self.store.connect() as db:
                for head, head_version_id in expected_version_ids.items():
                    head_row = db.execute(
                        """SELECT dv.finalized,d.task,d.registry_id,d.registry_version,d.model_id
                           FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id
                           WHERE dv.id=?""", (int(head_version_id),)
                    ).fetchone()
                    if (not head_row or not head_row["finalized"]
                            or head_row["task"] != expected_tasks[head]
                            or head_row["registry_id"] != version["registry_id"]
                            or head_row["registry_version"] != version["registry_version"]
                            or head_row["model_id"] != model_id):
                        raise ValueError("A shared package head is not bound to the same finalized model and registry.")
                    registry_row = db.execute(
                        """SELECT payload_json FROM registries
                           WHERE registry_id=? AND version=? ORDER BY id DESC LIMIT 1""",
                        (version["registry_id"], version["registry_version"]),
                    ).fetchone()
                    if not registry_row:
                        raise ValueError("The shared model registry is missing.")
                    if (json.loads((package_root / "registry.json").read_text(encoding="utf-8"))
                            != json.loads(registry_row["payload_json"])):
                        raise ValueError("The shared package registry differs from the Studio registry.")
                    for row in self.store.version_rows(int(head_version_id)):
                        if not row["included"]:
                            continue
                        annotation = row["annotation_snapshot"]
                        structured = (annotation.get("labels") or {}).get("structured") or {}
                        label = annotation.get("class_label") or row["class_label"]
                        target = annotation.get("target_class_id", row["target_class_id"])
                        relative_image = (
                            f"images/{row['split']}/{head}/"
                            f"{str(row['source_sha256'])[:16]}_{row['record_id']}.jpg"
                        )
                        expected_shared_records.append({
                            "record_id": str(row["record_id"]),
                            "task_head": head,
                            "class_label": label,
                            "target_class_id": int(target) if target is not None else None,
                            "source_sha256": row["source_sha256"],
                            "split": row["split"],
                            "image_path": relative_image,
                            "human_confirmed": True,
                            "training_eligible": True,
                            "human_confirmed_labels": structured.get("human_confirmed_labels", []),
                            **({"body_images_target_mask":
                                (annotation.get("body_images_target_mask")
                                 or structured.get("body_images_target_mask"))}
                               if head == "body_images"
                               and (annotation.get("body_images_target_mask")
                                    or structured.get("body_images_target_mask")) is not None else {}),
                        })
            packaged_records = shared_data.get("records")
            if not isinstance(packaged_records, list) or len(packaged_records) != len(expected_shared_records):
                raise ValueError("The shared package records differ from the finalized head snapshots.")
            expected_shared_records.sort(key=lambda row: (row["task_head"], row["record_id"]))
            packaged_records.sort(key=lambda row: (str(row.get("task_head")),
                                                    str(row.get("record_id"))))
            for expected, packaged in zip(expected_shared_records, packaged_records):
                if any(packaged.get(key) != value for key, value in expected.items()):
                    raise ValueError("The shared package records differ from the finalized head snapshots.")
                file_info = package_manifest.get("files", {}).get(expected["image_path"])
                if not file_info or packaged.get("sha256") != file_info.get("sha256"):
                    raise ValueError("A shared package crop hash is not covered by its package manifest.")
        else:
            if (package_manifest.get("dataset_version_id") != int(version_id)
                    or package_manifest.get("model_id") != model_id
                    or package_manifest.get("task") != version["task"]
                    or package_manifest.get("registry_id") != version["registry_id"]
                    or package_manifest.get("registry_version") != version["registry_version"]
                    or int(package_manifest.get("dataset_version", -1)) != int(version["version_number"])):
                raise ValueError("The training package is not bound to this exact finalized dataset version.")
            if not self._verify_dataset_provenance(version_id, package_root, package_manifest):
                raise ValueError("The package contents do not match the finalized dataset snapshot.")
        readiness_service = DatasetService(self.store, self.output_dir.parent)
        readiness_version_ids = (
            [int(value) for value in expected_version_ids.values()]
            if version["task"] in SHARED_TASKS else [int(version_id)]
        )
        blocked_versions = []
        for readiness_version_id in readiness_version_ids:
            readiness = readiness_service.version_readiness_report(readiness_version_id)
            if not readiness["ready_for_training"]:
                blocked_versions.append({
                    "version_id": readiness_version_id,
                    "blockers": readiness["blockers"],
                })
        if blocked_versions:
            raise ValueError(
                "Training is blocked until every selected dataset version meets minimum "
                f"source-group coverage and media integrity: {json.dumps(blocked_versions, sort_keys=True)}"
            )
        key = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S%fZ_") + uuid.uuid4().hex[:8]
        run_dir = self.output_dir / key
        run_dir.mkdir(parents=True, exist_ok=False)
        log_path = run_dir / "training.log"
        metadata_path = run_dir / "run_metadata.json"
        cancel_path = run_dir / "cancel.request"
        self._cancel_path = cancel_path
        compatibility = cpu_compatibility(version["task"], model_id, checkpoint,
                                          package_root, run_dir)
        if not compatibility["compatible"]:
            try:
                shutil.rmtree(run_dir)
            except OSError:
                pass
            raise ValueError("CPU training is unavailable: " + " ".join(compatibility["reasons"]))
        metadata = {"run_key": key, "dataset_version_id": int(version_id), "task": version["task"],
                    "registry_id": version["registry_id"], "model_id": model_id,
                    "checkpoint": str(checkpoint) if checkpoint else None, "device": "cpu", "params": params,
                    "dry_run": bool(dry_run), "compatibility": compatibility,
                    "created_at": datetime.now(timezone.utc).isoformat(), "status": "queued"}
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with self.store.connect() as db:
            db.execute("""INSERT INTO training_runs(run_key,version_id,model_id,checkpoint_path,device,
                         params_json,output_dir,status,log_path,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (key, int(version_id), model_id, str(checkpoint) if checkpoint else None, "cpu",
                        json.dumps(params, sort_keys=True), str(run_dir), "queued", str(log_path),
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True)))
        self._cancel.clear()
        self._thread = threading.Thread(target=self._run, args=(key, version["task"],
            package_root, Path(checkpoint) if checkpoint else None, params, run_dir, metadata, dry_run, callback,
            cancel_path),
            name="StudioTrainingRun", daemon=True)
        self._thread.start()
        return key

    @staticmethod
    def _verify_package_files(package_root: Path, manifest: dict) -> bool:
        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            return False
        expected_files = set(files)
        actual_files = {
            path.relative_to(package_root).as_posix()
            for path in package_root.rglob("*")
            if path.is_file() and path.name != "package_manifest.json"
        }
        if expected_files != actual_files:
            return False
        for relative, expected in files.items():
            path = package_root / relative
            if (not path.is_file()
                    or path.stat().st_size != int(expected.get("bytes", -1))
                    or sha256_file(path).casefold() != str(expected.get("sha256", "")).casefold()):
                return False
        return True

    def _verify_dataset_provenance(self, version_id: int, package_root: Path,
                                  package_manifest: dict) -> bool:
        metadata_path = package_root / "metadata.json"
        registry_path = package_root / "registry.json"
        if not metadata_path.is_file() or not registry_path.is_file():
            return False
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            package_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        with self.store.connect() as db:
            version = db.execute(
                """SELECT dv.version_number,d.task,d.registry_id,d.registry_version,d.model_id
                   FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id
                   WHERE dv.id=? AND dv.finalized=1""", (int(version_id),)
            ).fetchone()
            registry = db.execute(
                """SELECT payload_json,sha256 FROM registries
                   WHERE registry_id=? AND version=? ORDER BY id DESC LIMIT 1""",
                (package_manifest.get("registry_id"),
                 package_manifest.get("registry_version")),
            ).fetchone()
        if not version or not registry:
            return False
        identity = {
            "dataset_version_id": int(version_id),
            "dataset_version": int(version["version_number"]),
            "model_id": version["model_id"],
            "task": version["task"],
            "registry_id": version["registry_id"],
            "registry_version": version["registry_version"],
            "registry_sha256": registry["sha256"],
        }
        if any(metadata.get(key) != value or package_manifest.get(key) != value
               for key, value in identity.items()):
            return False
        if package_registry != json.loads(registry["payload_json"]):
            return False
        expected_records = []
        for row in self.store.version_rows(version_id):
            if not row["included"]:
                continue
            annotation = row["annotation_snapshot"]
            empty_yolo = (
                version["task"] in TASK_YOLO
                and annotation.get("empty_image") is True
                and annotation.get("class_label") == "__empty__"
                and annotation.get("labels", {}).get("structured", {}).get("no_objects") is True
                and annotation.get("bbox_xyxy") is None
                and annotation.get("target_class_id") is None
            )
            expected_records.append({
                "record_id": int(row["record_id"]),
                "source_sha256": row["source_sha256"],
                "split": row["split"],
                "class_label": annotation.get("class_label") or row["class_label"],
                "class_id": annotation.get("target_class_id", row["target_class_id"]),
                "bbox_xyxy": None if empty_yolo else annotation.get("bbox_xyxy"),
                "empty_image": empty_yolo,
            })
            if version["task"] == "body_images_classification":
                structured = (annotation.get("labels") or {}).get("structured") or {}
                expected_records[-1]["body_images_target_mask"] = (
                    annotation.get("body_images_target_mask")
                    or structured.get("body_images_target_mask")
                )
        return metadata.get("records") == expected_records

    def _run(self, key: str, task: str, dataset_package: Path, checkpoint: Path | None,
             params: dict, run_dir: Path, metadata: dict, dry_run: bool,
             callback: Callable[[str, str], None] | None, cancel_path: Path) -> None:
        status = "failed"
        entry_point = Path(__file__).resolve().parent / "train_entry.py"
        command = [self.python_executable, str(entry_point), "--task", task,
                   "--model-id", metadata["model_id"], "--dataset", str(dataset_package),
                   "--output", str(run_dir),
                   "--cancel-file", str(cancel_path),
                   "--params", json.dumps(params, sort_keys=True)]
        if checkpoint:
            command.extend(["--checkpoint", str(checkpoint)])
        if dry_run:
            command.append("--dry-run")
        try:
            with (run_dir / "training.log").open("a", encoding="utf-8") as log:
                with self.store.connect() as db:
                    db.execute("UPDATE training_runs SET status='running' WHERE run_key=?", (key,))
                metadata["status"] = "running"
                (run_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                self._process = subprocess.Popen(command, cwd=str(run_dir), stdout=subprocess.PIPE,
                                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
                assert self._process.stdout is not None
                for line in self._process.stdout:
                    log.write(line); log.flush()
                    if callback:
                        callback(key, line.rstrip())
                code = self._process.wait()
                status = "cancelled" if cancel_path.exists() else "completed" if code == 0 else "failed"
        except Exception as error:
            with (run_dir / "training.log").open("a", encoding="utf-8") as log:
                log.write(f"\n{type(error).__name__}: {error}\n")
            status = "failed"
        finally:
            if self._process and self._process.stdout:
                self._process.stdout.close()
            metadata["status"] = status
            metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
            (run_dir / "run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                                                        encoding="utf-8")
            with self.store.connect() as db:
                db.execute("UPDATE training_runs SET status=?,finished_at=CURRENT_TIMESTAMP,metadata_json=? WHERE run_key=?",
                           (status, json.dumps(metadata, ensure_ascii=False, sort_keys=True), key))
            if callback:
                callback(key, "RUN_STATUS:" + status)
            self._process = None

    def cancel(self) -> bool:
        if not self._thread or not self._thread.is_alive():
            return False
        self._cancel.set()
        if self._cancel_path:
            self._cancel_path.write_text("cancel requested\n", encoding="utf-8")
        return True

