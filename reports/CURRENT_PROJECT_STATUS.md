# NewAssetApp — Current Product and Audit Status

Date: 2026-11-22

This is the authoritative snapshot of the current implementation and verification
state. It replaces optimistic wording in older phase reports. It does not claim
live visual acceptance for captures that were not produced and inspected.

## Executive summary

- **Overall maturity:** Stabilizing; core database, review, export, and Studio
  workflows exist, but full manual visual acceptance is incomplete.
- **Safe for normal use:** Partially. Disposable end-to-end tests pass, but
  production data must remain under the normal review/export boundaries.
- **Professional Review:** Implemented substantially. Real Qt source/detection
  navigation, Inspector class/bbox interactions, and task-card controls were
  exercised. The Manual Proposal workflow now creates a detection-linked proposal
  and passed a focused real-Qt combined class/bbox save/reload gate.
- **Training-data collection:** Implemented for YOLO corrections, bbox approval,
  independent Professional CNN task reviews, and Normal Processing confirmations.
- **Studio integration:** Real Qt GUI import and dataset/version/package lifecycle
  passed in separate disposable scenarios. All nine navigation mappings also passed.
- **Not yet complete:** Full Professional Review dialog coverage for every head,
  every remaining Normal Processing export category, and headed-desktop acceptance.
- **Most serious risks:** stale documentation,
  incomplete live Studio verification, and no full manual Normal Processing
  walkthrough for every head/taxonomy combination.

## Verified baseline

- Full NewAssetApp suite: **196 tests passed**.
- Coverage includes YOLO corrected-annotation export, unchanged bbox approval,
  Studio handoff, independent CNN task review, crop staleness, and layouts.
- Schema migration 24 is applied.
- Live NewAssetApp launched with `run_app.bat`.
- Live Normal Processing and Professional Review were inspected at 1366x768.
- Automated screenshot capture returned accessibility text and no image for one
  attempt, but subsequent real PNG captures were produced for NewAssetApp and Studio.

## Repository and database facts

NewAssetApp database `data/newassetapp.sqlite3`:

- Schema migration: 22
- 358 source images
- 2807 YOLO detections
- 2822 asset proposals
- 351 CNN predictions
- 100 correction records
- 24 training examples
- 2 bbox reviews
- 17 Normal Processing crop choices
- 11 Normal Processing exports

TrainingDatasetStudio database `TrainingDatasetStudio/data/studio.sqlite3`:

- 1 imported bundle
- 21 records
- 4 registries
- 14 annotation events
- 5 training bundles
- No datasets
- No dataset versions
- No training runs
- No completed model artifacts

## Feature inventory

| Area | Status | Evidence |
|---|---|---|
| NewAssetApp launcher | Implemented / live verified | `run_app.bat` launched the app |
| Folder scan / analysis | Implemented / partially live verified | Live UI showed 358 sources and 2807 suggestions |
| Normal Processing | Implemented / live structure verified | Crop gallery, category controls, preview, export controls visible |
| Normal crop confirmation | Implemented / tests pass | Save/confirm methods in GUI and database |
| Normal filename/export grammar | Implemented / tests exist | `app/core/filename_grammar.py` |
| Professional Review navigation | Live verified | Tab, gallery, preview, inspector and action controls visible |
| YOLO class correction | Implemented / disposable E2E verified | `save_yolo_annotation_correction` |
| YOLO bbox edit/approval | Implemented / disposable E2E verified | Immutable original; effective bbox canonical |
| Independent CNN task cards | Implemented / tests pass | `classification_task_reviews` and eligibility helpers |
| Face → Corruption | Implemented / disposable tests pass | Target validation and independent review |
| YOLO/Studio handoff | Implemented / disposable tests pass | v4 bundle, importer and package tests |
| Studio GUI | Implemented / partial live verified | Dataset Records and Model Projects captured; remaining screens not all inspected |
| Studio projects/segments/validation | Implemented / database/tests exist | Store and GUI screens exist |
| Studio CPU training | Partial | Dry-run/package validation pass; real resume is unsupported |
| Production activation/rollback | Not implemented | Studio explicitly remains isolated |

## Training-data matrix

