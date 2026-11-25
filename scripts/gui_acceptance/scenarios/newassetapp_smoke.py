from __future__ import annotations

from pathlib import Path

from app.application import create_application
from app.config import AppConfig
from app.core.database import Database

from ..assertions import assert_in_window, assert_visible
from ..qt_helpers import process_events
from ..screenshot_capture import capture_widget


def run(app, fixture, output_root: Path, resolutions, capture: bool = True):
    config = AppConfig(
        data_dir_override=fixture.root / "app" / "data",
        output_dir_override=fixture.output_dir,
        logs_dir_override=fixture.root / "app" / "logs",
        database_path_override=fixture.app_database,
    )
    database = Database(fixture.app_database)
    database.initialize()
    window = create_application(config)
    window.show()
    process_events(app)
    screenshots = []
    for width, height in resolutions:
        window.resize(width, height)
        process_events(app)
        assert_visible(window, "NewAssetApp window")
        assert_visible(window.folder_edit, "Choose Folder")
        assert_visible(window.scan_button, "Scan Images")
        assert_visible(window.workspace_tabs, "Application tabs")
        assert_in_window(window, window.scan_button, "Scan Images")
        path = output_root / "newassetapp" / f"{width}x{height}_main.png"
        if capture:
            screenshots.append(capture_widget(
                window, path, f"{width}x{height}_main.png",
                "newassetapp", "startup", width, height))
    window.close()
    process_events(app)
    return {"pass": True, "screenshots": screenshots,
            "database": str(fixture.app_database)}
