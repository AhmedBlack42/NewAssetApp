# Phase 6 Professional Review Workflow

## Status

**Partially complete; GUI interaction is untested.** The professional tab retains the existing model proposal, detection, category, tag, annotation, and dataset-preparation tools. Detection rows are selectable and linked to the image preview. Original model detection data remains separate from corrected geometry.

Schema migration 8 adds classification events per detection and task (`fullbody_state`, `body_images`, `clothing_family`). Edits append an unconfirmed event; confirmation appends a distinct event. Editing a box invalidates the latest confirmed classification for that detection. Classification confirmation does not export crops. Annotation confirmation and classification confirmation have separate buttons and records.

## Important limitation

Training dataset preparation/export remains an explicit user action and is separate from crop export. This phase did not train models, split new datasets, change model checkpoints, change taxonomy, or configure CVAT. Validate the new UI state transitions interactively before relying on them for annotation work.