| Record type | User action | Verification |
|---|---|---|
| Unchanged bbox approval | `Approve BBox As-Is` | Canonical YOLO example/export verified |
| Edited bbox + class | Edit box, choose class, Save Correction | Corrected class/bbox exported and in Studio handoff |
| Class-only correction | Choose a new YOLO class and save | Preserves latest bbox |
| Bbox-only correction | Move/resize and save | Preserves latest approved class |
| Failed correction | Invalid save | Pending state and authoritative example remain unchanged |
| Shared CNN heads | Confirm/reject independent task | DB/target/export tests exist; full live GUI acceptance incomplete |
| Broad Clothing | Normal crop broad family/cover selection | Export implementation/tests exist |
| Detailed Clothing | Human-confirmed detailed tags | Registry/export implementation/tests exist |
| Corruption | Professional or Normal target | Eligibility and training paths exist; full live manual save incomplete |

## Live GUI findings

At 1366x768:

- Normal Processing and Professional Review tabs were visible.
- Normal Processing showed a crop gallery, category filter, classification pane,
  preview, navigation, and export controls.
- Professional Review showed source gallery, preview, bbox controls, detection
  inspector, and Detection/Classification Tasks/Tags Export tabs.
- Professional Review initially had no detection selected after tab switch.
- The Normal Processing right classification pane requires vertical scrolling
  for lower controls because its content height is larger than the visible area.

Screenshot inventory:

- `gui_screenshots/Capture.PNG`: Professional Review layout and detection list.
- `gui_screenshots/Capture2.PNG`: Others/correction dialog.
- `gui_screenshots/Capture3.PNG`: Fullbody/correction dialog.
- `gui_screenshots/Capture4.PNG`: Studio Dataset Records page with 21 records.
- `gui_screenshots/Capture5.PNG`: Studio Model Projects page with 5 projects and 21 accepted records.
- `gui_screenshots/Screenshot (1).png`: Windows Explorer, not NewAssetApp.

Real screenshot PNGs were produced for several existing and live surfaces.
They confirm layout, but do not replace recapture of 1280x720 and complete
interaction-based acceptance for every workflow.

## Confirmed defects and incomplete features

| ID | Severity | Finding | Evidence |
|---|---|---|---|
| NA-001 | High | Live screenshot capture is unavailable | Capture attempts returned AX text, no PNG |
| NA-002 | Medium | Documentation was stale about Studio | Root and Studio READMEs updated |
| NA-003 | Medium | Shared CNN training resume is not implemented | `TrainingDatasetStudio/studio/shared_train.py:62` |
| NA-004 | Medium | Studio activation is isolated and does not modify production | `TrainingDatasetStudio/studio/gui.py` |
| NA-005 | Medium | The 1366x768 Normal Processing pane requires lower-panel scrolling | Live AX geometry |

No production database, source image, model checkpoint, Girl Packer file,
training dataset, or existing export was modified during this audit.

## Documentation changes

- Added this authoritative status report.
- Updated the root README.
- Updated TrainingDatasetStudio README.

## Prioritized closure plan

1. Restore real screenshot capture and inspect Normal Processing and Professional
   Review at 1366x768 and 1280x720.
2. Launch Studio through its existing launcher and inspect every navigation page.
3. Perform disposable/manual Normal Processing verification for every category,
   filename grammar, head, and export.
4. Verify proposal selection, pending navigation, save failure, stale crop,
   and queue refresh with disposable data.
5. Define production activation/approval/rollback if required.
6. Implement shared-training resume or leave it explicitly unsupported.
7. Rerun full tests and retain this status report as the authoritative snapshot.

## Reusable GUI Acceptance Automation

Implemented in `scripts/gui_acceptance/`:

- Smoke and visual modes
- NewAssetApp-only, Studio-only, and both-app modes
- Disposable synthetic database/media fixture
- Qt `QWidget.grab()` screenshot capture
- JSON, Markdown, and screenshot manifests
- Exact run directories under `gui_screenshots/automated/`
- `--no-capture` and `--keep` options

Verified commands:

```powershell
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite smoke --app both
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite visual --app both --resolutions 1280x720,1366x768,1920x1080
.\.venv\Scripts\python.exe scripts\gui_acceptance\run_gui_acceptance.py --suite smoke --app newassetapp --no-capture
.\.venv\Scripts\python.exe -m unittest tests.test_gui_acceptance_runner -v
```

