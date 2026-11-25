# Phase 4 dataset preparation — superseded by Phase 4B

Phase 4B authorizes and records the training-data layout migration. Current inventory, backup, directory structure, and migration facts are in `PHASE4B_DATASET_REORGANIZATION.md`; eligibility and candidate counts are in `PHASE4B_TRAINING_READINESS.md`. Original data remains preserved and no training occurred.

<!-- Historical Phase 4 text retained below for audit context. -->

**Status:** Sample analysis and dataset generation are intentionally gated. The Phase 4A instruction requires review of unresolved taxonomy decisions before sample processing; no such decisions have been supplied yet.

## Inventory and work performed

The current `samples/` directory contains 66 `.jpg` files and one `.txt` file, based on filenames/extensions only. No image bytes were opened during this phase. Accordingly, this phase generated **zero** YOLO detections, **zero** candidate crops, **zero** image labels, **zero** human-confirmed examples, and **zero** trusted training examples. No inference or sample processing ran. The earlier `reports/sample_inventory.json` described a prior 44-image inventory and must not be treated as the current sample count.

| Task | Inference/crops this phase | Confirmed eligible examples | Review needed |
|---|---:|---:|---:|
| Clothing | 0 / 0 | 0 | All future samples |
| Portrait (`portrait`, `tportrait`) | 0 / 0 | 0 | All future samples |
| Body Images structured tags | 0 / 0 | 0 | All future samples |
| Fullbody state | 0 / 0 | 0 | All future samples |
| Canonical location | 0 / 0 | 0 | All future samples |

No class sufficiency or imbalance conclusion can be drawn from unprocessed samples. Readiness is **not ready for training** for every task. Existing human corrections, if present in the application database, are not included in these sample counts.

## Reproducible preparation contract

`data/datasets/phase4_dataset_manifest.schema.json` defines required manifest fields. `data/datasets/phase4_preparation_status.json` records the present gate, zero counts, seed 42, ratios 80/10/10, and source-hash grouping. `tools/validate_phase4_dataset.py` validates future manifests for source leakage and trusted-label status. Output belongs below `data/datasets/phase4/`; source images are referenced by hash and not duplicated as originals. Crops, once approved, should carry source/detection IDs, original box, corrected box when present, crop parameters/hash, candidate and human decisions separately, model version, and dataset split.

The existing exporter already consumes reviewed correction records and uses source SHA-256 split assignments. Current exports use timestamped output directories; the Phase 4 packaging flow should preserve its audit history and not treat AI-only predictions as confirmed.
