from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtGui import QPixmap


def capture_widget(widget, path: Path, name: str, app_name: str,
                   scenario: str, width: int, height: int,
                   capture_mode: str = "SYNTHETIC_FIXTURE_CAPTURE") -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    pixmap.save(str(path), "PNG")
    valid = path.is_file() and path.stat().st_size > 0
    return {
        "path": str(path),
        "name": name,
        "app": app_name,
        "scenario": scenario,
        "width": width,
        "height": height,
        "capture_mode": capture_mode,
        "captured": valid,
        "bytes": path.stat().st_size if valid else 0,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
