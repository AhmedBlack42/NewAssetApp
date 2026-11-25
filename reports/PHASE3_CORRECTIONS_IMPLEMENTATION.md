# Phase 3 corrections: implementation report

**Status:** Implemented and unit-tested, with the Fullbody state model itself remaining a future model deliverable. No models were trained, the sample folders were not processed, and Girl Packer was not modified.

## Category failure and resolution

Reproduced with the project interpreter by calling `fullbody_classification("bare", "normal")`. The operation failed in `app/core/fullbody_classification.py::fullbody_classification` with:

```text
ValueError: Fullbody main tag is not an approved selectable tag: 'bare'
```

The function filtered `bare` out of `verified_main_tag_values()` even though the guide lists `bare` as a Fullbody type and `data/tags/fullbody_tags.json` marks it selectable. The filter now reserves only `topless` and `bottomless` as state words. A regression test confirms `bare` serializes as the valid main tag `bare`.

A second category boundary mismatch rejected the guide’s `conservative` Fullbody filename subtag: that selectable value is registered in the Body Images source taxonomy, while the Fullbody validator only looked in the Fullbody group. The policy now includes a narrow crosswalk for the guide’s exact `clothed-bottomless,conservative.webp` example. Other unverified tags remain rejected. `bikini` + `topless` also remains rejected because it is absent from the verified Fullbody composition allowlist.

Clothing CNN outputs retain their raw prediction labels. The Phase 4A crosswalk maps source-defined broad-category candidates such as `footwear`→`shoes`, `outerwear`→`outer`, and `panty`→`panties` into pending review; no candidate confirms an individual garment. The legacy Asset CNN Fullbody group outputs are retained as raw evidence and do not determine the Fullbody main type or state.

## YOLO classes and review roles

The source checkpoint registry and policy retain all original IDs 0–31 and the exact names in `models/model_manifest.json`. Inference requests all 32 IDs. Every detection now creates a pending review record, including classes previously excluded by the active-class filter. An inference policy version change causes previously analyzed sources to be queued for analysis the next time the user invokes **Analyze new / changed**; no image analysis was run during this work.

| IDs | Original classes | Review role |
|---|---|---|
| 0 | `person` | Unclassified Fullbody fallback; never auto-confirms a type or state. |
| 1–6 | `face`, `portrait_frame`, `boobs`, `ass`, `pussy`, `legs` | Image-region proposals. Asset CNN output remains a review suggestion. |
| 7 | `action_event` | Retained event evidence in `Others`; not passed to the Asset CNN. |
| 8–11 | `pussy_cover_item`, `ass_cover_item`, `boobs_cover_item`, `leg_cover_item` | Coverage-region proposals; raw class and box retained for review. |
| 12–18 | `location_home`, `location_class`, `location_office`, `location_bathroom`, `location_bar`, `location_outdoor`, `location_bed` | Context detections in `Others`; not treated as asset tags or photoshoot assignments, and not passed to the Asset CNN. |
| 19–27 | `fullbody_shower`, `fullbody_maid`, `fullbody_nurse`, `fullbody_uniform`, `fullbody_athletic`, `fullbody_swim`, `fullbody_lingerie`, `fullbody_work`, `fullbody_casual` | Fullbody type candidates requiring human review. Exact selectable candidates include shower, maid, nurse, uniform, swimsuit, lingerie, and work. `athletic` remains unresolved because the source uses review-flagged `atheletic`; `casual` has no verified selectable token. Both raw detections remain visible for correction. |
| 28 | `accessory_footwear` | Review-only detection. The Asset CNN's broad `footwear` family candidate is crosswalked separately to source category `shoes`; neither prediction confirms a final garment. |
| 29–30 | `fullbody_topless`, `fullbody_bottomless` | Fullbody review detections; they do not auto-set the main type or the reviewed state. |
| 31 | `fullbody_bare` | Fullbody main-type candidate `bare`; state is still a separate human decision. |

Location and event classes are YOLO object-detection outputs with original box evidence. The app presents those detector regions as contextual evidence with their source class label; it does not turn them into an image-wide location assertion or an application tag automatically.

