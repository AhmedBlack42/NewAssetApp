# Model copy and integration report

## Copy and integrity

The YOLO, Asset CNN, matching class map, BiRefNet general/portrait code/config/weights, and Real-ESRGAN x2plus checkpoint were **copied** into `NewAssetApp/models/`; the Girl Packer originals were not moved or edited. All 14 copied files were SHA-256 compared source-to-destination and matched exactly, totaling 1,904,383,778 bytes. The full paths, sizes, and hashes are in `MODEL_COPY_HASH_VERIFICATION.json`; every model/code file hash is now recorded in `models/model_manifest.json`.

The first verification exposed a malformed 61-character Asset CNN hash in the prior manifest. The source and destination matched at the same valid 64-character SHA-256; that exact digest corrected the manifest. The all-model manifest check subsequently passed.

## Loading and bounded inference evidence

The copied YOLO and CNN checkpoints loaded from NewAssetApp paths using the verified Python 3.11.9 environment. YOLO's names/order matched all 32 registered classes; the Asset CNN strict state dict and 26-label map loaded; 300 individual supported detection crops were classified from 44 images. There were 367 YOLO detections total, 0 decode/crop/inference errors, and all 44 sample hashes were unchanged. Crop dimensions, boxes, confidence, CNN result, and class counts are recorded per observation in `MODEL_AND_SAMPLE_SMOKE_RESULTS.json`.

BiRefNet general and portrait both strictly loaded from their copied local files and returned 64x96 BGRA output on an in-memory synthetic fixture. The portrait fixture produced a fully transparent alpha mask; this is loader/shape evidence only and shows that the synthetic pattern is unsuitable for a quality claim. Real-ESRGAN loaded its checkpoint strictly and returned a 128x192 2x result from an in-memory 64x96 fixture. No sample file was processed by BiRefNet or Real-ESRGAN.

## Intended role and limits

- **YOLO:** scan source images, retain all raw boxes/class IDs/confidences, and use only the proposed reviewed class routes.
- **Asset CNN:** classify each supported YOLO crop, preserving its raw prediction and confidence. The mapped category is a review candidate; low/uncertain outcomes go to `others`.
- **BiRefNet:** invoke only after a human has accepted an asset that needs transparency; select general/portrait by the asset workflow. Preserve source bytes and the detection crop.
- **Real-ESRGAN:** optional, conservative derivative for a user-selected asset; preserve aspect ratio and source.
- **Photoshoots:** no model route. Assignments and group membership are human-only.

The sample run is a controlled compatibility/routing audit, not full production processing. It did not accept proposals, export final assets, or score prediction accuracy. No labeled ground truth is available. The main NewAssetApp scan worker is still a source indexer; end-user proposal execution/production processing remains gated until the tag review and YOLO policy are approved. The measured model path proves copied checkpoint load/inference compatibility; it does not certify image quality or human acceptance.
