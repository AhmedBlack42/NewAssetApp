# Phase 6 Normal Batch Processing

## Status

**Partially complete.** Image scanning and analysis already operate over folders, report progress, and retain per-image errors. The Normal Processing tab now filters reviewed outputs by Fullbody, Body Images, and Clothing; users can select multiple crops and export them in one operation. Individual crop failures do not stop other selected exports.

The tab currently shows only reviewed/confirmed output records. Preparing a first-time crop (selecting its region, category, and tags) still uses Professional Review, so ordinary users do not yet have a complete independent preparation workflow. Normal batch processing does not add records to training datasets.

## Reliability

- Existing source images are read-only; export writes derivatives.
- The normal export worker reports item progress and a success/failure/skip summary.
- Scanning, analysis, dataset export, and crop export are guarded against concurrent background operations.
- Re-running analysis uses the existing indexed/new-or-changed source logic.

## Manual acceptance

Scan and analyze a folder containing valid, duplicate, unchanged, and unreadable images. Confirm per-image errors do not prevent the rest of the batch from completing. Select a subset of reviewed crops and verify that only the selected items export. Confirm an export failure does not stop later items and that a second export does not overwrite the first.