## Preview and review editing

`BoundingBoxPreview` paints the source image and all persisted detections in one aspect-ratio-preserving preview. Boxes carry the class, application category, and confidence label. The legend identifies original AI boxes (blue), edited boxes (green), manual boxes (yellow), and rejected boxes (red).

Users can select boxes, drag to move them, drag the lower-right handle to resize, draw a manual box, change category/class in the review dialog, and reject a selected detection. Pointer positions are converted through the displayed image rectangle into source-image pixels. Geometry changes append a correction record and update the proposal’s corrected box while retaining the original `yolo_detections` row and snapshot. Manual detections are marked `user_manual`; rejected detections remain visible with their original coordinates.

## Fullbody main type, state, and filenames

YOLO Fullbody detections propose the main type; the reviewer verifies or corrects it. The state vocabulary in the UI and policy is exactly `clothed`, `topless`, and `bottomless`. The existing 26-class `asset_classifier` has broad `fullbody_clothed_states`, `fullbody_costume_states`, and `fullbody_nude_states`; its checkpoint and class IDs cannot implement those three states. It is preserved unchanged and is not reinterpreted as the state model.

No Fullbody State CNN checkpoint exists in NewAssetApp. The policy records the future crop-classifier labels and a separate three-output head. Until that model is trained in a later phase, state is entered and confirmed by the reviewer. No training occurred here.

Composition is constrained by the current verified allowlist:

| Confirmed main type | State | Serialized tag |
|---|---|---|
| `bikini` | `clothed` | `bikini` |
| `clothed` | `topless` | `clothed_topless` |
| `clothed` | `bottomless` | `clothed_bottomless` |
| `bikini` | `bottomless` | `bikini_bottomless` |

The guide’s `clothed-bottomless` spelling is read as a legacy alias; the current writer emits the canonical underscore composition. No other combinations are generated.

## Numbering and output layout

The guide says Body Images numbers matter because the game uses them to pair related assets (`ass1`, `boobs1`, `pussy1`, `face1`). The number is filename metadata for an image set, not part of the semantic tag. For reviewed multi-main output the writer repeats one common sequence across the main-tag set and allocates against the complete selected main/subtag composition.

The guide’s Fullbody examples are unnumbered. NewAssetApp appends a direct positive sequence such as `shower1.webp` and reads legacy underscore-numbered names. The latest approved grammar places Fullbody subtags after a hyphen and before that sequence, while preserving underscores inside the main/state composition.

Output files are organized under the selected output directory in `fullbody/`, `body_images/`, `clothing/`, or `others/`. Fullbody, Body Images, and Clothing filenames are composed from separately reviewed hierarchy fields; Others still requires a reviewer-supplied `.webp` filename. Body Images supports ordered main-tag groups while retaining paired image-set numbering.

## Separate output export

The GUI now offers **Export Output** and **Export Training Data** as separate actions. Export Output first shows a preview of eligible confirmed records, filenames, skipped records, and destination; it writes only after the user confirms. It reads only the latest human-confirmed review payload, checks the indexed source SHA-256, applies the corrected box crop if present, writes a WebP file, and stores export provenance in the existing `final_assets` table. It never moves or overwrites source files. A collision discovered after preview aborts safely.

Training-data export remains on its existing worker and formats, uses explicit human eligibility, and retains provenance and persistent source-hash splits. Normal output does not create dataset packages. Photoshoot membership stays manual.

## Database and migration safety

No schema migration was needed. Schema version remains 5. The implementation uses the existing append-only `correction_records`, `user_decisions`, `asset_proposals.corrected_bbox_json`, and `final_assets` structures to preserve original AI records, corrected geometry/category, decisions, source hashes, model digests, taxonomy version, serialized filename, and export history. Human edits do not update original YOLO coordinates or CNN predictions.

## Verification and remaining limits

