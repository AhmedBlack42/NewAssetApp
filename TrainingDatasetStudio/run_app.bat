@echo off
setlocal
set "APP_DIR=%~dp0"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%run_app.ps1" %*
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
  echo TrainingDatasetStudio exited with an error. Exit code: %APP_EXIT%
  exit /b %APP_EXIT%
)
endlocal
exit /b 0
