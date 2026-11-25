# GUI Acceptance Phase 2 Report

Date: 2026-11-22

## Executive summary

Phase 2 established that both applications can run against an isolated
acceptance workspace, but did not fabricate a complete live headed-desktop
acceptance. NewAssetApp opened and Studio opened as separate live windows.

The live NewAssetApp interaction was blocked by concurrent user input detected
by the desktop automation backend. Live Studio navigation was also not reliable
through the backend: row selection changed, but page switching did not complete
in one observed run. Automated real-widget and disposable integration tests did
complete and pass.

Concrete defects found and fixed:

- Studio navigation had no real History page and remapped row 8 to a removed
  activation path.
- Studio startup referenced stale `refresh_activation()` initialization.
- Acceptance launch isolation was upgraded to fail closed when an acceptance
  root overlaps NewAssetApp/Studio project or production storage.

## Isolation proof

Run ID: `20261122_174826_phase2`

Acceptance root:
`C:\Users\asker\AppData\Local\Temp\newassetapp_acceptance_phase2_20261122_174826`

Resolved paths:

- NewAssetApp database:
  `C:\Users\asker\AppData\Local\Temp\newassetapp_acceptance_phase2_20261122_174826\app\newassetapp.sqlite3`
- NewAssetApp media/data:
  `C:\Users\asker\AppData\Local\Temp\newassetapp_acceptance_phase2_20261122_174826\app\data`
- NewAssetApp output:
  `C:\Users\asker\AppData\Local\Temp\newassetapp_acceptance_phase2_20261122_174826\exports`
- NewAssetApp logs:
  `C:\Users\asker\AppData\Local\Temp\newassetapp_acceptance_phase2_20261122_174826\logs`
- Studio root:
  `C:\Users\asker\AppData\Local\Temp\newassetapp_acceptance_phase2_20261122_174826\studio`
- Studio database:
  `C:\Users\asker\AppData\Local\Temp\newassetapp_acceptance_phase2_20261122_174826\studio\data\studio.sqlite3`

Fail-closed checks passed:

- All resolved paths are under the acceptance root.
- Acceptance root does not overlap the repository or production directories.
- Production `data/newassetapp.sqlite3` was not opened.
- Production `TrainingDatasetStudio/data/studio.sqlite3` was not opened.
- No production source media or exports were selected.

Disposable database counts:

- 288 source images
- 2274 YOLO detections
- 2275 asset proposals
- 2 training examples
- 2 Normal Processing choices
- 0 Normal exports
- Studio: 0 bundles, 0 records, 0 registries, 0 datasets, 0 versions, 0 runs

These counts reflect the disposable launch workspace and acceptance fixture,
not production records.

## Live application launch

### NewAssetApp

- Status: OPENED
- Launch command: existing `run_app.bat` with acceptance overrides.
- Window title:
  `NewAssetApp - Normal Processing and Professional Review`
- Window size: 1360x749
- Live evidence:
  - 11 disposable suggestions were visible.
  - Normal Processing crop gallery, preview, classification inspector,
    export controls, and scrollable sections were visible.
  - Professional Review tab was available.
- Interaction status:
  - One crop selection succeeded.
  - Mutating category/check-box actions were declined because the desktop
    backend detected concurrent user input.
- Headed screenshot:
  BLOCKED — the screenshot backend returned accessibility text without an image.

### TrainingDatasetStudio

- Status: OPENED
- Launch command: existing `TrainingDatasetStudio/run_app.bat`
  with `--acceptance-root`.
- Window title: `TrainingDatasetStudio 0.1.0`
- Window size: 1370x749
- Live evidence:
  - All nine navigation labels were visible.
  - Model Projects showed 0 projects, 0 segments, 0 accepted records.
  - Studio declared its storage and database independent from NewAssetApp.
- Navigation status:
  PARTIAL/BLOCKED — row selection changed, but the Import/Activation page did
  not switch in the observed live automation attempt.
- Import status:
  TEST-ONLY — the actual GUI import could not be completed reliably.
- Headed screenshot:
  BLOCKED — the screenshot backend returned accessibility text without an image.

## Automated and synthetic evidence

Latest synthetic visual run:

`gui_screenshots/automated/20261122_162545_6584/`

It passed both NewAssetApp and Studio visual scenarios at:

- 1280x720
- 1366x768
- 1920x1080

