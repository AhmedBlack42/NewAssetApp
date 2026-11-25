# Phase 11.3 Environment and Screenshot Capture Diagnostic

Date: 2026-11-08

## Findings

### Python and execution context

- The restricted Codex shell runs as `DESKTOP-D5MESC0\codexsandboxoffline`, with the `CodexSandboxUsers` group and a medium integrity label. It is a different Windows account/token from the installation path under `C:\Users\asker`.
- In that restricted shell, `Test-Path` on the configured Python 3.11 executable returned `Access denied`; consequently it could not run the app's `.venv` interpreter (exit code 103). This is evidence of a session access boundary, not evidence that Python 3.11 is absent or that the virtual environment is damaged.
- A reviewed, elevated PowerShell read-only check could read and execute `C:\Users\asker\AppData\Local\Programs\Python\Python311\python.exe` and `NewAssetApp\.venv\Scripts\python.exe`. Both reported Python 3.11.9. The venv configuration identifies that same base interpreter.
- The existing `run_app.ps1` explicitly invokes only `NewAssetApp\.venv\Scripts\python.exe`. It does not select Python 3.15 or the CVAT environment.
- Running the existing launcher in the approved elevated execution context printed Python 3.11.9 and `F:\My Tools\New folder\NewAssetApp\.venv\Scripts\python.exe`, then opened the real NewAssetApp window. The app showed Ready and 1,124 crop suggestions. The user also reports that this launcher works in their normal Windows PowerShell session; that normal-user run was not independently repeated here.
- The distinction is supported by the differing account identities and the successful elevated access. A direct ACL comparison between the user's profile ACL and the restricted token was not obtained, so this report does not claim that the underlying file ACL itself is misconfigured.

### Desktop screenshot capture

- The CUA window-capture operation timed out for three different real windows: File Explorer, Brave, and the running NewAssetApp. This indicates a capture-service/channel limitation broader than NewAssetApp. The tool returned accessibility state for NewAssetApp, including its controls and Ready status, so the app window was present and responsive at the UI Automation level.
- The cause inside the CUA capture service is not exposed by its error. The repeated cross-window timeout means it cannot be attributed specifically to app elevation, app responsiveness, or a NewAssetApp-only window-selection problem. All observed windows and the app ran in interactive Windows session 1; a definitive integrity-level comparison between the CUA capture process and app process was unavailable.
- A native Win32 `PrintWindow` alternative succeeded against the actual NewAssetApp top-level window. It saved `gui_screenshots/phase11_3/normal_processing_empty_printwindow.png` at 1376×788 (254,054 bytes). The image was reopened and visually inspected: it contains the complete, readable app window and is neither blank nor black.
- The inspected image exposes the baseline Phase 11.3 defect: the crop preview and classification controls overlap. This is real-app evidence, not a reconstructed mock.

### Shared-app state caution

- During later capture work, the app accessibility state reported two selected crop suggestions and the status `Saved normal crop category for 1 crop(s)`. A read-only database query found a recent `normal_crop_choices` entry (proposal 29, Clothing / heels, updated at 2026-11-08 20:24:36 UTC at query time). The app provided no prior-value history for that row.
- This change may have resulted from an earlier mis-targeted UI action during capture, or from concurrent user activity in the shared desktop. The cause and prior value cannot be established from available history. No direct database write or attempted restoration was made. Further GUI interaction was stopped to avoid changing shared state.

## Verification status

| Check | Result |
|---|---|
| Python 3.11 installation | Verified in the approved elevated context: 3.11.9 |
| NewAssetApp virtual environment | Verified in the approved elevated context: 3.11.9 |
| NewAssetApp launcher interpreter | Verified from launcher output: project `.venv` Python 3.11 |
| CVAT/Python 3.15 used by NewAssetApp | No; launcher source points only to project `.venv` |
| Normal-user launcher | User reports success; not independently rerun |
| CUA screenshots of application windows | Timed out for Explorer, Brave, and NewAssetApp |
| Native screenshot alternative | `PrintWindow` succeeded and image was reopened |
| Actual app GUI state | Launched; UI Automation responded; screenshot confirms layout overlap |

## Scope and next step

No Python installation, virtual environment, launcher, dependency, ACL, display setting, or security setting was changed. The diagnostic screenshot and this report were added as requested. Phase 11.3 layout inspection and repair can now continue using the approved NewAssetApp Python 3.11 environment and the working native capture method.