Verified evidence:

- Smoke `both`: PASS, 2 scenarios
- Visual `both`: PASS, 6 scenarios, 36 Qt-rendered PNG screenshots
- No-capture mode: PASS with an empty screenshot manifest
- Runner test: PASS
- `1280x720`, `1366x768`, and `1920x1080` Qt widget captures produced and inspected

Representative run:

- `gui_screenshots/automated/20261122_004522_7552/`
- 9 NewAssetApp screenshots
- 27 Studio screenshots

This proves launcher, widget layout, navigation, and screenshot capture automation.
It does not yet prove manual task interactions, modal acceptance, Studio import-to-package
GUI completion, or headed desktop visual acceptance.

## Phase 2 — Functional Acceptance Audit

Date: 2026-11-21

This phase audited actual persistence, export, Studio, proposal, Normal Processing,
and GUI behavior. It did not make implementation or taxonomy changes.

### Test evidence

- Full NewAssetApp suite: 173 tests passed.
- Focused CNN, proposal, Normal Processing, and GUI layout suite: 66 tests passed.
- Focused handoff, YOLO, crop, and filename suite: 54 tests passed.
- Studio-specific suite: 22 tests passed.
- Final GUI/layout and independent-review suite: 28 tests passed.
- Disposable proposal lifecycle script confirmed:
  - `asset_proposals` remained linked to one YOLO detection.
  - A bbox edit changed the task review to `stale` and superseded training example 1.
  - Reconfirmation created training example 2 with the new bbox.
  - A separate arousal record remained `draft`.
  - An invalid bbox save raised `Edited box must stay within source image coordinates`
    and did not add another correction or training example.

### Acceptance matrix

| Workflow | GUI | DB persistence | Training example | Studio handoff | Package inclusion | Evidence |
|---|---|---|---|---|---|---|
| YOLO unchanged bbox approval | Partial live; controls observed | Verified disposable | Verified | Verified | Verified | 173-suite + independent review tests |
| YOLO edited bbox + class | Partial live; controls observed | Verified disposable | Verified | Verified | Verified | 173-suite + 54/66 focused suites |
| Shared CNN Fullbody | Implemented; live menu not exercised | Verified disposable | Verified Professional | Verified | Verified | 66/54 suites; handoff tests |
| Shared CNN Body Images | Implemented; live menu not exercised | Verified disposable | Verified Professional | Verified | Verified | 66/54 suites |
| Shared CNN Portrait | Implemented; live menu not exercised | Verified disposable | Verified Professional | Verified | Verified | 66/54 suites |
| Shared CNN Arousal | Implemented; live menu not exercised | Verified disposable | Verified Professional | Verified | Verified | 66/54 suites |
| Shared CNN Corruption | Implemented; live menu not exercised | Verified disposable | Verified Professional | Verified | Verified | 66/54 suites |
| Normal Processing shared CNN targets | Implemented; live save not completed | Partially verified disposable | Verified code/tests | Partially verified | Partially verified | GUI/menu code plus crop and Normal suites |
| Broad Clothing | Implemented; live save not completed | Verified disposable | Verified | Verified | Verified | 66/54 suites |
| Detailed Clothing | Implemented; live save not completed | Verified disposable | Verified | Verified | Verified | 66/54 suites |
| Proposal create/select/reject/correct | Live controls observed; full interaction blocked | Verified disposable states | Verified where applicable | N/A | N/A | 28/66 suites + disposable script |
| Normal Processing output/filenames | Implemented; not fully live-verified | Verified disposable | N/A for export-only state | N/A | N/A | 66 suite + output/crop tests |
| Studio Dataset Records | Live captured | Verified existing DB | N/A | N/A | N/A | `Capture4.PNG` |
| Studio Model Projects | Live captured | Verified existing DB | N/A | N/A | N/A | `Capture5.PNG` |
| Studio Dataset Segments/Builder/Validation | Implemented; live pages not fully inspected | Verified tests | N/A | N/A | Verified packages in tests | 22 Studio + workflow suites |
| Studio package import/export | Implemented/tested disposable | Verified | N/A | Verified | Verified | 22 + 54 suites |
| Studio 5 GB segment policy | Implemented/tested | Verified disposable | N/A | N/A | N/A | 22 Studio suite, rollover/dedup tests |
| 1280x720 and 1920x1080 live screenshots | Blocked/incomplete | N/A | N/A | N/A | N/A | Offscreen layout tests pass; live PNGs missing |

