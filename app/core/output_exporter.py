from __future__ import annotations

import hashlib
import json
import logging
import gc
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.crop_rules import (
    BODY_IMAGE_SPECS, FULLBODY_MIN_HEIGHT, _has_transparent_pixels, _scale_up,
    prepare_export_crop,
)
from app.core.fullbody_classification import fullbody_filename
from app.core.filename_grammar import body_images_filename, clothing_filename
from app.core.tag_library import TagLibrary

logger = logging.getLogger(__name__)


class ExportCancelled(Exception):
    """Raised when a normal export is stopped between crops."""


class _AlphaMaskCache:
    """Small bounded in-memory cache for deterministic BiRefNet alpha masks."""

    def __init__(self, max_bytes: int = 32 * 1024 * 1024):
        self.max_bytes = int(max_bytes)
        self._items: OrderedDict[tuple, tuple[tuple[int, int], bytes]] = OrderedDict()
        self._size_bytes = 0
        self._lock = threading.Lock()

    def get(self, key: tuple):
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            self._items.move_to_end(key)
            return entry

    def put(self, key: tuple, size: tuple[int, int], mask_bytes: bytes) -> None:
        if len(mask_bytes) > self.max_bytes:
            return
        with self._lock:
            previous = self._items.pop(key, None)
            if previous:
                self._size_bytes -= len(previous[1])
            self._items[key] = (size, mask_bytes)
            self._size_bytes += len(mask_bytes)
            while self._size_bytes > self.max_bytes and self._items:
                _, (_, old_bytes) = self._items.popitem(last=False)
                self._size_bytes -= len(old_bytes)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._size_bytes = 0


_BIREFNET_ALPHA_CACHE = _AlphaMaskCache()
_BIREFNET_RUNTIME = None
_BIREFNET_RUNTIME_LOCK = threading.Lock()
_BIREFNET_CACHE_MODEL_KEY = "birefnet-general-1024-v1"
_BIREFNET_INFERENCE_SIZES = (1024, 768, 512, 384, 320)
_BIREFNET_MIN_AVAILABLE_MEMORY_BYTES = 2 * 1024 ** 3
_BIREFNET_MAX_REGION_PIXELS = 25_000_000
_BIREFNET_MAX_REGION_SIDE = 12000


class _BiRefNetResourceError(RuntimeError):
    """A resource budget refusal before expensive model allocation."""


def _preflight_birefnet_resource(image: Image.Image) -> dict:
    """Reject inputs/runtime states that cannot safely use bundled BiRefNet on CPU."""
    pixels = int(image.width) * int(image.height)
    available = _available_physical_memory_bytes()
    if image.width > _BIREFNET_MAX_REGION_SIDE or image.height > _BIREFNET_MAX_REGION_SIDE:
        raise _BiRefNetResourceError(
            "Background removal refuses a crop wider or taller than "
            f"{_BIREFNET_MAX_REGION_SIDE} pixels. Reduce the selected region and retry."
        )
    if pixels > _BIREFNET_MAX_REGION_PIXELS:
        raise _BiRefNetResourceError(
            f"Background removal refuses this {pixels:,}-pixel crop; the validated limit is "
            f"{_BIREFNET_MAX_REGION_PIXELS:,} pixels. Reduce the selected region and retry."
        )
    if available is not None and available < _BIREFNET_MIN_AVAILABLE_MEMORY_BYTES:
        raise _BiRefNetResourceError(
            "Background removal needs at least 2 GiB of currently available memory "
            f"(currently available: {available / (1024 ** 3):.2f} GiB). "
            "Close other applications or retry on a machine with more available memory."
        )
    return {
        "available_memory_bytes": available,
        "region_width": int(image.width),
        "region_height": int(image.height),
        "region_pixels": pixels,
    }


def _available_physical_memory_bytes() -> int | None:
    """Return available RAM without adding a required system dependency."""
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except Exception:
        if os.name != "nt":
            return None
    try:
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    except Exception:
        logger.debug("Could not read available system memory for BiRefNet sizing", exc_info=True)
    return None


