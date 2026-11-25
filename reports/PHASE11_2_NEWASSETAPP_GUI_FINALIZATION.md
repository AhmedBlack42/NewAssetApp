# Phase 11.2 — NewAssetApp GUI Finalization

## Pre-implementation inspection and acceptance plan

### Existing functionality

- `run_app.ps1` launches `main.py` with the project `.venv`; the user confirms it works in their normal environment. In the prior Phase 11.1 elevated check, the launcher opened NewAssetApp; the restricted-context failure is not treated as a project environment failure.
- The main window already has distinct **Normal Processing** and **Professional Review** tabs. Normal Processing selects model crop suggestions, assigns an output category, and exports without professional confirmation. The exporter crops source pixels first, conditionally removes Fullbody backgrounds, applies crop rules/upscaling, writes WebP, and records provenance.
- Professional Review already supports detection selection, box editing, invalidation/restoration, correction history, and eligibility controls. Database is schema v9; model predictions and corrections are preserved separately.
- Filename serializers exist for Fullbody, Body Images, and Clothing, but their current grammars diverge; Body Images `cum`/`creampie`/`bb` use a dedicated sub-main path; subtags include free text in the correction dialog.

### Incomplete or incorrect before implementation

- Structured classification fields and taxonomy version are not first-class records; saved values primarily reside in correction JSON. Existing classification review rows cover only three simple task labels.
- Free-text editable tag controls accept values outside registries. The correction form also labels Body Images composition as “sub-main.”
- YOLO's actual legacy 32-class outputs are presented adjacent to selectable human classifications; the new 31-class future registry must remain explicitly separate.
- Location taxonomy has canonical values and a five-class legacy map, but the UI does not show evidence-specific candidate lists for the eight new target classes.
- Legacy Fullbody CNN outputs do not have explicit candidate-only migration suggestions for the two safe `clothed` candidates or the ambiguous nude class.
- Fresh live screenshots and GUI acceptance were not available in prior Phase 9 evidence; Phase 8 offscreen screenshots are not fresh desktop proof.

### Planned files and migration

- Modify `app/core/database.py` with additive schema v10 tables for current structured classifications and append-only classification events; preserve all existing tables and JSON history.
- Add a versioned NewAssetApp classification registry under `data/models/` and shared validation/serialization in `app/core/classification_taxonomy.py` and the existing filename modules.
- Update `app/gui/correction_dialog.py`, `app/gui/main_window.py`, and `app/core/output_exporter.py` to use controlled taxonomy values, save structured review fields, serialize confirmed structured records only at export, and generate a manifest.
- Add focused tests under `tests/` and update filename grammar expectations. No dependency or checkpoint changes are planned.
- Before migrating the live database, create a SQLite backup and validate migration/rollback on a temporary copy. Schema v10 is additive; no legacy rows are bulk converted from filenames or model outputs.

### GUI acceptance criteria

- Normal Processing remains independent from professional confirmation and shows the image preview as the dominant view; folder controls and crop selection remain usable.
- Professional Review visibly separates model evidence from human-selected/unconfirmed and confirmed values; categories have controlled structured inputs, history, validity, eligibility, and reason.
- Location suggestions are visibly suggestions only; the reviewer makes the final canonical choice. Fullbody legacy nude evidence requires a human choice between `topless` and `bottomless`.
- No buttons, labels, or essential controls are clipped at 900×560, 1280×800, or 1920×1080; selected source images remain fully visible.
- Fresh screenshots are saved for all three sizes. If live interaction/capture fails, acceptance remains explicitly incomplete.

## Implementation and validation

Implementation results, migrations, tests, screenshot evidence, checkpoint hashes, and outstanding limitations will be recorded below.

## Implementation and validation results (2026-11-08)

### Taxonomy and classification behavior

