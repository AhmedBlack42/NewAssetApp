# Phase 8 — Test Results

## Source validation

- Python 3.12.14 `compileall` completed for `app`, `tests`, and `tools`, writing bytecode to a temporary cache directory.
- Full unittest discovery could not start: the available Python 3.12 runtime does not have PySide6 (`ModuleNotFoundError`).
- The project `.venv\Scripts\python.exe` also cannot start: its `pyvenv.cfg` points to `C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe`, which is missing. The configured venv base records Python 3.11.9.
- Installed Python executables observed: Python 3.15.0 at `C:\Users\asker\AppData\Local\Python\pythoncore-3.15-64\python.exe`, Python 3.14.6 at `...\pythoncore-3.14-64\python.exe`, and the Codex bundled Python 3.12.14. The Python launcher reports no registered installations.
- No environment repair, package installation, upgrade, or removal was performed.

## Tests authored, not executed in this run

`tests/test_phase8_workflow_independence.py` includes five regression tests. Because the isolated app environment is broken and the available runtime lacks PySide6, no current full-suite or Phase 8 unittest pass is claimed. The earlier 81-test result predates the latest code edits and does not validate this exact state.

## Integrity and database snapshot

The YOLO checkpoint SHA-256 is `57449664AA24427C703770AE155A361DA252F26BE4840242AAE95F3017DF58EA`, matching the supplied recorded digest. The checkpoint was not modified. Read-only database inspection reports schema 9, 2 normal crop choices, 0 normal crop exports, 0 training records, 0 dataset split assignments, and 0 final assets.
