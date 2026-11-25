"""One-image CPU smoke check for the bundled BiRefNet segmentation model."""

from __future__ import annotations

import time
import sys
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms
from torchvision.transforms import ToPILImage
from transformers import AutoModelForImageSegmentation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import AppConfig
from app.core.database import Database


MODEL_DIR = ROOT / "models" / "birefnet" / "general"
OUTPUT = ROOT / "temp" / "phase8_birefnet_smoke.png"


def main() -> int:
    config = AppConfig.load()
    records = Database(config.database_path).normal_crop_records()
    candidate = next((row for row in records if row.get("category") == "fullbody"), None)
    if not candidate:
        raise RuntimeError("No Fullbody candidate is available for the smoke check.")

    model = AutoModelForImageSegmentation.from_pretrained(
        str(MODEL_DIR), trust_remote_code=True, local_files_only=True
    )
    model.to("cpu").eval()
    x1, y1, x2, y2 = (int(round(float(value))) for value in candidate["bbox_xyxy"])
    with Image.open(candidate["path"]) as original:
        crop = original.convert("RGB").crop((x1, y1, x2, y2))
    image_size = (1024, 1024)
    transform = transforms.Compose([
        transforms.Resize(image_size), transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    tensor = transform(crop).unsqueeze(0)
    started = time.perf_counter()
    with torch.inference_mode():
        mask_tensor = model(tensor)[-1].sigmoid().cpu()[0].squeeze()
    elapsed = time.perf_counter() - started
    mask = ToPILImage()(mask_tensor).resize(crop.size, Image.Resampling.BILINEAR)
    output = crop.convert("RGBA")
    output.putalpha(mask)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    output.save(OUTPUT)
    alpha = output.getchannel("A").getextrema()
    coverage = sum(1 for value in mask.getdata() if value >= 128) / (mask.width * mask.height)
    print(f"device=cpu size={image_size} elapsed_seconds={elapsed:.2f} alpha_extrema={alpha} foreground_coverage={coverage:.3f}")
    print(f"cropped_input_size={crop.size} transparent_output={alpha[0] < 255 and alpha[1] > 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
