# Phase 8 — Professional Review Redesign

The professional workspace has a source library, compact proposal gallery, large image preview, selectable detection list, editable box interactions, classification/tag controls, and an expandable technical-details panel. Box labels are hidden by default; the preview supports toggling them and attempts non-overlapping placement. The source image and original detections remain separate from review edits.

The normal-size offscreen render allocates most of the window to the preview. The 900×560 render is not acceptable: navigation and gallery labels are clipped, review controls truncate, and the image view is vertically constrained. Responsive behavior needs another pass and visual revalidation.

The current live interaction was partial. App launch and screen discovery were observed, but desktop input and screenshot capture calls were unreliable. Box move/resize/draw/delete, classification confirmation, and real interactive synchronization have not been fully accepted in this run.
