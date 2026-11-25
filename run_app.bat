@echo off
setlocal

set "APP_DIR=%~dp0"
set "PYTHON=%APP_DIR%.venv\Scripts\python.exe"
set "MAIN=%APP_DIR%main.py"
set "VIRTUAL_ENV=%APP_DIR%.venv"
set "PATH=%VIRTUAL_ENV%\Scripts;%PATH%"

if not exist "%APP_DIR%.venv\Scripts\python.exe" goto missing_venv
if not exist "%MAIN%" goto missing_main

pushd "%APP_DIR%"
if errorlevel 1 goto directory_failed
"%PYTHON%" --version
if errorlevel 1 goto startup_failed
"%PYTHON%" -c "import sys; print('NewAssetApp interpreter: ' + sys.executable)"
if errorlevel 1 goto startup_failed
"%PYTHON%" "%MAIN%" %*
set "APP_EXIT=%ERRORLEVEL%"
popd
if not "%APP_EXIT%"=="0" goto app_failed
endlocal
exit /b 0

:missing_venv
echo NewAssetApp's virtual environment is missing or incomplete.
echo Expected: "%APP_DIR%.venv\Scripts\python.exe"
echo Create or repair NewAssetApp's .venv and install its approved requirements before launching.
goto failed

:missing_main
echo NewAssetApp entry point is missing: "%MAIN%"
goto failed

:directory_failed
echo Could not set the working directory to NewAssetApp: "%APP_DIR%"
goto failed

:startup_failed
set "APP_EXIT=%ERRORLEVEL%"
popd
echo NewAssetApp could not start its dedicated Python interpreter. Exit code: %APP_EXIT%
goto failed

:app_failed
echo NewAssetApp exited with an error. Exit code: %APP_EXIT%
goto failed

:failed
echo.
pause
endlocal & exit /b 1