### Confirmed Phase 2 findings

| ID | Severity | Reproduction | Expected | Actual | Root cause / evidence | Smallest fix |
|---|---|---|---|---|---|---|
| P2-001 | High | Open an orphaned/manual proposal, choose task or YOLO class correction | Detection-backed actions should be unavailable or clearly rejected | Historical logs show task-classification and class-correction calls failing for proposal 2819/2821 without detection | `save_classification_task_review` and `save_yolo_class_correction` require detection-backed proposals; the dialog/GUI previously allowed the action to reach persistence | Disable and explain detection-dependent actions for manual proposals, or route manual proposals into a valid manual-crop workflow |
| P2-002 | High | Run Fullbody Normal Processing export with opaque source and background-removal enabled | Export should complete or return a bounded resource-safe failure | Historical live export attempted 1 GB allocation and failed with CPU out-of-memory | BiRefNet runtime allocated beyond available memory; synthetic failure tests pass but do not prove live capacity | Add preflight memory/image-size guard and bounded processing; stop before model allocation |
| P2-003 | Medium | Select Normal Processing, assign a CNN target, confirm | Target save, training example, handoff, and next-state behavior should complete | Code/database paths exist and disposable tests pass, but live GUI save and reload were not completed | Acceptance requires live interaction, not only unit coverage | Add a disposable-folder smoke workflow and manually record each head save |
| P2-004 | Medium | Capture 1280x720 and 1920x1080 live app/Studio surfaces | Complete real PNG captures should be inspected | Only 1366x768 live captures and existing 1368-style image-based captures are confirmed; capture backend was inconsistent | Live capture tooling and screen transitions | Resume with Snipping Tool and save named PNGs; no acceptance claim for missing resolutions |
| P2-005 | Medium | Open Normal Processing right pane at 1366x768 | Location, export preview, subtags and actions should remain discoverable | Content region is taller than its viewport; location/export preview require scrolling | Live AX showed a 577 px content region in a 489 px viewport | Verify compact layout and improve scrolling/section organization only after manual capture |
| P2-006 | Medium | Test `top`, `shirt`, `lingerie`, `bra`, `footwear`, location, invalid and filename combinations through GUI | Visible selections should match taxonomy and produce canonical filenames | Taxonomy/export unit coverage exists, but every choice was not manually exercised live | Incomplete GUI acceptance | Run a disposable image through each category and record exact saved/filename/export state |

### Normal Processing conclusion

Normal Processing has implemented category, crop, filename, fullbody, clothing,
body-image, shared CNN target, invalid, and export paths. The database and focused
tests demonstrate these paths, but live GUI save/reload/export was not completed
for every taxonomy choice. It is therefore **partially verified**, not complete.

### CNN conclusion

All five shared Professional Review heads are independently testable and pass
disposable persistence/export checks. Normal Processing exposes targets for
Fullbody, Body Images, Arousal, and Corruption and save logic for each. Portrait
appears through the Normal Body/Portrait classification route. Live GUI acceptance
and Studio import for each Normal-created head remain incomplete.

### Proposal lifecycle conclusion

Disposable lifecycle evidence confirms bbox staling, task supersession, independent
draft/confirmed/rejected states, and invalid-save preservation. Next/previous GUI
navigation, reload persistence, and failure behavior after real dialog interaction
were not fully live-tested.

### Studio conclusion

Dataset Records and Model Projects are visually verified. The 22 Studio tests pass
for navigation, import, datasets, validation, segments, package export, and dry-run
CPU training. Remaining live pages and complete GUI package creation are incomplete.
Production activation and shared-training resume are not implemented.

### Updated prioritized closure plan

1. Add the smallest test and UI guard for detection-backed-only actions (P2-001).
2. Add live Fullbody export memory preflight and bounded failure handling (P2-002).
3. Complete disposable live Normal Processing five-head acceptance.
4. Complete proposal previous/next/reload/failure GUI acceptance.
5. Capture and inspect 1280x720 and 1920x1080 real screenshots.
6. Complete every remaining Studio navigation page and one GUI import→dataset→package flow.

