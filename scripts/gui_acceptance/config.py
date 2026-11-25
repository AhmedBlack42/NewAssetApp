from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUI_SCREENSHOTS = PROJECT_ROOT / "gui_screenshots"


@dataclass(frozen=True)
class AcceptanceConfig:
    suite: str = "smoke"
    app: str = "both"
    resolutions: tuple[tuple[int, int], ...] = ((1366, 768),)
    scenarios: tuple[str, ...] = ()
    capture: bool = True
    keep: bool = False
    phase3: bool = False
    phase4: bool = False


def parse_args(argv: list[str] | None = None) -> AcceptanceConfig:
    parser = argparse.ArgumentParser(description="Run disposable NewAssetApp/Studio Qt GUI acceptance.")
    parser.add_argument("--suite", choices=("smoke", "visual"), default="smoke")
    parser.add_argument("--app", choices=("newassetapp", "studio", "both"), default="both")
    parser.add_argument("--resolutions", default="1366x768")
    parser.add_argument("--scenarios", default="")
    parser.add_argument("--no-capture", action="store_true")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--phase3", action="store_true")
    parser.add_argument("--phase4", action="store_true")
    args = parser.parse_args(argv)
    resolutions = tuple(
        tuple(int(value) for value in item.split("x", 1))
        for item in args.resolutions.split(",")
        if "x" in item
    )
    if args.suite == "visual" and not resolutions:
        resolutions = ((1280, 720), (1366, 768), (1920, 1080))
    elif args.suite == "visual":
        resolutions = tuple(resolutions)
    else:
        resolutions = ((1366, 768),)
    return AcceptanceConfig(
        suite=args.suite,
        app=args.app,
        resolutions=resolutions,
        scenarios=tuple(value for value in args.scenarios.split(",") if value),
        capture=not args.no_capture,
        keep=args.keep,
        phase3=args.phase3,
        phase4=args.phase4,
    )
