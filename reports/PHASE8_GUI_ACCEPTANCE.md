# Phase 8 — GUI Acceptance

## Result: PARTIAL — not accepted

| Area | Result | Evidence / limitation |
|---|---|---|
| Normal suggestions independent of professional review | Partial | Live app showed 1,124 suggestions; one category choice was saved. |
| Selection, filtering, preview | Partial | Implemented and present in offscreen renders; no reliable full mouse/keyboard session. |
| Normal WebP export and routing | Not tested live | No export was run; current database has 0 normal exports. |
| Fullbody background removal | Smoke-tested only | Local BiRefNet CPU smoke generated transparency in 121.48 seconds for one crop; not a CVAT or full-app export request. |
| Professional review without normal export | Partial | Independent source/proposal code path and UI render; real edit/confirm acceptance incomplete. |
| Box editing and synchronization | Not accepted | Desktop control was unreliable; operations need manual interactive verification. |
| Normal-size visual layout | Partial | Offscreen 1360×768 screenshots inspected. |
| Smaller-window layout | Failed visual check | 900×560 screenshot shows clipped labels and truncated controls. |
| Live inference | Not tested | No real live inference request was made during this run. |

Do not treat these results as full GUI acceptance. Repeat interaction testing after repairing the Python environment and refining the narrow-window layout.
