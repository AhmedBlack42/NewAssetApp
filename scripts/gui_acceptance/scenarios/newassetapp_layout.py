from __future__ import annotations

from pathlib import Path

from .newassetapp_smoke import run as smoke


def run(app, fixture, output_root: Path, resolutions, capture: bool = True):
    return smoke(app, fixture, output_root, resolutions, capture=capture)
