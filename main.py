from __future__ import annotations

import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from app.application import create_application
from app.config import AppConfig
from app.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def _acceptance_config(argv: list[str]) -> AppConfig:
    config = AppConfig.load()
    project_root = Path(__file__).resolve().parent
    acceptance_root = None
    if any(arg.startswith("--acceptance-") for arg in argv):
        if "--acceptance-root" not in argv:
            raise ValueError("Acceptance launch requires --acceptance-root.")
        root_index = argv.index("--acceptance-root")
        if root_index + 1 >= len(argv):
            raise ValueError("Acceptance launch requires --acceptance-root <path>.")
        acceptance_root = Path(argv[root_index + 1]).resolve()
        if (acceptance_root == project_root or project_root in acceptance_root.parents
                or acceptance_root in project_root.parents):
            raise ValueError("Acceptance root must not overlap the NewAssetApp project or production storage.")
    database = None
    data_dir = None
    output_dir = None
    logs_dir = None
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag == "--acceptance-db" and index + 1 < len(argv):
            database = Path(argv[index + 1]).resolve()
            index += 2
            continue
        if flag == "--acceptance-data" and index + 1 < len(argv):
            data_dir = Path(argv[index + 1]).resolve()
            index += 2
            continue
        if flag == "--acceptance-output" and index + 1 < len(argv):
            output_dir = Path(argv[index + 1]).resolve()
            index += 2
            continue
        if flag == "--acceptance-logs" and index + 1 < len(argv):
            logs_dir = Path(argv[index + 1]).resolve()
            index += 2
            continue
        index += 1
    if database is None and any(arg.startswith("--acceptance-") for arg in argv):
        raise ValueError("Acceptance launch requires --acceptance-db.")
    if database is not None:
        acceptance_root = Path(argv[argv.index("--acceptance-root") + 1]).resolve()
        resolved_acceptance_paths = [
            database,
            Path(data_dir).resolve() if data_dir is not None else database.parent,
            Path(output_dir).resolve() if output_dir is not None else acceptance_root / "output",
            Path(logs_dir).resolve() if logs_dir is not None else acceptance_root / "logs",
        ]
        production_db = (project_root / "data" / "newassetapp.sqlite3").resolve()
        production_output = (project_root / "output").resolve()
        production_data = (project_root / "data").resolve()
        for resolved in resolved_acceptance_paths:
            if resolved != acceptance_root and acceptance_root not in resolved.parents:
                raise ValueError(f"Acceptance path escapes the disposable root: {resolved}")
            if resolved == production_db or resolved == production_output or resolved == production_data:
                raise ValueError("Acceptance path overlaps production NewAssetApp storage.")
    if database is not None:
        return AppConfig(
            app_name=config.app_name,
            recursive_scan=config.recursive_scan,
            confidence_threshold=config.confidence_threshold,
            supported_extensions=config.supported_extensions,
            yolo_checkpoint=config.yolo_checkpoint,
            clothing_classifier_checkpoint=config.clothing_classifier_checkpoint,
            clothing_classifier_class_map=config.clothing_classifier_class_map,
            asset_classifier_checkpoint=config.asset_classifier_checkpoint,
            asset_class_map=config.asset_class_map,
            data_dir_override=data_dir,
            output_dir_override=output_dir,
            logs_dir_override=logs_dir,
            database_path_override=database,
        )
    return config


def main() -> int:
    config = _acceptance_config(sys.argv[1:])
    configure_logging(config.logs_dir)
    app = QApplication(sys.argv)
    app.setApplicationName(config.app_name)
    app.setOrganizationName("NewAssetApp")
    try:
        window = create_application(config)
        window.show()
    except Exception as exc:
        logger.exception("Application startup failed")
        QMessageBox.critical(
            None,
            "Could not start NewAssetApp",
            f"The application could not initialize.\n\n{type(exc).__name__}: {exc}\n\n"
            "See the application log for details.",
        )
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
