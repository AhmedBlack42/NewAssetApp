from __future__ import annotations

from pathlib import Path

from TrainingDatasetStudio.studio.config import StudioConfig
from TrainingDatasetStudio.studio.store import StudioStore
from TrainingDatasetStudio.studio.gui import StudioWindow

from ..qt_helpers import process_events
from ..screenshot_capture import capture_widget


def run(app, fixture, output_root: Path, resolutions, capture: bool = True):
    config = StudioConfig(root=fixture.root / "studio")
    config.ensure_directories()
    store = StudioStore(config.database_path)
    store.initialize()
    window = StudioWindow(config, store)
    window.show()
    process_events(app)
    screenshots = []
    for width, height in resolutions:
        window.resize(width, height)
        process_events(app)
        for row in range(window.studio_navigation.count()):
            window.studio_navigation.setCurrentRow(row)
            process_events(app)
            label = window.studio_navigation.item(row).text().lower().replace(" ", "_").replace("/", "_")
            path = output_root / "studio" / f"{width}x{height}_{label}.png"
            if capture:
                screenshots.append(capture_widget(
                    window, path, f"{width}x{height}_{label}.png",
                    "studio", label, width, height))
    window.close()
    process_events(app)
    return {"pass": True, "screenshots": screenshots,
            "database": str(config.database_path)}
