# Phase 6 Crop Export Workflow

## Status

**Partially complete; export logic has unit coverage.** Normal export remains distinct from training dataset export. It plans only confirmed, tagged proposals, writes collision-safe WebP derivatives in `fullbody/`, `body_images/`, and `clothing/`, records the source path/hash and crop policy, and preserves the source. Missing output directories are created as needed. Failed items are reported without cancelling other items.

## Guide-derived fitting rules

The requested Girl Packer guide was read as the output specification. Body Images ratios use the guide's documented target dimensions: Portrait and tportrait 350×350; Face 500×500; Boobs and Ass 495×240; Pussy and Legs 245×235. The crop is expanded around the reviewed box to include it at the required ratio; the image is uniformly upscaled only when needed to reach minimum dimensions. It is never stretched to force a ratio. Portrait/tportrait require existing alpha transparency. Face allows either.

The guide requires Fullbody output to retain transparency, be trimmed to visible subject bounds, preserve aspect ratio, and reach at least 1500 px in height. Export skips an opaque Fullbody crop with a clear error; no background-removal implementation is configured in NewAssetApp.

The guide gives no fixed Clothing ratio or dimensions. Clothing therefore preserves the reviewed crop box's original proportions and dimensions. This is a documented preservation rule, not an invented ratio.

## Validation limits

Unit tests cover Body Images ratio expansion, transparency checks, and Clothing box preservation. Existing exporter tests cover collision-safe names and source preservation. End-to-end WebP output routing and GUI review remain manual acceptance items; see `PHASE6_TEST_RESULTS.md`.
