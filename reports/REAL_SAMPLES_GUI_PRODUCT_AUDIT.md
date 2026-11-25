# NewAssetApp — Real Samples GUI Product Audit

Date: 2026-11-23

## A. Actual sample scan

- Samples folder: `F:\My Tools\New folder\NewAssetApp\samples`
- Image files: 287
- Supported formats: 287 `.jpg`
- Nested files: none
- Readable images: 287
- Unreadable/corrupt images: 0
- Unique content hashes: 283
- Duplicate content pairs: 4
- Scan duration: 9.562 seconds
- Analysis duration: 455.109 seconds for the inference worker
- Total isolated run: 464.843 seconds
- Source images indexed: 287
- YOLO detections: 2263
- Asset proposals: 2263
- Normal Processing choices: 0 at scan completion
- Training examples: 0 at scan completion
- Images with no detections: 0
- Maximum detections on one image: 21

Duplicate content pairs:

- `81455352_063_489c (1).jpg` / `81455352_063_489c.jpg`
- `81455352_077_2711 (1).jpg` / `81455352_077_2711.jpg`
- `81455352_092_1ca4 (1).jpg` / `81455352_092_1ca4.jpg`
- `93598058_003_6bed (1).jpg` / `93598058_003_6bed.jpg`

The real GUI scan reported:

`Verified 287 / 287 · 287 new/changed · 0 unchanged · 4 duplicate(s) · 0 error(s)`

The real Analysis button reported:

`Analyzed 287 / 287 · 0 error(s)`

Model:

- Checkpoint: `models/yolo/best.pt`
- Checkpoint SHA-256: `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA`
- YOLO policy: `data/models/yolo_class_policy.json`
- Approved target registry: `TrainingDatasetStudio/registries/yolo_detector_v1.json`
- Clothing CNN checkpoint: not present

## 31-versus-32 registry mismatch

The runtime checkpoint produced 32 preserved legacy class names. The approved
31-class target registry does not contain these runtime names:

- `action_event`
- `fullbody_bottomless`
- `fullbody_casual`
- `fullbody_lingerie`
- `fullbody_swim`
- `fullbody_topless`
- `location_bed`
- `location_outdoor`

The target registry contains target names absent from the runtime policy:

- `fullbody_bikini`
- `fullbody_clothed`
- `fullbody_swimsuit`
- `fullbody_underwear`
- `location_beach`
- `location_clinic`
- `location_park`

No registry remapping was performed. This remains the deferred 31/32 item.

## B. GUI control inventory

### Normal Processing category

- Options: Fullbody, Body Images, Clothing, Invalid.
- Required uncategorized state: now `Choose category`.
- Canonical values: `fullbody`, `body_images`, `clothing`, `invalid`, `null`.
- Finding: uncategorized real proposals previously could inherit Fullbody UI state.
- Fix: explicit placeholder and disabled confirmation until a category is chosen.

### Normal Fullbody main tags

Runtime confirmed values include:

- `clothed`
- `underwear`
- `bikini`
- `lingerie`
- `bare`
- `shower`
- `maid`
- `swimsuit`
- `nurse`
- `uniform`
- `work`
- `cosplay`

Finding: duplicate `bikini` entries existed with both `Bikini` and `bikini`
labels but the same canonical stored value. The runtime list now deduplicates
canonical values, preserving the first visible label.

### Normal Fullbody state

- `Choose state`
- `clothed`
- `topless`
- `bottomless`

### Normal Fullbody CNN target

- `clothed`
- `topless`
- `bottomless`
- `bra`
- `panty`

### Normal Arousal

- `aroused`
- `edging`

### Normal Corruption

- `conservative`
- `slut`
- `whore`
- `u_whore`

The visible `u_whore` label is `Ultimate Whore · u_whore`; canonical data remains
`u_whore`.

### Normal Clothing Broad

The runtime list contains all 12 approved classes:

- `bra`
- `dress`
- `footwear`
- `lingerie`
- `outerwear`
- `pants`
- `panty`
- `shirt`
- `shorts`
- `skirt`
- `socks`
- `top`

