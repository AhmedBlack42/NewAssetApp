from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "NewAssetApp"
    recursive_scan: bool = True
    confidence_threshold: float = 0.77
    supported_extensions: tuple[str, ...] = (
        ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"
    )
    yolo_checkpoint: str | None = None
    clothing_classifier_checkpoint: str | None = "models/clothing_classifier/clothing_classifier_12class.pth"
    clothing_classifier_class_map: str | None = "data/models/clothing_classifier_12class_map.json"
    # Deprecated configuration keys remain readable for existing user configs.
    asset_classifier_checkpoint: str | None = None
    asset_class_map: str | None = None
    data_dir_override: Path | str | None = None
    output_dir_override: Path | str | None = None
    logs_dir_override: Path | str | None = None
    database_path_override: Path | str | None = None

    @property
    def data_dir(self) -> Path:
        return (Path(self.data_dir_override).resolve()
                if self.data_dir_override else PROJECT_ROOT / "data")

    @property
    def output_dir(self) -> Path:
        return (Path(self.output_dir_override).resolve()
                if self.output_dir_override else PROJECT_ROOT / "output")

    @property
    def logs_dir(self) -> Path:
        return (Path(self.logs_dir_override).resolve()
                if self.logs_dir_override else PROJECT_ROOT / "logs")

    @property
    def database_path(self) -> Path:
        return (Path(self.database_path_override).resolve()
                if self.database_path_override else self.data_dir / "newassetapp.sqlite3")

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AppConfig":
        defaults = cls()
        raw: dict[str, Any] = {}
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        config = cls(
            app_name=str(raw.get("app_name", defaults.app_name)),
            recursive_scan=bool(raw.get("recursive_scan", defaults.recursive_scan)),
            confidence_threshold=float(raw.get("confidence_threshold", defaults.confidence_threshold)),
            supported_extensions=tuple(
                str(ext).lower() if str(ext).startswith(".") else "." + str(ext).lower()
                for ext in raw.get("supported_extensions", defaults.supported_extensions)
            ),
            yolo_checkpoint=raw.get("yolo_checkpoint"),
            clothing_classifier_checkpoint=raw.get("clothing_classifier_checkpoint") or
                raw.get("asset_classifier_checkpoint") or defaults.clothing_classifier_checkpoint,
            clothing_classifier_class_map=raw.get("clothing_classifier_class_map") or
                raw.get("asset_class_map") or defaults.clothing_classifier_class_map,
            asset_classifier_checkpoint=raw.get("asset_classifier_checkpoint"),
            asset_class_map=raw.get("asset_class_map"),
        )
        if not 0.0 <= config.confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be between 0 and 1.")
        return config
