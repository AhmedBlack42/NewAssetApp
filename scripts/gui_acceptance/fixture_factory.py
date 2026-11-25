from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.core.database import Database
from app.core.training_source_exporter import export_training_source_bundle
from TrainingDatasetStudio.studio.store import StudioStore


@dataclass(frozen=True)
class AcceptanceFixture:
    root: Path
    source_path: Path
    app_database: Path
    studio_database: Path
    output_dir: Path
    handoff_dir: Path


def create_fixture(root: Path) -> AcceptanceFixture:
    root.mkdir(parents=True, exist_ok=True)
    source_dir = root / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parents[2]
    disposable_app_data = root / "app" / "data"
    disposable_app_data.mkdir(parents=True, exist_ok=True)
    # Copy taxonomy assets only: model/checkpoint directories and production media
    # remain untouched and are never used as acceptance fixtures.
    shutil.copytree(project_root / "data" / "tags",
                    disposable_app_data / "tags",
                    dirs_exist_ok=True)
    disposable_models = disposable_app_data / "models"
    disposable_models.mkdir(parents=True, exist_ok=True)
    production_models = project_root / "data" / "models"
    for model_file in production_models.rglob("*"):
        if model_file.is_file() and model_file.suffix.lower() in {".json", ".txt"}:
            destination = disposable_models / model_file.relative_to(production_models)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(model_file, destination)
    source = source_dir / "gui_acceptance_fixture.png"
    image = Image.new("RGB", (920, 1200), "white")
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = ((x * 3) % 255, (y * 2) % 255, ((x + y) % 255))
    image.save(source)

    app_db = root / "app" / "newassetapp.sqlite3"
    app_db.parent.mkdir(parents=True, exist_ok=True)
    database = Database(app_db)
    database.initialize()
    source_id, _ = database.upsert_source_image({
        "path": str(source.resolve()),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "width": 920,
        "height": 1200,
        "file_size": source.stat().st_size,
        "modified_ns": source.stat().st_mtime_ns,
        "source_root": str(source_dir.resolve()),
    })

    detections = (
        (1, "face", [60, 80, 220, 300]),
        (2, "portrait_frame", [180, 60, 380, 330]),
        (3, "boobs", [240, 320, 480, 560]),
        (4, "ass", [420, 600, 650, 820]),
        (5, "pussy", [220, 700, 420, 930]),
        (6, "legs", [520, 800, 760, 1120]),
        (20, "fullbody_maid", [50, 200, 870, 1160]),
        (24, "location_office", [50, 50, 870, 170]),
        (10, "boobs_cover_item", [260, 330, 500, 570]),
        (0, "person", [650, 350, 850, 700]),
    )
    for index, (class_id, class_name, bbox) in enumerate(detections):
        database.record_yolo_detection(
            source_id, model_id="gui-fixture", model_digest="disposable-fixture",
            class_id=class_id, class_name=class_name, confidence=0.81 + index * 0.01,
            bbox_xyxy=bbox,
        )
    database.create_manual_proposal(source_id)
    manual_detection = database.create_manual_detection(
        source_id, [690, 360, 860, 540])
    with database.connect() as connection:
        body_row = connection.execute(
            "SELECT p.id,d.class_name FROM asset_proposals p JOIN yolo_detections d ON d.id=p.detection_id "
            "WHERE d.class_name='boobs' ORDER BY d.id LIMIT 1").fetchone()
        fullbody_row = connection.execute(
            "SELECT p.id FROM asset_proposals p JOIN yolo_detections d ON d.id=p.detection_id "
            "WHERE d.class_name='fullbody_maid' ORDER BY d.id LIMIT 1").fetchone()
    if body_row:
        database.save_normal_crop_choice(
            int(body_row["id"]), "body_images", main_tag="boobs",
            subtags=["cum"], body_images_cnn_target="bodypart_cum")
        database.confirm_normal_crop_classification(int(body_row["id"]))
    if fullbody_row:
        database.save_normal_crop_choice(
            int(fullbody_row["id"]), "fullbody", main_tag="clothed",
            fullbody_state="clothed", fullbody_cnn_target="clothed")
        database.confirm_normal_crop_classification(int(fullbody_row["id"]))

    studio_db = root / "studio" / "studio.sqlite3"
    studio_db.parent.mkdir(parents=True, exist_ok=True)
    studio_root = root / "studio"
    shutil.copytree(project_root / "TrainingDatasetStudio" / "contracts",
                    studio_root / "contracts",
                    dirs_exist_ok=True)
    shutil.copytree(project_root / "TrainingDatasetStudio" / "registries",
                    studio_root / "registries",
                    dirs_exist_ok=True)
    studio_store = StudioStore(studio_db)
    studio_store.initialize()
    output_dir = root / "studio_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    handoff_dir = root / "handoff"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    export_training_source_bundle(database, handoff_dir)
    return AcceptanceFixture(
        root=root,
        source_path=source,
        app_database=app_db,
        studio_database=studio_db,
        output_dir=output_dir,
        handoff_dir=handoff_dir,
    )
