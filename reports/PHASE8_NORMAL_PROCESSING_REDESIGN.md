# Phase 8 — Normal Processing Redesign

The normal gallery now displays model crop suggestions independently of professional review. It provides category filtering, checked multi-selection, select-all-visible, a large selected-crop preview, previous/next navigation, category assignment, Body Images crop-type selection, and WebP export routing to `fullbody/`, `body_images/`, or `clothing/`.

The export plan uses existing crop rules in `app/core/crop_rules.py`, preserves source images, creates collision-safe names, verifies the source hash before writing, and records normal export history separately. It does not create final assets or training data. Clothing preserves the selected box aspect ratio; Fullbody trims transparent bounds and enforces the documented minimum height; Body Images uses the existing guide-derived aspect and minimum-size rules. It does not stretch crops to arbitrary ratios.

Opaque Fullbody crops use the bundled BiRefNet general model during export. A local CPU smoke run produced a transparent mask in 121.48 seconds for a 775×1334 crop at 1024×1024 model input, on an 8-core system with four threads. This shows the segmentation path can execute, not that its masks are accurate for all images. The confirmation warns that processing many Fullbody crops may take a while. No dependency was installed.

The current UI screenshot predates the latest preview-message and confirmation-text edits, and should be refreshed when the GUI runtime is usable. The live desktop interaction exercised a normal category choice, but no export was performed. Current database counts show 0 normal exports.
