# Phase 8 — Workflow Independence

## Implemented architecture

Normal Processing reads current model crop suggestions directly, without requiring professional confirmation. Its category decisions are saved in `normal_crop_choices`; ordinary WebP exports are recorded in `normal_crop_exports`. Neither operation writes professional confirmation, `final_assets`, training records, or split assignments.

Professional Review continues to read scanned sources and proposal/detection records directly. It does not depend on normal export history. Confirmation and training preparation remain separate operations.

The database migration is schema version 9. The app database currently reports 2 normal crop choices, 0 normal crop exports, 0 training records, 0 dataset split assignments, and 0 final assets. These are current counts, not proof of all workflows.

## Regression coverage

`tests/test_phase8_workflow_independence.py` contains five focused cases for unconfirmed normal export, independent category choice, transparent Fullbody export, opaque Fullbody export through an injected segmenter, and Body Images rule validation. Test execution is currently blocked because the project `.venv` points to a missing Python 3.11 base interpreter and the available Python 3.12 runtime lacks PySide6. These tests are present but are not reported as passing in this run.

## Acceptance

Architecture and database separation are implemented. Current end-to-end acceptance remains partial until the Python environment is restored and regression tests and live interactions can be rerun.
