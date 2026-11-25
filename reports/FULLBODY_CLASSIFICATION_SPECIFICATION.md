# Fullbody classification proposal

**Status:** Proposed for review. No model classes are frozen and no model has been trained.

## Separate fields

Store four distinct values: the source-defined Fullbody main tag, the reviewed state (`normal`, `topless`, or `bottomless`), the output category (`fullbody`, `fullbody_topless`, or `fullbody_bottomless`), and the complete serialized tag/composition when one is valid. The output category follows the explicit state mapping in `data/models/fullbody_classification_policy.json`; it is not a YOLO label.

The current verified main-tag tokens from `data/tags/fullbody_tags.json` are:

- Clothed state context: `clothed`, `underwear`, `bikini`, `atheletic`, `lingerie`.
- Nude state context: `topless`, `bare`, `bottomless`, `shower`.
- Costume state context: `maid`, `swimsuit`, `bikini`, `nurse`, `uniform`, `work`, `cosplay`.

The two contextual `bikini` entries remain separate in the taxonomy. The misspelling `atheletic` remains review-flagged. The existing `topless` and `bottomless` source entries also overlap with the requested state vocabulary; do not assign them to a main-type head until that distinction is resolved. The currently supported compound allowlist is limited to `clothed_topless`, `clothed_bottomless`, and `bikini_bottomless`; the historical hyphen spelling is a read alias only. Do not generate arbitrary main-tag/state combinations.

## Proposed classifier

Use a hierarchical multi-head image classifier only after users confirm the class definitions and enough human-confirmed data exists:

1. A main-tag head predicts a source token and retains its source context.
2. A state head predicts normal, topless, or bottomless.
3. A constrained composition layer permits only user-approved combinations and derives the separate output category.
4. A review/abstain outcome handles low confidence, unsupported combinations, and ambiguous images.

The legacy Asset CNN labels `fullbody_clothed_states`, `fullbody_costume_states`, and `fullbody_nude_states` are broad classes. They do not identify the source main tag and cannot distinguish topless from bottomless. They may be stored as raw review evidence only; they must not fill any final Fullbody field automatically.

## Training classes and records

Candidate main labels come from the guide's type list and verified Fullbody taxonomy, preserving exact serialized tokens and context. Candidate state labels are the three explicit state values. Keep overlapping `topless`/`bottomless` source entries visible but out of the main-type class list pending review. Do not train a Cartesian product of every main type and state. Any combination outside the current allowlist requires an explicit source rule or user approval.

Training examples require a human-confirmed final main tag, state, output category, and serialized tag. Preserve the original model proposal, corrected/confirmed label, source image ID/hash, crop or whole-image relationship, model and taxonomy versions, annotator decision, and split. All records from one source image remain in one split. The current export package can represent this provenance; no dataset was exported in this phase.
