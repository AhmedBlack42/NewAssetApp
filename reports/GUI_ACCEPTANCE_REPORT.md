# GUI Acceptance Report

Date: 2026-11-22

## Executive summary

This pass established a live launch baseline, automated disposable interaction
evidence, and page-level layout evidence. It did not claim live headed-desktop
acceptance for workflows that were only exercised by Qt fixtures or database
tests.

The live NewAssetApp launcher opened and exposed the Normal Processing and
Professional Review workstations. The live launcher also automatically migrated
the existing NewAssetApp database from schema 23 to 24 while initializing.
No production source media or training record was intentionally modified.

Studio live launch could not be completed: the `.ps1` association opened
Notepad rather than executing Studio, and direct PowerShell launch was blocked
by UI safety policy.

## Live headed-desktop baseline

### NewAssetApp

- Launcher: `run_app.bat`
- Observed window: `NewAssetApp - Normal Processing and Professional Review`
- Observed window size: 1360x749
- Normal Processing was visible.
- Professional Review was reachable as a tab.
- The crop gallery, 2807-suggestion count, scrollable classification inspector,
  Fullbody state controls, Body Images binary controls, Arousal/Corruption
  controls, location controls, export preview, navigation, and export actions
  were exposed.
- Computer Use accessibility text was readable.
- Screenshot capture returned no image, so the observation is not a visual PNG
  acceptance artifact.
- The app was left open after a close action was interrupted by concurrent user input.

### TrainingDatasetStudio

- Existing launcher: `TrainingDatasetStudio/run_app.ps1`
- BLOCKED: `.ps1` opened in Notepad through the OS file association.
- Direct PowerShell launch was blocked by UI safety policy.
- No live Studio page interaction or headed-desktop capture was obtained.

## Automated GUI evidence

Latest visual run:

- `gui_screenshots/automated/20261122_142103_5776/`
- Overall: PASS
- Synthetic Qt captures at 1280x720, 1366x768, and 1920x1080
- NewAssetApp Normal Processing: PASS
- NewAssetApp Professional Review: PASS
- Studio smoke and workflow: PASS

This evidence proves fixture/widget layout and navigation, not headed-desktop
workflow completion.

Unique acceptance evidence directory:

`gui_screenshots/acceptance/20261122_170446_live_observation/`

Synthetic screenshots were copied here; they must not be described as live
desktop evidence.

## Workflow acceptance matrix

| Workflow | Automated/DB | Live headed | Status | Evidence |
|---|---|---|---|---|
| NewAssetApp launch | PASS | PASS window | PASS/blocked screenshot | `run_app.bat`, AX window observation |
| Normal Processing layout | PASS | PARTIAL | BLOCKED for live save/export | Qt fixture + live AX |
| Fullbody Normal Processing | PASS unit/export | Not completed | BLOCKED | Disposable crop/export suite |
| Body Images Normal Processing | PASS interaction fixture | Not completed | BLOCKED live | TDA test + fixture runner |
| Cum/Accessory both positive | PASS DB/fixture | Not completed | BLOCKED live | `test_tda_001_002.py` |
| Cum/Accessory explicit none | PASS DB/fixture | Not completed | BLOCKED live | `test_tda_001_002.py` |
| Pending/partial Body Images | PASS DB/fixture | Not completed | BLOCKED live | `test_tda_001_002.py` |
| Portrait/tPortrait | PASS DB/layout | Not completed | BLOCKED live | Existing test suite |
| Arousal | PASS DB/fixture | Not completed | BLOCKED live | TDA and independent-review tests |
| Corruption | PASS DB/fixture | Not completed | BLOCKED live | TDA and independent-review tests |
| Clothing Broad/Detailed | PASS DB/handoff | Not completed | BLOCKED live | Existing suite |
| Location | PASS DB/layout | Not completed | BLOCKED live | Existing suite |
| Invalid/rejected crop | PASS DB | Not completed | BLOCKED live | Existing suite |
| Professional detection navigation | PASS Qt fixture | PARTIAL live tab/AX | BLOCKED full interaction | Live AX + fixture |
| Professional class/bbox correction | PASS DB | Not completed | BLOCKED live | Independent-review tests |
| Handoff export/import | PASS disposable | N/A | PASS disposable | Handoff tests |
| Studio page layout | PASS Qt fixture | BLOCKED launch | BLOCKED live | Layout suite |
| Studio import to Dataset | PASS disposable | BLOCKED launch | BLOCKED live GUI | Studio workflow suite |
| Dataset Builder/Validation | PASS disposable | BLOCKED launch | BLOCKED live GUI | Studio suite |
| Immutable version/package | PASS disposable | BLOCKED launch | BLOCKED live GUI | Studio suite |
| 5 GB segment policy | PASS unit | N/A | PASS unit | Segment suite |
| RAR packaging | Not tested/intentional scope exclusion | N/A | BLOCKED/deferred | `STUDIO-RAR-001` |