## Final pre-release audit addendum — 2026-11-22

- Fullbody stabilization is partially implemented, not yet equivalent to a
  completed live desktop acceptance. Lazy process-level model reuse, CPU-sized
  fallback resolutions, resource preflight, bounded alpha caching, and
  opaque-output blocking are present. A focused 177-test suite passed after
  tensor cleanup was added in `app/core/output_exporter.py`.
- Real CPU measurement on a 720×1345 realistic crop used a 384×384 inference:
  before model load RSS 0.181 GiB, after load 1.072 GiB, after inference
  1.145 GiB, and after cleanup 1.133 GiB. Model load took 49.75 seconds;
  inference took 21.90 seconds and postprocessing 0.28 seconds.
- The 1 GiB allocation failure is not caused by mask/WebP conversion alone.
  The complete cost includes model load, normalized tensor, 384–1024-square
  CPU activation/output tensors, and temporary RGBA/PIL buffers.
- No model checkpoint or alternative checkpoint was changed. 1024×1024 quality
  baseline evidence remains in the Phase 9 reports; 384×384 is the current
  conservative CPU fallback.
- Latest visual runner: PASS; 36+ headless Qt PNG captures were produced for
  NewAssetApp and Studio at 1280x720, 1366x768, and 1920x1080. The captures
  use synthetic fixture widgets, so they verify layout automation, not final
  live production workflows or headed desktop visuals.
- GUI redesign was not started. Small layout fixes and test-runner fixes already
  present in the workspace remain separate from the requested broad redesign
  decision.

## TDA-001 and TDA-002 implementation addendum — 2026-11-22

- TDA-001 is implemented for independent Cum/Accessory binary decisions,
  explicit both-negative `none`, pending, partial evaluation, and
  backward-compatible legacy single-target records.
- TDA-002 is implemented in shared eligibility APIs and Normal Processing:
  face/body-region Arousal and Corruption targets now use the same approved
  eligibility rules as Professional Review.
- NewAssetApp schema migration 24 adds Normal Processing Body Images binary
  fields; existing migration 23 already added Professional Review binary fields.
- Handoff v4 accepts a versioned Body Images target-mask object.
- Studio import preserves target masks, including legacy derived masks.
- Shared CNN export/validation and masked-loss training code preserve independent
  Cum/Accessory targets and exclude pending outputs.
- Focused TDA tests: 6 passed.
- Full NewAssetApp suite: 183 tests passed.
- Full TrainingDatasetStudio suite: 22 tests passed.
- Visual GUI runner: PASS, 36+ synthetic Qt captures at 1280x720, 1366x768,
  and 1920x1080.
- Compileall and `git diff --check`: passed.

## GUI acceptance Phase 5.1 addendum — 2026-11-22

- Root cause fixed: Manual Proposal previously created an orphan proposal with
  no detection, disabling dialog class/bbox correction.
- `_create_manual_proposal()` now creates a real manual detection and linked
  proposal with a valid default source-pixel bbox.
- Focused real-Qt Manual Proposal test: PASS.
- Effective class and bbox persisted and reloaded correctly.
- Original manual detection class and bbox remained immutable.
- Broader Professional task-card and correction matrices remain incomplete.

## Real-samples GUI product audit — 2026-11-23

- Loaded the actual `samples` folder through the real scan and analysis GUI
 handlers against an isolated disposable database.
- 287 sources scanned successfully in 9.562 seconds.
- 287 sources analyzed successfully in 455.109 seconds.
- 2263 detections and 2263 proposals were created.
- Four duplicate-content sample pairs were detected.
- No unreadable/corrupt sample images were found.
- No sample image had zero detections.
- Fixed legacy unmatched YOLO class fallback so it cannot silently default to
 Person.
- Fixed uncategorized Normal crops so they require an explicit category.
- Fixed duplicate canonical `bikini` entries in the Normal Fullbody main-tag UI.
- The runtime 32-class checkpoint registry remains mismatched with the approved
 31-class target registry; no remapping was performed.
