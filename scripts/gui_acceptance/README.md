# Reusable Qt GUI Acceptance Runner

This runner launches the real NewAssetApp and TrainingDatasetStudio Qt widgets
with temporary databases, synthetic media, and temporary output paths.

## Smoke

```powershell
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite smoke --app both
```

## Visual

```powershell
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite visual --app both --resolutions 1280x720,1366x768,1920x1080
```

## Application selection

```powershell
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite smoke --app newassetapp
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite smoke --app studio
```

## Selected scenarios

```powershell
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite smoke --app newassetapp --scenarios smoke,normal,professional,layout
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite visual --app studio --scenarios smoke,workflow
```

Use `--no-capture` to run the workflows without PNG capture and `--keep` to
retain the temporary fixture/workspace. Temporary data is cleaned by default.

Reports and screenshots are created under:

`gui_screenshots/automated/<run-id>/`

The runner emits:

- `report.json`
- `report.md`
- `screenshots.json`
- scenario screenshots
- per-failure diagnostic text

Screenshots use `QWidget.grab()` and are Qt-rendered widget captures. They are
not claimed to be native Windows desktop captures. The smoke suite is intended
after ordinary code changes; the visual suite is intended for major UI/workflow
releases.
