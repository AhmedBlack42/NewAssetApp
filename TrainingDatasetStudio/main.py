from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from studio import __version__
from studio.config import StudioConfig
from studio.gui import StudioWindow
from studio.store import StudioStore


def _acceptance_studio_config(argv: list[str]) -> StudioConfig:
    if "--acceptance-root" not in argv:
        return StudioConfig()
    index = argv.index("--acceptance-root")
    if index + 1 >= len(argv):
        raise ValueError("Acceptance launch requires --acceptance-root <path>.")
    return StudioConfig.for_acceptance(argv[index + 1])


def main() -> int:
    args = list(sys.argv[1:])
    config = _acceptance_studio_config(args)
    config.ensure_directories()
    logging.basicConfig(filename=config.log_dir / "studio.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger = logging.getLogger("training_dataset_studio")
    store = StudioStore(config.database_path)
    store.initialize()
    app = QApplication(sys.argv)
    app.setApplicationName("TrainingDatasetStudio")
    app.setOrganizationName("NewAssetAppTraining")
    window = StudioWindow(config, store)
    window.setWindowTitle(f"TrainingDatasetStudio {__version__}")
    window.show()
    logger.info("Studio started with Python %s; database=%s", sys.version.split()[0], config.database_path)
    if "--smoke" in sys.argv:
        QTimer.singleShot(1500, app.quit)
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("Studio startup failed")
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "TrainingDatasetStudio could not start", f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)