- The Clothing CNN checkpoint is not installed.
- Headed Windows desktop interaction remains a separate category. One
  real-sample Clothing export is now verified; the full output matrix and
  transparent-background export remain unverified.
- Full NewAssetApp suite: 196 tests passed.

## GUI acceptance implementation follow-up — 2026-11-22

- Live NewAssetApp launch exposed Normal Processing and Professional Review,
  with headed-desktop window text/geometry observed at 1360x749.
- TrainingDatasetStudio live launcher launch remained blocked by `.ps1`
  association and UI safety, but a desktop `run_app.bat` entry point was added
  to invoke the existing PowerShell launcher.
- NewAssetApp now supports `--acceptance-db`, `--acceptance-data`,
  `--acceptance-output`, and `--acceptance-logs` for isolated live acceptance.
- Studio now supports `--acceptance-root` for isolated live/config data.
- Launch override tests pass.
- Full NewAssetApp suite: 186 tests passed.
- Full Studio suite: 22 tests passed.
- GUI visual runner final run: PASS.
- The live NewAssetApp launch migrated the existing database from schema 23
  to 24. No production source, export, or training record was intentionally
  changed.

## GUI acceptance baseline addendum — 2026-11-22

- Live NewAssetApp launcher: observed opening a headed desktop window at
  1360x749 through the existing `run_app.bat` path. Accessibility text exposed
  Normal Processing and Professional Review, 2807 suggestions, the crop gallery,
  inspector controls, navigation, export controls, and scrollable sections.
- Live headed-desktop screenshot capture was unavailable from the Computer Use
  backend; it returned accessibility state without an image.
- Live Studio launcher: blocked. The `.ps1` file association opened the script in
  Notepad instead of executing it, and direct PowerShell launch was unavailable
  through the UI safety policy.
- Synthetic Qt GUI acceptance: PASS. The `both` visual smoke/visual runner
  captures NewAssetApp and Studio pages at 1280x720, 1366x768, and 1920x1080.
- Automated Normal Processing interaction: PASS for one disposable Body Images
  crop, including checkbox/none-style state, confirmation, reload, and database
  verification.
- Automated Professional Review: PASS for navigation and layout fixtures.
- Full NewAssetApp suite: 183 tests passed.
- Full Studio suite: 22 tests passed.
- Exact production schema result: the existing database migrated automatically
  from schema 23 to 24 when the live launcher initialized the application.
  No source image, crop, export, or training record result was intentionally
  changed during acceptance.
- RAR/Colab archive implementation remains deferred.

## GUI acceptance Phase 2 addendum — 2026-11-22

- A unique isolated acceptance root was created outside the repository and
  launched with explicit fail-closed NewAssetApp and Studio overrides.
- Live NewAssetApp opened against its disposable database and synthetic fixture.
- Live Studio opened against its disposable acceptance root and isolated database.
- Live NewAssetApp mutation/save acceptance was blocked by concurrent desktop
  user input and the desktop automation backend.
- Live Studio navigation/import remained blocked by desktop automation page-switch
  reliability; its real-widget navigation test passed after a History-page fix.
- Studio now has a real History page and no stale activation-page remapping.
- Full NewAssetApp suite: 186 tests passed.
- Full Studio suite: 22 tests passed.
- GUI visual runner: PASS.
- Detailed evidence: `reports/GUI_ACCEPTANCE_PHASE2_REPORT.md`.

## GUI acceptance Phase 3 addendum — 2026-11-22

- Added a real-application Qt acceptance scenario for Normal Processing and
  Studio navigation.
- Phase 3 isolation manifest: PASS for a disposable root outside the repository,
  with separate NewAssetApp/Studio databases and synthetic source media.
- Real Qt Normal Processing save/reload: PASS for a Body Images crop with
  Cum positive and Accessory explicitly negative.
- Studio actual navigation: PASS for all 9 existing rows/pages.
- Professional Review correction-dialog acceptance remains TEST-ONLY/PARTIAL.
- Complete Studio GUI import/dataset/version/package acceptance remains
  BLOCKED after a bounded workflow run did not complete.
- Headed desktop capture remains unavailable.
- Full NewAssetApp suite: 186 tests passed.
- Full Studio suite: 22 tests passed.
- Detailed evidence: `reports/GUI_ACCEPTANCE_PHASE3_REPORT.md`.

