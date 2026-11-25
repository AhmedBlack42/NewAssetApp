from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


STUDIO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class StudioConfig:
    root: Path = STUDIO_ROOT

    @classmethod
    def for_acceptance(cls, root: Path | str) -> "StudioConfig":
        resolved = Path(root).resolve()
        project_root = STUDIO_ROOT.resolve()
        if resolved == project_root or project_root in resolved.parents or resolved in project_root.parents:
            raise ValueError("Studio acceptance root must not overlap production Studio storage.")
        return cls(root=resolved)

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "studio.sqlite3"

    @property
    def storage_dir(self) -> Path:
        return self.root / "storage"

    @property
    def media_dir(self) -> Path:
        return self.storage_dir / "media"

    @property
    def output_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"

    @property
    def registry_dir(self) -> Path:
        return self.root / "registries"

    @property
    def contract_dir(self) -> Path:
        return self.root / "contracts"

    @property
    def app_db_file(self) -> Path:
        return self.database_path

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.media_dir, self.output_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)

    def load_settings(self) -> dict:
        if not self.config_path.exists():
            return {"schema_version": 1, "database": "data/studio.sqlite3",
                    "storage": "storage", "outputs": "outputs", "logs": "logs"}
        return json.loads(self.config_path.read_text(encoding="utf-8"))