### Portrait

- `portrait`
- `tportrait`

These remain available through the Body Images/portrait tag and task selectors.

### Professional YOLO class selector

The corrected target selector exposes approved target registry classes, plus a
`Choose approved target class` placeholder.

Finding: unmatched legacy runtime detections previously defaulted to Person.
The Inspector now disables Save Correction and explains that no approved
31-class match exists.

## C. Real application behavior

### Scan and inference

- Folder selection worked.
- The real GUI scanned all 287 files recursively with no unreadable files.
- The real Analysis button processed all 287 sources.
- 2263 detections and 2263 proposals were persisted to the isolated database.
- No source images were modified.
- No sample files were copied or moved.
- The scan created 4 duplicate records by content as expected from the same
  content appearing under duplicate filenames.

### Detection distribution

Highest real detection counts:

- `person`: 381
- `face`: 286
- `portrait_frame`: 231
- `pussy_cover_item`: 141
- `boobs_cover_item`: 115
- `accessory_footwear`: 113

No sample image had zero detections.

Representative source `80983975_013_fc20.jpg` had 8 detections, including:

- `fullbody_topless`
- `pussy_cover_item`
- `person`
- `face`
- `legs`
- `boobs`
- `portrait_frame`
- `location_bed`

This source was used to verify the legacy mismatch guard. The real Inspector
displayed `Choose approved target class`, disabled Save Correction, and explained
that silent remapping is unsafe.

### Normal Processing

The real Normal Processing widget loaded 2263 crop records and showed:

- Crop gallery
- Category selector
- Fullbody state controls
- Fullbody main-tag list
- Arousal and Corruption selectors
- Confirm and Next controls

The uncategorized-crop fallback was reproduced in real Qt state and fixed.
The duplicate Fullbody Bikini canonical value was reproduced from the real tag
library and fixed.

No disposable Normal classification/export was performed in this audit because
the task's priority was real-product discovery and the export behavior is
separate from the confirmed UI bugs.

### Professional Review

The real sample-loaded Professional page opened and showed:

- Source gallery
- Detection list
- Source/box preview
- Detection Inspector
- Task controls

Real detection selection was verified for the representative source above.
The unmatched `fullbody_topless` detection no longer silently maps to Person.

### Manual Proposal

The previously reported Phase 5.1 Manual Proposal fix remained unchanged and
passed its focused real-Qt test. The audit did not repeat the old orphan-proposal
flow.

### Studio

No additional Studio behavior was changed or re-tested in this audit.
Phase 4 Studio findings remain unchanged.

## D. Visual findings

Evidence:

- `1366x768_real_samples_after_scan.png`
- `1366x768_real_samples_after_analysis.png`
- `1366x768_real_samples_professional.png`
- `1366x768_real_samples_normal.png`
- `1366x768_real_sample_legacy_fullbody_guard.png`
- `1366x768_real_sample_normal_crop.png`

Observed:

- The 1366x768 layout remains dense and uses a long right Inspector panel.
- Lower Normal Processing controls require scrolling.
- The source gallery and right Inspector remain readable at 1366x768.
- Real Qt captures are not headed-desktop screenshots.
- No headed Windows desktop session was available for this audit.

## E. Bug register

| ID | Severity | GUI location | Finding | Root cause | Status | Verification |
|---|---|---|---|---|---|---|
| RSA-001 | Critical | Professional Inspector | Legacy unmatched runtime class could default to Person | `_populate_inspector_class_controls()` used `max(0, -1)` | Fixed | Real Qt selected `fullbody_topless`; placeholder displayed and Save disabled; focused test passed |
| RSA-002 | High | Normal Processing | Uncategorized crop could inherit the previous Fullbody state | Category combo had no explicit `None`/placeholder and fallback selection could persist | Fixed | Uncategorized real row requires explicit category; confirmation disabled |
| RSA-003 | High | Normal Processing Fullbody main tag | Duplicate canonical `bikini` entries displayed twice | Two authoritative tag entries share `bikini` | Fixed | Deduplicate canonical values in UI; focused test passed |
| RSA-004 | High | 31/32 correction workflow | 32 runtime legacy classes do not exactly match approved 31 target classes | Preserved legacy checkpoint registry is not the target registry | Guarded | Mismatches listed; no remapping; Save disabled for unmatched runtime class |
| RSA-005 | Medium | Normal Processing pane | Lower controls remain scroll-dependent | Right classification content is taller than viewport | Existing/unchanged | Real screenshot and widget geometry evidence |

