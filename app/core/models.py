from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]
    image_width: int
    image_height: int
    coordinate_space: str = "source_pixels"


@dataclass(frozen=True)
class Classification:
    class_name: str | None
    confidence: float | None
    probabilities: dict[str, float] | None = None
    status: str = "ok"
    model_id: str | None = None
    model_digest: str | None = None


class Detector(Protocol):
    def detect(self, image_path: str) -> Sequence[Detection]: ...


class AssetClassifier(Protocol):
    def classify_crop(self, crop, *, source_identity: str | None = None) -> Classification: ...


def extract_detection_crop(image, detection: Detection):
    """Crop using clamped source-pixel coordinates; invalid boxes return None."""
    width, height = image.size
    x1, y1, x2, y2 = detection.bbox
    left, top = max(0, min(width, int(x1))), max(0, min(height, int(y1)))
    right = max(0, min(width, int(x2 + 0.999999)))
    bottom = max(0, min(height, int(y2 + 0.999999)))
    if right <= left or bottom <= top:
        return None
    return image.crop((left, top, right, bottom))