## GUI acceptance Phase 4 addendum — 2026-11-22

- Normal Processing real Qt scenarios passed for `false/false`, `true/false`,
  `false/true`, `true/true`, both-pending, Cum-partial, and
  Accessory-partial states.
- Professional Review source/detection navigation, real Inspector class and
  bbox interaction, correction-dialog opening/cancel, and independent task-card
  controls were exercised. Complete coverage for every head/dialog variant is
  still `PARTIAL`.
- A reload regression was fixed so Professional Inspector task status exposes
  Cum/Accessory evaluated and target-mask state.
- Studio real Qt import passed.
- Studio real Qt dataset creation, draft version, finalization, validation
  refresh, and Colab package export passed in separate bounded scenarios.
- Phase 4 evidence run: `20261122_174821_5324`.
- Full NewAssetApp suite: 192 tests passed in 122.970 seconds.
- Full Studio suite: 22 tests passed in 104.105 seconds.
- Compileall and `git diff --check`: passed.

## Targeted real-sample GUI completion attempt — 2026-11-23

- Reused the isolated real-samples database: integrity check `ok`, 287 source
  paths resolved, 2,263 detections, and 2,263 proposals.
- Launched the actual Qt application with the isolated database/data/output/log
  paths. A bounded **Scan Images** repeat reached 100%; the GUI reported
  `Scan complete · model inference is not connected`. No Analysis run occurred.
- Post-scan counts remained 287 sources, 2,263 detections, and 2,263 proposals;
  four duplicate-content groups remained, with no new Normal Processing
  choices, Professional task reviews, or exports.
- The actual Normal Processing GUI selected a real Fullbody crop (proposal 5,
  `fullbody_casual`, source `10963092_002_1fcf.jpg`) and opened the Fullbody
  main-tag list. Its option did not commit, so no classification or export was
  saved. Screenshot capture failed, preventing visual crop-content verification.
- Professional Review loaded the same real source. The Face #4 row highlight
  changed while the Inspector still showed Location Home #1. No task decision
  was saved; the observation is not attributed to a product defect because the
  accessibility action may not represent the user's current-item click.
- **Actual GUI actions:** isolated Qt launch, real crop selection, partial
  dropdown inspection, source/detection navigation, and scan-only repeat.
- **Not verified:** category classifications and reloads, exports, independent
  Professional task saves, and complete runtime dropdown/filter/action coverage.
- **Blocked:** screenshot capture and reliable selector/detection activation.
  No production code change or new test run was made. Existing historical test
  results above are not evidence of this GUI completion.
- Evidence: `gui_screenshots/real_samples_audit/20261123_002448_real_samples/gui_completion_20261123_evidence.json`.

## Completed in-process Qt real-sample workflows — 2026-11-23

- Reused the existing isolated real-samples database without scanning or
  inference. Final read-only checks: integrity `ok`, 287/287 source paths
  resolve, 2,263 detections, 2,263 proposals, and all 287 inference statuses
  remain completed.
- Actual QTest events and production callbacks saved/reloaded representative
  Normal Processing classifications for Fullbody, Body Images, Clothing, and
  Invalid. Invalid crops remain ineligible for training examples.
- Actual QTest Professional Review decisions saved/reloaded Body Images,
  Portrait, Arousal, Fullbody, and Corruption. Human/model provenance remains
  distinct; task siblings remain independent.
- Fixed the Invalid callback error, source/proposal ID collision in Sources
  view, missing Body Images validation exception for `portrait_frame`, and
  narrow-panel clipping of Normal Arousal/Corruption controls.
- Captured and inspected native-platform Qt `grab()` images. These are not
  headed Windows desktop screenshots. Exported one isolated Clothing crop as
  `mini_skirt1.webp` (245x235); background removal was not run.
- Targeted `test_main_window_layout.py`: 14 passed. Targeted
  `test_independent_classification_reviews.py`: 24 passed in the preceding
  validation pass. Full suite was not rerun.
- Remaining: full export matrix and transparent-background output, exact
  pixel-level preview alignment, headed desktop interaction, and the unchanged
  31/32 registry mapping.