## F. Final status

Verified using the real sample-loaded application:

- 287-image GUI folder scan
- 287-image real inference
- 2263 detections/proposals
- Real Qt Professional Review source/detection selection
- Real Qt legacy mismatch guard
- Real Qt Normal Processing gallery/options
- Real Qt Manual Proposal fix preservation

Verified using real Qt widgets with disposable data:

- Uncategorized Normal category placeholder
- Duplicate Fullbody main-tag canonical deduplication

Verified only by unit/service tests:

- Broader export matrices
- Clothing Detailed combinations
- Full Professional task-card matrix

Not verified:

- Headed Windows desktop interaction and screenshot capture
- Disposable Normal user-facing export for the real sample crops
- Complete Manual Proposal matrix beyond the preserved focused test

Blocked:

- 31/32 registry remapping is explicitly deferred.
- Clothing CNN output is unavailable because the Clothing checkpoint is not installed.

Final test verification:

- Full NewAssetApp suite: 196 tests passed in 85.755 seconds.
- Focused audit fixes: 3 tests passed.
- Manual Proposal preservation: 1 test passed.
- Compileall and `git diff --check`: passed.

## Targeted real-sample GUI completion addendum — 2026-11-23

### Reused run and scan-only repeat

- Reused the existing disposable database and its `app\data\models` and
  `app\data\tags` assets. `PRAGMA integrity_check` returned `ok`; all 287 source
  paths resolved.
- Launched the actual NewAssetApp Qt window with the existing isolated DB,
  isolated data, export, and log paths. No production DB or output path was
  selected.
- Repeated the sample-folder scan using **Scan Images** only. The GUI reached
  100% and showed `Scan complete · model inference is not connected`; the
  separate **Analyze new / changed** action was not run.
- After the scan: 287 source rows, 2,263 detections, 2,263 proposals, 4
  duplicate-content groups, and 0 classification choices, task reviews, or
  normal exports. All source paths still resolved and the DB integrity check
  remained `ok`.
- The scanner code confirms that an unchanged path and content hash take the
  `unchanged` branch, update only the source root, and skip `upsert_source_image`.
  The observed source, detection, and proposal counts did not grow. This bounded
  scan did not run inference.

### Actual Qt GUI interactions

- In Normal Processing, selected proposal 5 from
  `samples\10963092_002_1fcf.jpg`: source 1, detection 5,
  `fullbody_casual`, bbox `[309.8026, 9.8695, 678.6696, 612.5708]`.
  The UI displayed `Fullbody`, `Model evidence: fullbody_casual · suggestion
  only`, and `Detected region shown; background removal runs during export`.
  The preview was exposed as an image control, but Computer Use screenshot
  capture failed twice, so image content and pixel alignment were not visually
  verified.
- Opened the actual Fullbody main-tag dropdown. The visible runtime labels were
  `Choose a main tag`, `Clothed`, `Underwear`, `Bikini`, `Lingerie`, `Nude`,
  `In Shower`, `Maid`, `swimsuit`, `Nurse`, and `Uniform`. The control did not
  commit a selected value; its value remained `Choose a main tag`, and no
  classification was saved.