- Added `data/models/classification_taxonomy_v1.json` (registry `newassetapp_structured_classification`, version `1.0.0`) and `app/core/classification_taxonomy.py` for typed validation and the shared filename serializer/parser.
- **Final naming rule:** every tagged category uses `main_tag[,main_tag2]-sub_tag[,sub_tag2]{sequence}.webp`; the hyphen is omitted when there are no subtags. Collision-safe numeric suffixes remain required. The retired sub-main concept is not emitted or stored as a separate classification: legacy Body Images sub-main values are normalized into ordinary subtags at the correction API boundary. Fullbody state remains a separate structured field and is serialized as a subtag.
- Historical filename parsing is explicitly metadata-only and cannot populate or confirm structured fields. Normal Processing stores human-selected values independently of professional confirmation; Professional Review output requires a confirmed, valid structured record.
- Legacy Fullbody CNN candidates are advisory only and require the exact legacy Asset CNN model ID and checkpoint digest. The two clothing/costume outputs suggest `clothed`; the nude output offers the ambiguous `topless`/`bottomless` choices. None is auto-confirmed. Location suggestions likewise require a verified target registry identity or exact legacy YOLO model/digest/class identity; canonical manual locations remain available.
- The legacy YOLO output remains identified as 32 classes. The separate 31-class future target registry is not represented as the legacy checkpoint output.

### Files changed

- `app/core/classification_taxonomy.py` (new)
- `app/core/database.py`
- `app/core/filename_grammar.py`
- `app/core/fullbody_classification.py`
- `app/core/output_exporter.py`
- `app/gui/correction_dialog.py`
- `app/gui/main_window.py`
- `data/models/classification_taxonomy_v1.json` (new)
- `data/models/body_images_composition_policy.json`
- `data/tags/tag_grammar.json`
- `tests/test_classification_taxonomy.py` (new)
- `tests/test_filename_grammar.py`
- `tests/test_phase9_crop_export.py`
- `reports/PHASE11_2_NEWASSETAPP_GUI_FINALIZATION.md`

### Database and launcher

- Schema v10 adds structured current-classification and append-only event tables and additive fields for Normal Processing choices/export manifests. It does not infer labels from prior filenames or predictions and does not remove legacy values.
- Before migration, a complete SQLite backup was saved to `reports/backups/phase11_2_pre_v10/newassetapp_pre_v10.sqlite3`. A v9-to-v10 trial copy passed at `reports/backups/phase11_2_pre_v10/newassetapp_v10_migration_trial.sqlite3`; the migration rollback test passed.
- Launched via `run_app.ps1` in the project Python 3.11.9 environment. Live database is now schema v10. Preserved counts: 139 source images, 1,124 YOLO detections, 351 CNN predictions, and 30 correction records. New structured tables contain zero rows because no historical rows were silently reclassified.

### Tests and GUI acceptance

- Passed: `& '.venv\Scripts\python.exe' -m unittest tests.test_classification_taxonomy tests.test_filename_grammar tests.test_phase9_crop_export -v` — 18 tests.
- Full regression command (rerun after the compatibility normalization patch): `& '.venv\Scripts\python.exe' -m unittest discover -s tests -v` — 96 tests ran; 11 failures and 16 errors remain. Most failures are older tests that still assume the retired sub-main filename grammar, or omit required explicit Normal Processing tags / a valid confirmed classification. This is not a passing regression suite; those cases must be reconciled and rerun before phase acceptance.
- The app window opened through the real launcher, but live screenshot capture timed out. No fresh screenshots were saved. Acceptance at 900×560, 1280×800, and 1920×1080 is therefore **incomplete**; visual clipping, image-preview dominance, and interaction were not accepted.
- Normal Processing and Professional Review were verified by focused code/tests, not fully accepted through live GUI interaction. Export/crop tests passed, including WebP output, source traceability, collision handling, background-removal fallback, and cancellation between completed items.

### Preservation and scope

- Verified current SHA-256 values against the recorded legacy identities: `models/yolo/best.pt` = `57449664aa24427c703770ae155a361da252f26be4840242aae95f3017df58ea`; `models/asset_classifier/asset_classifier.pth` = `eb1251dade9293098e327f3e708bf92f0c5fc09c272c6cddb0f4f04f210ae6d2`. Other checkpoint files were not edited; no pre-change hashes were captured for each copy, so byte-identity is only directly evidenced for these two.
- Girl Packer was not modified. No training, Studio workflow, dataset splitting, package building, or CVAT changes were started. No dependencies were installed or changed.

## Acceptance status

**PARTIAL — NOT ACCEPTED.** Structured taxonomy, universal serialization, additive migration, focused tests, and crop-export regression tests are in place. Phase 11.2 remains open until the legacy full-suite cases are reconciled, the full suite passes, and fresh live GUI screenshots/interactions pass at all three requested resolutions.
