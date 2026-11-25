import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [%(process)d:%(threadName)s]: %(message)s",
        handlers=[
            RotatingFileHandler(log_dir / "newassetapp.log", maxBytes=2_000_000,
                                backupCount=5, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    logging.getLogger(__name__).info("Application logging initialized; log directory=%s", log_dir)
