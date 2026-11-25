# Phase 7 CVAT Live Test — Current Status

## Status: registration and agent connection verified; prediction test pending

- The existing `cvat_agent\.venv` now starts under restored Python 3.11.9 x64. `pip check` passed, package imports passed, and local inference through `cvat_agent/func.py` returned predictions on a single local sample using CPU and image size 640.
- Read-only authenticated CVAT API request returned HTTP 200. PAT metadata reports `read_only=false`; token contents were not displayed or logged.
- Native detector registered and verified as `NewAssetApp YOLO detector`, function ID **5250**, CPU and image size 640. Its complete pre-registration duplicate check found zero functions in one page.
- Agent ID 5250 was started. The CLI log confirms it began watching interactive and batch queues and connected to the queue event stream. It remains running in the launching PowerShell session.
- Live CVAT inference was **not** triggered. The target project contains only task 2748095 (`31 class annotate`), with 683 frames, and one job (4709070) spanning frames 0–682. Running that job would exceed the requested small-test scope. No predictions were produced or added to the task, and prediction editability has not been verified.
- Computer-use capture/control failed with `FrameArrived timed out` and then `user input was detected in this window`; no UI action was completed.
- Project labels remain unchanged. The 32-class model taxonomy is preserved. Proposed mappings, including previously selected broader targets for a small test, remain unapplied.

To complete this test, provide a small task ID in project 462846 or authorize creation of a separate one-frame test task from a project image. Then trigger one inference and verify that its draft prediction can be edited. Do not run inference across task 2748095's full 683-frame job or bulk annotate.