This run is synthetic `QWidget.grab()` evidence. It is not headed-desktop
evidence.

Unique evidence directory:

`gui_screenshots/acceptance/20261122_174826_phase2/`

## Acceptance matrix

| Workflow | Status | Evidence |
|---|---|---|
| Production isolation | PASS | Disposable root outside repository; fail-closed launch test passed |
| NewAssetApp live launch | PARTIAL | Live window and AX structure observed; no mutation/save |
| NewAssetApp live Normal save/reload/export | BLOCKED | Concurrent user input rejected mutation |
| Body Images live four combinations | BLOCKED live | 6 focused DB/fixture tests pass |
| Portrait/tPortrait live workflow | TEST-ONLY | Existing unit/GUI layout suites |
| Arousal/Corruption live workflow | TEST-ONLY | Existing DB/eligibility suites |
| Clothing live workflow | TEST-ONLY | Existing DB/handoff suites |
| Location live workflow | TEST-ONLY | Existing DB/layout suites |
| Invalid crop live workflow | TEST-ONLY | Existing DB suites |
| Professional live detection navigation | BLOCKED | Automated navigation fixture only |
| Professional live corrections | TEST-ONLY | Database and independent-task tests |
| Handoff/export/import | PASS disposable | Bundle, importer, package tests pass |
| Studio live launch | PASS | Isolated window opened |
| Studio live page navigation | PARTIAL | Nine labels visible; page switch unreliable in live automation |
| Studio live import | BLOCKED | GUI automation could not complete page switch |
| Studio live dataset/version/package | BLOCKED | Requires live GUI navigation/import |
| Studio real-widget navigation fix | PASS automated | `test_studio_gui_layout` passes |
| Studio import/dataset/package | TEST-ONLY | Disposable workflow suite passed |
| 5 GB segment policy | PASS | Existing capacity suite passed |
| RAR package | DEFERRED | `STUDIO-RAR-001` only |

## Defects and fixes

### GAP-001 — Studio live navigation did not switch page

- Severity: High
- Reproduction: click/select Import / Activation or History in the live Studio
  window.
- Actual: row selection changed, visible page remained Model Projects.
- Expected: selected row changes to the corresponding page.
- Root: navigation refresh list and page construction were misaligned after
  activation was replaced in the UI.
- Fix: added a real History page and mapped row 8 to it; retained Import /
  Activation on row 7.
- Regression: `test_studio_gui_layout` passes.
- Remaining: live desktop page switching still could not be confirmed through
  the current automation backend.

### GAP-002 — Desktop mutation blocked by concurrent user input

- Severity: Medium
- Reproduction: set Normal Processing category or checkbox in the live app.
- Actual: backend reported `interrupted` due concurrent user input.
- Expected: accepted user action commits to the disposable database.
- Root: external desktop interaction conflict, not a confirmed application bug.
- Impact: no live save/reload/export acceptance was completed.
- Next: rerun from an interaction-free desktop session with the disposable
  launcher arguments.

### GAP-003 — Fail-closed acceptance launch

- Severity: High
- Actual: production/acceptance overlap was possible in the previous launch
  contract.
- Fix: NewAssetApp requires `--acceptance-root` and rejects project/production
  overlap.
- Fix: Studio uses `StudioConfig.for_acceptance()` and rejects its project root
  or an overlapping parent/child.
- Regression: isolated launcher tests pass.

## Test evidence

Full NewAssetApp suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
```

Result: 186 tests passed in 98.552 seconds.

Full Studio suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\studio -p "test*.py" -v
```

Result: 22 tests passed in 98.213 seconds.

Visual runner:

```powershell
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite visual --app both --resolutions 1280x720,1366x768,1920x1080
```

Result: PASS.

Compilation and diff:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app TrainingDatasetStudio tests
git --no-pager diff --check
```

Both passed.

## Deferred backlog

- `STUDIO-RAR-001 — External RAR Archive Integration`
- Shared-training resume
- Production activation and rollback
- 31/32 YOLO registry mapping
- Broad GUI redesign

## Final maturity

NewAssetApp:

- Live launch is proven.
- Mutation and live save/reload acceptance is not complete.
- Database, handoff, and eligibility behavior are well covered in disposable tests.

TrainingDatasetStudio:

- Live launch is proven.
- Live page navigation/import/dataset/package acceptance is not complete.
- Disposable real-widget, import, dataset, segment, and package behavior passes tests.
