# Phase 9 Test Results

## Full suite

Command:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result: **89 tests passed, 0 failures, 0 errors** in 20.249 seconds.

The run used NewAssetApp's isolated `.venv` under the approved elevated route. No dependencies were changed. The suite includes the Phase 8 workflow-independence tests and seven Phase 9 crop-export tests covering category routing/WebP/traceability/training isolation, alpha-cache behavior, background-removal failure fallback, collision safety, cancellation preservation, and disabled background-removal behavior.

## Other verification

- `pip check`: no broken requirements.
- Project runtime: Python 3.11.9 x64.
- Checkpoint SHA-256: matches the recorded value.
- BiRefNet: four actual transparent WebPs generated and visually reviewed via checkerboard composites; see performance and quality reports.
- Live GUI acceptance and end-to-end GUI crop export: **not run**, because the Windows screenshot capture failed twice. The test suite is not presented as a substitute for desktop acceptance.