- The required interpreter ran `python -m unittest discover -v`: **46 tests passed**.
- `python -m compileall -q app tests` passed; importing `MainWindow` and the output exporter passed.
- Tests cover class registry preservation, all-class proposal creation, GUI box display/selection/move/resize/manual creation, corrected source-pixel persistence, manual/rejected provenance, Fullbody composition/parsing and numbering, separate output export, collision safety, original source hash preservation, and existing training eligibility/split behavior.
- The Fullbody State CNN is specified but unavailable; state confirmation remains manual.
- No live GUI session, checkpoint accuracy evaluation, model training, or sample-folder processing was performed.
- Clothing and Others output filenames are deliberately user-entered; the report does not claim an unverified automatic filename rule for those categories.

## Phase 3 follow-up: filename sequencing and shared corruption subtags

Updated the writer and reviewer after the follow-up requirements. Shared corruption tokens are now declared once in `data/tags/shared_corruption_tags.json` and exposed as manually selectable subtags for Clothing, Fullbody, and Body Images. The `corruption_subtag` correction field is stored separately from the main tag, optional Body Images sub-main tag, and ordinary subtags. `u_whore` is preserved exactly. Validation does not depend on training data or a corruption classifier.

This first follow-up grammar was superseded by the later critical grammar correction below; current serialization follows that definitive category-specific grammar.

The initial follow-up's Body Images and Clothing separator descriptions were superseded by the later critical grammar correction below. The current grammar and implementation are documented there. Existing no-overwrite checks remain in force. Fullbody composition allowlist and the three state values are unchanged.

Follow-up tests were extended for the critical grammar correction. The full suite ran in NewAssetApp's existing `.venv`: **55 tests passed**. A normal sandbox invocation initially reported the `.venv` base interpreter missing; running in the approved execution context resolved that access issue. No dependency installation was performed.

## Critical filename grammar correction

The subsequent confirmed grammar is implemented in `app/core/fullbody_classification.py` and the new `app/core/filename_grammar.py`. Fullbody stores `main_tag`, `sub_main_tag` (the separately reviewed state), and ordered `subtags` independently. Its serializer emits `<main>_<sub-main>-<subtag1>,<subtag2>N.webp`, with the `-subtags` segment omitted when empty; e.g. `clothed_topless-slut1.webp`, `clothed_topless-slut,park1.webp`, and `bikini-slut1.webp`. The Fullbody allowlist remains enforced.

Clothing serialization emits `<main>_<subtag1>,<subtag2>N.webp`, for example `mini_skirt_slut1.webp` and `mini_skirt_slut,conservative1.webp`. It does not use the reviewer-entered filename as taxonomy; the clothing selection is the main tag and the output planner builds the filename. Body Images single-main output emits `boobs-cum1.webp` and `boobs-cum,whore1.webp`; grouped main tags retain the guide/naming-helper convention of repeating the same image-set sequence on each main (`ass3,boobs3-cum.webp`). Output preview lists actual planned filenames and collision-advanced sequence values before export.

Parsers round-trip the approved forms. Fullbody parsing additionally reads unnumbered guide names, direct suffixes, legacy `_N` names, guide comma subtags, and unambiguous prior-app underscore/sequence-before-subtag names. Clothing reads the prior hyphen spelling as legacy. Body Images reads both the canonical single-main complete-tag sequence and guide paired-main sequence form. The guide itself documents Body Images comma-separated mains followed by hyphen-separated subtags and paired numbered examples; it does not define the new Fullbody underscore-plus-hyphen extension or Clothing underscore-subtag grammar. These follow the user's definitive app rules, leaving a documented difference from the original guide. The grammar audit below corrects the earlier `bobbs` example to canonical `boobs`; the serializer and parser now reject `bobbs` as a new Body Images main tag.

Changed files for this grammar correction: `app/core/fullbody_classification.py`, new `app/core/filename_grammar.py`, `app/core/output_exporter.py`, `app/core/database.py`, `app/gui/correction_dialog.py`, `data/models/fullbody_classification_policy.json`, `data/tags/shared_corruption_tags.json`, `app/core/tag_library.py`, `tests/test_filename_grammar.py`, `tests/test_phase2_architecture.py`, and this report.