def _preferred_birefnet_input_size(available_bytes: int | None) -> int:
    """Choose a conservative CPU-friendly input size from currently free RAM."""
    if available_bytes is None:
        return 512
    available_gib = available_bytes / (1024 ** 3)
    if available_gib < 3.5:
        return 384
    if available_gib < 6:
        return 512
    if available_gib < 11:
        return 768
    return 1024


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _write_export_manifest(root: Path, export_type: str, entries: list[dict]) -> str | None:
    if not entries:
        return None
    from datetime import datetime, timezone
    from app.core.classification_taxonomy import REGISTRY_ID, REGISTRY_VERSION
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"newassetapp_{export_type}_manifest_{stamp}.json"
    suffix = 2
    while path.exists():
        path = root / f"newassetapp_{export_type}_manifest_{stamp}_{suffix}.json"
        suffix += 1
    payload = {"schema_version": 1, "export_type": export_type,
               "taxonomy_registry_id": REGISTRY_ID, "taxonomy_version": REGISTRY_VERSION,
               "generated_at": datetime.now(timezone.utc).isoformat(), "files": entries}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path)


def _safe_manual_filename(payload: dict) -> str:
    name = str(payload.get("output_filename") or "").strip()
    if not name or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("This category needs a user-confirmed output filename.")
    if Path(name).suffix.lower() != ".webp":
        raise ValueError("Normal output filenames must use the guide's .webp format.")
    return name


def build_output_plan(database: Database, output_dir: Path | str,
                      proposal_ids: set[int] | list[int] | tuple[int, ...] | None = None) -> dict:
    """Build a read-only export preview from latest human-confirmed records."""
    root = Path(output_dir).resolve()
    tags = TagLibrary(Path(__file__).resolve().parents[2] / "data" / "tags")
    body_entries = tags.entries(group="body_images")
    body_main = {row.get("serialized_value") for row in body_entries if row.get("tag_type") == "main"}
    body_subtags = {row.get("serialized_value") for row in body_entries
                    if row.get("tag_type") in {"subtag", "tag"}}
    clothing_entries = tags.entries(group="clothing")
    clothing_main = {row.get("serialized_value") for row in clothing_entries
                     if row.get("tag_type") in {"main", "tag"}}
    planned = []
    skipped = []
    occupied: set[str] = set()
    rows = database.output_review_records()
    selected = None if proposal_ids is None else {int(value) for value in proposal_ids}
    if selected is not None:
        rows = [row for row in rows if int(row["id"]) in selected]
        included_ids = {int(row["id"]) for row in rows}
        skipped.extend({"proposal_id": ident, "reason": "not classification-reviewed and confirmed for tagged output"}
                       for ident in sorted(selected - included_ids))
    for row in rows:
        if not row.get("confirmed_json"):
            skipped.append({"proposal_id": row["id"], "reason": "no human review payload"})
            continue
        payload = json.loads(row["confirmed_json"])
        category = payload.get("category", row["category"])
        category = row["category"]
        main = row.get("structured_main_category")
        subtags = json.loads(row.get("structured_subtags_json") or "[]")
        location = row.get("structured_location_value")
        if location and location not in subtags:
            subtags.append(location)
        taxonomy_version = row.get("structured_taxonomy_version")
        if row.get("structured_registry_id") != "newassetapp_structured_classification" or taxonomy_version != "1.0.0":
            skipped.append({"proposal_id": row["id"], "reason": "Structured classification uses an unknown registry version."})
            continue
        classification = {
            "task": category, "main_category": main,
            "fullbody_state": row.get("structured_fullbody_state"),
            "clothing_family": row.get("structured_clothing_family"),
            "subtags": list(subtags), "location": location,
            "validity_state": row.get("structured_validity_state"),
            "human_review_state": row.get("structured_human_review_state"),
            "human_confirmed": bool(row.get("structured_human_confirmed")),
            "training_eligible": bool(row.get("structured_training_eligible")),
            "exclusion_reason": row.get("structured_exclusion_reason"),
            "registry_id": row.get("structured_registry_id"),
            "taxonomy_version": taxonomy_version,
        }
        try:
            from app.core.classification_taxonomy import validate_record
            if category in {"fullbody", "body_images", "clothing"}:
                validate_record(category, {"main_tag": main, "main_tags": [main] if main else [],
                                           "subtags": subtags, "location": location,
                                           "state_spec": classification["fullbody_state"],
                                           "validity_state": classification["validity_state"],
                                           "human_review_state": classification["human_review_state"]})
            if category == "fullbody":
                state = classification["fullbody_state"]
                if not main or not state:
                    raise ValueError("Fullbody main type and state both need human confirmation.")
                sequence = 1
                while True:
                    filename = fullbody_filename(main, state, sequence, subtags)
                    target = root / "fullbody" / filename
                    key = str(target).casefold()
                    if key not in occupied and not target.exists():
                        break
                    sequence += 1
            elif category == "body_images":
                if not main:
                    raise ValueError("Body Images output needs a confirmed main category.")
                sequence = 1
                while True:
                    filename = body_images_filename([main], sequence, subtags)
                    target = root / "body_images" / filename
                    if str(target).casefold() not in occupied and not target.exists():
                        break
                    sequence += 1
            elif category == "clothing":
                main = str(main or "").strip()
                if main not in clothing_main:
                    raise ValueError("Clothing output needs a verified selectable main tag.")
                sequence = 1
                while True:
                    filename = clothing_filename(main, sequence, subtags)
                    target = root / "clothing" / filename
                    if str(target).casefold() not in occupied and not target.exists():
                        break
                    sequence += 1
            elif category == "others":
                filename = _safe_manual_filename(payload)
                folder = "others"
                target = root / folder / filename
                if str(target).casefold() in occupied or target.exists():
                    raise ValueError(f"Output filename collision: {target.name}")
            else:
                raise ValueError(f"Unsupported output category: {category!r}")
            occupied.add(str(target).casefold())
            planned.append({"proposal_id": row["id"], "source_id": row["source_id"],
                            "source_path": row["path"], "source_sha256": row["content_sha256"],
                            "bbox_xyxy": payload.get("bbox_xyxy") or
                                         (json.loads(row["corrected_bbox_json"])
                                          if row.get("corrected_bbox_json") else None),
                            "category": category, "tag": main,
                            "main_tag": main,
                            "state_spec": classification.get("fullbody_state"),
                            "fullbody_output_category": payload.get("fullbody_output_category"),
                            "subtags": subtags,
                            "location": location,
                            "classification": classification,
                            "filename": filename, "target": str(target),
                            "taxonomy_version": taxonomy_version,
                            "model_provenance": {"yolo_model_id": row.get("yolo_model_id"),
                                                 "yolo_model_digest": row.get("yolo_model_digest"),
                                                 "cnn_model_id": row.get("cnn_model_id"),
                                                 "cnn_model_digest": row.get("cnn_model_digest")}})
        except (ValueError, TypeError) as error:
            skipped.append({"proposal_id": row["id"], "reason": str(error)})
    return {"output_dir": str(root), "items": planned, "skipped": skipped,
            "item_count": len(planned), "skipped_count": len(skipped)}


