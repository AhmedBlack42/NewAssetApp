# Phase 8 — GUI Screenshot Audit

Screenshots are stored under `gui_screenshots/phase8/`. The 15 captures cover Normal Processing initial/selected/filter states, folder selection, export confirmation, Professional Review initial/selected/detection/overlap/details/tag-editor states, and a 900×560 window.

They were rendered from the real Qt widgets offscreen with the current database and representative source images. They are not desktop captures and do not demonstrate real mouse/keyboard acceptance. The captures were visually inspected. Normal Processing gives the preview more room and makes crop selection visible. The Professional Review normal-size capture gives the image panel most of the width; the smaller-window capture has clipped navigation text and truncated action controls. The initial selected Fullbody capture shows the former “no background-removal step” preview message because it predates the final wording edit. The screenshot set needs regeneration after the current UI edits.

The CUA desktop session exposed the app and showed 1,124 model crop suggestions. User input and screenshot calls failed intermittently; one normal category choice was saved. No normal export, bulk annotation, or training operation was performed. The screenshot dimensions are 1360×768 and 900×560 renders; actual desktop resolution was not verified.
