# Phase 7 CVAT Setup — Current Status

## Status: registration succeeded; live inference awaits a suitably small task

### Agent runtime

Python 3.11.9 x64 is restored at `C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe`. The existing `cvat_agent\.venv` was reused without rebuilding or installing packages. Its Python, pip (24.0), and CVAT CLI (2.82.0) launchers work. `pip check` reports no broken requirements. Imports verified: CVAT SDK 2.82.0, CVAT CLI 2.82.0, Ultralytics 8.3.204, PyTorch 2.0.1+cpu, torchvision 0.15.2+cpu, Pillow 11.3.0, NumPy 1.26.4, OpenCV 4.10.0.84. CUDA is unavailable; CPU is appropriate.

A local function-level smoke test loaded the unmodified checkpoint, exposed all 32 labels, and returned 6 predictions on one sample at CPU/image size 640. Checkpoint SHA-256 is unchanged: `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA`.

### CVAT authentication and registration

The authorized token file was read directly; its value was not displayed, logged, passed in process arguments, or saved. It was kept only in the PowerShell process environment for authenticated requests and removed from completed request processes. CVAT accepted the PAT: `GET /api/tasks?page_size=1` returned HTTP 200 when no explicit `Accept` header was set. A diagnostic with `Accept: application/json` returned 406; the successful response content type was `application/vnd.cvat+json`. `GET /api/auth/access_tokens/self` reported `read_only=false`.

The authenticated account is `ahmed220`. CVAT server, CLI, and SDK versions are all 2.82.0. Project `Yolo_v2` (ID 462846) is accessible with 31 labels. Full live label IDs/names and the unapplied proposal are in `PHASE7_CVAT_LABEL_MAPPING.md`.

The complete personal function listing was paged to completion: one page, zero functions total, no duplicate name. Registration then succeeded using the existing checkpoint, CPU, and image size 640. CVAT returned and verified:

- Function ID: **5250**
- Name: `NewAssetApp YOLO detector`
- Provider: `native`
- Kind: `detector`

No weights, class names/IDs, project labels, or label mappings were changed.

### Agent status and live inference boundary

The agent was started with function ID 5250, CPU, and image size 640. Its log reported that it started, began watching the function queue, and connected to the queue event stream. It remains running in the launching PowerShell session for the live test.

The target project has only one task (`31 class annotate`, task 2748095), with 683 frames and one job (4709070, frames 0–682). No inference request was sent because that would process the full 683-frame job, outside the requested small-test scope. The desktop-control attempt also failed (`FrameArrived timed out`, then `user input was detected in this window`). Thus live CVAT predictions and prediction editability have not yet been tested.

## Next step

Provide a small task ID in project 462846 (ideally one to a few frames), or authorize creation of a separate one-frame test task from a project image. Then request one inference and manually verify that the returned prediction can be edited. No mappings are to be applied until separately authorized. Keep the current agent window open while testing; stop it with Ctrl+C when finished.
