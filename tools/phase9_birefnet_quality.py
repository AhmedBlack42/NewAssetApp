"""Run a small, read-only-source BiRefNet quality set for Phase 9."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.output_exporter import _get_birefnet_runtime

OUT = ROOT / "gui_screenshots" / "phase9" / "birefnet"
SAMPLES = [
    ("busy_multi_person_room", "19958866_017_9e32.jpg", (200, 35, 920, 1380)),
    ("bright_overlapping_subjects", "25612293_068_9173.jpg", (120, 0, 730, 518)),
    ("low_resolution_lying_pose", "41148888_002_1fa9.jpg", (0, 0, 460, 345)),
    ("dim_cluttered_room", "70750369_004_ed98.jpg", (0, 190, 730, 1190)),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    import torch

    if torch.cuda.is_available():
        raise RuntimeError("This quality pass is intended to use CPU only.")
    OUT.mkdir(parents=True, exist_ok=True)
    load_started = time.perf_counter()
    runtime, model_load_seconds = _get_birefnet_runtime()
    total_first_load_seconds = time.perf_counter() - load_started
    records = []
    for label, filename, box in SAMPLES:
        source = ROOT / "samples" / filename
        with Image.open(source) as original:
            source_size = original.size
            rgb = original.convert("RGB")
            try:
                region = rgb.crop(box)
            finally:
                rgb.close()
        started = time.perf_counter()
        segmented, metrics = runtime.segment(region, cache_key=None)
        elapsed = time.perf_counter() - started
        try:
            target = OUT / f"{label}.webp"
            segmented.save(target, format="WEBP")
            alpha = segmented.getchannel("A")
            extrema = alpha.getextrema()
            histogram = alpha.histogram()
            total = max(1, segmented.width * segmented.height)
            opaque_fraction = sum(histogram[128:]) / total
            transparent_fraction = sum(histogram[:128]) / total
            records.append({
                "sample": label,
                "source": filename,
                "source_sha256": sha256(source),
                "source_size": list(source_size),
                "roi_xyxy": list(box),
                "crop_size": list(region.size),
                "output": str(target.relative_to(ROOT)),
                "output_format": "WebP",
                "output_mode": segmented.mode,
                "output_size": list(segmented.size),
                "alpha_extrema": list(extrema),
                "opaque_fraction_alpha_ge_128": opaque_fraction,
                "transparent_fraction_alpha_lt_128": transparent_fraction,
                "elapsed_seconds": elapsed,
                "runtime_metrics": metrics,
            })
            print(f"{label}: {elapsed:.2f}s, crop={region.size}, output={target.name}, "
                  f"opaque={opaque_fraction:.3f}, cache_hit={metrics.get('cache_hit')}", flush=True)
        finally:
            segmented.close()
            region.close()
    manifest = {
        "model": "bundled BiRefNet general; unchanged local model.safetensors",
        "device": runtime.device,
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "model_load_seconds_excluding_imports": model_load_seconds,
        "first_load_call_elapsed_seconds_including_imports": total_first_load_seconds,
        "samples": records,
    }
    (OUT / "quality_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Manifest: {OUT / 'quality_manifest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
