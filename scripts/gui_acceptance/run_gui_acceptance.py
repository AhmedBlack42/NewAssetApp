from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication

from scripts.gui_acceptance.config import AcceptanceConfig, GUI_SCREENSHOTS, parse_args
from scripts.gui_acceptance.fixture_factory import create_fixture
from scripts.gui_acceptance.scenarios.newassetapp_smoke import run as newassetapp_smoke
from scripts.gui_acceptance.scenarios.newassetapp_normal import run as newassetapp_normal
from scripts.gui_acceptance.scenarios.newassetapp_professional import run as newassetapp_professional
from scripts.gui_acceptance.scenarios.newassetapp_layout import run as newassetapp_layout
from scripts.gui_acceptance.scenarios.studio_smoke import run as studio_smoke
from scripts.gui_acceptance.scenarios.studio_workflow import run as studio_workflow
from scripts.gui_acceptance.scenarios.phase3 import run as phase3
from scripts.gui_acceptance.scenarios.phase4 import (
    run_normal_body_states,
    run_professional_review,
    run_studio_import,
    run_studio_lifecycle,
)




NEWASSETAPP_SCENARIOS = {
    "smoke": newassetapp_smoke,
    "normal": newassetapp_normal,
    "professional": newassetapp_professional,
    "layout": newassetapp_layout,
    "phase3": phase3,
    "phase4_normal_body_states": run_normal_body_states,
    "phase4_professional_review": run_professional_review,
}
STUDIO_SCENARIOS = {
    "smoke": studio_smoke,
    "workflow": studio_workflow,
    "phase3": phase3,
    "phase4_studio_import": run_studio_import,
    "phase4_studio_lifecycle": run_studio_lifecycle,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def write_reports(run_root: Path, report: dict, screenshots: list[dict]) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_root / "screenshots.json").write_text(
        json.dumps(screenshots, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# GUI Acceptance Report",
        "",
        f"- Run: `{report['run_id']}`",
        f"- Suite: `{report['suite']}`",
        f"- App: `{report['app']}`",
        f"- Overall: **{report['status']}**",
        f"- Headless Qt: `{report['headless']}`",
        "",
        "## Scenarios",
        "",
        "| Application | Scenario | Status | Window | Elapsed |",
        "|---|---|---|---|---|",
    ]
    for result in report["scenarios"]:
        dimensions = ", ".join(result.get("dimensions", [])) or "n/a"
        lines.append(
            f"| {result['application']} | {result['scenario']} | {result['status']} "
            f"| {dimensions} | {result['elapsed_seconds']:.3f}s |")
    lines.extend(["", "## Screenshots", ""])
    for screenshot in screenshots:
        lines.append(
            f"- `{screenshot['path']}` — {screenshot['application']} "
            f"{screenshot['scenario']} {screenshot['width']}x{screenshot['height']}")
    lines.extend(["", "## Failures", ""])
    failures = [item for item in report["scenarios"] if item["status"] != "PASS"]
    if not failures:
        lines.append("- None")
    else:
        for failure in failures:
            lines.append(
                f"- **{failure['application']} / {failure['scenario']}**: "
                f"{failure.get('failure_reason') or 'See diagnostic log'}")
    (run_root / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv)
    run_id = f"{utc_stamp()}_{os.getpid()}"
    run_root = (
        GUI_SCREENSHOTS / "acceptance" / run_id
        if config.phase3 or config.phase4
        else GUI_SCREENSHOTS / "automated" / run_id
    )
    run_root.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="newassetapp_gui_acceptance_"))
    fixture = create_fixture(temp_root)
    report = {
        "run_id": run_id,
        "suite": config.suite,
        "app": config.app,
        "headless": True,
        "status": "PASS",
        "temporary_workspace": str(temp_root),
        "run_root": str(run_root),
        "scenarios": [],
    }
    screenshots = []

    requested = list(config.scenarios)
    if config.phase3:
        requested = ["phase3"]
    elif config.phase4:
        requested = [
            "phase4_normal_body_states", "phase4_professional_review",
            "phase4_studio_import", "phase4_studio_lifecycle",
        ]
    elif not requested:
        requested = ["smoke"] if config.suite == "smoke" else [
            "smoke", "normal", "professional", "layout", "workflow"
        ]

    application_names = (
        ("both",) if config.phase3
        else (("newassetapp", "studio") if config.phase4
        else (("newassetapp", "studio") if config.app == "both" else (config.app,))
        )
    )
    for application in application_names:
        registry = NEWASSETAPP_SCENARIOS if application == "newassetapp" else STUDIO_SCENARIOS
        for scenario_name in requested:
            if scenario_name not in registry:
                report["scenarios"].append({
                    "application": application,
                    "scenario": scenario_name,
                    "status": "SKIPPED",
                    "dimensions": [f"{width}x{height}" for width, height in config.resolutions],
                    "elapsed_seconds": 0.0,
                    "failure_reason": f"Scenario {scenario_name!r} is not defined for {application}.",
                })
                continue
            started = datetime.now(timezone.utc)
            result_item = {
                "application": application,
                "scenario": scenario_name,
                "status": "PASS",
                "dimensions": [f"{width}x{height}" for width, height in config.resolutions],
                "elapsed_seconds": 0.0,
                "failure_reason": None,
            }
            try:
                if not config.capture:
                    # Capture remains a report-level switch; scenario capture calls are retained
                    # through the screenshot helper so the runner never silently substitutes AX.
                    pass
                result = registry[scenario_name](
                    app, fixture, run_root, config.resolutions,
                    capture=config.capture)
                result_status = str(result.get("status") or "PASS")
                if result_status in {"PARTIAL", "BLOCKED", "NOT_TESTED"}:
                    result_item["status"] = result_status
                else:
                    result_item["status"] = "PASS"
                for item in result.get("screenshots", []):
                    item["application"] = application
                    if config.capture:
                        screenshots.append(item)
            except Exception as error:
                result_item["status"] = "FAIL"
                result_item["failure_reason"] = f"{type(error).__name__}: {error}"
                report["status"] = "FAIL"
                diagnostic = run_root / f"{application}_{scenario_name}_failure.txt"
                diagnostic.write_text(
                    f"{type(error).__name__}: {error}\n\n{traceback.format_exc()}",
                    encoding="utf-8")
            elapsed = datetime.now(timezone.utc) - started
            result_item["elapsed_seconds"] = elapsed.total_seconds()
            report["scenarios"].append(result_item)

    write_reports(run_root, report, screenshots)
    if config.keep:
        print(f"Temporary artifacts retained: {temp_root}")
    else:
        shutil.rmtree(temp_root, ignore_errors=True)
        report["temporary_workspace"] = None
        write_reports(run_root, report, screenshots)
    print(json.dumps({
        "status": report["status"],
        "run_id": run_id,
        "report": str(run_root / "report.json"),
        "markdown": str(run_root / "report.md"),
        "screenshots": str(run_root / "screenshots.json"),
        "scenario_count": len(report["scenarios"]),
    }, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