## Confirmed live NewAssetApp observations

- Window and tab structure opened successfully.
- Normal Processing classification controls exist in a scrollable right inspector.
- The live inspector remains vertically larger than the visible area.
- No live crop was selected or modified during acceptance.
- No production export or source image was changed.
- Existing data remained production data; no save/export action was taken.

## Concrete defect/limitation list

### GUA-001 — Live Studio launcher association

- Severity: High
- Workflow: TrainingDatasetStudio launch
- Reproduction: execute `TrainingDatasetStudio/run_app.ps1`.
- Actual: OS association opened the script in Notepad.
- Expected: existing launcher starts Studio with its dedicated environment.
- Code: launcher file is present but has no working executable association.
- Recommendation: bind launcher through an approved desktop shortcut or verified
  PowerShell invocation method. Do not alter virtual environments or install dependencies.
- Verification: headless/disposable Qt suite is not a substitute for live launch.
- Fix status: `TrainingDatasetStudio/run_app.bat` was added as an explicit desktop
  launcher. It invokes the existing `run_app.ps1` and dedicated environment.

### GUA-002 — Live headed screenshot unavailable

- Severity: Medium
- Workflow: Live NewAssetApp/Studio evidence
- Reproduction: request a live screenshot from Computer Use.
- Actual: AX state was returned, but no screenshot image was captured.
- Expected: real PNG or a documented fallback.
- Recommendation: use a Windows-native screenshot method approved for headed
  desktop capture, or keep synthetic evidence separately.

### GUA-003 — Normal Processing right inspector scrolling

- Severity: Medium
- Workflow: Normal Processing
- Reproduction: open live app at 1360x749, inspect classification controls.
- Actual: content height exceeds its visible 489-pixel viewport.
- Expected: key controls and state remain discoverable without excessive scrolling.
- Evidence: live AX geometry; 279×577 content in 248×489 viewport.
- Recommendation: compact or sectioned inspector only after live workflow acceptance.

### GUA-004 — Production database migration occurred during live launch

- Severity: High
- Workflow: NewAssetApp launch
- Reproduction: launch live app with the existing production database.
- Actual: schema migrated automatically from 23 to 24.
- Expected: acceptance must not run production migrations.
- Root: application initialization executes pending migrations.
- Impact: additive schema change occurred despite acceptance safety instructions.
- No source/export/training-record change was intentionally made.
- Recommendation: add an explicit acceptance launcher mode that opens against a
  disposable database, or require migration approval before live launch.
- Fix status: NewAssetApp now accepts `--acceptance-db`,
  `--acceptance-data`, `--acceptance-output`, and `--acceptance-logs`.
  Studio now accepts `--acceptance-root`. Focused tests verify these paths stay
  isolated. Repeated acceptance use must still supply an explicit disposable
  database; the fixed launch flags were not yet exercised through a headed app.

## Existing RAR backlog

**STUDIO-RAR-001 — External RAR Archive Integration**

Deferred. No RAR/ZIP/7z implementation or investigation was performed beyond
the separate backlog record.

## Test evidence

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_tda_001_002 tests.test_training_heads_handoff tests.test_independent_classification_reviews -v
```

Result: 30 tests passed in 57.121 seconds.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_main_window_layout tests.test_studio_gui_layout tests.test_gui_acceptance_runner tests.test_tda_001_002 -v
```

Result: 16 tests passed in 10.806 seconds.

Full NewAssetApp:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*.py" -v
```

Result: 186 tests passed in 75.391 seconds.

Full Studio:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/studio -p "test*.py" -v
```

Result: 22 tests passed in 83.559 seconds.

GUI visual runner:

```powershell
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite visual --app both --resolutions 1280x720,1366x768,1920x1080
```

Result: PASS. Final run:
`gui_screenshots/automated/20261122_153748_12044/`

Python compilation and diff:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app TrainingDatasetStudio tests
git --no-pager diff --check
```

Both passed.

## Remaining implementation order

1. Exercise the new disposable-database launch flags through headed desktop apps.
2. Complete live Studio launcher/capture verification with its `.bat` entry point.
3. Complete headed Normal Processing save/reload/export acceptance.
4. Complete headed Professional Review correction and independent-task acceptance.
5. Complete Studio import→dataset→validation→version→package acceptance.
6. Resolve GUA-003 only after live workflow evidence identifies it as blocking.
7. Keep RAR/Colab integration separate as `STUDIO-RAR-001`.
