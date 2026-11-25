# TrainingDatasetStudio

TrainingDatasetStudio is implemented as a separate PySide6 application with an
independent Python environment and SQLite store:

- GUI entry point: `main.py`
- Launcher: `run_app.ps1`
- Config and store: `studio/config.py`, `studio/store.py`
- Import: `studio/importer.py`
- Dataset builder/export: `studio/datasets.py`
- Validation and Colab packages: `studio/datasets.py`
- Model-artifact and CPU training workflows: `studio/training.py`,
  `studio/train_entry.py`, `studio/shared_train.py`

Launch from this directory:

```powershell
.\run_app.ps1
```

The Studio database is `data/studio.sqlite3`. It is independent from NewAssetApp's
database. Shared-training resume is explicitly not implemented; new confirmed
runs must be started from a package and finalized dataset version. Production
activation is not performed by Studio.

NewAssetApp publishes immutable source bundles under the project-root
`training_source/bundles/` directory. New bundles use `contracts/newassetapp_import_v4.schema.json`; earlier v2/v3
bundles remain backward-compatible as supported by the importer. Studio must not
scan `output/` or the legacy `train_data/` directory as a substitute for reviewed
training records. Imported decisions belong to Studio and are not written back
into NewAssetApp.

For YOLO, `registries/yolo_detector_v1.json` is the only active Studio class
registry. Imports with a different class-ID/name mapping are quarantined, and
dataset finalization and training authorization independently recheck that
registry. Historical annotations remain available for review but cannot become
current training targets unless corrected to an approved class.

The latest bounded lifecycle verification and its remaining readiness blockers
are recorded in `../reports/TRAINING_DATA_LIFECYCLE_CONTINUATION.md`.