def export_reviewed_output(database: Database, output_dir: Path | str,
                           plan: dict | None = None, progress_callback=None) -> dict:
    """Write normal WebP application output; source files are read-only."""
    plan = plan or build_output_plan(database, output_dir)
    written = []
    failures = []
    manifest_entries = []
    items = plan["items"]
    for index, item in enumerate(items, start=1):
        source = Path(item["source_path"])
        target = Path(item["target"])
        try:
            if _hash(source) != item["source_sha256"]:
                raise ValueError("Source image changed after review.")
            if target.exists():
                raise FileExistsError(f"Output collision appeared after preview: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as original:
                source_image = original.convert("RGBA" if "A" in original.getbands() else "RGB")
            try:
                output_image, crop_policy = prepare_export_crop(source_image, item)
            finally:
                source_image.close()
            try:
                # Exclusive creation prevents another process from silently
                # replacing a crop after the preview was built.
                with target.open("xb") as destination:
                    output_image.save(destination, format="WEBP")
                processing = {key: value for key, value in item.items()
                              if key not in {"source_path", "target"}}
                processing["source_path"] = str(source)
                processing["crop_policy"] = crop_policy
                processing["classification"] = item.get("classification")
                database.record_final_asset(item["proposal_id"], str(target),
                                            width=output_image.width, height=output_image.height,
                                            processing=processing)
                written.append(str(target))
                manifest_entries.append({
                    "proposal_id": item["proposal_id"], "source_id": item["source_id"],
                    "source_sha256": item["source_sha256"],
                    "output_relative_path": target.relative_to(Path(output_dir).resolve()).as_posix(),
                    "output_sha256": _hash(target), "filename": target.name,
                    "classification": item.get("classification"),
                })
            except Exception:
                target.unlink(missing_ok=True)
                raise
            finally:
                output_image.close()
            if progress_callback:
                progress_callback(index, len(items), item["proposal_id"], "exported")
        except Exception as error:
            logger.exception("Professional export failed proposal_id=%s category=%s target=%s",
                             item.get("proposal_id"), item.get("category"), target.name)
            failures.append({"proposal_id": item["proposal_id"], "source_path": str(source),
                             "target": str(target), "reason": str(error)})
            if progress_callback:
                progress_callback(index, len(items), item["proposal_id"], "failed")
    manifest_path = _write_export_manifest(Path(output_dir).resolve(), "professional_review", manifest_entries)
    return {**plan, "written": written, "written_count": len(written), "manifest_path": manifest_path,
            "failures": failures, "failure_count": len(failures)}


def _normal_filename(category: str, row: dict, target_root: Path, occupied: set[str]) -> Path:
    folder = {"fullbody": "fullbody", "body_images": "body_images", "clothing": "clothing"}[category]
    relative_folder = Path(folder)
    if category == "clothing":
        from app.core.crop_rules import clothing_cover_rule
        family = row.get("normal_clothing_broad_family")
        _body_tag, cover_folder = clothing_cover_rule(
            str(family or ""), str(row.get("normal_clothing_cover_area") or "")
        )
        relative_folder = relative_folder / Path(cover_folder)
    from app.core.classification_taxonomy import serialize_filename
    main = row.get("normal_main_tag")
    tags = list(row.get("normal_subtags") or [])
    location = row.get("normal_location_value")
    if location and location not in tags:
        tags.append(location)
    if category == "fullbody":
        state = row.get("normal_fullbody_state")
        if not state:
            raise ValueError("Choose the Fullbody state in Normal Processing.")
        tags.insert(0, state)
    if not main:
        raise ValueError("Choose a human-selected main tag in Normal Processing.")
    index = 1
    while True:
        filename = serialize_filename([main], tags, index)
        target = target_root / relative_folder / filename
        if str(target).casefold() not in occupied and not target.exists():
            return target
        index += 1


def build_normal_output_plan(database: Database, output_dir: Path | str,
                             proposal_ids: set[int] | list[int] | tuple[int, ...]) -> dict:
    """Plan ordinary-user exports from selected proposals, independent of review confirmation."""
    root = Path(output_dir).resolve()
    selected = {int(value) for value in proposal_ids}
    rows = [row for row in database.normal_crop_records() if int(row["id"]) in selected]
    by_id = {int(row["id"]): row for row in rows}
    skipped = []
    items = []
    occupied: set[str] = set()
    for missing in sorted(selected - set(by_id)):
        skipped.append({"proposal_id": missing, "reason": "No current model crop suggestion exists."})
    for row in rows:
        category = row.get("category")
        if category not in {"fullbody", "body_images", "clothing"}:
            skipped.append({"proposal_id": row["id"], "reason": "Choose Fullbody, Body Images, or Clothing."})
            continue
        main_tag = row.get("normal_main_tag")
        if not main_tag:
            skipped.append({"proposal_id": row["id"], "reason": "Choose a human-selected main tag in Normal Processing."})
            continue
        try:
            from app.core.classification_taxonomy import validate_record, REGISTRY_VERSION
            validate_record(category, {"main_tag": main_tag, "main_tags": [main_tag],
                                       "subtags": row.get("normal_subtags", []),
                                       "location": row.get("normal_location_value"),
                                       "state_spec": row.get("normal_fullbody_state")})
            target = _normal_filename(category, row, root, occupied)
        except ValueError as error:
            skipped.append({"proposal_id": row["id"], "reason": str(error)})
            continue
        occupied.add(str(target).casefold())
        items.append({
            "proposal_id": int(row["id"]),
            "source_id": int(row["source_id"]),
            "source_path": row["path"],
            "source_sha256": row["content_sha256"],
            "bbox_xyxy": row["bbox_xyxy"],
            "category": category,
            "main_tag": main_tag,
            "fullbody_state": row.get("normal_fullbody_state"),
            "subtags": list(row.get("normal_subtags", [])),
            "location": row.get("normal_location_value"),
            "taxonomy_version": row.get("normal_taxonomy_version") or REGISTRY_VERSION,
            "human_selected": True,
            "human_confirmed": bool(row.get("normal_confirmed")),
            "training_eligible": bool(row.get("normal_confirmed")),
            "clothing_broad_family": row.get("normal_clothing_broad_family"),
            "clothing_cover_area": row.get("normal_clothing_cover_area"),
            "remove_background": category == "fullbody",
            "target": str(target),
        })
    return {"output_dir": str(root), "items": items, "skipped": skipped,
            "item_count": len(items), "skipped_count": len(skipped)}


class _BirefNetRuntime:
    def __init__(self, model, device, transform, to_pil, torch):
        self.model = model
        self.device = str(device)
        self.transform = transform
        self.to_pil = to_pil
        self.torch = torch
        self.inference_lock = threading.Lock()

    def segment(self, image: Image.Image, cache_key: tuple | None = None):
        started = time.perf_counter()
        preferred_size = _preferred_birefnet_input_size(_available_physical_memory_bytes())
        candidate_sizes = [preferred_size, *(size for size in _BIREFNET_INFERENCE_SIZES
                                             if size < preferred_size)]
        for input_size in candidate_sizes:
            size_cache_key = (*cache_key, input_size) if cache_key else None
            cached = _BIREFNET_ALPHA_CACHE.get(size_cache_key) if size_cache_key else None
            if cached is not None:
                size, mask_bytes = cached
                mask = Image.frombytes("L", size, mask_bytes)
                output = image.convert("RGBA")
                output.putalpha(mask)
                mask.close()
                return output, {"cache_hit": True, "inference_seconds": 0.0,
                                "postprocess_seconds": time.perf_counter() - started,
                                "inference_size": [input_size, input_size]}
        preprocess_seconds = 0.0
        inference_seconds = 0.0
        mask_tensor = None
        used_size = None
        for input_size in candidate_sizes:
            size_cache_key = (*cache_key, input_size) if cache_key else None
            preprocess_started = time.perf_counter()
            rgb = image if image.mode == "RGB" else image.convert("RGB")
            owned_rgb = rgb is not image
            resized = rgb.resize((input_size, input_size), Image.Resampling.BILINEAR)
            if owned_rgb:
                rgb.close()
            try:
                tensor = self.transform(resized).unsqueeze(0).to(self.device)
            finally:
                resized.close()
            preprocess_seconds += time.perf_counter() - preprocess_started

            inference_started = time.perf_counter()
            try:
                with self.inference_lock, self.torch.inference_mode():
                    mask_tensor = self.model(tensor)[-1].sigmoid().cpu()[0].squeeze()
                inference_seconds += time.perf_counter() - inference_started
                used_size = input_size
                break
            except RuntimeError as error:
                del tensor
                gc.collect()
                if self.device.startswith("cuda"):
                    self.torch.cuda.empty_cache()
                message = str(error).lower()
                memory_error = any(token in message for token in
                                   ("out of memory", "not enough memory", "defaultcpuallocator"))
                if not memory_error or input_size == candidate_sizes[-1]:
                    raise
                logger.warning("BiRefNet ran out of memory at %sx%s on %s; retrying smaller input: %s",
                               input_size, input_size, self.device, error)
                continue
            finally:
                if "tensor" in locals():
                    del tensor
        if mask_tensor is None or used_size is None:
            raise RuntimeError("BiRefNet could not produce a mask at a safe inference resolution.")

        postprocess_started = time.perf_counter()
        mask = self.to_pil(mask_tensor).resize(image.size, Image.Resampling.BILINEAR)
        del mask_tensor
        gc.collect()
        if self.device.startswith("cuda"):
            self.torch.cuda.empty_cache()
        mask_bytes = mask.tobytes()
        if cache_key:
            _BIREFNET_ALPHA_CACHE.put((*cache_key, used_size), image.size, mask_bytes)
        output = image.convert("RGBA")
        output.putalpha(mask)
        mask.close()
        return output, {
            "cache_hit": False,
            "preprocess_seconds": preprocess_seconds,
            "inference_seconds": inference_seconds,
            "postprocess_seconds": time.perf_counter() - postprocess_started,
            "inference_size": [used_size, used_size],
        }


def _get_birefnet_runtime():
    """Load the bundled model lazily once per application process."""
    global _BIREFNET_RUNTIME
    if _BIREFNET_RUNTIME is not None:
        return _BIREFNET_RUNTIME, 0.0
    with _BIREFNET_RUNTIME_LOCK:
        if _BIREFNET_RUNTIME is not None:
            return _BIREFNET_RUNTIME, 0.0
        import torch
        from torchvision import transforms
        from torchvision.transforms import ToPILImage
        from transformers import AutoModelForImageSegmentation

        model_path = Path(__file__).resolve().parents[2] / "models" / "birefnet" / "general"
        if not (model_path / "model.safetensors").is_file():
            raise FileNotFoundError("Bundled BiRefNet general weights are unavailable.")
        started = time.perf_counter()
        model = AutoModelForImageSegmentation.from_pretrained(
            str(model_path), trust_remote_code=True, local_files_only=True
        )
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        model.to(device).eval()
        transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        _BIREFNET_RUNTIME = _BirefNetRuntime(model, device, transform, ToPILImage(), torch)
        return _BIREFNET_RUNTIME, time.perf_counter() - started


def _birefnet_cache_key(item: dict, region: Image.Image,
                        model_key: str = _BIREFNET_CACHE_MODEL_KEY) -> tuple | None:
    digest = item.get("source_sha256")
    box = item.get("bbox_xyxy")
    if not digest or box is None:
        return None
    return (model_key, str(digest),
            tuple(int(round(float(value))) for value in box), region.size)


def export_normal_output(database: Database, plan: dict, progress_callback=None,
                         background_remover=None, background_remover_key: str | None = None,
                         cancel_event: threading.Event | None = None) -> dict:
    """Write WebP crops independently; preserve completed files on cancellation."""
    written = []
    failures = []
    fallbacks = []  # Retained in the result shape for compatibility; alpha-required exports do not fall back.
    manifest_entries = []
    cancelled_ids = []
    items = plan["items"]
    for index, item in enumerate(items, start=1):
        if cancel_event and cancel_event.is_set():
            cancelled_ids = [int(row["proposal_id"]) for row in items[index - 1:]]
            break
        source, target = Path(item["source_path"]), Path(item["target"])
        output_image = None
        created = False
        try:
            if _hash(source) != item["source_sha256"]:
                raise ValueError("Source image changed after scanning; scan it again before export.")
            if target.exists():
                raise FileExistsError(f"Output collision appeared after preview: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source) as original:
                source_image = original.convert("RGBA" if "A" in original.getbands() else "RGB")
            try:
                if item["category"] == "fullbody":
                    x1, y1, x2, y2 = (int(round(float(value))) for value in item["bbox_xyxy"])
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(source_image.width, x2), min(source_image.height, y2)
                    if not (x1 < x2 and y1 < y2):
                        raise ValueError("Fullbody crop box is outside the source image.")
                    region = source_image.crop((x1, y1, x2, y2))
                    try:
                        if _has_transparent_pixels(region):
                            output_image, crop_policy = prepare_export_crop(source_image, item)
                        elif not item.get("remove_background", True):
                            raise ValueError(
                                "Fullbody output requires a transparent background; enable background removal."
                            )
                        else:
                            pre_removal = region.copy()
                            scaled_region = _scale_up(pre_removal, 1, FULLBODY_MIN_HEIGHT)
                            if scaled_region is not pre_removal:
                                pre_removal.close()
                            runtime_metrics = {}
                            try:
                                if progress_callback:
                                    progress_callback(index - 1, len(items), item["proposal_id"],
                                                      "Upscaling selected crop before background removal")
                                if background_remover is None:
                                    _preflight_birefnet_resource(scaled_region)
                                    runtime, load_seconds = _get_birefnet_runtime()
                                    remover_device = runtime.device
                                    cache_key = _birefnet_cache_key(item, scaled_region)
                                    if progress_callback:
                                        progress_callback(index - 1, len(items), item["proposal_id"],
                                                          f"Removing background on {remover_device}")
                                    segmented, runtime_metrics = runtime.segment(scaled_region, cache_key)
                                else:
                                    remover_device = "injected"
                                    cache_key = (_birefnet_cache_key(
                                        item, scaled_region, background_remover_key
                                    ) if background_remover_key else None)
                                    cached = (_BIREFNET_ALPHA_CACHE.get(cache_key)
                                              if cache_key else None)
                                    load_seconds = 0.0
                                    if cached is not None:
                                        cached_size, mask_bytes = cached
                                        cached_mask = Image.frombytes("L", cached_size, mask_bytes)
                                        segmented = scaled_region.convert("RGBA")
                                        segmented.putalpha(cached_mask)
                                        cached_mask.close()
                                        runtime_metrics = {"cache_hit": True, "inference_seconds": 0.0}
                                    else:
                                        if progress_callback:
                                            progress_callback(index - 1, len(items), item["proposal_id"],
                                                              "Removing background")
                                        segmented = background_remover(scaled_region)
                                        if (isinstance(segmented, Image.Image)
                                                and segmented.size == scaled_region.size
                                                and "A" in segmented.getbands()
                                                and cache_key):
                                            alpha = segmented.getchannel("A")
                                            _BIREFNET_ALPHA_CACHE.put(cache_key, scaled_region.size,
                                                                      alpha.tobytes())
                                            alpha.close()
                                        runtime_metrics = {"cache_hit": False}
                                if not isinstance(segmented, Image.Image) or segmented.size != scaled_region.size:
                                    raise ValueError("Background removal returned an invalid crop.")
                                try:
                                    if not _has_transparent_pixels(segmented):
                                        raise ValueError("Background removal returned no transparent pixels.")
                                    item_for_crop = {**item,
                                                     "bbox_xyxy": [0, 0, segmented.width, segmented.height]}
                                    output_image, crop_policy = prepare_export_crop(segmented, item_for_crop)
                                finally:
                                    segmented.close()
                            except Exception as error:
                                raise RuntimeError(
                                    "Required Fullbody background removal failed; no opaque output was written: "
                                    f"{type(error).__name__}: {error}"
                                ) from error
                            else:
                                crop_policy["background_removal"] = {
                                    "model": "BiRefNet general (bundled)" if background_remover is None
                                             else "injected test remover",
                                    "device": remover_device,
                                    "input_size": runtime_metrics.get("inference_size")
                                                  if background_remover is None else None,
                                    "model_load_seconds": load_seconds,
                                    **runtime_metrics,
                                }
                            finally:
                                scaled_region.close()
                    finally:
                        region.close()
                elif (item["category"] == "body_images"
                      and item.get("main_tag") in {"portrait", "tportrait"}):
                    output_image, crop_policy = prepare_export_crop(
                        source_image, item, allow_missing_alpha=True
                    )
                    needs_removal = not _has_transparent_pixels(output_image)
                    if needs_removal and "A" in output_image.getbands():
                        alpha = output_image.getchannel("A")
                        visible = alpha.getbbox() is not None
                        alpha.close()
                        if not visible:
                            raise ValueError("Portrait crop has no visible subject pixels.")
                    if needs_removal:
                        geometry_crop = output_image
                        segmented = None
                        try:
                            runtime_metrics = {}
                            cache_key = _birefnet_cache_key(item, geometry_crop)
                            if background_remover is None:
                                _preflight_birefnet_resource(geometry_crop)
                                runtime, load_seconds = _get_birefnet_runtime()
                                remover_device = runtime.device
                                if progress_callback:
                                    progress_callback(index - 1, len(items), item["proposal_id"],
                                                      f"Removing background on {remover_device}")
                                segmented, runtime_metrics = runtime.segment(geometry_crop, cache_key)
                            else:
                                remover_device = "injected"
                                cache_key = (_birefnet_cache_key(
                                    item, geometry_crop, background_remover_key
                                ) if background_remover_key else None)
                                cached = (_BIREFNET_ALPHA_CACHE.get(cache_key) if cache_key else None)
                                if cached is not None:
                                    cached_size, mask_bytes = cached
                                    mask = Image.frombytes("L", cached_size, mask_bytes)
                                    segmented = geometry_crop.convert("RGBA")
                                    segmented.putalpha(mask)
                                    mask.close()
                                    runtime_metrics = {"cache_hit": True, "inference_seconds": 0.0}
                                else:
                                    if progress_callback:
                                        progress_callback(index - 1, len(items), item["proposal_id"],
                                                          "Removing portrait background")
                                    segmented = background_remover(geometry_crop)
                                    if (isinstance(segmented, Image.Image)
                                            and segmented.size == geometry_crop.size
                                            and "A" in segmented.getbands() and cache_key):
                                        alpha = segmented.getchannel("A")
                                        _BIREFNET_ALPHA_CACHE.put(cache_key, geometry_crop.size,
                                                                  alpha.tobytes())
                                        alpha.close()
                                    runtime_metrics = {"cache_hit": False}
                            if not isinstance(segmented, Image.Image) or segmented.size != geometry_crop.size:
                                raise ValueError("Background removal returned an invalid portrait crop.")
                            if not _has_transparent_pixels(segmented):
                                raise ValueError("Background removal returned no transparent portrait pixels.")
                            alpha = segmented.getchannel("A")
                            visible = alpha.getbbox() is not None
                            alpha.close()
                            if not visible:
                                raise ValueError("Background removal removed all visible portrait pixels.")
                            output_image = segmented
                            crop_policy["background_removal"] = {
                                "model": "BiRefNet general (bundled)" if background_remover is None
                                         else "injected test remover",
                                "device": remover_device,
                                "input_size": runtime_metrics.get("inference_size")
                                              if background_remover is None else None,
                                "model_load_seconds": load_seconds if background_remover is None else 0.0,
                                **runtime_metrics,
                            }
                        except Exception:
                            if isinstance(segmented, Image.Image) and segmented is not geometry_crop:
                                segmented.close()
                            geometry_crop.close()
                            raise
                        else:
                            geometry_crop.close()
                else:
                    output_image, crop_policy = prepare_export_crop(source_image, item)
            finally:
                source_image.close()
            with target.open("xb") as destination:
                created = True
                output_image.save(destination, format="WEBP")
            processing = {
                "bbox_xyxy": item["bbox_xyxy"],
                "crop_policy": crop_policy,
                "source_path": str(source),
                "category": item["category"],
                "classification": {"main_tag": item["main_tag"],
                                   "fullbody_state": item.get("fullbody_state"),
                                   "subtags": item.get("subtags", []),
                                   "location": item.get("location"),
                                   "taxonomy_version": item.get("taxonomy_version"),
                                   "human_selected": True, "human_confirmed": False,
                                   "training_eligible": False},
            }
            manifest_entry = {
                "proposal_id": item["proposal_id"], "source_id": item["source_id"],
                "source_sha256": item["source_sha256"],
                "output_relative_path": target.relative_to(Path(plan["output_dir"]).resolve()).as_posix(),
                "output_sha256": _hash(target), "filename": target.name,
                "classification": processing["classification"],
            }
            database.record_normal_crop_export(
                item["proposal_id"], item["source_id"], item["source_sha256"], str(target),
                item["category"], output_image.width, output_image.height, processing,
                export_manifest=manifest_entry,
            )
            written.append(str(target))
            manifest_entries.append(manifest_entry)
            if progress_callback:
                try:
                    progress_callback(index, len(items), item["proposal_id"], "exported")
                except Exception:
                    pass
        except Exception as error:
            if created:
                target.unlink(missing_ok=True)
            try:
                database.record_normal_crop_export_attempt(
                    item["proposal_id"], item["source_sha256"], "failed", str(target), str(error))
            except Exception:
                logger.exception("Could not persist failed export attempt proposal_id=%s",
                                 item.get("proposal_id"))
            logger.exception("Normal export failed proposal_id=%s category=%s target=%s",
                             item.get("proposal_id"), item.get("category"), target.name)
            failures.append({"proposal_id": item["proposal_id"], "source_path": str(source),
                             "target": str(target), "reason": str(error)})
            if progress_callback:
                progress_callback(index, len(items), item["proposal_id"], "failed")
        finally:
            if output_image is not None:
                output_image.close()
    manifest_path = _write_export_manifest(Path(plan["output_dir"]).resolve(), "normal_processing", manifest_entries)
    return {**plan, "written": written, "written_count": len(written), "manifest_path": manifest_path,
            "failures": failures, "failure_count": len(failures),
            "fallbacks": fallbacks, "fallback_count": len(fallbacks),
            "cancelled": bool(cancelled_ids), "cancelled_ids": cancelled_ids}