- In Professional Review, loaded the same real source. The detection list
  displayed Location Home (#1), Person (#2), Pussy Cover Item (#3), and, after
  scrolling, Face (#4). The AX row highlight moved to Face (#4), but the
  Inspector continued to report Location Home (#1). No task decision was saved.
  The accessible-row interaction did not establish whether this is a product
  defect or an accessibility-action limitation; no production change was made.
- No Fullbody, Body Images, Clothing, or Invalid classification was confirmed;
  no Professional task decision was confirmed or reloaded; no export was
  attempted. The disposable DB contains no new classification, task-review, or
  export records from this attempt.

### Lists, export safety, and final verification state

- Only the visible portion of the Fullbody main-tag dropdown was inspected in
  this run. Fullbody state/CNN target, Body Images Cum/Accessory, Arousal,
  Corruption, Portrait, Clothing Broad/Detailed, invalid/rejection reasons,
  detection/review filters, and proposal actions were not fully opened and
  exercised in the actual GUI.
- Before any export, reviewed the BiRefNet preflight and export path: it rejects
  regions over 25,000,000 pixels or 12,000 pixels on either side, requires at
  least 2 GiB available memory when measurable, and selects bounded inference
  sizes. No background-removal model was loaded or run.
- Actual real-sample GUI actions: isolated Qt app launch, sample crop selection,
  partial dropdown inspection, Professional Review source/detection navigation,
  and a bounded scan-only repeat.
- Unit/service-only: prior test results in this report remain historical; no
  tests were run for this addendum.
- Not verified: Normal classifications, save/reload, export files/metadata,
  independent Professional task saves, all runtime list matrices, and visual
  preview alignment.
- Blocked: GUI screenshot capture failed and accessible selector/row actions did
  not reliably commit or synchronize state. No bug is recorded as fixed from
  these interactions. The 31/32 registry mapping remains unchanged; unmatched
  legacy classes remain guarded. The Clothing CNN checkpoint remains absent.

Evidence: `gui_screenshots/real_samples_audit/20261123_002448_real_samples/gui_completion_20261123_evidence.json`.

## Completed in-process Qt real-sample audit addendum — 2026-11-23

This addendum records the completed actual-widget workflows and supersedes the
earlier incomplete interaction attempt above. It does not claim headed desktop
acceptance.

### Reused workspace and data guard

- Reused `C:\Users\asker\AppData\Local\Temp\newassetapp_real_samples_20261123_002448_real_samples\`.
  The existing database is `app\newassetapp.sqlite3`; its `app\data\models` and
  `app\data\tags` assets were retained.
- No scan, analysis, or inference was run. Read-only verification returned
  `PRAGMA integrity_check = ok`, 287/287 resolvable sample paths, 2,263
  `yolo_detections`, 2,263 `asset_proposals`, and 287/287 sources with
  `inference_status = completed`.
- The existing workspace had zero Normal choices, Professional task reviews,
  and Normal exports before these GUI decisions. Afterwards, read-only
  verification found four Normal choices, five independent task-review
  records, and one export record.
- All exported data remained under the isolated workspace's `exports` folder.
  No production database or output path was used; no source image was modified.

### Normal Processing: actual widget events and saves

- **Fullbody, proposal 5 / detection 5 / source 1**:
  `samples\10963092_002_1fcf.jpg`, class `fullbody_casual`, bbox
  `[309.8026, 9.8695, 678.6696, 612.5708]`. A `QTest.mouseClick` on the
  `NormalCropGallery` (`QListWidget`) viewport selected the item displayed as
  `Fullbody / Confirmed`; its item data identified proposal 5. The unnamed
  `normal_body_tag` `QComboBox` popup was opened with a mouse click. A popup
  item mouse click did not commit in this environment; the actual focused
  combo accepted `Home`, `Down`, `Enter`, selecting visible `Clothed` with
  `currentData() == "clothed"`. `normal_fullbody_state` also displayed
  `Clothed` with canonical data `"clothed"`. The `PrimaryButton` confirmation
  was enabled and clicked through QTest; the production callback saved the
  classification. Navigation away and back reloaded Fullbody / `clothed` /
  state `clothed`.
- **Body Images, proposal 6 / detection 6 / source 1**: the same real source,
  class `portrait_frame`, bbox
  `[384.6401, 20.8102, 612.3593, 391.1069]`. QTest selected its
  `NormalCropGallery` item. The main-tag combo displayed `Clothed Portrait`
  with canonical data `"portrait"`. QTest keyboard events set Cum to
  unchecked/false and Accessory to checked/true; both decisions were marked
  complete. The confirmation button enabled and its production callback saved
  the record. Reload preserved Cum `0`/evaluated `1`, Accessory `1`/evaluated
  `1`, and completion `1`.
- **Clothing, proposal 3 / detection 3 / source 1**: class `pussy_cover_item`.
  QTest selected its actual gallery item. The detailed main tag displayed
  `Mini Skirt` (`"mini_skirt"`), Broad Clothing group displayed `Skirt`
  (`"skirt"`), and guide cover area displayed `Pussy cover` (`"pussy_cover"`).
  No extra detailed subtag options were exposed by the authoritative taxonomy.
  The production confirmation callback saved these values and navigation
  reloaded them.
- **Invalid, proposal 1 / detection 1 / source 1**: QTest selected the real
  `NormalCropGallery` (`QListWidget`) item, chose Invalid in
  `normal_assign_category` (`QComboBox`, canonical data `"invalid"`), and
  clicked the `PrimaryButton` (`QPushButton`). This exposed and fixed an
  undefined `record_draft` reference in the category callback. The effective
  UI category reloaded as Invalid; storage uses the existing `is_invalid = 1`
  sentinel (`category = "body_images"`). Read-only inspection found zero
  eligible training examples for proposal 1.

The other Normal Processing controls were also checked by runtime widget and
value: `normal_body_tag`, `normal_fullbody_state`, `normal_clothing_broad`, and
`normal_clothing_cover_area` are `QComboBox` controls (their Qt object names are
empty); the Cum, Accessory, and completion controls are `QCheckBox` widgets.
The Fullbody, Body Images, and Clothing selections were made on the
`NormalCropGallery` (`QListWidget`) viewport, then saved using the enabled
`PrimaryButton` (`QPushButton`). The initial Normal choice count was zero; the
four saved choices are proposal IDs 1, 3, 5, and 6.

### Professional Review: selection and independent task decisions

- On source 1, QTest clicked detection 4's actual visual rectangle in the
  `DetectionList` (`QListWidget`) viewport. After the fix, the current list
  item, Inspector, and preview all identified detection 4 / `face`; source 1
  stayed selected. The Inspector bbox was
  `[410.6094, 47.7765, 500.1613, 175.7891]`; Body Images, Arousal, and
  Corruption cards were available. The reproduced defect was a proposal-ID /
  source-ID collision that could switch the source gallery while browsing
  Sources; proposal-gallery synchronization is now skipped in Sources view.
- **Detection 6 / `portrait_frame`**: QTest selected the real detection row and
  its Classification Tasks tab. The `DetectionList` (`QListWidget`) current
  item and Inspector ID were 6. The Body Images `InspectorTaskCard` (`QFrame`)
  checkboxes (`QCheckBox`, visible labels Cum detected, Accessory detected,
  Both decisions complete) were focused and changed through QTest keyboard
  events; `Confirm task` (`QPushButton`) became enabled and its real callback
  saved Cum false and Accessory true, both evaluated. Immediately after that
  save, only the
  Body Images task review existed. Separate QTest popup selections in the
  Portrait and Arousal cards' `QComboBox` controls, followed by their
  `Confirm task` (`QPushButton`) clicks, saved `portrait` and `aroused`.
  Reload showed those three independent reviews; Corruption remained not
  reviewed.
- **Detection 5 / `fullbody_casual`** exposed Corruption and Fullbody cards.
  QTest selected the existing `Clothed` (`"clothed"`) Fullbody `QComboBox`
  item on its `InspectorTaskCard` and clicked `Confirm task` (`QPushButton`).
  Reload showed only the Fullbody decision on that detection.
- **Detection 179 / source 22** from
  `samples\22757255_017_dda1.jpg`, class `fullbody_work`, bbox
  `[212.8504, 63.7503, 699.7626, 1348.2106]`. QTest selected the actual
  Corruption `InspectorTaskCard` (`QFrame`) `QComboBox` item `Slut` (`"slut"`)
  and clicked `Confirm task` (`QPushButton`). Reload showed
  Corruption=`slut` while its Fullbody sibling remained not reviewed.
- All five saved Professional decisions (Body Images, Portrait, Arousal,
  Fullbody, Corruption) have `human_confirmed = 1`, `training_eligible = 1`,
  `model_verified = 0`, and null model confidence. The records retain YOLO
  provenance as suggestion evidence; no CNN predictions were present or
  represented as human decisions.

### Actual Qt captures and export

- Captures were made using the real application's `QWidget.grab()` on the
  native Qt platform and inspected for readable text, visible controls, and
  layout. They are `REAL_APP_QT_CAPTURE` artifacts, not headed Windows
  screenshots or external Computer Use captures. Main-window images are
  1360x749; the captured dropdown popup is 244x192.
- Captures in
  `C:\Users\asker\AppData\Local\Temp\newassetapp_real_samples_20261123_002448_real_samples\gui_captures\`:
  `REAL_APP_QT_CAPTURE_normal_selected_fullbody_crop_native.png`,
  `REAL_APP_QT_CAPTURE_fullbody_main_tag_open_popup_native.png`,
  `REAL_APP_QT_CAPTURE_normal_fullbody_dropdown_open_native.png`,
  `REAL_APP_QT_CAPTURE_normal_fullbody_confirmed_reloaded_native.png`,
  `REAL_APP_QT_CAPTURE_normal_body_images_controls_native.png`,
  `REAL_APP_QT_CAPTURE_normal_clothing_controls_native.png`,
  `REAL_APP_QT_CAPTURE_professional_face4_selected_native.png`,
  `REAL_APP_QT_CAPTURE_professional_task_cards_saved_reloaded_native.png`,
  and `REAL_APP_QT_CAPTURE_professional_detection179_task_cards_native.png`.
- Visual inspection found the Normal Processing Arousal/Corruption controls
  clipped side-by-side in the narrow classification panel. They now stack
  vertically; the post-fix capture shows both complete and readable. The
  Professional task-card panel remains vertically scrollable, with cards below
  the visible area. The screenshots show preview content and bbox overlays, but
  no pixel-coordinate alignment measurement was performed.
- A QTest click on proposal 3's `NormalCropGallery` item, the actual
  `normal_export_button` (`QPushButton`, text `Export selected crops`), the
  real Qt `QFileDialog` Choose button, and the `QMessageBox` Yes button
  produced
  `exports\clothing\pussy_cover\lower\mini_skirt1.webp` (245x235, WebP).
  The GUI reported 1 exported, 0 failed, 0 skipped. The export manifest is
  `exports\newassetapp_normal_processing_manifest_20261123T012840Z.json`.
  This Clothing export does not require background removal; no background
  removal model was loaded or run.

### Defects, validation, and remaining limits

- Fixed the Invalid callback's undefined draft reference; fixed the
  Professional selection ID collision; allowed an eligible `portrait_frame`
  Body Images binary review without an irrelevant body-part main tag; and
  stacked the Normal target controls to prevent narrow-panel clipping.
- Added regression coverage for the layout change. The targeted
  `test_main_window_layout.py` run passed 14 tests. The targeted
  `test_independent_classification_reviews.py` run passed 24 tests in the
  preceding validation pass. No full-suite rerun was performed.
- **Evidence categories:** saves, task decisions, and the Clothing export were
  actual in-process Qt widget events and production callbacks; database
  integrity/count/provenance checks were read-only SQLite inspection; test
  results are unit tests; captures are actual Qt `grab()` output.
- **Not verified:** the full export matrix, BiRefNet/transparent-background
  output, exact pixel-level preview alignment, and headed desktop interaction.
  The 31/32 registry mapping remains unchanged; no remapping, model training,
  bulk relabeling, or source modification occurred.
